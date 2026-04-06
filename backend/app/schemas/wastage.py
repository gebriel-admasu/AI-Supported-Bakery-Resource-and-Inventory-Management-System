from typing import Optional
from uuid import UUID
from datetime import date, datetime

from pydantic import BaseModel


class WastageCreate(BaseModel):
    store_id: UUID
    product_id: UUID
    date: date
    quantity: int
    reason: str
    notes: Optional[str] = None


class WastageResponse(BaseModel):
    id: UUID
    store_id: UUID
    store_name: Optional[str] = None
    product_id: UUID
    product_name: Optional[str] = None
    date: date
    quantity: int
    reason: str
    notes: Optional[str] = None
    recorded_by: Optional[UUID] = None
    created_at: datetime

    model_config = {"from_attributes": True}
