"""Real prediction endpoints.

- ``POST /ai/predict`` — ad-hoc forecast for a (store, product) on a single
  day or a multi-day horizon. Persists each prediction to ``ai_forecasts`` so
  the daily backtest job can score it later.
- ``GET  /ai/forecasts`` — list archived forecasts with optional matched
  actuals; the main UI uses this for the accuracy timeline.
- ``GET  /ai/optimal-batches`` — derived view that ceil-rounds the daily
  forecast into integer batch suggestions plus a safety-stock buffer; powers
  the "Suggested batches for next 24h" panel on the production page.
"""

from __future__ import annotations

import logging
import math
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.database import get_db
from app.db.models import (
    Forecast,
    ForecastActual,
    ForecastHorizon,
)
from app.ml.forecaster import ForecastPoint, load_forecaster
from app.ml.registry import get_champion
from app.pipeline.data_loader import load_training_data
from app.schemas.predictions import (
    ForecastItem,
    ForecastListItem,
    ForecastListResponse,
    OptimalBatchItem,
    OptimalBatchResponse,
    PredictRequest,
    PredictResponse,
)

router = APIRouter()
logger = logging.getLogger(__name__)


# Safety stock: production suggestions add this fraction on top of the raw
# forecast before ceiling. Tunable later — kept low so the demo doesn't look
# obviously inflated.
SAFETY_STOCK_FACTOR = 0.10


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_champion(db: Session):
    """Resolve the current CHAMPION or raise 503 if no model is registered."""
    champion = get_champion(db)
    if champion is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "No CHAMPION model registered yet. Run the bootstrap script: "
                "`python -m scripts.bootstrap_champion`"
            ),
        )
    return champion


def _load_recent_history(db: Session, *, lookback_days: int = 60) -> pd.DataFrame:
    """Loads enough recent data so lag-28 + rolling-28 features resolve."""
    load = load_training_data(db=db)
    df = load.df
    if df.empty:
        raise HTTPException(
            status_code=503,
            detail="No training data available to build inference history.",
        )
    df["date"] = pd.to_datetime(df["date"])
    cutoff = df["date"].max() - pd.Timedelta(days=lookback_days)
    return df[df["date"] >= cutoff].copy()


def _archive_forecasts(
    db: Session,
    *,
    model_version: int,
    horizon: str,
    points: list[ForecastPoint],
) -> None:
    """Bulk-insert every forecast into ``ai_forecasts``."""
    if not points:
        return
    rows = [
        Forecast(
            id=uuid.uuid4(),
            model_version=model_version,
            store_ref=p.store_ref,
            product_ref=p.product_ref,
            target_date=p.target_date,
            horizon=horizon,
            predicted_qty=float(p.predicted_qty),
            generated_at=datetime.now(timezone.utc),
        )
        for p in points
    ]
    db.bulk_save_objects(rows)
    db.commit()


# ---------------------------------------------------------------------------
# POST /ai/predict
# ---------------------------------------------------------------------------


@router.post("/predict", response_model=PredictResponse)
def predict_demand(
    payload: PredictRequest,
    db: Session = Depends(get_db),
) -> PredictResponse:
    """Forecast demand for one (store, product) or every combo in history.

    Behaviour:
    - ``days=1`` and both refs provided -> single point forecast.
    - ``days=N`` with refs -> N consecutive daily forecasts for that pair.
    - Refs omitted -> forecast every (store, product) combo present in the
      most recent training data, for ``days`` consecutive days.
    """
    champion = _require_champion(db)
    forecaster = load_forecaster(champion.model_path)

    history = _load_recent_history(db)
    start_date = payload.target_date or (date.today() + timedelta(days=1))

    if payload.store_ref and payload.product_ref:
        pairs = [(payload.store_ref, payload.product_ref)]
    elif payload.store_ref or payload.product_ref:
        raise HTTPException(
            status_code=400,
            detail="Provide both store_ref and product_ref, or neither.",
        )
    else:
        pairs = None  # forecaster will use every combo in history

    points = forecaster.predict_horizon(
        history,
        start_date=start_date,
        days=payload.days,
        pairs=pairs,
    )

    horizon_label = (
        ForecastHorizon.WEEK.value if payload.days >= 7 else ForecastHorizon.DAY.value
    )
    _archive_forecasts(
        db,
        model_version=champion.version,
        horizon=horizon_label,
        points=points,
    )

    return PredictResponse(
        model_version=champion.version,
        generated_at=datetime.now(timezone.utc),
        horizon_days=payload.days,
        items=[
            ForecastItem(
                store_ref=p.store_ref,
                product_ref=p.product_ref,
                target_date=p.target_date,
                predicted_qty=round(p.predicted_qty, 4),
                horizon=horizon_label,
            )
            for p in points
        ],
    )


