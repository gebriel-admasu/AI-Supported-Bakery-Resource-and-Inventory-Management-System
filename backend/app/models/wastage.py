import uuid
from datetime import datetime, date, timezone

from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey, Enum as SAEnum, Uuid

from app.database import Base
from app.core.constants import WastageReason


class WastageRecord(Base):
    __tablename__ = 'wastage_records'

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    store_id = Column(Uuid, ForeignKey('stores.id'), nullable=False)
    product_id = Column(Uuid, ForeignKey('products.id'), nullable=False)
    date = Column(Date, nullable=False, default=date.today)
    quantity = Column(Integer, nullable=False)
    reason = Column(SAEnum(WastageReason, native_enum=False), nullable=False)
    notes = Column(String(500), nullable=True)
    recorded_by = Column(Uuid, ForeignKey('users.id'), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
