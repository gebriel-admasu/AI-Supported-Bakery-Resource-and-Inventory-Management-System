"""Helpers around the ``ai_model_registry`` table.

The trainer + scheduler need a small, well-tested API for:

- Picking the next version number
- Inserting a CANDIDATE row after a fresh training run
- Promoting a CANDIDATE to CHAMPION (archives the prior CHAMPION)
- Resolving "the current CHAMPION" for the forecaster to load
- Listing all rows for the ``GET /ai/models`` endpoint

We keep this distinct from the SQLAlchemy model file so the table definition
stays a thin schema declaration and the business logic lives here.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.db.models import (
    MlopsEventType,
    MlopsLog,
    ModelRegistry,
    ModelStatus,
)
from app.ml.forecaster import invalidate_loader_cache

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


def list_versions(db: Session) -> list[int]:
    """All version numbers ever trained, in ascending order."""
    rows = db.query(ModelRegistry.version).order_by(ModelRegistry.version.asc()).all()
    return [r[0] for r in rows]


def get_by_version(db: Session, version: int) -> Optional[ModelRegistry]:
    return db.query(ModelRegistry).filter(ModelRegistry.version == version).first()


def get_champion(db: Session) -> Optional[ModelRegistry]:
    """Returns the single CHAMPION row, or None if no champion is registered yet."""
    return (
        db.query(ModelRegistry)
        .filter(ModelRegistry.status == ModelStatus.CHAMPION.value)
        .order_by(ModelRegistry.version.desc())
        .first()
    )


def get_latest_candidate(db: Session) -> Optional[ModelRegistry]:
    """Returns the most recent CANDIDATE row, or None."""
    return (
        db.query(ModelRegistry)
        .filter(ModelRegistry.status == ModelStatus.CANDIDATE.value)
        .order_by(ModelRegistry.version.desc())
        .first()
    )


def list_all(db: Session, *, limit: int = 50) -> list[ModelRegistry]:
    """Most-recent first listing for the admin UI."""
    return (
        db.query(ModelRegistry)
        .order_by(ModelRegistry.trained_at.desc())
        .limit(limit)
        .all()
    )


# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------


def register_candidate(
    db: Session,
    *,
    version: int,
    model_path: str,
    holdout_mae: float,
    training_rows_used: int,
    training_source: str,
    feature_columns: list[str],
    notes: Optional[str] = None,
) -> ModelRegistry:
    """Insert a fresh CANDIDATE row + append a TRAIN mlops log entry."""
    row = ModelRegistry(
        id=uuid.uuid4(),
        version=version,
        status=ModelStatus.CANDIDATE.value,
        trained_at=datetime.now(timezone.utc),
        training_rows_used=training_rows_used,
        training_source=training_source,
        holdout_mae=holdout_mae,
        model_path=model_path,
        feature_list=json.dumps(feature_columns),
        notes=notes,
    )
    db.add(row)
    db.flush()

    _log_event(
        db,
        event_type=MlopsEventType.TRAIN,
        candidate_version=version,
        champion_version=(get_champion(db).version if get_champion(db) else None),
        payload={
            "holdout_mae": holdout_mae,
            "training_rows": training_rows_used,
            "training_source": training_source,
            "feature_count": len(feature_columns),
        },
        message=f"Trained candidate v{version} from {training_source} ({training_rows_used} rows).",
    )
    db.commit()
    db.refresh(row)
    return row


def promote_candidate(
    db: Session,
    *,
    candidate_version: int,
    reason: str,
    payload: Optional[dict] = None,
) -> ModelRegistry:
    """Promote a CANDIDATE to CHAMPION; archive any current CHAMPION.

    Idempotent in the sense that re-promoting an already-CHAMPION version is a
    no-op (returns the existing row). Anything else (non-existent version,
    already-archived) raises ``ValueError`` to surface misuse.
    """
    candidate = get_by_version(db, candidate_version)
    if candidate is None:
        raise ValueError(f"No model version {candidate_version} in the registry.")
    if candidate.status == ModelStatus.CHAMPION.value:
        return candidate
    if candidate.status == ModelStatus.ARCHIVED.value:
        raise ValueError(
            f"Cannot promote archived version {candidate_version}; train a fresh candidate instead."
        )

    prev_champion = get_champion(db)
    now = datetime.now(timezone.utc)

    if prev_champion is not None and prev_champion.version != candidate_version:
        prev_champion.status = ModelStatus.ARCHIVED.value
        prev_champion.archived_at = now

    candidate.status = ModelStatus.CHAMPION.value
    candidate.promoted_at = now
    db.flush()

    _log_event(
        db,
        event_type=MlopsEventType.PROMOTE,
        candidate_version=candidate_version,
        champion_version=candidate_version,
        payload={
            "previous_champion_version": (prev_champion.version if prev_champion else None),
            "reason": reason,
            **(payload or {}),
        },
        message=f"Promoted v{candidate_version} to CHAMPION ({reason}).",
    )
    db.commit()
    db.refresh(candidate)

    # Anyone holding a stale forecaster for the old champion should reload.
    invalidate_loader_cache()
    return candidate


def reject_candidate(
    db: Session,
    *,
    candidate_version: int,
    reason: str,
    payload: Optional[dict] = None,
) -> ModelRegistry:
    """Mark a CANDIDATE as ARCHIVED without promoting it."""
    candidate = get_by_version(db, candidate_version)
    if candidate is None:
        raise ValueError(f"No model version {candidate_version} in the registry.")
    if candidate.status != ModelStatus.CANDIDATE.value:
        raise ValueError(
            f"Cannot reject version {candidate_version} with status={candidate.status}."
        )

    candidate.status = ModelStatus.ARCHIVED.value
    candidate.archived_at = datetime.now(timezone.utc)
    db.flush()

    _log_event(
        db,
        event_type=MlopsEventType.REJECT,
        candidate_version=candidate_version,
        champion_version=(get_champion(db).version if get_champion(db) else None),
        payload={"reason": reason, **(payload or {})},
        message=f"Rejected v{candidate_version}: {reason}",
    )
    db.commit()
    db.refresh(candidate)
    return candidate


# ---------------------------------------------------------------------------
# MLOps log writer
# ---------------------------------------------------------------------------


def _log_event(
    db: Session,
    *,
    event_type: MlopsEventType,
    candidate_version: Optional[int],
    champion_version: Optional[int],
    payload: Optional[dict] = None,
    message: Optional[str] = None,
) -> MlopsLog:
    """Append a single audit log row. Kept private so callers go through the
    semantic helpers above (which guarantee event_type matches the action)."""
    entry = MlopsLog(
        id=uuid.uuid4(),
        event_type=event_type.value,
        candidate_version=candidate_version,
        champion_version=champion_version,
        payload=json.dumps(payload) if payload is not None else None,
        message=message,
        occurred_at=datetime.now(timezone.utc),
    )
    db.add(entry)
    db.flush()
    return entry


def log_event(
    db: Session,
    *,
    event_type: MlopsEventType,
    candidate_version: Optional[int] = None,
    champion_version: Optional[int] = None,
    payload: Optional[dict] = None,
    message: Optional[str] = None,
) -> MlopsLog:
    """Public wrapper for non-promotion events (backtest, validate, error)
    that the scheduler / pipeline modules need to emit."""
    entry = _log_event(
        db,
        event_type=event_type,
        candidate_version=candidate_version,
        champion_version=champion_version,
        payload=payload,
        message=message,
    )
    db.commit()
    db.refresh(entry)
    return entry
