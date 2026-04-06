import uuid
from datetime import datetime, date, timezone

from sqlalchemy import Column, String, Integer, Date, DateTime, ForeignKey, Enum as SAEnum, Uuid

from app.database import Base
from app.core.constants import BatchStatus


class ProductionBatch(Base):
    __tablename__ = 'production_batches'

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    recipe_id = Column(Uuid, ForeignKey('recipes.id'), nullable=False)
    product_id = Column(Uuid, ForeignKey('products.id'), nullable=False)
    batch_size = Column(Integer, nullable=False)
    actual_yield = Column(Integer, nullable=True)
    waste_qty = Column(Integer, nullable=True, default=0)
    production_date = Column(Date, nullable=False, default=date.today)
    status = Column(SAEnum(BatchStatus, native_enum=False), default=BatchStatus.PLANNED)
    created_by = Column(Uuid, ForeignKey('users.id'), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
