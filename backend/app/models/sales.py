import uuid
from datetime import datetime, date, timezone

from sqlalchemy import Column, Integer, Numeric, Date, DateTime, ForeignKey, Uuid

from app.database import Base


class SalesRecord(Base):
    __tablename__ = 'sales_records'

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    store_id = Column(Uuid, ForeignKey('stores.id'), nullable=False)
    product_id = Column(Uuid, ForeignKey('products.id'), nullable=False)
    date = Column(Date, nullable=False, default=date.today, index=True)
    opening_stock = Column(Integer, nullable=False, default=0)
    quantity_sold = Column(Integer, nullable=False, default=0)
    closing_stock = Column(Integer, nullable=False, default=0)
    total_amount = Column(Numeric(12, 2), nullable=False, default=0)
    recorded_by = Column(Uuid, ForeignKey('users.id'), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
