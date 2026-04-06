import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, DateTime, Text, Uuid

from app.database import Base


class AuditLog(Base):
    __tablename__ = 'audit_logs'

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, nullable=True)
    action = Column(String(100), nullable=False)
    resource = Column(String(100), nullable=True)
    resource_id = Column(String(100), nullable=True)
    details = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)
    timestamp = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
