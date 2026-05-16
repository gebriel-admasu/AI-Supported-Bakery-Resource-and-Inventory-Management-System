"""End-to-end retraining orchestrator: load data -> train -> register
candidate -> validate -> promote or reject.

Every caller that wants to "retrain" goes through this function — the
APScheduler jobs, the manual ``POST /ai/retrain`` endpoint, and the smoke
tests all share the exact same code path so the MLOps audit trail looks
identical no matter how the run was triggered.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import MlopsEventType
from app.ml.registry import (
    get_champion,
    list_versions,
    log_event,
    promote_candidate,
    register_candidate,
    reject_candidate,
)
from app.ml.trainer import next_version_number, train_model
from app.ml.validation import ValidationResult, validate_candidate
from app.pipeline.data_loader import DataSource, load_training_data

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result wrapper
# ---------------------------------------------------------------------------


@dataclass
class RetrainOutcome:
    """Single object that captures everything a caller might want to know
    after a retraining run finished."""

    candidate_version: int
    final_status: str  # "champion" | "rejected"
    promoted: bool
    holdout_mae: float
    training_rows: int
    training_source: str
    validation: ValidationResult
    message: str

    def to_dict(self) -> dict:
        return {
            "candidate_version": self.candidate_version,
            "final_status": self.final_status,
            "promoted": self.promoted,
            "holdout_mae": round(self.holdout_mae, 4),
            "training_rows": self.training_rows,
            "training_source": self.training_source,
            "validation": self.validation.to_log_payload(),
            "message": self.message,
        }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run_retrain(
    db: Session,
    *,
    reason: str = "manual",
    prefer_source: Optional[DataSource] = None,
    holdout_days: int = 14,
    eval_days: int = 14,
    notes: Optional[str] = None,
) -> RetrainOutcome:
    """Run a full retraining cycle. See module docstring for context.

    Args:
        db: open SQLAlchemy session.
        reason: free-form note attached to the MLOps log entry
            (e.g. ``"scheduler.cron"``, ``"scheduler.volume_threshold"``,
            ``"manual"``).
        prefer_source: force a specific data source. ``None`` = auto-pick.
        holdout_days: trailing-day window reserved for the trainer's holdout
            MAE measurement.
        eval_days: trailing-day window used by the validation gate to
            compare candidate vs champion.
        notes: optional human-readable note stored on the registry row.

    Returns a :class:`RetrainOutcome`. Raises only on truly unrecoverable
    errors (e.g. no training data anywhere) — anything inside the train /
    validate cycle is captured into the outcome and logged.
    """
    logger.info("Starting retrain (reason=%s, prefer_source=%s)", reason, prefer_source)

    # --------------------------------------------------------------
    # 1. Load training data
    # --------------------------------------------------------------
    load = load_training_data(db=db, prefer=prefer_source)
    if load.df.empty:
        raise RuntimeError(
            "No training data available from any configured source. "
            "Cannot retrain."
        )
    logger.info(
        "Loaded %d rows from %s for retraining.", load.rows, load.source.value
    )

    # --------------------------------------------------------------
    # 2. Train a fresh candidate
    # --------------------------------------------------------------
    next_version = next_version_number(list_versions(db))
    model_dir = Path(settings.MODEL_DIR)
    training_result = train_model(
        load.df,
        model_dir=model_dir,
        version=next_version,
        holdout_days=holdout_days,
    )

    candidate = register_candidate(
        db,
        version=next_version,
        model_path=str(training_result.model_path),
        holdout_mae=training_result.holdout_mae,
        training_rows_used=training_result.training_rows,
        training_source=load.source.value,
        feature_columns=training_result.state.feature_columns,
        notes=notes or f"Retrain ({reason}) from {load.source.value}",
    )

    # --------------------------------------------------------------
    # 3. Validation gate
    # --------------------------------------------------------------
    log_event(
        db,
        event_type=MlopsEventType.VALIDATE,
        candidate_version=candidate.version,
        champion_version=(get_champion(db).version if get_champion(db) else None),
        payload={"eval_days": eval_days, "reason": reason},
        message=f"Validating candidate v{candidate.version} on last {eval_days} days.",
    )
    validation = validate_candidate(db, candidate=candidate, eval_days=eval_days)

    # --------------------------------------------------------------
    # 4. Promote or reject based on the gate
    # --------------------------------------------------------------
    if validation.should_promote:
        promoted = promote_candidate(
            db,
            candidate_version=candidate.version,
            reason=reason,
            payload=validation.to_log_payload(),
        )
        final_status = "champion"
        promoted_flag = True
        message = (
            f"Promoted v{promoted.version} to CHAMPION. {validation.reason}"
        )
        logger.info(message)
    else:
        reject_candidate(
            db,
            candidate_version=candidate.version,
            reason=validation.reason,
            payload=validation.to_log_payload(),
        )
        final_status = "rejected"
        promoted_flag = False
        message = f"Rejected v{candidate.version}. {validation.reason}"
        logger.info(message)

    return RetrainOutcome(
        candidate_version=candidate.version,
        final_status=final_status,
        promoted=promoted_flag,
        holdout_mae=training_result.holdout_mae,
        training_rows=training_result.training_rows,
        training_source=load.source.value,
        validation=validation,
        message=message,
    )
