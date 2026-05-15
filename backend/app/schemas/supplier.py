from typing import Optional, List
from uuid import UUID
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Supplier schemas
# ---------------------------------------------------------------------------


class SupplierCreate(BaseModel):
    name: str
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    lead_time_days: Optional[int] = None


class SupplierUpdate(BaseModel):
    name: Optional[str] = None
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    lead_time_days: Optional[int] = None
    is_active: Optional[bool] = None


class SupplierResponse(BaseModel):
    id: UUID
    name: str
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    lead_time_days: Optional[int] = None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Purchase order schemas
# ---------------------------------------------------------------------------


class PurchaseOrderCreate(BaseModel):
    supplier_id: UUID
    ingredient_id: UUID
    quantity: Decimal
    unit_cost: Decimal
    expected_delivery: Optional[date] = None
    notes: Optional[str] = None


class PurchaseOrderResponse(BaseModel):
    id: UUID
    supplier_id: UUID
    supplier_name: Optional[str] = None
    ingredient_id: UUID
    ingredient_name: Optional[str] = None
    ingredient_unit: Optional[str] = None
    quantity: Decimal
    unit_cost: Decimal
    total_cost: Decimal
    order_date: date
    expected_delivery: Optional[date] = None
    actual_delivery: Optional[date] = None
    status: str
    created_by: Optional[UUID] = None
    created_by_username: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PurchaseOrderApprovePayload(BaseModel):
    note: Optional[str] = None


class PurchaseOrderSendPayload(BaseModel):
    expected_delivery: Optional[date] = None
    note: Optional[str] = None


class PurchaseOrderReceivePayload(BaseModel):
    actual_delivery: Optional[date] = None
    note: Optional[str] = None


class PurchaseOrderCancelPayload(BaseModel):
    reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Reorder suggestion schemas
# ---------------------------------------------------------------------------


class ReorderSupplierOption(BaseModel):
    supplier_id: UUID
    supplier_name: str
    lead_time_days: Optional[int] = None
    last_unit_cost: Optional[Decimal] = None
    last_order_date: Optional[date] = None
    has_history: bool


class ReorderSuggestionItem(BaseModel):
    ingredient_id: UUID
    ingredient_name: str
    ingredient_unit: str
    current_qty: Decimal
    min_threshold: Decimal
    shortage_qty: Decimal
    suggested_qty: Decimal
    suppliers: List[ReorderSupplierOption] = []


class ReorderSuggestionResponse(BaseModel):
    items: List[ReorderSuggestionItem] = []
