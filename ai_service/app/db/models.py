"""SQLAlchemy models owned by the AI service.

These four tables live alongside the backend's schema in the shared SQLite
database file. They fulfil the Phase 11 + 12 functional requirements:

- ``model_registry``    — Champion/Candidate model versioning (FR-55, FR-56)
- ``forecasts``         — archived predictions for learning (FR-52)
- ``forecast_actuals``  — actual sales matched to a forecast for backtesting (FR-50)
- ``mlops_logs``        — full audit log of training, validation, promotions (FR-57)

We intentionally avoid SQLAlchemy enum types for ``status`` / ``event_type`` /
``horizon`` columns. The backend used ``native_enum=False`` strings for the same
reason — SQLite enum support is awkward, and string-typed columns are easier to
evolve when new event kinds appear.
"""

import enum
import uuid
from datetime import datetime, date, timezone

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
)

from app.database import Base


# ---------------------------------------------------------------------------
# Constants (kept as plain enums on the Python side for type-hint friendliness)
# ---------------------------------------------------------------------------


class ModelStatus(str, enum.Enum):
    CHAMPION = "champion"
    CANDIDATE = "candidate"
    ARCHIVED = "archived"


class ForecastHorizon(str, enum.Enum):
    DAY = "day"
    WEEK = "week"


class MlopsEventType(str, enum.Enum):
    TRAIN = "train"
    BACKTEST = "backtest"
    VALIDATE = "validate"
    PROMOTE = "promote"
    REJECT = "reject"
    ERROR = "error"


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------


class ModelRegistry(Base):
    """One row per trained model. Exactly one ``CHAMPION`` row is expected at
    any given time; ``CANDIDATE`` is the most recent training output awaiting
    validation; ``ARCHIVED`` rows are prior champions kept for traceability.
    """

    __tablename__ = "ai_model_registry"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    version = Column(Integer, nullable=False, unique=True, index=True)
    status = Column(String(20), nullable=False, default=ModelStatus.CANDIDATE.value, index=True)

    trained_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    training_rows_used = Column(Integer, nullable=False, default=0)
    training_source = Column(String(50), nullable=True)  # "kaggle" | "synthetic" | "live"
    holdout_mae = Column(Float, nullable=True)

    model_path = Column(String(500), nullable=False)
    feature_list = Column(Text, nullable=True)  # JSON-encoded list of feature names

    promoted_at = Column(DateTime(timezone=True), nullable=True)
    archived_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Forecast(Base):
    """One forecasted (store, product, target_date, horizon) tuple, archived
    immediately on prediction so we can later compute backtest accuracy."""

    __tablename__ = "ai_forecasts"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    model_version = Column(
        Integer, ForeignKey("ai_model_registry.version"), nullable=False, index=True
    )

    # Either a real store/product UUID from the backend, OR a synthetic
    # identifier (string-encoded int) when the data came from Kaggle / generated.
    store_ref = Column(String(64), nullable=False, index=True)
    product_ref = Column(String(64), nullable=False, index=True)

    target_date = Column(Date, nullable=False, index=True)
    horizon = Column(String(10), nullable=False, default=ForecastHorizon.DAY.value)

    predicted_qty = Column(Float, nullable=False)
    generated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ForecastActual(Base):
    """A single observed-vs-predicted pair, populated by the daily backtest
    job that runs at ``BACKTEST_DAILY_CRON``."""

    __tablename__ = "ai_forecast_actuals"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    forecast_id = Column(Uuid, ForeignKey("ai_forecasts.id"), nullable=False, unique=True)

    actual_qty = Column(Float, nullable=False)
    abs_error = Column(Float, nullable=False)
    recorded_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class MlopsLog(Base):
    """Every MLOps event — training, validation, promotion, rejection, error
    — appends an immutable row here so the platform can show a full audit
    trail to the user (FR-57)."""

    __tablename__ = "ai_mlops_logs"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    event_type = Column(String(30), nullable=False, index=True)

    candidate_version = Column(Integer, nullable=True)
    champion_version = Column(Integer, nullable=True)

    payload = Column(Text, nullable=True)  # JSON-encoded extra data (metrics, p-value, etc.)
    message = Column(Text, nullable=True)

    occurred_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)


# ---------------------------------------------------------------------------
# Convenience for Alembic + bootstrap to import everything at once.
# ---------------------------------------------------------------------------

__all__ = [
    "Base",
    "ModelRegistry",
    "ModelStatus",
    "Forecast",
    "ForecastHorizon",
    "ForecastActual",
    "MlopsLog",
    "MlopsEventType",
]
