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


class DistributionCreate(BaseModel):
    store_id: UUID
    dispatch_date: date
    items: List[DistributionItemPayload]


class DistributionItemResponse(BaseModel):
    id: UUID
    product_id: UUID
    product_name: Optional[str] = None
    quantity_sent: int
    quantity_received: Optional[int] = None

    model_config = {"from_attributes": True}


class DistributionResponse(BaseModel):
    id: UUID
    store_id: UUID
    store_name: Optional[str] = None
    dispatch_date: date
    status: str
    dispatched_by: Optional[UUID] = None
    received_by: Optional[UUID] = None
    is_locked: bool
    items: List[DistributionItemResponse] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
