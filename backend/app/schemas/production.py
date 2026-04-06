from typing import Optional
from uuid import UUID
from datetime import date, datetime

from pydantic import BaseModel


class BatchCreate(BaseModel):
    recipe_id: UUID
    product_id: UUID
    batch_size: int
    production_date: date


class BatchUpdate(BaseModel):
    status: Optional[str] = None
    actual_yield: Optional[int] = None
    waste_qty: Optional[int] = None


class BatchResponse(BaseModel):
    id: UUID
    recipe_id: UUID
    recipe_name: Optional[str] = None
    product_id: UUID
    product_name: Optional[str] = None
    batch_size: int
    actual_yield: Optional[int] = None
    waste_qty: Optional[int] = None
    production_date: date
    status: str
    created_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
