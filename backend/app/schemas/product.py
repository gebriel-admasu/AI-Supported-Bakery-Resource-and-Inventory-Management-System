from typing import Optional
from uuid import UUID
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class ProductCreate(BaseModel):
    name: str
    sku: str
    sale_price: Decimal
    unit: str = "piece"
    recipe_id: Optional[UUID] = None
    description: Optional[str] = None


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    sku: Optional[str] = None
    sale_price: Optional[Decimal] = None
    unit: Optional[str] = None
    recipe_id: Optional[UUID] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class ProductResponse(BaseModel):
    id: UUID
    name: str
    sku: str
    sale_price: Decimal
    unit: str
    recipe_id: Optional[UUID] = None
    recipe_name: Optional[str] = None
    description: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
