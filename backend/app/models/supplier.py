import uuid
from datetime import datetime, date, timezone

from sqlalchemy import Column, String, Numeric, Date, DateTime, ForeignKey, Integer, Boolean, Uuid

from app.database import Base


class Supplier(Base):
    __tablename__ = 'suppliers'

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False, unique=True)
    contact_person = Column(String(100), nullable=True)
    phone = Column(String(20), nullable=True)
    email = Column(String(100), nullable=True)
    address = Column(String(255), nullable=True)
    lead_time_days = Column(Integer, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class PurchaseOrder(Base):
    __tablename__ = 'purchase_orders'

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    supplier_id = Column(Uuid, ForeignKey('suppliers.id'), nullable=False)
    ingredient_id = Column(Uuid, ForeignKey('ingredients.id'), nullable=False)
    quantity = Column(Numeric(12, 3), nullable=False)
    unit_cost = Column(Numeric(10, 2), nullable=False)
    total_cost = Column(Numeric(12, 2), nullable=False)
    order_date = Column(Date, nullable=False, default=date.today)
    expected_delivery = Column(Date, nullable=True)
    actual_delivery = Column(Date, nullable=True)
    status = Column(String(20), nullable=False, default='pending')
    created_by = Column(Uuid, ForeignKey('users.id'), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
