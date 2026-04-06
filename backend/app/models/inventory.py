import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Numeric, DateTime, ForeignKey, Enum as SAEnum, Uuid

from app.database import Base
from app.core.constants import AlertStatus


class Inventory(Base):
    __tablename__ = 'inventories'

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    location_type = Column(String(50), nullable=False)
    location_id = Column(Uuid, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class InventoryStock(Base):
    __tablename__ = 'inventory_stocks'

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    inventory_id = Column(Uuid, ForeignKey('inventories.id'), nullable=False)
    ingredient_id = Column(Uuid, ForeignKey('ingredients.id'), nullable=True)
    product_id = Column(Uuid, ForeignKey('products.id'), nullable=True)
    quantity = Column(Numeric(12, 3), nullable=False, default=0)
    min_threshold = Column(Numeric(12, 3), nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class StockAlert(Base):
    __tablename__ = 'stock_alerts'

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    inventory_stock_id = Column(
        Uuid, ForeignKey('inventory_stocks.id'), nullable=False
    )
    ingredient_id = Column(Uuid, ForeignKey('ingredients.id'), nullable=True)
    current_qty = Column(Numeric(12, 3), nullable=False)
    min_qty = Column(Numeric(12, 3), nullable=False)
    status = Column(SAEnum(AlertStatus, native_enum=False), default=AlertStatus.ACTIVE)
    timestamp = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
