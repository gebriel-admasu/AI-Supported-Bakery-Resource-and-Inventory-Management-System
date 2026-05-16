"""Block A smoke test: data loader + feature engineering end-to-end.

Run with::

    python -m scripts.smoke_test_pipeline
"""

from __future__ import annotations

import sys

from app.database import SessionLocal
from app.pipeline.data_loader import DataSource, load_training_data
from app.pipeline.feature_engineering import build_feature_matrix


def _section(title: str) -> None:
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def main() -> int:
    _section("1. Auto-select source")
    with SessionLocal() as db:
        result = load_training_data(db=db)
    print(f"  source        = {result.source.value}")
    print(f"  rows          = {result.rows:,}")
    print(f"  description   = {result.description}")
    print(f"  date range    = {result.df['date'].min().date()} -> {result.df['date'].max().date()}")
    print(f"  unique stores = {result.df['store_ref'].nunique()}")
    print(f"  unique prods  = {result.df['product_ref'].nunique()}")

    _section("2. Explicit SYNTHETIC source")
    synth = load_training_data(prefer=DataSource.SYNTHETIC)
    print(f"  source = {synth.source.value}, rows = {synth.rows:,}")

    _section("3. Explicit KAGGLE source")
    try:
        kaggle = load_training_data(prefer=DataSource.KAGGLE)
        print(f"  source = {kaggle.source.value}, rows = {kaggle.rows:,}")
    except FileNotFoundError as e:
        print(f"  skipped: {e}")
        kaggle = None

    _section("4. Feature matrix on a small subset (synthetic)")
    sample = synth.df.copy()
    # Take only the first 3 stores and 5 products to keep this fast
    keep_stores = sorted(sample["store_ref"].unique())[:3]
    keep_products = sorted(sample["product_ref"].unique())[:5]
    sample = sample[
        sample["store_ref"].isin(keep_stores)
        & sample["product_ref"].isin(keep_products)
    ].reset_index(drop=True)
    print(f"  input rows    = {len(sample):,}")

    X, y, state = build_feature_matrix(sample)
    print(f"  matrix shape  = {X.shape}")
    print(f"  target shape  = {y.shape}")
    print(f"  features      = {len(state.feature_columns)}")
    print(f"  feature names = {state.feature_columns}")
    print(f"  store encoder = {len(state.store_encoder.name_to_code)} categories")
    print(f"  prod  encoder = {len(state.product_encoder.name_to_code)} categories")
    print(f"  last obs date = {state.last_observed_date}")
    print()
    print("  Sample X head (first 3 rows):")
    print(X.head(3).to_string(index=False))
    print()
    print("  Sample y head (first 3 values):", y.head(3).tolist())

    _section("5. Feature matrix on Kaggle data (full)")
    if kaggle is not None:
        # Just sample the first 200k rows to keep memory sane on the smoke run
        kaggle_sample = kaggle.df.head(200_000).copy()
        print(f"  input rows    = {len(kaggle_sample):,}")
        Xk, yk, state_k = build_feature_matrix(kaggle_sample)
        print(f"  matrix shape  = {Xk.shape}")
        print(f"  target shape  = {yk.shape}")
        print(f"  features      = {len(state_k.feature_columns)}")
        print(f"  store encoder = {len(state_k.store_encoder.name_to_code)} categories")
        print(f"  prod  encoder = {len(state_k.product_encoder.name_to_code)} categories")
    else:
        print("  Kaggle CSV not available, skipped.")

    print()
    print("Smoke test PASSED.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
