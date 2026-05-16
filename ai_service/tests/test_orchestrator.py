"""Integration tests for ``ml/orchestrator.py`` and the
``POST /ai/retrain`` + ``POST /ai/backtest`` endpoints.

The orchestrator wires together the trainer, registry, validation gate and
MLOps logging — these tests exercise the complete cold-start path
(first ever training -> auto-promote) and the warm-start path (champion
exists -> validation gate decides).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.db.models import MlopsEventType, MlopsLog, ModelStatus
from app.main import app
from app.ml.orchestrator import run_retrain
from app.ml.registry import get_champion, list_versions


@pytest.fixture(autouse=True)
def _disable_scheduler(monkeypatch):
    """The scheduler is not relevant for these tests and would spin up real
    APScheduler threads. Force it off via the env var the lifespan reads."""
    monkeypatch.setenv("SCHEDULER_ENABLED", "false")


@pytest.fixture
def patched_data_loader(monkeypatch, synthetic_sales):
    """Have the orchestrator + validation gate see the synthetic fixture."""
    from app.pipeline.data_loader import DataSource, LoadResult

    def _fake_load(*_a, **_kw):
        return LoadResult(
            df=synthetic_sales.copy(),
            source=DataSource.SYNTHETIC,
            rows=len(synthetic_sales),
            description="test fixture",
        )

    import app.ml.orchestrator as orch_module
    import app.ml.validation as val_module
    import app.api.predictions as pred_module

    monkeypatch.setattr(orch_module, "load_training_data", _fake_load)
    monkeypatch.setattr(val_module, "load_training_data", _fake_load)
    monkeypatch.setattr(pred_module, "load_training_data", _fake_load)


@pytest.fixture
def model_dir(tmp_path, monkeypatch):
    """Send all trained artifacts into the per-test tmp dir."""
    target = tmp_path / "models"
    target.mkdir()
    import app.ml.orchestrator as orch_module

    monkeypatch.setattr(orch_module.settings, "MODEL_DIR", str(target))
    return target


# ---------------------------------------------------------------------------
# Direct orchestrator tests
# ---------------------------------------------------------------------------


def test_orchestrator_cold_start_auto_promotes(
    db_session, patched_data_loader, model_dir
):
    assert get_champion(db_session) is None

    outcome = run_retrain(db_session, reason="test.cold_start")
    assert outcome.promoted is True
    assert outcome.final_status == "champion"
    assert outcome.candidate_version == 1
    assert outcome.validation.decision == "PROMOTE_COLD_START"

    champion = get_champion(db_session)
    assert champion is not None
    assert champion.version == 1
    assert champion.status == ModelStatus.CHAMPION.value


def test_orchestrator_logs_train_validate_promote_events(
    db_session, patched_data_loader, model_dir
):
    run_retrain(db_session, reason="test.cold_start")

    log_types = {
        row.event_type
        for row in db_session.query(MlopsLog).all()
    }
    assert MlopsEventType.TRAIN.value in log_types
    assert MlopsEventType.VALIDATE.value in log_types
    assert MlopsEventType.PROMOTE.value in log_types


def test_orchestrator_second_run_either_promotes_or_rejects(
    db_session, patched_data_loader, model_dir
):
    """After a cold-start champion exists, a second retrain on the SAME data
    should go through the validation gate. Same data -> tiny/no improvement
    -> reject."""
    first = run_retrain(db_session, reason="test.cold_start")
    assert first.promoted

    second = run_retrain(db_session, reason="test.no_change")
    # With identical training data, validation should reject the new candidate.
    assert second.promoted is False
    assert second.final_status == "rejected"
    assert second.validation.decision == "REJECT"

    # Champion should still be v1
    champion = get_champion(db_session)
    assert champion.version == 1
    assert list_versions(db_session) == [1, 2]


# ---------------------------------------------------------------------------
# Endpoint integration
# ---------------------------------------------------------------------------


@pytest.fixture
def client(patch_app_engine):
    return TestClient(app)


def test_retrain_endpoint_runs_full_cycle(
    client, patched_data_loader, model_dir, db_session
):
    resp = client.post("/ai/retrain", json={"reason": "endpoint_test"})
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert body["candidate_version"] == 1
    assert body["status"] == "champion"
    assert body["promoted"] is True
    assert "MAE" in body["message"] or "PROMOTE" in body["message"].upper() or body["training_rows"] > 0


def test_retrain_endpoint_rejects_invalid_source(client):
    resp = client.post("/ai/retrain", json={"source": "not-a-real-source"})
    assert resp.status_code == 422  # Pydantic validation error


def test_backtest_endpoint_returns_summary(
    client, patched_data_loader, db_session
):
    resp = client.post("/ai/backtest", params={"lookback_days": 7})
    assert resp.status_code == 200
    body = resp.json()
    # No forecasts seeded -> 0 rows scored, mean_abs_error is None
    assert body["rows_scored"] == 0
    assert body["mean_abs_error"] is None


def test_backtest_endpoint_rejects_invalid_lookback(client):
    resp = client.post("/ai/backtest", params={"lookback_days": 0})
    assert resp.status_code == 400
