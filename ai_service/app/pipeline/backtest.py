"""Daily backtest job.

Runs once a day (typically 02:00 via ``BACKTEST_DAILY_CRON``). For every
forecast whose ``target_date`` is in the past and which doesn't yet have a
matching ``ai_forecast_actuals`` row, the job:

1. Looks up the actual ``quantity_sold`` from the backend's ``sales_records``
   table — or, in warm-start / demo mode where forecasts may be on Kaggle
   ``S{n}`` / ``P{n}`` refs that don't exist in ``sales_records``, falls back
   to the same data loader used at training time (which transparently merges
   live + canonical sources).
2. Computes ``abs_error = |predicted - actual|``.
3. Inserts an ``ai_forecast_actuals`` row.
4. Emits an MLOps ``BACKTEST`` log entry summarising the run (rows scored,
   mean MAE, date window).

The job is **idempotent** — re-running it the same day is a no-op because the
``ai_forecast_actuals.forecast_id`` unique constraint guarantees one actual
per forecast, and the lookup query explicitly excludes forecasts that already
have a matched actual.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import pandas as pd
from sqlalchemy.orm import Session

from app.db.models import (
    Forecast,
    ForecastActual,
    MlopsEventType,
)
from app.ml.registry import log_event
from app.pipeline.data_loader import load_training_data

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result wrapper
# ---------------------------------------------------------------------------


@dataclass
class BacktestResult:
    rows_scored: int
    forecasts_skipped_no_actual: int
    mean_abs_error: Optional[float]
    window_start: Optional[date]
    window_end: Optional[date]

    def to_log_payload(self) -> dict:
        return {
            "rows_scored": self.rows_scored,
            "forecasts_skipped_no_actual": self.forecasts_skipped_no_actual,
            "mean_abs_error": (
                round(self.mean_abs_error, 4) if self.mean_abs_error is not None else None
            ),
            "window_start": self.window_start.isoformat() if self.window_start else None,
            "window_end": self.window_end.isoformat() if self.window_end else None,
        }


# ---------------------------------------------------------------------------
# Core entry point
# ---------------------------------------------------------------------------


def run_backtest(
    db: Session,
    *,
    target_date: Optional[date] = None,
    lookback_days: int = 1,
    log: bool = True,
) -> BacktestResult:
    """Score every unmatched forecast whose ``target_date`` is in the past.

    Args:
        db: open SQLAlchemy session.
        target_date: defaults to "yesterday" (UTC). Pass an explicit date to
            re-score a specific day (useful for tests and the manual smoke run).
        lookback_days: how many days back from ``target_date`` to sweep. With
            the default ``1`` the job scores exactly ``target_date``. With
            ``7`` it sweeps the full previous week — used by the manual
            replay endpoint to catch up after extended downtime.
        log: if True, append a ``BACKTEST`` MLOps log entry. Tests disable
            this so they can introspect the log without scheduler noise.
    """
    if target_date is None:
        target_date = date.today() - timedelta(days=1)
    window_start = target_date - timedelta(days=lookback_days - 1)
    window_end = target_date

    # 1. Pull every unmatched forecast in the window.
    unmatched = (
        db.query(Forecast)
        .outerjoin(ForecastActual, ForecastActual.forecast_id == Forecast.id)
        .filter(Forecast.target_date >= window_start)
        .filter(Forecast.target_date <= window_end)
        .filter(ForecastActual.id.is_(None))
        .all()
    )

    if not unmatched:
        logger.info(
            "Backtest %s..%s: no unmatched forecasts (nothing to score).",
            window_start,
            window_end,
        )
        result = BacktestResult(
            rows_scored=0,
            forecasts_skipped_no_actual=0,
            mean_abs_error=None,
            window_start=window_start,
            window_end=window_end,
        )
        if log:
            log_event(
                db,
                event_type=MlopsEventType.BACKTEST,
                payload=result.to_log_payload(),
                message=f"Backtest {window_start}..{window_end}: nothing to score.",
            )
        return result

    # 2. Build a lookup table of actuals for the same window. Using the data
    #    loader (rather than a raw SQL query on sales_records) keeps the
    #    backtest aware of the same Kaggle/synthetic warm-start data the
    #    training pipeline uses, so demo-mode forecasts can still be scored.
    actuals = _load_actuals_for_window(db, window_start, window_end)

    # 3. Score each forecast we have an actual for; skip the rest.
    new_rows: list[ForecastActual] = []
    abs_errors: list[float] = []
    skipped = 0

    for fc in unmatched:
        key = (fc.store_ref, fc.product_ref, fc.target_date)
        actual_qty = actuals.get(key)
        if actual_qty is None:
            skipped += 1
            continue

        abs_err = abs(float(fc.predicted_qty) - float(actual_qty))
        new_rows.append(
            ForecastActual(
                id=uuid.uuid4(),
                forecast_id=fc.id,
                actual_qty=float(actual_qty),
                abs_error=abs_err,
                recorded_at=datetime.now(timezone.utc),
            )
        )
        abs_errors.append(abs_err)

    if new_rows:
        db.bulk_save_objects(new_rows)
        db.commit()

    mean_mae = (sum(abs_errors) / len(abs_errors)) if abs_errors else None
    result = BacktestResult(
        rows_scored=len(new_rows),
        forecasts_skipped_no_actual=skipped,
        mean_abs_error=mean_mae,
        window_start=window_start,
        window_end=window_end,
    )

    logger.info(
        "Backtest %s..%s: scored=%d, skipped=%d, mean_abs_error=%s",
        window_start,
        window_end,
        result.rows_scored,
        result.forecasts_skipped_no_actual,
        f"{mean_mae:.4f}" if mean_mae is not None else "n/a",
    )

    if log:
        log_event(
            db,
            event_type=MlopsEventType.BACKTEST,
            payload=result.to_log_payload(),
            message=(
                f"Backtest {window_start}..{window_end}: "
                f"scored {result.rows_scored} forecasts, skipped {skipped} "
                f"(no matching actuals)."
            ),
        )
    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_actuals_for_window(
    db: Session, window_start: date, window_end: date
) -> dict[tuple[str, str, date], float]:
    """Returns ``{(store_ref, product_ref, target_date): quantity_sold}``
    spanning ``[window_start, window_end]``.

    Uses ``load_training_data`` so the same Kaggle/synthetic warm-start data
    the model was trained on is also visible at scoring time. In a true
    production deployment this collapses to the LIVE source automatically
    once the volume threshold is met.
    """
    load = load_training_data(db=db)
    df = load.df
    if df.empty:
        return {}

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date
    mask = (df["date"] >= window_start) & (df["date"] <= window_end)
    df = df[mask]

    actuals: dict[tuple[str, str, date], float] = {}
    for row in df.itertuples(index=False):
        actuals[(row.store_ref, row.product_ref, row.date)] = float(row.quantity_sold)
    return actuals
