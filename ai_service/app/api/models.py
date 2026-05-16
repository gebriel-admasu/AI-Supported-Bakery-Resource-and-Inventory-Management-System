"""Read-only views into ``ai_model_registry`` and forecast accuracy.

Phase 11 ships ``GET /ai/models`` (registry listing) and
``GET /ai/models/performance`` (MAE timeline). The mutation endpoints
(``POST /ai/retrain``, promotion + rejection) are owned by Phase 12 and live
in ``api/training.py``.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.db.models import Forecast, ForecastActual
from app.ml.registry import get_champion, list_all
from app.schemas.predictions import (
    ModelPerformancePoint,
    ModelPerformanceResponse,
    ModelRegistryItem,
    ModelRegistryListResponse,
)

router = APIRouter()


@router.get("/models", response_model=ModelRegistryListResponse)
def list_models(db: Session = Depends(get_db)) -> ModelRegistryListResponse:
    """All registered models, most-recently-trained first."""
    rows = list_all(db, limit=100)
    champion = get_champion(db)
    return ModelRegistryListResponse(
        champion_version=(champion.version if champion else None),
        items=[
            ModelRegistryItem(
                id=str(r.id),
                version=r.version,
                status=r.status,
                trained_at=r.trained_at or datetime.now(timezone.utc),
                training_rows_used=r.training_rows_used,
                training_source=r.training_source,
                holdout_mae=(float(r.holdout_mae) if r.holdout_mae is not None else None),
                model_path=r.model_path,
                promoted_at=r.promoted_at,
                archived_at=r.archived_at,
                notes=r.notes,
            )
            for r in rows
        ],
    )


@router.get("/models/performance", response_model=ModelPerformanceResponse)
def model_performance(
    db: Session = Depends(get_db),
    version: int | None = Query(
        default=None, description="Model version to score (defaults to current CHAMPION)."
    ),
    window_days: int = Query(default=14, ge=1, le=90),
) -> ModelPerformanceResponse:
    """Daily MAE for a model over the last ``window_days``.

    Joins ``ai_forecasts`` to ``ai_forecast_actuals``; rows without an actual
    are excluded (their backtest hasn't run yet).
    """
    if version is None:
        champion = get_champion(db)
        if champion is None:
            raise HTTPException(status_code=503, detail="No CHAMPION model registered yet.")
        version = champion.version

    cutoff = date.today() - timedelta(days=window_days)
    rows = (
        db.query(
            Forecast.target_date.label("bucket_date"),
            func.avg(ForecastActual.abs_error).label("mae"),
            func.count(ForecastActual.id).label("predictions"),
        )
        .join(ForecastActual, ForecastActual.forecast_id == Forecast.id)
        .filter(Forecast.model_version == version)
        .filter(Forecast.target_date >= cutoff)
        .group_by(Forecast.target_date)
        .order_by(Forecast.target_date.asc())
        .all()
    )

    overall_mae: float | None = None
    if rows:
        weighted_num = sum((r.mae or 0.0) * (r.predictions or 0) for r in rows)
        total_preds = sum(r.predictions or 0 for r in rows)
        if total_preds > 0:
            overall_mae = round(weighted_num / total_preds, 4)

    return ModelPerformanceResponse(
        model_version=version,
        window_days=window_days,
        overall_mae=overall_mae,
        daily=[
            ModelPerformancePoint(
                bucket_date=r.bucket_date,
                mae=round(float(r.mae or 0.0), 4),
                predictions=int(r.predictions or 0),
            )
            for r in rows
        ],
    )
