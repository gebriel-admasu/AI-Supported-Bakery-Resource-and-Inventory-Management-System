from typing import Optional
from uuid import UUID
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel


class InventoryStockResponse(BaseModel):
    id: UUID
    inventory_id: UUID
    ingredient_id: Optional[UUID] = None
    product_id: Optional[UUID] = None
    quantity: Decimal
    min_threshold: Optional[Decimal] = None
    ingredient_name: Optional[str] = None
    product_name: Optional[str] = None
    updated_at: datetime
    model_config = {"from_attributes": True}


class StockUpdatePayload(BaseModel):
    quantity: Decimal
    min_threshold: Optional[Decimal] = None


class StockAlertResponse(BaseModel):
    id: UUID
    inventory_stock_id: UUID
    ingredient_id: Optional[UUID] = None
    current_qty: Decimal
    min_qty: Decimal
    status: str
    timestamp: datetime
    ingredient_name: Optional[str] = None
    model_config = {"from_attributes": True}
