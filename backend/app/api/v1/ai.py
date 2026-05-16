"""Backend proxy for the AI forecasting microservice (Phases 11 + 12 wiring).

Why a proxy and not direct frontend → AI calls?
  - **Single auth boundary.** All frontend requests carry the backend's JWT;
    the AI service stays unauthenticated and bound to localhost.
  - **RBAC at the gateway.** Role checks happen here using the same
    ``require_role`` dependency the rest of the platform uses, so AI access
    follows the same permission matrix as Reports / Production / etc.
  - **Identifier enrichment.** The AI service stores ``store_ref`` /
    ``product_ref`` as opaque strings (live UUIDs OR ``S{n}``/``P{n}`` for
    Kaggle warm-start). The proxy joins them to ``Store`` / ``Product`` rows
    so the frontend can display human-readable names without a second round-trip.
  - **Failure isolation.** AI downtime (port closed, model not registered)
    surfaces as predictable HTTP errors rather than CORS or network failures
    on the frontend.

Permission matrix (see role list in ``backend/app/core/constants.py``):

  POST /predict           — owner, finance_manager, production_manager, store_manager
  GET  /forecasts         — owner, finance_manager, production_manager, store_manager
  GET  /optimal-batches   — owner, production_manager  (batch planning)
  GET  /models            — admin, owner, production_manager
  GET  /models/performance— admin, owner, production_manager
  POST /retrain           — admin, owner            (manual MLOps trigger)
  POST /backtest          — admin, owner            (manual replay)
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.config import settings
from app.core.constants import RoleEnum
from app.database import get_db
from app.models.product import Product
from app.models.store import Store
from app.models.user import User
from app.schemas.ai import (
    BacktestResponse,
    ForecastItem,
    ForecastListItem,
    ForecastListResponse,
    ModelPerformanceResponse,
    ModelRegistryListResponse,
    OptimalBatchItem,
    OptimalBatchResponse,
    PredictRequest,
    PredictResponse,
    RetrainRequest,
    RetrainResponse,
)

router = APIRouter()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# httpx client + error mapping
# ---------------------------------------------------------------------------


# Network timeouts that match the slowest operation we'd ever proxy
# (retrain on a full Kaggle dataset = ~5 s). We deliberately don't share a
# module-level Client because that complicates testing — per-request clients
# are fine for our throughput.
PROXY_TIMEOUT = httpx.Timeout(connect=5.0, read=300.0, write=10.0, pool=10.0)


def _ai_url(path: str) -> str:
    base = settings.AI_SERVICE_URL.rstrip("/")
    return f"{base}{path}"


def _proxy_request(
    method: str,
    path: str,
    *,
    params: Optional[dict] = None,
    json: Optional[dict] = None,
) -> Any:
    """Forward a request to the AI service and translate any failure into the
    most appropriate HTTPException for the calling frontend.

    Status code translation:
      - 200..299  -> returns parsed JSON
      - 4xx       -> bubbled up as-is (validation errors, invalid requests)
      - 503       -> bubbled up (e.g. "no CHAMPION registered yet")
      - 5xx other -> mapped to 502 "AI service error"
      - ConnectError / Timeout -> mapped to 503 with a hint
    """
    url = _ai_url(path)
    try:
        with httpx.Client(timeout=PROXY_TIMEOUT) as client:
            response = client.request(method, url, params=params, json=json)
    except httpx.ConnectError as exc:
        logger.warning("AI service unreachable at %s: %s", url, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "AI service is not running. Start it with: "
                "`cd ai_service && python -m uvicorn app.main:app --port 8001`"
            ),
        )
    except httpx.TimeoutException as exc:
        logger.warning("AI service timeout for %s %s: %s", method, url, exc)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="AI service did not respond in time.",
        )

    if 200 <= response.status_code < 300:
        try:
            return response.json()
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="AI service returned a non-JSON response.",
            )

    # Best-effort detail extraction
    detail: Any
    try:
        body = response.json()
        detail = body.get("detail", body) if isinstance(body, dict) else body
    except ValueError:
        detail = response.text or f"AI service responded {response.status_code}"

    if 400 <= response.status_code < 500:
        raise HTTPException(status_code=response.status_code, detail=detail)

    # Bubble 503 / 504 through unchanged — these are semantic "AI is busy /
    # not ready" signals the frontend already knows how to render. Only true
    # 500-class crashes get flattened to 502.
    if response.status_code in {
        status.HTTP_503_SERVICE_UNAVAILABLE,
        status.HTTP_504_GATEWAY_TIMEOUT,
    }:
        raise HTTPException(status_code=response.status_code, detail=detail)

    logger.error(
        "AI service error %d on %s %s: %s",
        response.status_code,
        method,
        url,
        detail,
    )
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"AI service error: {detail}",
    )


# ---------------------------------------------------------------------------
# Store / Product ref resolution
# ---------------------------------------------------------------------------


def _coerce_uuid(value: str) -> Optional[UUID]:
    try:
        return UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


def _build_label_lookup(
    db: Session, store_refs: set[str], product_refs: set[str]
) -> tuple[dict[str, str], dict[str, str]]:
    """Returns ``(store_labels, product_labels)`` indexed by the original
    string ref. Refs that don't parse as UUIDs (Kaggle ``S1`` / ``P1``) are
    omitted from the lookup so the proxy falls back to the raw ref in the
    response."""
    store_uuids = {ref: _coerce_uuid(ref) for ref in store_refs}
    product_uuids = {ref: _coerce_uuid(ref) for ref in product_refs}

    valid_store_uuids = [u for u in store_uuids.values() if u is not None]
    valid_product_uuids = [u for u in product_uuids.values() if u is not None]

    store_label: dict[str, str] = {}
    if valid_store_uuids:
        rows = db.query(Store.id, Store.name).filter(Store.id.in_(valid_store_uuids)).all()
        uuid_to_name = {str(r.id): r.name for r in rows}
        for ref, parsed in store_uuids.items():
            if parsed is not None and str(parsed) in uuid_to_name:
                store_label[ref] = uuid_to_name[str(parsed)]

    product_label: dict[str, str] = {}
    if valid_product_uuids:
        rows = db.query(Product.id, Product.name).filter(Product.id.in_(valid_product_uuids)).all()
        uuid_to_name = {str(r.id): r.name for r in rows}
        for ref, parsed in product_uuids.items():
            if parsed is not None and str(parsed) in uuid_to_name:
                product_label[ref] = uuid_to_name[str(parsed)]

    return store_label, product_label


# ---------------------------------------------------------------------------
# Dependency aliases (compact RBAC declarations)
# ---------------------------------------------------------------------------

_READ_ROLES = (
    RoleEnum.OWNER,
    RoleEnum.FINANCE_MANAGER,
    RoleEnum.PRODUCTION_MANAGER,
    RoleEnum.STORE_MANAGER,
)
_PRODUCTION_ROLES = (RoleEnum.OWNER, RoleEnum.PRODUCTION_MANAGER)
_MODEL_VIEW_ROLES = (RoleEnum.ADMIN, RoleEnum.OWNER, RoleEnum.PRODUCTION_MANAGER)
_MLOPS_ROLES = (RoleEnum.ADMIN, RoleEnum.OWNER)


# ---------------------------------------------------------------------------
# POST /api/v1/ai/predict
# ---------------------------------------------------------------------------


@router.post("/predict", response_model=PredictResponse)
def predict(
    payload: PredictRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*_READ_ROLES)),
) -> PredictResponse:
    """Proxy ``POST /ai/predict`` and enrich the response with store/product
    names so the frontend doesn't need a second round-trip."""
    body = _proxy_request(
        "POST",
        "/ai/predict",
        json={
            "store_ref": payload.store_id,
            "product_ref": payload.product_id,
            "target_date": (
                payload.target_date.isoformat() if payload.target_date else None
            ),
            "days": payload.days,
        },
    )

    items_raw = body.get("items", [])
    store_refs = {item["store_ref"] for item in items_raw}
    product_refs = {item["product_ref"] for item in items_raw}
    store_labels, product_labels = _build_label_lookup(db, store_refs, product_refs)

    return PredictResponse(
        model_version=body["model_version"],
        generated_at=body["generated_at"],
        horizon_days=body["horizon_days"],
        items=[
            ForecastItem(
                store_ref=item["store_ref"],
                product_ref=item["product_ref"],
                store_name=store_labels.get(item["store_ref"]),
                product_name=product_labels.get(item["product_ref"]),
                target_date=item["target_date"],
                predicted_qty=item["predicted_qty"],
                horizon=item.get("horizon", "day"),
            )
            for item in items_raw
        ],
    )


