import uuid
from datetime import datetime, date, timezone

from sqlalchemy import Column, String, Integer, Numeric, Date, DateTime, ForeignKey, Enum as SAEnum, Boolean, Uuid

from app.database import Base
from app.core.constants import RetrainingTrigger, RetrainingResult


class DemandForecast(Base):
    __tablename__ = 'demand_forecasts'

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    product_id = Column(Uuid, ForeignKey('products.id'), nullable=False)
    store_id = Column(Uuid, ForeignKey('stores.id'), nullable=True)
    forecast_date = Column(Date, nullable=False)
    predicted_qty = Column(Integer, nullable=False)
    actual_qty = Column(Integer, nullable=True)
    accuracy_score = Column(Numeric(5, 4), nullable=True)
    model_version = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class MLModel(Base):
    __tablename__ = 'ml_models'

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    version = Column(String(50), nullable=False, unique=True)
    model_path = Column(String(255), nullable=False)
    trained_on = Column(Date, nullable=False)
    mae_score = Column(Numeric(10, 4), nullable=True)
    rmse_score = Column(Numeric(10, 4), nullable=True)
    is_active = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class RetrainingLog(Base):
    __tablename__ = 'retraining_logs'

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    model_id = Column(Uuid, ForeignKey('ml_models.id'), nullable=True)
    trigger_type = Column(SAEnum(RetrainingTrigger, native_enum=False), nullable=False)
    result = Column(SAEnum(RetrainingResult, native_enum=False), nullable=False)
    old_mae = Column(Numeric(10, 4), nullable=True)
    new_mae = Column(Numeric(10, 4), nullable=True)
    data_points_used = Column(Integer, nullable=True)
    training_duration_seconds = Column(Numeric(10, 2), nullable=True)
    details = Column(String(1000), nullable=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
