"""End-to-end tests for the prediction + models endpoints.

We use FastAPI's ``TestClient`` against the real app, but with two things swapped:

1. The DB engine + ``SessionLocal`` are pointed at an in-memory SQLite
   schema (via the ``patch_app_engine`` fixture).
2. The data loader is monkey-patched to return the synthetic fixture so we
   don't depend on the Kaggle CSV being present.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.db.models import Forecast, ForecastActual
from app.main import app
from app.ml.registry import promote_candidate, register_candidate


@pytest.fixture
def client(patch_app_engine):
    return TestClient(app)


@pytest.fixture
def bootstrapped_champion(
    patch_app_engine,
    db_session,
    trained_model,
    monkeypatch,
    synthetic_sales,
):
    """Register the trained model as CHAMPION + stub the data loader so the
    API can find history without touching the shared DB."""
    candidate = register_candidate(
        db_session,
        version=1,
        model_path=str(trained_model.model_path),
        holdout_mae=trained_model.holdout_mae,
        training_rows_used=trained_model.training_rows,
        training_source="synthetic",
        feature_columns=trained_model.state.feature_columns,
    )
    promote_candidate(db_session, candidate_version=candidate.version, reason="bootstrap")

    # Patch the data loader used by the prediction endpoints. The endpoint
    # imports the symbol locally, so patch where it's *used*.
    import app.api.predictions as predictions_module
    from app.pipeline.data_loader import DataSource, LoadResult

    def _fake_load(*_args, **_kwargs):
        return LoadResult(
            df=synthetic_sales.copy(),
            source=DataSource.SYNTHETIC,
            rows=len(synthetic_sales),
            description="test fixture",
        )

    monkeypatch.setattr(predictions_module, "load_training_data", _fake_load)
    yield candidate


# ---------------------------------------------------------------------------
# /ai/predict
# ---------------------------------------------------------------------------


def test_predict_requires_champion(client, db_session):
    """Without a registered model the endpoint should return 503."""
    resp = client.post("/ai/predict", json={"days": 1})
    assert resp.status_code == 503
    assert "CHAMPION" in resp.json()["detail"]


def test_predict_returns_forecasts_and_archives_them(client, bootstrapped_champion, db_session):
    resp = client.post("/ai/predict", json={"days": 1})
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert body["model_version"] == bootstrapped_champion.version
    assert body["horizon_days"] == 1
    assert len(body["items"]) > 0
    for item in body["items"]:
        assert item["predicted_qty"] >= 0
        assert item["horizon"] == "day"

    # The endpoint must have persisted those forecasts.
    persisted = db_session.query(Forecast).count()
    assert persisted == len(body["items"])


def test_predict_horizon_label_switches_to_week_for_7_days(client, bootstrapped_champion):
    resp = client.post("/ai/predict", json={"days": 7})
    assert resp.status_code == 200
    body = resp.json()
    assert body["horizon_days"] == 7
    assert all(item["horizon"] == "week" for item in body["items"])


def test_predict_rejects_partial_pair(client, bootstrapped_champion):
    resp = client.post("/ai/predict", json={"store_ref": "S1", "days": 1})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# /ai/forecasts
# ---------------------------------------------------------------------------


def test_forecasts_listing_filters_and_paginates(client, bootstrapped_champion, db_session):
    # Seed a couple of forecasts manually
    base = date.today()
    forecasts = [
        Forecast(
            id=uuid.uuid4(),
            model_version=1,
            store_ref="S1",
            product_ref="P1",
            target_date=base + timedelta(days=i),
            horizon="day",
            predicted_qty=10.0 + i,
        )
        for i in range(5)
    ]
    db_session.bulk_save_objects(forecasts)
    db_session.commit()

    resp = client.get("/ai/forecasts", params={"limit": 3})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 5
    assert len(body["items"]) == 3


def test_forecasts_listing_joins_actuals(client, bootstrapped_champion, db_session):
    fc = Forecast(
        id=uuid.uuid4(),
        model_version=1,
        store_ref="S1",
        product_ref="P1",
        target_date=date.today(),
        horizon="day",
        predicted_qty=10.0,
    )
    db_session.add(fc)
    db_session.flush()
    db_session.add(
        ForecastActual(
            id=uuid.uuid4(),
            forecast_id=fc.id,
            actual_qty=12.0,
            abs_error=2.0,
        )
    )
    db_session.commit()

    resp = client.get("/ai/forecasts", params={"product_ref": "P1"})
    assert resp.status_code == 200
    items = resp.json()["items"]
    matched = [i for i in items if i["id"] == str(fc.id)]
    assert len(matched) == 1
    assert matched[0]["actual_qty"] == 12.0
    assert matched[0]["abs_error"] == 2.0


# ---------------------------------------------------------------------------
# /ai/optimal-batches
# ---------------------------------------------------------------------------


def test_optimal_batches_aggregates_across_stores(client, bootstrapped_champion):
    resp = client.get("/ai/optimal-batches", params={"days": 1})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["horizon_days"] == 1
    products_in_resp = {item["product_ref"] for item in body["items"]}
    # 4 products in the synthetic fixture
    assert products_in_resp == {"P1", "P2", "P3", "P4"}
    # Every suggestion must be an int >= 0
    for item in body["items"]:
        assert isinstance(item["suggested_batch_qty"], int)
        assert item["suggested_batch_qty"] >= 0
        assert item["confidence"] in {"low", "medium", "high"}


def test_optimal_batches_filters_by_store(client, bootstrapped_champion):
    resp = client.get("/ai/optimal-batches", params={"store_ref": "S1", "days": 2})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 4 * 2  # 4 products x 2 days


def test_optimal_batches_404s_for_unknown_store(client, bootstrapped_champion):
    resp = client.get("/ai/optimal-batches", params={"store_ref": "S999", "days": 1})
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# /ai/models
# ---------------------------------------------------------------------------


def test_models_listing_returns_champion(client, bootstrapped_champion):
    resp = client.get("/ai/models")
    assert resp.status_code == 200
    body = resp.json()
    assert body["champion_version"] == bootstrapped_champion.version
    assert any(m["status"] == "champion" for m in body["items"])


def test_models_performance_requires_actuals(client, bootstrapped_champion, db_session):
    fc = Forecast(
        id=uuid.uuid4(),
        model_version=1,
        store_ref="S1",
        product_ref="P1",
        target_date=date.today() - timedelta(days=1),
        horizon="day",
        predicted_qty=10.0,
    )
    db_session.add(fc)
    db_session.flush()
    db_session.add(
        ForecastActual(
            id=uuid.uuid4(),
            forecast_id=fc.id,
            actual_qty=11.5,
            abs_error=1.5,
        )
    )
    db_session.commit()

    resp = client.get("/ai/models/performance", params={"window_days": 7})
    assert resp.status_code == 200
    body = resp.json()
    assert body["model_version"] == bootstrapped_champion.version
    assert body["overall_mae"] == pytest.approx(1.5, abs=0.01)
    assert len(body["daily"]) == 1
