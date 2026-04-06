from typing import Optional
from uuid import UUID
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


class IngredientCreate(BaseModel):
    name: str
    unit: str
    unit_cost: Decimal
    expiry_date: Optional[date] = None
    description: Optional[str] = None


class IngredientUpdate(BaseModel):
    name: Optional[str] = None
    unit: Optional[str] = None
    unit_cost: Optional[Decimal] = None
    expiry_date: Optional[date] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class IngredientResponse(BaseModel):
    id: UUID
    name: str
    unit: str
    unit_cost: Decimal
    expiry_date: Optional[date] = None
    description: Optional[str] = None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
