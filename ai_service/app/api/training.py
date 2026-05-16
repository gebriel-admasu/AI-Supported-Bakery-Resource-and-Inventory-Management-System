"""Manual training + backtest endpoints.

- ``POST /ai/retrain`` — manually fire the same orchestrator the scheduler
  uses (handy for the thesis defence demo and for tests).
- ``POST /ai/backtest`` — manually run the daily backtest for a target date.

Both endpoints are intentionally synchronous: the training run takes
~5 seconds on a Kaggle subset, which is well within an HTTP request timeout
and lets the caller see the full outcome (validation verdict, MAE, MLOps
log entry) in the response. Async / background tasks are overkill at this
scale and would complicate the demo.
"""

from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.ml.orchestrator import run_retrain
from app.pipeline.backtest import run_backtest
from app.pipeline.data_loader import DataSource
from app.schemas.predictions import RetrainRequest, RetrainResponse

router = APIRouter()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# POST /ai/retrain
# ---------------------------------------------------------------------------


@router.post("/retrain", response_model=RetrainResponse)
def trigger_retraining(
    payload: RetrainRequest = RetrainRequest(),
    db: Session = Depends(get_db),
) -> RetrainResponse:
    """Manually fire a retraining cycle.

    Runs synchronously: train -> register candidate -> validate -> promote
    or reject, then returns the full outcome. Same code path as the
    scheduler's cron + volume-trigger jobs, so the MLOps audit trail looks
    identical regardless of trigger source.
    """
    prefer_source = _resolve_source(payload.source) if payload.source else None
    try:
        outcome = run_retrain(
            db,
            reason=f"manual: {payload.reason}",
            prefer_source=prefer_source,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    return RetrainResponse(
        candidate_version=outcome.candidate_version,
        status=outcome.final_status,
        holdout_mae=outcome.holdout_mae,
        training_rows=outcome.training_rows,
        training_source=outcome.training_source,
        promoted=outcome.promoted,
        message=outcome.message,
    )


# ---------------------------------------------------------------------------
# POST /ai/backtest  (operational helper, not in the original plan but
# cheap to expose so reviewers can re-score forecasts on demand)
# ---------------------------------------------------------------------------


@router.post("/backtest")
def trigger_backtest(
    db: Session = Depends(get_db),
    target_date: date | None = None,
    lookback_days: int = 1,
) -> dict:
    """Manually run the daily backtest.

    Defaults to scoring yesterday's forecasts; pass ``target_date`` to score
    a specific day, or ``lookback_days`` to sweep a wider window.
    """
    if lookback_days < 1 or lookback_days > 30:
        raise HTTPException(status_code=400, detail="lookback_days must be in 1..30")

    result = run_backtest(db, target_date=target_date, lookback_days=lookback_days)
    return {
        "rows_scored": result.rows_scored,
        "forecasts_skipped_no_actual": result.forecasts_skipped_no_actual,
        "mean_abs_error": (
            round(result.mean_abs_error, 4) if result.mean_abs_error is not None else None
        ),
        "window_start": result.window_start.isoformat() if result.window_start else None,
        "window_end": result.window_end.isoformat() if result.window_end else None,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_source(name: str) -> DataSource:
    mapping = {
        "kaggle": DataSource.KAGGLE,
        "synthetic": DataSource.SYNTHETIC,
        "live": DataSource.LIVE,
    }
    return mapping[name]