# ---------------------------------------------------------------------------
# GET /ai/forecasts
# ---------------------------------------------------------------------------


@router.get("/forecasts", response_model=ForecastListResponse)
def list_forecasts(
    db: Session = Depends(get_db),
    model_version: Optional[int] = Query(default=None),
    store_ref: Optional[str] = Query(default=None),
    product_ref: Optional[str] = Query(default=None),
    target_date_from: Optional[date] = Query(default=None),
    target_date_to: Optional[date] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
) -> ForecastListResponse:
    """Paginated listing of archived forecasts joined with their matched
    actual (if the backtest job has filled one in)."""
    filters = []
    if model_version is not None:
        filters.append(Forecast.model_version == model_version)
    if store_ref:
        filters.append(Forecast.store_ref == store_ref)
    if product_ref:
        filters.append(Forecast.product_ref == product_ref)
    if target_date_from:
        filters.append(Forecast.target_date >= target_date_from)
    if target_date_to:
        filters.append(Forecast.target_date <= target_date_to)

    base_query = db.query(Forecast).outerjoin(ForecastActual, ForecastActual.forecast_id == Forecast.id)
    if filters:
        base_query = base_query.filter(and_(*filters))

    total = base_query.count()
    rows = (
        base_query.order_by(Forecast.target_date.desc(), Forecast.generated_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    items: list[ForecastListItem] = []
    for row in rows:
        actual = (
            db.query(ForecastActual).filter(ForecastActual.forecast_id == row.id).first()
        )
        items.append(
            ForecastListItem(
                id=str(row.id),
                model_version=row.model_version,
                store_ref=row.store_ref,
                product_ref=row.product_ref,
                target_date=row.target_date,
                horizon=row.horizon,
                predicted_qty=float(row.predicted_qty),
                actual_qty=float(actual.actual_qty) if actual else None,
                abs_error=float(actual.abs_error) if actual else None,
                generated_at=row.generated_at,
            )
        )
    return ForecastListResponse(items=items, total=total)


# ---------------------------------------------------------------------------
# GET /ai/optimal-batches
# ---------------------------------------------------------------------------


def _confidence_bucket(predicted_qty: float) -> str:
    """Quick heuristic so the UI can colour-code suggestions. Tiny demand =
    'low' confidence (noise dominates); medium / large = 'medium' / 'high'."""
    if predicted_qty < 5:
        return "low"
    if predicted_qty < 25:
        return "medium"
    return "high"


@router.get("/optimal-batches", response_model=OptimalBatchResponse)
def optimal_batches(
    db: Session = Depends(get_db),
    target_date: Optional[date] = Query(
        default=None,
        description="First day to plan for. Defaults to tomorrow.",
    ),
    days: int = Query(default=1, ge=1, le=7, description="How many consecutive days to plan."),
    store_ref: Optional[str] = Query(default=None),
) -> OptimalBatchResponse:
    """Translate the forecast into integer batch suggestions per product per day.

    Aggregates across stores when ``store_ref`` is omitted — production planners
    typically want a single "bake N units today" recommendation per product.
    """
    champion = _require_champion(db)
    forecaster = load_forecaster(champion.model_path)
    history = _load_recent_history(db)

    if store_ref:
        history = history[history["store_ref"] == store_ref]
        if history.empty:
            raise HTTPException(
                status_code=404,
                detail=f"No recent history for store_ref={store_ref}.",
            )

    start_date = target_date or (date.today() + timedelta(days=1))
    points = forecaster.predict_horizon(history, start_date=start_date, days=days)

    # Roll up by (product_ref, target_date) so multiple stores collapse to one
    # production target. We deliberately do NOT archive these as separate
    # forecasts — they're derived from the per-(store, product) predictions
    # which /ai/predict already persists.
    bucket: dict[tuple[str, date], float] = {}
    for p in points:
        key = (p.product_ref, p.target_date)
        bucket[key] = bucket.get(key, 0.0) + float(p.predicted_qty)

    items: list[OptimalBatchItem] = []
    for (product_ref, plan_date), demand in sorted(bucket.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        suggested = max(0, math.ceil(demand * (1.0 + SAFETY_STOCK_FACTOR)))
        items.append(
            OptimalBatchItem(
                product_ref=product_ref,
                target_date=plan_date,
                forecasted_demand=round(demand, 2),
                suggested_batch_qty=suggested,
                confidence=_confidence_bucket(demand),
            )
        )

    return OptimalBatchResponse(
        model_version=champion.version,
        generated_at=datetime.now(timezone.utc),
        horizon_days=days,
        items=items,
    )
