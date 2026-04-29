import uuid
from datetime import datetime, date, timezone

from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey, Enum as SAEnum, Uuid

from app.database import Base
from app.core.constants import WastageReason, WastageSourceType


class WastageRecord(Base):
    __tablename__ = 'wastage_records'

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    source_type = Column(
        SAEnum(WastageSourceType, native_enum=False),
        nullable=False,
        default=WastageSourceType.STORE,
    )
    store_id = Column(Uuid, ForeignKey('stores.id'), nullable=True)
    product_id = Column(Uuid, ForeignKey('products.id'), nullable=True)
    ingredient_id = Column(Uuid, ForeignKey('ingredients.id'), nullable=True)
    date = Column(Date, nullable=False, default=date.today)
    quantity = Column(Integer, nullable=False)
    reason = Column(SAEnum(WastageReason, native_enum=False), nullable=False)
    notes = Column(String(500), nullable=True)
    recorded_by = Column(Uuid, ForeignKey('users.id'), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
