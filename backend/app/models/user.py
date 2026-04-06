import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Boolean, DateTime, Enum as SAEnum, Uuid

from app.database import Base
from app.core.constants import RoleEnum


class User(Base):
    __tablename__ = 'users'

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(100), nullable=False)
    role = Column(
        SAEnum(RoleEnum, name="roleenum", create_constraint=True, native_enum=False),
        nullable=False,
        default=RoleEnum.STORE_MANAGER,
    )
    is_active = Column(Boolean, default=True)
    store_id = Column(Uuid, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
