"""Validation gate: decide whether a freshly-trained CANDIDATE deserves
promotion to CHAMPION, or should be rejected.

The gate has two criteria — **both** must pass for the candidate to be
promoted:

1. **Holdout MAE improvement.** Candidate's MAE on a held-out backtest
   window must be at least ``MAE_IMPROVEMENT_MIN`` (default 2 %) lower than
   the current champion's MAE on the same window. This catches "the new
   model is technically different but no better" regressions.
2. **Paired t-test significance.** The per-row absolute-error difference
   between champion and candidate must be statistically significant
   (``p < TTEST_P_VALUE_MAX``, default 0.05). This catches "the new model
   looks better on aggregate but it's within noise" cases.

Why both? Either criterion alone is gameable:
- MAE-only would promote tiny improvements that are pure noise.
- t-test-only would promote any consistently-different model even if it's
  consistently *worse*. The MAE delta enforces direction; the t-test enforces
  significance.

If there's **no current champion** (cold-start case), the gate auto-promotes
without testing — there's nothing to compare against.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import ModelRegistry
from app.ml.forecaster import ForecastTarget, Forecaster
from app.ml.registry import get_champion
from app.pipeline.data_loader import load_training_data
from app.pipeline.feature_engineering import LAG_DAYS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result wrapper
# ---------------------------------------------------------------------------


@dataclass
class ValidationResult:
    """Verdict + diagnostics that we both log to MLOps and surface in the
    ``POST /ai/retrain`` response so callers can see exactly why a candidate
    was promoted or rejected."""

    decision: str  # "PROMOTE" | "REJECT" | "PROMOTE_COLD_START"
    candidate_mae: Optional[float]
    champion_mae: Optional[float]
    relative_improvement: Optional[float]
    p_value: Optional[float]
    sample_size: int
    reason: str

    def to_log_payload(self) -> dict:
        return {
            "decision": self.decision,
            "candidate_mae": self._round(self.candidate_mae),
            "champion_mae": self._round(self.champion_mae),
            "relative_improvement": self._round(self.relative_improvement, 4),
            "p_value": self._round(self.p_value, 6),
            "sample_size": self.sample_size,
            "reason": self.reason,
        }

    @staticmethod
    def _round(value: Optional[float], digits: int = 4) -> Optional[float]:
        return round(value, digits) if value is not None else None

    @property
    def should_promote(self) -> bool:
        return self.decision in {"PROMOTE", "PROMOTE_COLD_START"}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_candidate(
    db: Session,
    *,
    candidate: ModelRegistry,
    eval_days: int = 14,
) -> ValidationResult:
    """Compare a CANDIDATE against the current CHAMPION over a recent window.

    Args:
        db: open SQLAlchemy session.
        candidate: the ``ModelRegistry`` row of the candidate to validate.
            We load its artifact from ``candidate.model_path``.
        eval_days: how many trailing days of data form the evaluation window
            (default 14 — same as trainer holdout for consistency).

    Returns a :class:`ValidationResult` with verdict + diagnostics.
    """
    champion = get_champion(db)

    # ------------------------------------------------------------------
    # Cold-start branch — no champion to beat, auto-promote.
    # ------------------------------------------------------------------
    if champion is None:
        logger.info("No current CHAMPION; auto-promoting candidate v%d.", candidate.version)
        return ValidationResult(
            decision="PROMOTE_COLD_START",
            candidate_mae=float(candidate.holdout_mae) if candidate.holdout_mae is not None else None,
            champion_mae=None,
            relative_improvement=None,
            p_value=None,
            sample_size=0,
            reason="No current CHAMPION — first trained model is auto-promoted.",
        )

    # ------------------------------------------------------------------
    # Same-version branch — re-validating the existing champion is a no-op.
    # ------------------------------------------------------------------
    if champion.version == candidate.version:
        return ValidationResult(
            decision="REJECT",
            candidate_mae=float(candidate.holdout_mae) if candidate.holdout_mae is not None else None,
            champion_mae=float(champion.holdout_mae) if champion.holdout_mae is not None else None,
            relative_improvement=0.0,
            p_value=None,
            sample_size=0,
            reason="Candidate and champion are the same model version.",
        )

    # ------------------------------------------------------------------
    # Real validation: re-score both models on the same evaluation window.
    # ------------------------------------------------------------------
    eval_df = _load_evaluation_window(db, eval_days)
    if eval_df is None or eval_df.empty:
        return ValidationResult(
            decision="REJECT",
            candidate_mae=float(candidate.holdout_mae) if candidate.holdout_mae is not None else None,
            champion_mae=float(champion.holdout_mae) if champion.holdout_mae is not None else None,
            relative_improvement=None,
            p_value=None,
            sample_size=0,
            reason="No data available in the evaluation window.",
        )

    champion_errors, candidate_errors = _compute_error_arrays(
        eval_df,
        champion_path=Path(champion.model_path),
        candidate_path=Path(candidate.model_path),
    )

    if len(champion_errors) == 0:
        return ValidationResult(
            decision="REJECT",
            candidate_mae=None,
            champion_mae=None,
            relative_improvement=None,
            p_value=None,
            sample_size=0,
            reason="Models produced no comparable predictions on the evaluation window.",
        )

    champ_mae = float(np.mean(champion_errors))
    cand_mae = float(np.mean(candidate_errors))

    rel_improvement = (
        (champ_mae - cand_mae) / champ_mae if champ_mae > 0 else 0.0
    )

    # Paired t-test on per-row error differences.
    # H0: mean(candidate_errors - champion_errors) == 0 (no difference)
    # We want H0 rejected AND the candidate to be the smaller one.
    if len(champion_errors) >= 2:
        t_stat, p_value = stats.ttest_rel(candidate_errors, champion_errors)
        # If candidate is BETTER, t_stat < 0; we treat one-sided test for "better".
        # scipy returns two-sided p; divide by 2 when the sign aligns with our hypothesis.
        if t_stat < 0:
            one_sided_p = float(p_value) / 2.0
        else:
            one_sided_p = 1.0 - float(p_value) / 2.0
    else:
        one_sided_p = 1.0

    sample_size = len(champion_errors)

    # ------------------------------------------------------------------
    # Decision matrix
    # ------------------------------------------------------------------
    if rel_improvement < settings.MAE_IMPROVEMENT_MIN:
        return ValidationResult(
            decision="REJECT",
            candidate_mae=cand_mae,
            champion_mae=champ_mae,
            relative_improvement=rel_improvement,
            p_value=one_sided_p,
            sample_size=sample_size,
            reason=(
                f"Relative MAE improvement {rel_improvement:.2%} below threshold "
                f"{settings.MAE_IMPROVEMENT_MIN:.2%}."
            ),
        )

    if one_sided_p > settings.TTEST_P_VALUE_MAX:
        return ValidationResult(
            decision="REJECT",
            candidate_mae=cand_mae,
            champion_mae=champ_mae,
            relative_improvement=rel_improvement,
            p_value=one_sided_p,
            sample_size=sample_size,
            reason=(
                f"Paired t-test p={one_sided_p:.4f} above threshold "
                f"{settings.TTEST_P_VALUE_MAX:.4f} — improvement not statistically significant."
            ),
        )

    return ValidationResult(
        decision="PROMOTE",
        candidate_mae=cand_mae,
        champion_mae=champ_mae,
        relative_improvement=rel_improvement,
        p_value=one_sided_p,
        sample_size=sample_size,
        reason=(
            f"Candidate beats champion by {rel_improvement:.2%} "
            f"(MAE {champ_mae:.4f} -> {cand_mae:.4f}, p={one_sided_p:.4f})."
        ),
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _load_evaluation_window(db: Session, eval_days: int) -> Optional[pd.DataFrame]:
    """Load enough data so we can ask each model to predict the last
    ``eval_days`` and compare predictions to actuals."""
    load = load_training_data(db=db)
    df = load.df
    if df.empty:
        return None

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    return df


def _compute_error_arrays(
    df: pd.DataFrame,
    *,
    champion_path: Path,
    candidate_path: Path,
    eval_days: int = 14,
) -> tuple[np.ndarray, np.ndarray]:
    """Run both champion and candidate on the last ``eval_days`` of ``df``
    and return paired ``|actual - predicted|`` arrays in the same order.

    Both models predict the same (store, product, date) targets so their
    error arrays are paired row-for-row — that's what makes the t-test
    meaningful.
    """
    last_date = df["date"].max().date()
    eval_start = last_date - timedelta(days=eval_days - 1)
    eval_mask = df["date"].dt.date >= eval_start

    targets_df = df[eval_mask].copy()
    if targets_df.empty:
        return np.array([]), np.array([])

    # History window for lag features (everything before the eval window plus
    # a buffer for lag-28 + rolling-28).
    history_end = eval_start - timedelta(days=1)
    history_start = history_end - timedelta(days=max(LAG_DAYS) + 28)
    history_df = df[
        (df["date"].dt.date >= history_start) & (df["date"].dt.date <= history_end)
    ].copy()

    if history_df.empty:
        logger.warning("Validation: empty history window — cannot compute lag features.")
        return np.array([]), np.array([])

    champion = Forecaster.from_artifact(champion_path)
    candidate = Forecaster.from_artifact(candidate_path)

    # Build (store, product, date) targets from the actual eval rows.
    target_keys = [
        ForecastTarget(
            store_ref=row.store_ref,
            product_ref=row.product_ref,
            target_date=row.date.date(),
        )
        for row in targets_df.itertuples(index=False)
    ]

    champ_preds = {
        (p.store_ref, p.product_ref, p.target_date): p.predicted_qty
        for p in champion.predict_for_targets(history_df, target_keys)
    }
    cand_preds = {
        (p.store_ref, p.product_ref, p.target_date): p.predicted_qty
        for p in candidate.predict_for_targets(history_df, target_keys)
    }

    champ_errors: list[float] = []
    cand_errors: list[float] = []
    for row in targets_df.itertuples(index=False):
        key = (row.store_ref, row.product_ref, row.date.date())
        if key not in champ_preds or key not in cand_preds:
            continue
        actual = float(row.quantity_sold)
        champ_errors.append(abs(actual - champ_preds[key]))
        cand_errors.append(abs(actual - cand_preds[key]))

    return np.array(champ_errors), np.array(cand_errors)
