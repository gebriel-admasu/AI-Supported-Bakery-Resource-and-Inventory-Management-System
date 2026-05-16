"""Model registry mutation tests against an in-memory SQLite database."""

from __future__ import annotations

import pytest

from app.db.models import MlopsEventType, MlopsLog, ModelRegistry, ModelStatus
from app.ml.registry import (
    get_champion,
    get_latest_candidate,
    list_all,
    list_versions,
    log_event,
    promote_candidate,
    register_candidate,
    reject_candidate,
)


def _register(db, version: int, mae: float = 1.0):
    return register_candidate(
        db,
        version=version,
        model_path=f"models/v{version}.joblib",
        holdout_mae=mae,
        training_rows_used=100,
        training_source="synthetic",
        feature_columns=["a", "b"],
        notes=f"test v{version}",
    )


def test_register_candidate_writes_row_and_log(db_session):
    row = _register(db_session, version=1, mae=0.5)
    assert row.status == ModelStatus.CANDIDATE.value
    assert row.holdout_mae == pytest.approx(0.5)

    logs = db_session.query(MlopsLog).all()
    assert len(logs) == 1
    assert logs[0].event_type == MlopsEventType.TRAIN.value
    assert logs[0].candidate_version == 1


def test_promote_archives_previous_champion(db_session):
    _register(db_session, version=1, mae=1.0)
    promote_candidate(db_session, candidate_version=1, reason="bootstrap")
    champion_v1 = get_champion(db_session)
    assert champion_v1.version == 1
    assert champion_v1.status == ModelStatus.CHAMPION.value

    _register(db_session, version=2, mae=0.8)
    promote_candidate(db_session, candidate_version=2, reason="better mae")

    champion_v2 = get_champion(db_session)
    assert champion_v2.version == 2

    # v1 should now be ARCHIVED with archived_at populated
    db_session.refresh(champion_v1)
    assert champion_v1.status == ModelStatus.ARCHIVED.value
    assert champion_v1.archived_at is not None


def test_promote_unknown_version_raises(db_session):
    with pytest.raises(ValueError):
        promote_candidate(db_session, candidate_version=99, reason="missing")


def test_promote_already_champion_is_noop(db_session):
    _register(db_session, version=1)
    promote_candidate(db_session, candidate_version=1, reason="first")
    # Second promotion should return the existing champion without raising.
    result = promote_candidate(db_session, candidate_version=1, reason="second")
    assert result.version == 1
    # And no extra PROMOTE log entry is created.
    promote_logs = (
        db_session.query(MlopsLog)
        .filter(MlopsLog.event_type == MlopsEventType.PROMOTE.value)
        .all()
    )
    assert len(promote_logs) == 1


def test_reject_candidate_archives_without_promotion(db_session):
    _register(db_session, version=1)
    reject_candidate(db_session, candidate_version=1, reason="failed validation")
    assert get_champion(db_session) is None
    row = db_session.query(ModelRegistry).filter_by(version=1).first()
    assert row.status == ModelStatus.ARCHIVED.value


def test_list_helpers(db_session):
    _register(db_session, version=1)
    _register(db_session, version=2)
    _register(db_session, version=3)

    assert list_versions(db_session) == [1, 2, 3]
    all_rows = list_all(db_session)
    assert len(all_rows) == 3
    assert get_latest_candidate(db_session).version == 3


def test_log_event_writes_audit_row(db_session):
    log_event(
        db_session,
        event_type=MlopsEventType.BACKTEST,
        payload={"mae": 1.23},
        message="backtest ran",
    )
    logs = db_session.query(MlopsLog).all()
    assert len(logs) == 1
    assert logs[0].event_type == MlopsEventType.BACKTEST.value
    assert "mae" in (logs[0].payload or "")
