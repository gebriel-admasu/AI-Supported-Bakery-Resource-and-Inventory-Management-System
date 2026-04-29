from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class SalesOpenPayload(BaseModel):
    store_id: UUID
    product_id: UUID
    date: date
    opening_stock: int
    notes: Optional[str] = None


class SalesSellPayload(BaseModel):
    quantity_sold: int
    notes: Optional[str] = None


class SalesClosePayload(BaseModel):
    closing_stock: int
    notes: Optional[str] = None
    auto_record_wastage: bool = True


class SalesUpdatePayload(BaseModel):
    opening_stock: Optional[int] = None
    quantity_sold: Optional[int] = None
    closing_stock: Optional[int] = None
    notes: Optional[str] = None


class SalesRecordResponse(BaseModel):
    id: UUID
    store_id: UUID
    store_name: Optional[str] = None
    product_id: UUID
    product_name: Optional[str] = None
    date: date
    opening_stock: int
    today_received_qty: int = 0
    total_product_qty: int
    quantity_sold: int
    closing_stock: int
    wastage_qty: int
    expected_closing: int
    variance_qty: int
    total_amount: float
    is_closed: bool
    closed_at: Optional[datetime] = None
    notes: Optional[str] = None
    recorded_by: Optional[UUID] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
