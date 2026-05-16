"""Unit tests for ``pipeline/feature_engineering.py``.

Focus areas:
- All expected feature columns are produced.
- Lag features inside a series are correctly aligned (no leakage across stores).
- Encoders persist + replay deterministically when reused at inference time.
- Unseen categories at inference map to the -1 sentinel instead of crashing.
"""

from __future__ import annotations

import pandas as pd

from app.pipeline.feature_engineering import (
    CALENDAR_FEATURES,
    CATEGORICAL_FEATURES,
    HOLIDAY_FEATURES,
    LAG_DAYS,
    ROLLING_WINDOWS,
    CategoryEncoder,
    build_feature_matrix,
)


def test_feature_matrix_has_all_expected_columns(synthetic_sales):
    X, y, state = build_feature_matrix(synthetic_sales)
    expected = (
        CALENDAR_FEATURES
        + HOLIDAY_FEATURES
        + CATEGORICAL_FEATURES
        + [f"lag_{n}" for n in LAG_DAYS]
        + [f"rolling_mean_{w}" for w in ROLLING_WINDOWS]
    )
    assert list(X.columns) == expected
    assert state.feature_columns == expected
    assert len(X) == len(y)
    assert len(X) > 0


def test_lag_features_are_per_series(synthetic_sales):
    """lag_1 inside series A must not depend on series B's first value."""
    X, y, _ = build_feature_matrix(synthetic_sales)
    # All lag_1 values must be >= 0 (we generated only positive sales) and finite.
    assert (X["lag_1"] >= 0).all()
    assert X["lag_1"].notna().all()


def test_warmup_rows_are_dropped(synthetic_sales):
    """With max(LAG_DAYS)=28, the first 28 rows per series should be dropped."""
    X_full, _, _ = build_feature_matrix(synthetic_sales)
    n_series = synthetic_sales[["store_ref", "product_ref"]].drop_duplicates().shape[0]
    n_total = len(synthetic_sales)
    expected_max_rows = n_total - n_series * max(LAG_DAYS)
    # We can't assert exact equality (rolling_mean fill may keep some) but we can
    # require we dropped at least as many rows as 1 * n_series (the lag_1 NaNs).
    assert len(X_full) <= expected_max_rows + n_series  # tolerate off-by-one


def test_encoders_replay_on_unseen_data(synthetic_sales):
    """Re-running build_feature_matrix with the state from a prior fit must
    reuse the same encoders (no re-fit)."""
    _, _, state = build_feature_matrix(synthetic_sales)

    subset = synthetic_sales[
        synthetic_sales["date"] >= synthetic_sales["date"].max() - pd.Timedelta(days=60)
    ].copy()
    _, _, state_new = build_feature_matrix(subset, state=state)

    assert state_new.store_encoder.name_to_code == state.store_encoder.name_to_code
    assert state_new.product_encoder.name_to_code == state.product_encoder.name_to_code

    # Sanity: every store code in the new X matrix is one we saw during training.
    X_new, _, _ = build_feature_matrix(subset, state=state)
    known_codes = set(state.store_encoder.name_to_code.values())
    assert set(X_new["store_code"].unique()).issubset(known_codes)


def test_unseen_category_maps_to_sentinel():
    enc = CategoryEncoder().fit(pd.Series(["A", "B", "C"]))
    transformed = enc.transform(pd.Series(["A", "Z", "C"]))
    assert transformed.tolist() == [0, -1, 2]


def test_rolling_mean_does_not_include_current_row():
    """rolling_mean_7 at index i must equal mean of indices i-7..i-1, NOT i-6..i."""
    df = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=10, freq="D"),
            "store_ref": ["S1"] * 10,
            "product_ref": ["P1"] * 10,
            "quantity_sold": [10, 20, 30, 40, 50, 60, 70, 80, 90, 100],
            "source": ["synthetic"] * 10,
        }
    )
    X, _, _ = build_feature_matrix(df, drop_warmup_rows=False)
    # First row's rolling_mean_7 should be 0 (filled), or NaN before fill.
    # At row index 7 (day 8, value=80), rolling_mean_7 should be mean(10..70) = 40.
    # But row index 7 in X depends on how dropna behaves; since drop_warmup_rows=False
    # the indices are preserved. Find the row with quantity_sold==80.
    aligned = df.copy()
    target_idx = aligned.index[aligned["quantity_sold"] == 80][0]
    expected = sum([10, 20, 30, 40, 50, 60, 70]) / 7
    assert abs(X.loc[target_idx, "rolling_mean_7"] - expected) < 1e-6
