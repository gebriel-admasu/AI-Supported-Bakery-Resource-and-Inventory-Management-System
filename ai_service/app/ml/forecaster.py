"""Inference wrapper for a persisted LightGBM forecasting artifact.

Responsibilities:
1. Load a ``.joblib`` artifact written by ``trainer.train_model`` and re-hydrate
   the LightGBM booster + ``FeaturePipelineState`` (encoders, feature column
   order, last training date).
2. Provide ``predict_for_targets`` which produces forecasts for an arbitrary
   list of (store, product, target_date) tuples, given a sufficient history
   window for lag features.
3. Provide higher-level helpers ``predict_daily`` (single horizon) and
   ``predict_horizon`` (1- or 7-day rolling) that pull the history straight
   from the canonical data source so callers don't have to assemble it.

Design notes:
- The forecaster doesn't know anything about the database — that's the API
  layer's job. It only operates on the canonical DataFrame schema.
- We never mutate the booster after loading; thread-safety is delegated to
  the caller (the FastAPI app re-uses a single ``Forecaster`` instance via
  an LRU cache).
- For multi-step horizons we DO NOT re-feed predictions as lag inputs.
  Reason: the lag features use day-1, day-7, day-14, day-28 historic actuals
  — for a 7-day horizon all those lags still exist from the real history
  window (we just shift the target date forward day-by-day). Recursive
  prediction-as-input would compound error and isn't necessary at this
  horizon length.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd

from app.pipeline.feature_engineering import (
    FeaturePipelineState,
    LAG_DAYS,
    build_feature_matrix,
)

logger = logging.getLogger(__name__)


HISTORY_BUFFER_DAYS = max(LAG_DAYS) + 7  # extra week for the 28-day rolling mean to be meaningful


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ForecastTarget:
    """A single point we want a prediction for."""

    store_ref: str
    product_ref: str
    target_date: date


@dataclass(frozen=True)
class ForecastPoint:
    """A single forecasted value returned to callers."""

    store_ref: str
    product_ref: str
    target_date: date
    predicted_qty: float


# ---------------------------------------------------------------------------
# Forecaster
# ---------------------------------------------------------------------------


class Forecaster:
    """Lightweight wrapper around a persisted LightGBM booster.

    Use :meth:`load` (cached) to grab an instance for a specific model version.
    """

    def __init__(
        self,
        booster: lgb.Booster,
        state: FeaturePipelineState,
        version: int,
        best_iteration: int,
        trained_at: datetime,
    ):
        self.booster = booster
        self.state = state
        self.version = version
        self.best_iteration = best_iteration
        self.trained_at = trained_at

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    @classmethod
    def from_artifact(cls, artifact_path: Path) -> "Forecaster":
        """Load a forecaster from a ``.joblib`` artifact produced by
        :func:`trainer.train_model`."""
        artifact_path = Path(artifact_path)
        if not artifact_path.exists():
            raise FileNotFoundError(f"Model artifact not found: {artifact_path}")

        payload = joblib.load(artifact_path)
        booster = lgb.Booster(model_str=payload["booster_text"])
        state = FeaturePipelineState.from_dict(payload["state"])
        trained_at = datetime.fromisoformat(payload["trained_at"])
        return cls(
            booster=booster,
            state=state,
            version=int(payload["version"]),
            best_iteration=int(payload["best_iteration"]),
            trained_at=trained_at,
        )

    # ------------------------------------------------------------------
    # Core prediction
    # ------------------------------------------------------------------

    def predict_for_targets(
        self,
        history: pd.DataFrame,
        targets: Iterable[ForecastTarget],
    ) -> list[ForecastPoint]:
        """Predict for an explicit list of (store, product, date) targets.

        The caller supplies ``history`` — a canonical-schema DataFrame containing
        AT LEAST the most recent ``HISTORY_BUFFER_DAYS`` of actual sales for
        each (store, product) combo present in ``targets``. We pad zero-valued
        rows where history is missing so the lag features still resolve.
        """
        targets = list(targets)
        if not targets:
            return []

        if history.empty:
            raise ValueError("History DataFrame is empty — cannot compute lag features.")

        history = history.copy()
        history["date"] = pd.to_datetime(history["date"])
        history["quantity_sold"] = history["quantity_sold"].astype(float)

        target_df = pd.DataFrame(
            [
                {
                    "date": pd.Timestamp(t.target_date),
                    "store_ref": t.store_ref,
                    "product_ref": t.product_ref,
                    "quantity_sold": 0.0,  # placeholder, replaced by prediction
                    "source": "forecast",
                }
                for t in targets
            ]
        )

        combined = pd.concat([history, target_df], ignore_index=True)
        combined = combined.sort_values(["store_ref", "product_ref", "date"]).reset_index(drop=True)
        combined["date"] = pd.to_datetime(combined["date"])

        # build_feature_matrix re-fits its encoders if state is None — we pass
        # the loaded state so the same store_code / product_code mapping is used.
        X, _, _ = build_feature_matrix(
            combined,
            state=self.state,
            drop_warmup_rows=False,
        )

        # Build a boolean index that selects exactly the target rows.
        target_keys = {(t.store_ref, t.product_ref, pd.Timestamp(t.target_date)) for t in targets}
        is_target = combined.apply(
            lambda r: (r["store_ref"], r["product_ref"], r["date"]) in target_keys,
            axis=1,
        )

        X_target = X[is_target].reset_index(drop=True)
        if X_target.empty:
            logger.warning("No matching feature rows for the requested targets.")
            return []

        # Re-order columns to match the trained model exactly.
        X_target = X_target[self.state.feature_columns]

        preds = self.booster.predict(X_target, num_iteration=self.best_iteration)
        preds = np.clip(preds, a_min=0.0, a_max=None)  # demand can't be negative

        target_rows = combined[is_target].reset_index(drop=True)
        return [
            ForecastPoint(
                store_ref=row["store_ref"],
                product_ref=row["product_ref"],
                target_date=row["date"].date(),
                predicted_qty=float(preds[i]),
            )
            for i, row in target_rows.iterrows()
        ]

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def predict_daily(
        self,
        history: pd.DataFrame,
        target_date: date,
        pairs: Optional[Iterable[tuple[str, str]]] = None,
    ) -> list[ForecastPoint]:
        """Predict every (store, product) combo for a single target date.

        If ``pairs`` is None we predict for every combo present in ``history``
        — useful for production where we want a full daily forecast.
        """
        if pairs is None:
            pairs = (
                history[["store_ref", "product_ref"]]
                .drop_duplicates()
                .itertuples(index=False, name=None)
            )
        targets = [
            ForecastTarget(store_ref=s, product_ref=p, target_date=target_date) for s, p in pairs
        ]
        return self.predict_for_targets(history, targets)

    def predict_horizon(
        self,
        history: pd.DataFrame,
        *,
        start_date: date,
        days: int = 7,
        pairs: Optional[Iterable[tuple[str, str]]] = None,
    ) -> list[ForecastPoint]:
        """Predict every (store, product) combo for each day in
        ``[start_date, start_date + days)``.

        ``pairs`` defaults to all combos found in ``history``.
        """
        if days < 1:
            raise ValueError("days must be >= 1")

        if pairs is None:
            pairs_list = list(
                history[["store_ref", "product_ref"]]
                .drop_duplicates()
                .itertuples(index=False, name=None)
            )
        else:
            pairs_list = list(pairs)

        targets: list[ForecastTarget] = []
        for offset in range(days):
            day = start_date + timedelta(days=offset)
            for store_ref, product_ref in pairs_list:
                targets.append(ForecastTarget(store_ref, product_ref, day))
        return self.predict_for_targets(history, targets)


# ---------------------------------------------------------------------------
# Cached loader — one Booster per artifact path
# ---------------------------------------------------------------------------


@lru_cache(maxsize=4)
def load_forecaster(artifact_path: str) -> Forecaster:
    """Cached loader so we don't re-read the joblib file on every request.

    The cache key is the path string. After a promotion the path changes
    (new ``v{N}.joblib``) so the next call returns a fresh forecaster
    without any manual invalidation.
    """
    return Forecaster.from_artifact(Path(artifact_path))


def invalidate_loader_cache() -> None:
    """Clear the cached forecasters — call this after promote / archive
    operations so subsequent requests pick up the new champion."""
    load_forecaster.cache_clear()
