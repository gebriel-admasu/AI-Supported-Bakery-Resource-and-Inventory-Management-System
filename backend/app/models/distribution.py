import uuid
from datetime import datetime, date, timezone

from sqlalchemy import Column, Integer, Date, DateTime, ForeignKey, Enum as SAEnum, Boolean, String, Uuid

from app.database import Base
from app.core.constants import DistributionStatus, DiscrepancyStatus


class Distribution(Base):
    __tablename__ = 'distributions'

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    store_id = Column(Uuid, ForeignKey('stores.id'), nullable=False)
    dispatch_date = Column(Date, nullable=False, default=date.today)
    status = Column(SAEnum(DistributionStatus, native_enum=False), default=DistributionStatus.DISPATCHED)
    dispatched_by = Column(Uuid, ForeignKey('users.id'), nullable=True)
    delivery_person_id = Column(Uuid, ForeignKey('users.id'), nullable=True)
    driver_count_confirmed = Column(Boolean, default=False, nullable=False)
    driver_count_confirmed_by = Column(Uuid, ForeignKey('users.id'), nullable=True)
    driver_count_confirmed_at = Column(DateTime(timezone=True), nullable=True)
    received_by = Column(Uuid, ForeignKey('users.id'), nullable=True)
    received_at = Column(DateTime(timezone=True), nullable=True)
    has_discrepancy = Column(Boolean, default=False, nullable=False)
    discrepancy_status = Column(
        SAEnum(DiscrepancyStatus, native_enum=False),
        default=DiscrepancyStatus.NONE,
        nullable=False,
    )
    reviewed_by = Column(Uuid, ForeignKey('users.id'), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    review_note = Column(String(255), nullable=True)
    is_locked = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class DistributionItem(Base):
    __tablename__ = 'distribution_items'

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    distribution_id = Column(
        Uuid, ForeignKey('distributions.id'), nullable=False
    )
    product_id = Column(Uuid, ForeignKey('products.id'), nullable=False)
    quantity_sent = Column(Integer, nullable=False)
    quantity_received = Column(Integer, nullable=True)
    discrepancy_qty = Column(Integer, nullable=False, default=0)
    discrepancy_reason = Column(String(100), nullable=True)
    discrepancy_note = Column(String(255), nullable=True)
