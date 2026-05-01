from typing import Optional
from uuid import UUID
from datetime import date, datetime

from pydantic import BaseModel


class WastageCreate(BaseModel):
    source_type: str = "store"
    store_id: Optional[UUID] = None
    product_id: Optional[UUID] = None
    ingredient_id: Optional[UUID] = None
    date: date
    quantity: int
    reason: str
    notes: Optional[str] = None


class WastageResponse(BaseModel):
    id: UUID
    source_type: str
    store_id: Optional[UUID] = None
    store_name: Optional[str] = None
    product_id: Optional[UUID] = None
    product_name: Optional[str] = None
    product_unit: Optional[str] = None
    ingredient_id: Optional[UUID] = None
    ingredient_name: Optional[str] = None
    ingredient_unit: Optional[str] = None
    date: date
    quantity: int
    unit_price: Optional[float] = None
    total_price: Optional[float] = None
    unit_cost_snapshot: Optional[float] = None
    total_cost_snapshot: Optional[float] = None
    cost_source: Optional[str] = None
    is_estimated_cost: bool = False
    reason: str
    notes: Optional[str] = None
    recorded_by: Optional[UUID] = None
    recorded_by_name: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}
