"""Tests for the AI proxy router (Block D.15).

Strategy: we do NOT spin up the real AI service in tests. Instead we
monkey-patch ``app.api.v1.ai._proxy_request`` to return canned responses and
assert that:

1. The proxy converts AI-side ``store_ref`` / ``product_ref`` into
   ``store_name`` / ``product_name`` when those refs are valid backend UUIDs.
2. Kaggle-style refs (``S1`` / ``P1``) pass through unchanged with
   ``None`` labels (graceful degradation, no 500s).
3. RBAC matches the documented permission matrix — anyone outside the
   allowed role list gets a 403.
4. Connection / upstream errors are translated to predictable HTTP statuses.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from unittest.mock import patch

import httpx
import pytest

from app.core.constants import RoleEnum
from app.core.security import create_access_token
from app.models.product import Product
from app.models.store import Store
from app.models.user import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _auth_headers(user_id) -> dict:
    return {"Authorization": f"Bearer {create_access_token({'sub': str(user_id)})}"}


def _seed_user(db, *, role: RoleEnum, username: str, store_id=None) -> User:
    user = User(
        username=username,
        email=f"{username}@example.com",
        password_hash="hashed",
        full_name=username.replace("_", " ").title(),
        role=role,
        is_active=True,
        store_id=store_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _seed_store(db, name: str = "Main Store") -> Store:
    s = Store(name=name, location="Addis", is_active=True)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _seed_product(db, *, name: str = "Whole Wheat Bread", sku: str = "WWB-1") -> Product:
    p = Product(name=name, sku=sku, sale_price="10.00", is_active=True)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def _patch_proxy(return_value: Any):
    """Helper to stub the upstream call to the AI service."""
    return patch("app.api.v1.ai._proxy_request", return_value=return_value)


# ---------------------------------------------------------------------------
# /predict  ── enrichment + RBAC
# ---------------------------------------------------------------------------


def test_predict_enriches_uuid_refs_with_real_names(client, db_session):
    store = _seed_store(db_session, name="Bole Branch")
    product = _seed_product(db_session, name="Croissant", sku="CR-1")
    owner = _seed_user(db_session, role=RoleEnum.OWNER, username="owner_predict")

    fake_ai_response = {
        "model_version": 5,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "horizon_days": 1,
        "items": [
            {
                "store_ref": str(store.id),
                "product_ref": str(product.id),
                "target_date": date.today().isoformat(),
                "predicted_qty": 12.5,
                "horizon": "day",
            },
            {
                # Kaggle warm-start ref — no UUID, label stays None
                "store_ref": "S1",
                "product_ref": "P1",
                "target_date": date.today().isoformat(),
                "predicted_qty": 8.0,
                "horizon": "day",
            },
        ],
    }

    with _patch_proxy(fake_ai_response):
        resp = client.post(
            "/api/v1/ai/predict",
            json={"days": 1},
            headers=_auth_headers(owner.id),
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["model_version"] == 5
    assert len(body["items"]) == 2

    uuid_item = next(i for i in body["items"] if i["store_ref"] == str(store.id))
    assert uuid_item["store_name"] == "Bole Branch"
    assert uuid_item["product_name"] == "Croissant"

    kaggle_item = next(i for i in body["items"] if i["store_ref"] == "S1")
    assert kaggle_item["store_name"] is None
    assert kaggle_item["product_name"] is None


def test_predict_forbidden_for_delivery_staff(client, db_session):
    user = _seed_user(db_session, role=RoleEnum.DELIVERY_STAFF, username="driver")
    resp = client.post(
        "/api/v1/ai/predict",
        json={"days": 1},
        headers=_auth_headers(user.id),
    )
    assert resp.status_code == 403


def test_predict_requires_auth(client):
    resp = client.post("/api/v1/ai/predict", json={"days": 1})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# /forecasts  ── enrichment + RBAC
# ---------------------------------------------------------------------------


def test_forecasts_listing_enriches_and_passes_filters(client, db_session):
    product = _seed_product(db_session, name="Sourdough", sku="SD-1")
    owner = _seed_user(db_session, role=RoleEnum.OWNER, username="owner_forecasts")

    fake_response = {
        "items": [
            {
                "id": "abc-123",
                "model_version": 1,
                "store_ref": "S1",
                "product_ref": str(product.id),
                "target_date": date.today().isoformat(),
                "horizon": "day",
                "predicted_qty": 10.0,
                "actual_qty": 11.0,
                "abs_error": 1.0,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
        ],
        "total": 1,
    }

    with patch("app.api.v1.ai._proxy_request", return_value=fake_response) as mock:
        resp = client.get(
            "/api/v1/ai/forecasts?limit=10&product_id=" + str(product.id),
            headers=_auth_headers(owner.id),
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["product_name"] == "Sourdough"
    assert body["items"][0]["store_name"] is None
    # Verify the proxy translated store_id -> store_ref / product_id -> product_ref
    call_args = mock.call_args
    assert call_args.kwargs["params"]["product_ref"] == str(product.id)
    assert call_args.kwargs["params"]["limit"] == 10


# ---------------------------------------------------------------------------
# /optimal-batches  ── RBAC narrower than /predict
# ---------------------------------------------------------------------------


def test_optimal_batches_allows_production_manager(client, db_session):
    product = _seed_product(db_session, name="Bagel", sku="BG-1")
    pm = _seed_user(db_session, role=RoleEnum.PRODUCTION_MANAGER, username="prod_mgr")

    fake_response = {
        "model_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "horizon_days": 1,
        "items": [
            {
                "product_ref": str(product.id),
                "target_date": date.today().isoformat(),
                "forecasted_demand": 22.5,
                "suggested_batch_qty": 25,
                "confidence": "high",
            }
        ],
    }

    with _patch_proxy(fake_response):
        resp = client.get(
            "/api/v1/ai/optimal-batches?days=1",
            headers=_auth_headers(pm.id),
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["items"][0]["product_name"] == "Bagel"
    assert body["items"][0]["suggested_batch_qty"] == 25


def test_optimal_batches_forbidden_for_finance_manager(client, db_session):
    finance = _seed_user(db_session, role=RoleEnum.FINANCE_MANAGER, username="fin_mgr")
    resp = client.get(
        "/api/v1/ai/optimal-batches?days=1",
        headers=_auth_headers(finance.id),
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# /models  ── admin/owner/production_manager only
# ---------------------------------------------------------------------------


def test_models_listing_allows_admin(client, db_session):
    admin = _seed_user(db_session, role=RoleEnum.ADMIN, username="admin_models")
    fake_response = {
        "champion_version": 2,
        "items": [
            {
                "id": "model-uuid",
                "version": 2,
                "status": "champion",
                "trained_at": datetime.now(timezone.utc).isoformat(),
                "training_rows_used": 50000,
                "training_source": "kaggle",
                "holdout_mae": 4.5,
                "model_path": "trained_models/v2.joblib",
                "promoted_at": datetime.now(timezone.utc).isoformat(),
                "archived_at": None,
                "notes": "test",
            }
        ],
    }
    with _patch_proxy(fake_response):
        resp = client.get("/api/v1/ai/models", headers=_auth_headers(admin.id))
    assert resp.status_code == 200
    assert resp.json()["champion_version"] == 2


def test_models_forbidden_for_store_manager(client, db_session):
    sm = _seed_user(db_session, role=RoleEnum.STORE_MANAGER, username="store_mgr")
    resp = client.get("/api/v1/ai/models", headers=_auth_headers(sm.id))
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# /retrain  ── admin/owner only
# ---------------------------------------------------------------------------


def test_retrain_allows_owner(client, db_session):
    owner = _seed_user(db_session, role=RoleEnum.OWNER, username="owner_retrain")
    fake_response = {
        "candidate_version": 3,
        "status": "champion",
        "holdout_mae": 4.1,
        "training_rows": 60000,
        "training_source": "kaggle",
        "promoted": True,
        "message": "Promoted v3.",
    }
    with _patch_proxy(fake_response):
        resp = client.post(
            "/api/v1/ai/retrain",
            json={"reason": "test"},
            headers=_auth_headers(owner.id),
        )
    assert resp.status_code == 200
    assert resp.json()["promoted"] is True


def test_retrain_forbidden_for_production_manager(client, db_session):
    """Production manager can VIEW models but not trigger MLOps actions."""
    pm = _seed_user(db_session, role=RoleEnum.PRODUCTION_MANAGER, username="pm_no_retrain")
    resp = client.post(
        "/api/v1/ai/retrain",
        json={"reason": "should_fail"},
        headers=_auth_headers(pm.id),
    )
    assert resp.status_code == 403


def test_retrain_rejects_invalid_source(client, db_session):
    owner = _seed_user(db_session, role=RoleEnum.OWNER, username="owner_bad_source")
    resp = client.post(
        "/api/v1/ai/retrain",
        json={"source": "wikipedia"},
        headers=_auth_headers(owner.id),
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------


def test_ai_service_down_returns_503(client, db_session):
    owner = _seed_user(db_session, role=RoleEnum.OWNER, username="owner_down")

    with patch("httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.request.side_effect = (
            httpx.ConnectError("Connection refused")
        )
        resp = client.post(
            "/api/v1/ai/predict",
            json={"days": 1},
            headers=_auth_headers(owner.id),
        )

    assert resp.status_code == 503
    assert "AI service" in resp.json()["detail"]


def test_ai_service_timeout_returns_504(client, db_session):
    owner = _seed_user(db_session, role=RoleEnum.OWNER, username="owner_timeout")
    with patch("httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.request.side_effect = (
            httpx.ReadTimeout("Too slow")
        )
        resp = client.post(
            "/api/v1/ai/predict",
            json={"days": 1},
            headers=_auth_headers(owner.id),
        )
    assert resp.status_code == 504


def test_ai_4xx_bubbles_up(client, db_session):
    """An AI service 503 (no champion yet) should be passed through unchanged."""
    owner = _seed_user(db_session, role=RoleEnum.OWNER, username="owner_4xx")

    class _MockResponse:
        status_code = 503
        text = '{"detail": "No CHAMPION model registered yet."}'

        def json(self):
            return {"detail": "No CHAMPION model registered yet."}

    with patch("httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.request.return_value = (
            _MockResponse()
        )
        resp = client.post(
            "/api/v1/ai/predict",
            json={"days": 1},
            headers=_auth_headers(owner.id),
        )

    assert resp.status_code == 503
    assert "CHAMPION" in resp.json()["detail"]
