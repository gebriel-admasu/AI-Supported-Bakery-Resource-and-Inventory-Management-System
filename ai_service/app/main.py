"""AI forecasting service entry point.

Wires up the FastAPI app, routers, and the APScheduler-based MLOps
automation. The scheduler is started on app boot and stopped gracefully
on shutdown.

A single env var ``SCHEDULER_ENABLED`` (defaults to ``true``) can disable
the scheduler — handy for tests and for running the API in a constrained
container where you'd rather kick off retrains externally.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import models, predictions, training
from app.config import settings
from app.scheduler.retrain_scheduler import start_scheduler, stop_scheduler

logger = logging.getLogger(__name__)


def _scheduler_enabled() -> bool:
    return os.environ.get("SCHEDULER_ENABLED", "true").lower() in {"1", "true", "yes"}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """FastAPI lifespan — starts the scheduler on boot, stops on shutdown."""
    if _scheduler_enabled():
        try:
            start_scheduler()
        except Exception:  # noqa: BLE001 — never block app boot on scheduler errors
            logger.exception("Failed to start scheduler; API will run without it.")
    else:
        logger.info("Scheduler disabled via SCHEDULER_ENABLED=false.")

    yield

    if _scheduler_enabled():
        try:
            stop_scheduler()
        except Exception:  # noqa: BLE001
            logger.exception("Error stopping scheduler.")


app = FastAPI(
    title=settings.APP_NAME,
    description="AI demand forecasting microservice for the Bakery Management System",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(predictions.router, prefix="/ai", tags=["Predictions"])
app.include_router(training.router, prefix="/ai", tags=["Training"])
app.include_router(models.router, prefix="/ai", tags=["Models"])


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": settings.APP_NAME}