# ---------------------------------------------------------------------------
# GET /api/v1/ai/forecasts
# ---------------------------------------------------------------------------


@router.get("/forecasts", response_model=ForecastListResponse)
def list_forecasts(
    db: Session = Depends(get_db),
    model_version: Optional[int] = Query(default=None),
    store_id: Optional[str] = Query(default=None),
    product_id: Optional[str] = Query(default=None),
    target_date_from: Optional[str] = Query(default=None),
    target_date_to: Optional[str] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    _user: User = Depends(require_role(*_READ_ROLES)),
) -> ForecastListResponse:
    """Proxy ``GET /ai/forecasts`` with the same enrichment as ``/predict``."""
    body = _proxy_request(
        "GET",
        "/ai/forecasts",
        params={
            k: v
            for k, v in {
                "model_version": model_version,
                "store_ref": store_id,
                "product_ref": product_id,
                "target_date_from": target_date_from,
                "target_date_to": target_date_to,
                "limit": limit,
                "offset": offset,
            }.items()
            if v is not None
        },
    )

    items_raw = body.get("items", [])
    store_refs = {item["store_ref"] for item in items_raw}
    product_refs = {item["product_ref"] for item in items_raw}
    store_labels, product_labels = _build_label_lookup(db, store_refs, product_refs)

    return ForecastListResponse(
        items=[
            ForecastListItem(
                id=item["id"],
                model_version=item["model_version"],
                store_ref=item["store_ref"],
                product_ref=item["product_ref"],
                store_name=store_labels.get(item["store_ref"]),
                product_name=product_labels.get(item["product_ref"]),
                target_date=item["target_date"],
                horizon=item["horizon"],
                predicted_qty=item["predicted_qty"],
                actual_qty=item.get("actual_qty"),
                abs_error=item.get("abs_error"),
                generated_at=item["generated_at"],
            )
            for item in items_raw
        ],
        total=body.get("total", len(items_raw)),
    )


