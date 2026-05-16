"""Feature engineering for the demand forecasting model.

Inputs the canonical DataFrame produced by ``data_loader`` and emits a
LightGBM-ready feature matrix plus the target series. Splits the
responsibility into three layers:

1. **Calendar + holiday features** — purely date-derived, no per-(store,
   product) state. Computed once over the whole frame.
2. **Lag + rolling features** — require per-(store, product, date) state.
   Computed via groupby-shift / rolling so they're consistent at training
   time and at inference time.
3. **Categorical encoding** — store_ref and product_ref are label-encoded.
   We persist the encoding dictionaries with the model so future inferences
   produce the same integer codes.

The single public entry point is :func:`build_feature_matrix`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import holidays as _holidays_pkg
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TARGET_COLUMN = "quantity_sold"

LAG_DAYS: tuple[int, ...] = (1, 7, 14, 28)
ROLLING_WINDOWS: tuple[int, ...] = (7, 28)


CALENDAR_FEATURES = [
    "year",
    "month",
    "day",
    "day_of_week",
    "day_of_year",
    "week_of_year",
    "is_weekend",
    "is_month_start",
    "is_month_end",
]

HOLIDAY_FEATURES = ["is_holiday_et", "is_holiday_us"]

CATEGORICAL_FEATURES = ["store_code", "product_code"]


# ---------------------------------------------------------------------------
# Encoding dictionaries — serialised with the model so predictions reuse them
# ---------------------------------------------------------------------------


@dataclass
class CategoryEncoder:
    """Tiny dict-based label encoder. Unseen categories at predict time map to
    a sentinel ``-1`` so the model degrades gracefully instead of crashing."""

    name_to_code: dict[str, int] = field(default_factory=dict)

    def fit(self, values: pd.Series) -> "CategoryEncoder":
        uniques = sorted(values.dropna().unique())
        self.name_to_code = {v: i for i, v in enumerate(uniques)}
        return self

    def transform(self, values: pd.Series) -> pd.Series:
        return values.map(self.name_to_code).fillna(-1).astype(int)

    def fit_transform(self, values: pd.Series) -> pd.Series:
        return self.fit(values).transform(values)

    def to_dict(self) -> dict[str, int]:
        return dict(self.name_to_code)

    @classmethod
    def from_dict(cls, payload: dict[str, int]) -> "CategoryEncoder":
        return cls(name_to_code=dict(payload))


@dataclass
class FeaturePipelineState:
    """Captures everything we need to re-create the exact feature matrix at
    inference time. Persisted alongside the LightGBM model."""

    store_encoder: CategoryEncoder
    product_encoder: CategoryEncoder
    feature_columns: list[str]
    last_observed_date: date

    def to_dict(self) -> dict:
        return {
            "store_encoder": self.store_encoder.to_dict(),
            "product_encoder": self.product_encoder.to_dict(),
            "feature_columns": list(self.feature_columns),
            "last_observed_date": self.last_observed_date.isoformat(),
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "FeaturePipelineState":
        return cls(
            store_encoder=CategoryEncoder.from_dict(payload["store_encoder"]),
            product_encoder=CategoryEncoder.from_dict(payload["product_encoder"]),
            feature_columns=list(payload["feature_columns"]),
            last_observed_date=date.fromisoformat(payload["last_observed_date"]),
        )


# ---------------------------------------------------------------------------
# Calendar + holiday layer
# ---------------------------------------------------------------------------

# Cached so we don't rebuild the holiday tables every call. We pick a wide
# range that covers Kaggle (2013+) and a safe forward horizon for forecasts.
_ETHIOPIAN_HOLIDAYS = _holidays_pkg.country_holidays("ET", years=range(2010, 2040))
_US_HOLIDAYS = _holidays_pkg.country_holidays("US", years=range(2010, 2040))


def _add_calendar_features(df: pd.DataFrame) -> pd.DataFrame:
    """Mutates and returns ``df`` with the calendar + holiday columns added."""
    dt = df["date"].dt
    df["year"] = dt.year.astype("int16")
    df["month"] = dt.month.astype("int8")
    df["day"] = dt.day.astype("int8")
    df["day_of_week"] = dt.dayofweek.astype("int8")
    df["day_of_year"] = dt.dayofyear.astype("int16")
    df["week_of_year"] = dt.isocalendar().week.astype("int8")
    df["is_weekend"] = (df["day_of_week"] >= 5).astype("int8")
    df["is_month_start"] = dt.is_month_start.astype("int8")
    df["is_month_end"] = dt.is_month_end.astype("int8")

    df["is_holiday_et"] = df["date"].apply(lambda d: int(d.date() in _ETHIOPIAN_HOLIDAYS)).astype("int8")
    df["is_holiday_us"] = df["date"].apply(lambda d: int(d.date() in _US_HOLIDAYS)).astype("int8")
    return df


# ---------------------------------------------------------------------------
# Lag + rolling layer
# ---------------------------------------------------------------------------


def _add_lag_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add ``lag_{n}`` and ``rolling_mean_{w}`` per (store_ref, product_ref).

    Note: we sort by ``date`` first (groupby preserves the within-group order),
    then shift inside each group. This is critical — a global shift would
    leak signal across series.
    """
    df = df.sort_values(["store_ref", "product_ref", "date"]).reset_index(drop=True)
    grouped = df.groupby(["store_ref", "product_ref"], sort=False)[TARGET_COLUMN]

    for lag in LAG_DAYS:
        df[f"lag_{lag}"] = grouped.shift(lag)

    for window in ROLLING_WINDOWS:
        # Shift by 1 inside .transform() so the rolling window NEVER includes
        # the current row — otherwise the model would have target leakage.
        df[f"rolling_mean_{window}"] = grouped.transform(
            lambda s, w=window: s.shift(1).rolling(window=w, min_periods=1).mean()
        )

    return df


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_feature_matrix(
    df: pd.DataFrame,
    *,
    state: Optional[FeaturePipelineState] = None,
    drop_warmup_rows: bool = True,
) -> tuple[pd.DataFrame, pd.Series, FeaturePipelineState]:
    """Build the LightGBM feature matrix from a canonical-schema DataFrame.

    Args:
        df: canonical DataFrame from ``data_loader``.
        state: if provided, reuse the encoders + column order from a prior
            fit (used at inference time). If ``None``, fit fresh encoders.
        drop_warmup_rows: drops rows whose largest lag feature is NaN
            (i.e. the first ``max(LAG_DAYS)`` rows per series). Set False
            during inference to keep all rows.

    Returns:
        (feature_matrix, target_series, state)
    """
    if df.empty:
        raise ValueError("Cannot build features from an empty DataFrame.")
    if not pd.api.types.is_datetime64_any_dtype(df["date"]):
        df = df.copy()
        df["date"] = pd.to_datetime(df["date"])

    working = df.copy()
    working = _add_calendar_features(working)
    working = _add_lag_features(working)

    # Categorical encoding (fit-or-reuse)
    if state is None:
        store_enc = CategoryEncoder().fit(working["store_ref"])
        prod_enc = CategoryEncoder().fit(working["product_ref"])
    else:
        store_enc = state.store_encoder
        prod_enc = state.product_encoder

    working["store_code"] = store_enc.transform(working["store_ref"])
    working["product_code"] = prod_enc.transform(working["product_ref"])

    lag_cols = [f"lag_{n}" for n in LAG_DAYS]
    rolling_cols = [f"rolling_mean_{w}" for w in ROLLING_WINDOWS]
    feature_columns = (
        CALENDAR_FEATURES + HOLIDAY_FEATURES + CATEGORICAL_FEATURES + lag_cols + rolling_cols
    )

    if drop_warmup_rows:
        max_lag = max(LAG_DAYS)
        before = len(working)
        working = working.dropna(subset=lag_cols).reset_index(drop=True)
        logger.debug(
            "Dropped %d warm-up rows (max lag=%d)", before - len(working), max_lag
        )

    # Fill any remaining NaNs in rolling features (early-series edge case)
    working[rolling_cols] = working[rolling_cols].fillna(0.0)

    X = working[feature_columns].copy()
    y = working[TARGET_COLUMN].astype(float).copy()

    last_date = working["date"].max().date()
    fitted_state = FeaturePipelineState(
        store_encoder=store_enc,
        product_encoder=prod_enc,
        feature_columns=feature_columns,
        last_observed_date=last_date,
    )
    return X, y, fitted_state


def build_inference_frame(
    history: pd.DataFrame,
    target_rows: pd.DataFrame,
    state: FeaturePipelineState,
) -> pd.DataFrame:
    """Construct a feature matrix for prediction.

    Args:
        history: canonical-schema DataFrame containing the most recent
            ``max(LAG_DAYS)`` days of actual sales for the (store, product)
            combos we want to forecast.
        target_rows: canonical-schema rows with the future ``date`` /
            ``store_ref`` / ``product_ref`` and ``quantity_sold=NaN`` (placeholder).
        state: encoders + column order from the most recent training run.

    Returns the feature matrix only (no target series).
    """
    combined = pd.concat([history, target_rows], ignore_index=True)
    X, _, _ = build_feature_matrix(combined, state=state, drop_warmup_rows=False)
    # Only return rows that correspond to target_rows (those after history)
    target_mask = combined["date"].isin(target_rows["date"]) & (
        combined["store_ref"].isin(target_rows["store_ref"])
        & combined["product_ref"].isin(target_rows["product_ref"])
    )
    return X.loc[target_mask].reset_index(drop=True)
