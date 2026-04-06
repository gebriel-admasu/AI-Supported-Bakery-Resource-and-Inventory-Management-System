import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, DateTime, Boolean, Uuid

from app.database import Base


class Store(Base):
    __tablename__ = 'stores'

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False, unique=True)
    location = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
