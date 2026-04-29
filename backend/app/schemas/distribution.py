from typing import Optional, List
from uuid import UUID
from datetime import date, datetime
from pydantic import BaseModel


class DistributionItemPayload(BaseModel):
    product_id: UUID
    quantity_sent: int


class DistributionItemReceive(BaseModel):
    item_id: UUID
    quantity_received: int
    discrepancy_reason: Optional[str] = None
    discrepancy_note: Optional[str] = None


class DistributionCreate(BaseModel):
    store_id: UUID
    dispatch_date: date
    delivery_person_id: Optional[UUID] = None
    items: List[DistributionItemPayload]


class DistributionItemResponse(BaseModel):
    id: UUID
    product_id: UUID
    product_name: Optional[str] = None
    quantity_sent: int
    quantity_received: Optional[int] = None
    discrepancy_qty: int = 0
    discrepancy_reason: Optional[str] = None
    discrepancy_note: Optional[str] = None

    model_config = {"from_attributes": True}


class DistributionDiscrepancyDecision(BaseModel):
    review_note: Optional[str] = None


class DistributionResponse(BaseModel):
    id: UUID
    store_id: UUID
    store_name: Optional[str] = None
    dispatch_date: date
    status: str
    dispatched_by: Optional[UUID] = None
    delivery_person_id: Optional[UUID] = None
    delivery_person_name: Optional[str] = None
    driver_count_confirmed: bool = False
    driver_count_confirmed_by: Optional[UUID] = None
    driver_count_confirmed_at: Optional[datetime] = None
    received_by: Optional[UUID] = None
    received_at: Optional[datetime] = None
    has_discrepancy: bool = False
    discrepancy_status: str = "none"
    reviewed_by: Optional[UUID] = None
    reviewed_by_name: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    review_note: Optional[str] = None
    is_locked: bool
    items: List[DistributionItemResponse] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
