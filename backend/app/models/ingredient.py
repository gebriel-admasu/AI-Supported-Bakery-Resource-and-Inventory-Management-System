import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Numeric, Date, DateTime, Boolean, Uuid

from app.database import Base


class Ingredient(Base):
    __tablename__ = 'ingredients'

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    name = Column(String(100), unique=True, nullable=False, index=True)
    unit = Column(String(20), nullable=False)
    unit_cost = Column(Numeric(10, 2), nullable=False, default=0)
    expiry_date = Column(Date, nullable=True)
    description = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
