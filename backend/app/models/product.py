import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Numeric, DateTime, ForeignKey, Boolean, Uuid

from app.database import Base


class Product(Base):
    __tablename__ = 'products'

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False, index=True)
    sku = Column(String(50), unique=True, nullable=False)
    sale_price = Column(Numeric(10, 2), nullable=False)
    unit = Column(String(20), nullable=False, default='piece')
    recipe_id = Column(Uuid, ForeignKey('recipes.id'), nullable=True)
    description = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
