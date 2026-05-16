"""APScheduler wiring for the AI service.

Three jobs are registered when the scheduler starts:

1. **Daily backtest** (cron, default 02:00) — calls ``pipeline.backtest.run_backtest``
   to score yesterday's forecasts.
2. **Weekly cron retrain** (cron, default Sunday 00:00) — calls
   ``ml.orchestrator.run_retrain`` regardless of data volume.
3. **Hourly volume-trigger check** (interval) — counts new SalesRecord rows
   since the most recent training run; if the count exceeds
   ``RETRAIN_VOLUME_THRESHOLD`` (or the demo threshold under DEMO_MODE),
   fires an orchestrator retrain.

The scheduler runs in-process (``BackgroundScheduler``) inside the FastAPI
worker. For a multi-worker deployment we'd add a distributed lock or
external scheduler, but at the project's scale a single worker is the
operational baseline.

Each job uses a fresh ``SessionLocal`` rather than sharing one — APScheduler
runs jobs on its own thread pool, and SQLAlchemy sessions are not
thread-safe.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.db.models import MlopsEventType, ModelRegistry
from app.ml.orchestrator import run_retrain
from app.ml.registry import log_event
from app.pipeline.backtest import run_backtest
from app.pipeline.data_loader import count_live_sales

logger = logging.getLogger(__name__)


# A module-level lock prevents accidental concurrent retrains if both the
# cron and volume triggers fire on the same tick. APScheduler also has a
# `max_instances` setting per job, but the lock guards across DIFFERENT
# jobs that both call run_retrain.
_retrain_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Job bodies
# ---------------------------------------------------------------------------


def _job_daily_backtest() -> None:
    db: Session = SessionLocal()
    try:
        result = run_backtest(db)
        logger.info(
            "[scheduler.backtest] scored=%d, mean_mae=%s",
            result.rows_scored,
            f"{result.mean_abs_error:.4f}" if result.mean_abs_error is not None else "n/a",
        )
    except Exception as exc:  # noqa: BLE001 — schedulers must not crash the app
        logger.exception("Daily backtest failed: %s", exc)
        _safe_log_error(db, "scheduler.backtest", exc)
    finally:
        db.close()


def _job_weekly_retrain() -> None:
    """Fires on the ``RETRAIN_SCHEDULE_CRON`` schedule, regardless of volume."""
    _trigger_retrain(reason="scheduler.cron")


def _job_volume_check() -> None:
    """Hourly poll: counts new sales rows since the latest training. If the
    count exceeds the (effective) threshold, fires a retrain."""
    db: Session = SessionLocal()
    try:
        last_training = _latest_training_row_count(db)
        current_live = count_live_sales(db)
        delta = current_live - last_training
        threshold = settings.effective_retrain_volume_threshold

        logger.debug(
            "[scheduler.volume] live=%d, last_training_rows=%d, delta=%d, threshold=%d",
            current_live,
            last_training,
            delta,
            threshold,
        )

        if delta >= threshold:
            logger.info(
                "[scheduler.volume] delta=%d >= threshold=%d — triggering retrain.",
                delta,
                threshold,
            )
            _trigger_retrain(reason=f"scheduler.volume_threshold(delta={delta})")
    except Exception as exc:  # noqa: BLE001
        logger.exception("Volume check failed: %s", exc)
        _safe_log_error(db, "scheduler.volume", exc)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Shared retrain wrapper
# ---------------------------------------------------------------------------


def _trigger_retrain(*, reason: str) -> None:
    """Acquire the lock and call ``run_retrain``. Any exception inside is
    caught + logged as an MLOps ERROR event so the scheduler thread keeps
    ticking."""
    if not _retrain_lock.acquire(blocking=False):
        logger.warning(
            "[scheduler] Retrain already in progress; skipping trigger (reason=%s).",
            reason,
        )
        return

    db: Session = SessionLocal()
    try:
        outcome = run_retrain(db, reason=reason)
        logger.info(
            "[scheduler.retrain] v%d %s (mae=%.4f) — %s",
            outcome.candidate_version,
            outcome.final_status,
            outcome.holdout_mae,
            outcome.message,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Retrain (%s) failed: %s", reason, exc)
        _safe_log_error(db, reason, exc)
    finally:
        db.close()
        _retrain_lock.release()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _latest_training_row_count(db: Session) -> int:
    """Returns ``training_rows_used`` from the most recently trained model.
    If no model has ever been trained, returns 0 so the first volume-trigger
    will fire as soon as we cross the threshold from zero."""
    row = (
        db.query(ModelRegistry.training_rows_used)
        .order_by(ModelRegistry.trained_at.desc())
        .first()
    )
    return int(row[0]) if row and row[0] else 0


def _safe_log_error(db: Optional[Session], context: str, exc: BaseException) -> None:
    """Best-effort error logging that never re-raises (we're already in a
    failure path)."""
    if db is None:
        return
    try:
        log_event(
            db,
            event_type=MlopsEventType.ERROR,
            payload={"context": context, "error": str(exc)},
            message=f"{context}: {type(exc).__name__}: {exc}",
        )
    except Exception:  # noqa: BLE001
        logger.exception("Failed to write ERROR log entry for %s", context)


# ---------------------------------------------------------------------------
# Scheduler lifecycle
# ---------------------------------------------------------------------------


_scheduler: Optional[BackgroundScheduler] = None


def start_scheduler() -> BackgroundScheduler:
    """Start the background scheduler and register the three jobs.

    Safe to call multiple times — re-entry returns the existing instance.
    """
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        logger.info("Scheduler already running; skipping start.")
        return _scheduler

    _scheduler = BackgroundScheduler(timezone="UTC")

    _scheduler.add_job(
        _job_daily_backtest,
        trigger=CronTrigger.from_crontab(settings.BACKTEST_DAILY_CRON, timezone="UTC"),
        id="daily_backtest",
        name="Daily backtest (score yesterday's forecasts)",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )

    _scheduler.add_job(
        _job_weekly_retrain,
        trigger=CronTrigger.from_crontab(settings.RETRAIN_SCHEDULE_CRON, timezone="UTC"),
        id="weekly_retrain",
        name="Weekly cron retrain",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )

    _scheduler.add_job(
        _job_volume_check,
        trigger=IntervalTrigger(hours=1),
        id="hourly_volume_check",
        name="Hourly volume-threshold check",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
        next_run_time=datetime.now(timezone.utc),  # run one immediately for fast warm-up
    )

    _scheduler.start()
    logger.info(
        "Scheduler started: backtest=%r weekly_retrain=%r volume_check=interval(1h)",
        settings.BACKTEST_DAILY_CRON,
        settings.RETRAIN_SCHEDULE_CRON,
    )
    return _scheduler


def stop_scheduler() -> None:
    """Gracefully shut down the scheduler (called on FastAPI shutdown)."""
    global _scheduler
    if _scheduler is None or not _scheduler.running:
        return
    logger.info("Stopping scheduler...")
    _scheduler.shutdown(wait=False)
    _scheduler = None


def get_scheduler() -> Optional[BackgroundScheduler]:
    """Returns the running scheduler instance (or None if not started)."""
    return _scheduler


# Re-export so tests + the manual /ai/retrain endpoint can share the same
# entry point as the scheduler jobs.
trigger_retrain_now = _trigger_retrain
