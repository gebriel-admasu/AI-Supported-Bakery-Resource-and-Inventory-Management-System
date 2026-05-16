"""Train a LightGBM regressor on the unified sales DataFrame.

The trainer is intentionally minimal — one set of hyperparameters tuned for
the Kaggle Store Item Demand benchmark, a chronological holdout for honest
MAE measurement, and a single persisted artifact (LightGBM model + feature
state) that the forecaster can re-hydrate at inference time.

Design notes:
- **Chronological split, not random.** Sales are time-series; a random split
  would leak future information into the training set and inflate the holdout
  MAE estimate. We always hold out the last ``holdout_days`` days.
- **One artifact, one file.** ``joblib.dump`` serialises a small dict containing
  the LightGBM booster *and* the ``FeaturePipelineState`` (encoders + feature
  column order). The forecaster only needs to load this one file.
- **Reproducibility.** Seeded RNG everywhere so the same dataset produces the
  same model every time. Critical for the Champion vs Candidate comparison
  in Phase 12 to be apples-to-apples.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd

from app.pipeline.feature_engineering import (
    FeaturePipelineState,
    build_feature_matrix,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Hyperparameters
# ---------------------------------------------------------------------------

DEFAULT_LGBM_PARAMS = {
    "objective": "regression_l1",   # MAE is the optimisation target — matches our gate metric
    "metric": "mae",
    "learning_rate": 0.05,
    "num_leaves": 63,
    "max_depth": -1,
    "min_data_in_leaf": 100,
    "feature_fraction": 0.9,
    "bagging_fraction": 0.9,
    "bagging_freq": 5,
    "verbose": -1,
    "seed": 42,
    "deterministic": True,
}

DEFAULT_NUM_ROUNDS = 600
DEFAULT_EARLY_STOPPING_ROUNDS = 40
DEFAULT_HOLDOUT_DAYS = 14


# ---------------------------------------------------------------------------
# Result wrapper
# ---------------------------------------------------------------------------


@dataclass
class TrainingResult:
    """Everything callers need to log + register the trained model."""

    model_path: Path
    holdout_mae: float
    holdout_rows: int
    training_rows: int
    feature_count: int
    runtime_seconds: float
    best_iteration: int
    state: FeaturePipelineState

    def to_log_payload(self) -> dict:
        return {
            "model_path": str(self.model_path),
            "holdout_mae": round(self.holdout_mae, 4),
            "holdout_rows": self.holdout_rows,
            "training_rows": self.training_rows,
            "feature_count": self.feature_count,
            "runtime_seconds": round(self.runtime_seconds, 2),
            "best_iteration": self.best_iteration,
        }


# ---------------------------------------------------------------------------
# Trainer
# ---------------------------------------------------------------------------


def _chronological_split(
    df: pd.DataFrame, holdout_days: int
) -> tuple[pd.DataFrame, pd.DataFrame]:
    max_date = df["date"].max()
    cutoff = max_date - pd.Timedelta(days=holdout_days)
    train_df = df[df["date"] <= cutoff].reset_index(drop=True)
    holdout_df = df[df["date"] > cutoff].reset_index(drop=True)
    return train_df, holdout_df


def train_model(
    df: pd.DataFrame,
    *,
    model_dir: Path,
    version: int,
    holdout_days: int = DEFAULT_HOLDOUT_DAYS,
    params: Optional[dict] = None,
    num_rounds: int = DEFAULT_NUM_ROUNDS,
    early_stopping_rounds: int = DEFAULT_EARLY_STOPPING_ROUNDS,
) -> TrainingResult:
    """Train a LightGBM regressor on the canonical sales DataFrame.

    Args:
        df: canonical DataFrame from ``data_loader``.
        model_dir: directory under which the artifact is persisted.
        version: registry version number used for the filename
            (``v{version}.joblib``).
        holdout_days: number of trailing days to reserve for holdout MAE.
        params: optional override for ``DEFAULT_LGBM_PARAMS``.
        num_rounds: maximum boosting rounds.
        early_stopping_rounds: stop if holdout MAE doesn't improve for N
            consecutive rounds.

    Returns a :class:`TrainingResult` describing the persisted artifact.
    """
    if df.empty:
        raise ValueError("Cannot train on an empty DataFrame.")
    if "date" not in df.columns:
        raise ValueError("DataFrame must include a 'date' column.")

    started = time.perf_counter()
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])

    train_raw, holdout_raw = _chronological_split(df, holdout_days)
    if holdout_raw.empty:
        raise ValueError(
            f"holdout_days={holdout_days} produced an empty holdout window. "
            f"Data spans only {(df['date'].max() - df['date'].min()).days} days."
        )

    # Build features on the FULL dataset so lag features at the start of the
    # holdout window can look back into the training window. Then split into
    # X_train / y_train / X_holdout / y_holdout by date.
    cutoff = train_raw["date"].max()
    X, y, state = build_feature_matrix(df)

    # Re-align by date: we need to know which feature rows belong to which split
    aligned = df.sort_values(["store_ref", "product_ref", "date"]).reset_index(drop=True)
    # Drop the same warm-up rows that build_feature_matrix dropped (rows where
    # max lag is NaN). Easiest way is to take the tail matching X's length.
    aligned = aligned.iloc[-len(X) :].reset_index(drop=True)

    train_mask = aligned["date"] <= cutoff
    X_train, y_train = X[train_mask].reset_index(drop=True), y[train_mask].reset_index(drop=True)
    X_holdout, y_holdout = X[~train_mask].reset_index(drop=True), y[~train_mask].reset_index(drop=True)

    if X_train.empty or X_holdout.empty:
        raise ValueError(
            f"Split produced an unusable train/holdout (train={len(X_train)}, "
            f"holdout={len(X_holdout)}). Increase the date range."
        )

    train_dataset = lgb.Dataset(X_train, label=y_train, free_raw_data=False)
    holdout_dataset = lgb.Dataset(
        X_holdout,
        label=y_holdout,
        reference=train_dataset,
        free_raw_data=False,
    )

    booster = lgb.train(
        params=params or DEFAULT_LGBM_PARAMS,
        train_set=train_dataset,
        num_boost_round=num_rounds,
        valid_sets=[holdout_dataset],
        valid_names=["holdout"],
        callbacks=[
            lgb.early_stopping(early_stopping_rounds, verbose=False),
            lgb.log_evaluation(period=0),  # silence per-round noise
        ],
    )

    # Compute holdout MAE explicitly so the registry stores the same number the
    # validation gate will recompute later (avoids subtle differences between
    # LightGBM's internal metric and our scipy comparison).
    preds = booster.predict(X_holdout, num_iteration=booster.best_iteration)
    holdout_mae = float(np.mean(np.abs(y_holdout.to_numpy() - preds)))

    model_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = model_dir / f"v{version}.joblib"
    joblib.dump(
        {
            "booster_text": booster.model_to_string(),  # portable string repr
            "best_iteration": booster.best_iteration,
            "state": state.to_dict(),
            "trained_at": datetime.now(timezone.utc).isoformat(),
            "version": version,
        },
        artifact_path,
    )

    runtime = time.perf_counter() - started
    logger.info(
        "Trained v%d in %.2fs: train=%d, holdout=%d, MAE=%.4f, best_iter=%d",
        version,
        runtime,
        len(X_train),
        len(X_holdout),
        holdout_mae,
        booster.best_iteration,
    )

    return TrainingResult(
        model_path=artifact_path,
        holdout_mae=holdout_mae,
        holdout_rows=len(X_holdout),
        training_rows=len(X_train),
        feature_count=len(state.feature_columns),
        runtime_seconds=runtime,
        best_iteration=booster.best_iteration,
        state=state,
    )


def next_version_number(existing_versions: list[int]) -> int:
    """Returns ``max(existing) + 1`` (or 1 if the registry is empty)."""
    return max(existing_versions) + 1 if existing_versions else 1