# ---------------------------------------------------------------------------
# GET /api/v1/ai/optimal-batches
# ---------------------------------------------------------------------------


@router.get("/optimal-batches", response_model=OptimalBatchResponse)
def optimal_batches(
    db: Session = Depends(get_db),
    target_date: Optional[str] = Query(default=None),
    days: int = Query(default=1, ge=1, le=7),
    store_id: Optional[str] = Query(default=None),
    _user: User = Depends(require_role(*_PRODUCTION_ROLES)),
) -> OptimalBatchResponse:
    """Proxy ``GET /ai/optimal-batches``. Aggregates per-product across all
    stores by default; pass ``store_id`` to scope to one store."""
    body = _proxy_request(
        "GET",
        "/ai/optimal-batches",
        params={
            k: v
            for k, v in {
                "target_date": target_date,
                "days": days,
                "store_ref": store_id,
            }.items()
            if v is not None
        },
    )

    items_raw = body.get("items", [])
    _, product_labels = _build_label_lookup(
        db, set(), {item["product_ref"] for item in items_raw}
    )

    return OptimalBatchResponse(
        model_version=body["model_version"],
        generated_at=body["generated_at"],
        horizon_days=body["horizon_days"],
        items=[
            OptimalBatchItem(
                product_ref=item["product_ref"],
                product_name=product_labels.get(item["product_ref"]),
                target_date=item["target_date"],
                forecasted_demand=item["forecasted_demand"],
                suggested_batch_qty=item["suggested_batch_qty"],
                confidence=item.get("confidence", "medium"),
            )
            for item in items_raw
        ],
    )


# ---------------------------------------------------------------------------
# GET /api/v1/ai/models
# ---------------------------------------------------------------------------


@router.get("/models", response_model=ModelRegistryListResponse)
def list_models(
    _user: User = Depends(require_role(*_MODEL_VIEW_ROLES)),
) -> ModelRegistryListResponse:
    body = _proxy_request("GET", "/ai/models")
    return ModelRegistryListResponse(**body)


# ---------------------------------------------------------------------------
# GET /api/v1/ai/models/performance
# ---------------------------------------------------------------------------


@router.get("/models/performance", response_model=ModelPerformanceResponse)
def model_performance(
    version: Optional[int] = Query(default=None),
    window_days: int = Query(default=14, ge=1, le=90),
    _user: User = Depends(require_role(*_MODEL_VIEW_ROLES)),
) -> ModelPerformanceResponse:
    params = {"window_days": window_days}
    if version is not None:
        params["version"] = version
    body = _proxy_request("GET", "/ai/models/performance", params=params)
    return ModelPerformanceResponse(**body)


# ---------------------------------------------------------------------------
# POST /api/v1/ai/retrain
# ---------------------------------------------------------------------------


@router.post("/retrain", response_model=RetrainResponse)
def retrain(
    payload: RetrainRequest = RetrainRequest(),
    _user: User = Depends(require_role(*_MLOPS_ROLES)),
) -> RetrainResponse:
    """Admin/owner-only manual retrain trigger. Returns the full outcome so
    the UI can display the validation verdict (PROMOTE / REJECT / cold-start)."""
    body = _proxy_request(
        "POST",
        "/ai/retrain",
        json={"source": payload.source, "reason": payload.reason},
    )
    return RetrainResponse(**body)


# ---------------------------------------------------------------------------
# POST /api/v1/ai/backtest
# ---------------------------------------------------------------------------


@router.post("/backtest", response_model=BacktestResponse)
def backtest(
    lookback_days: int = Query(default=1, ge=1, le=30),
    target_date: Optional[str] = Query(default=None),
    _user: User = Depends(require_role(*_MLOPS_ROLES)),
) -> BacktestResponse:
    params: dict[str, Any] = {"lookback_days": lookback_days}
    if target_date:
        params["target_date"] = target_date
    body = _proxy_request("POST", "/ai/backtest", params=params)
    return BacktestResponse(**body)
