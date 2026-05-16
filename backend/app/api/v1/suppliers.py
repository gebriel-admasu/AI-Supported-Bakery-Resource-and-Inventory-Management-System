from datetime import date, timedelta
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.api.v1.inventory import get_or_create_production_inventory
from app.core.constants import AlertStatus, PurchaseOrderStatus, RoleEnum
from app.database import get_db
from app.models.ingredient import Ingredient
from app.models.inventory import Inventory, InventoryStock, StockAlert
from app.models.supplier import PurchaseOrder, Supplier
from app.models.user import User
from app.schemas.supplier import (
    PurchaseOrderApprovePayload,
    PurchaseOrderCancelPayload,
    PurchaseOrderCreate,
    PurchaseOrderReceivePayload,
    PurchaseOrderResponse,
    PurchaseOrderSendPayload,
    ReorderSuggestionItem,
    ReorderSuggestionResponse,
    ReorderSupplierOption,
    SupplierCreate,
    SupplierResponse,
    SupplierUpdate,
)
from app.services.audit_service import log_action

# Three sibling routers — kept in one module because they share helpers and
# semantics, but mounted at separate prefixes to avoid path collisions
# (/{supplier_id} would otherwise shadow /purchase-orders).
supplier_router = APIRouter()
purchase_order_router = APIRouter()
reorder_router = APIRouter()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _to_decimal(value: object) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _client_ip(request: Optional[Request]) -> Optional[str]:
    if request is None or request.client is None:
        return None
    return request.client.host


def _status_value(status_obj) -> str:
    if isinstance(status_obj, PurchaseOrderStatus):
        return status_obj.value
    return str(status_obj)


def _build_po_response(db: Session, po: PurchaseOrder) -> PurchaseOrderResponse:
    supplier = db.query(Supplier).filter(Supplier.id == po.supplier_id).first()
    ingredient = (
        db.query(Ingredient).filter(Ingredient.id == po.ingredient_id).first()
    )
    creator = (
        db.query(User).filter(User.id == po.created_by).first()
        if po.created_by
        else None
    )
    return PurchaseOrderResponse(
        id=po.id,
        supplier_id=po.supplier_id,
        supplier_name=supplier.name if supplier else None,
        ingredient_id=po.ingredient_id,
        ingredient_name=ingredient.name if ingredient else None,
        ingredient_unit=ingredient.unit if ingredient else None,
        quantity=_to_decimal(po.quantity),
        unit_cost=_to_decimal(po.unit_cost),
        total_cost=_to_decimal(po.total_cost),
        order_date=po.order_date,
        expected_delivery=po.expected_delivery,
        actual_delivery=po.actual_delivery,
        status=_status_value(po.status),
        created_by=po.created_by,
        created_by_username=creator.username if creator else None,
        created_at=po.created_at,
    )


def _resolve_low_stock_alert_if_resolved(
    db: Session, stock: InventoryStock
) -> None:
    """If the stock is now at or above its min_threshold, mark all active alerts
    on this stock as RESOLVED. Mirrors the resolution branch of
    app.api.v1.inventory._sync_low_stock_alert.

    Note: We do NOT create new alerts here because PO receipt only INCREASES stock
    (which can only resolve, never trigger, a low-stock alert).
    """
    if stock.min_threshold is None:
        return
    if stock.quantity < stock.min_threshold:
        return
    active_alerts = (
        db.query(StockAlert)
        .filter(
            StockAlert.inventory_stock_id == stock.id,
            StockAlert.status == AlertStatus.ACTIVE,
        )
        .all()
    )
    for alert in active_alerts:
        alert.status = AlertStatus.RESOLVED
        alert.current_qty = stock.quantity
        alert.min_qty = stock.min_threshold


def _credit_inventory_for_received_po(db: Session, po: PurchaseOrder) -> None:
    """Add the received PO quantity to the production inventory stock for this
    ingredient. Creates the stock row if one doesn't exist yet."""
    inv = get_or_create_production_inventory(db)
    stock = (
        db.query(InventoryStock)
        .filter(
            InventoryStock.inventory_id == inv.id,
            InventoryStock.ingredient_id == po.ingredient_id,
        )
        .first()
    )
    qty_received = _to_decimal(po.quantity)
    if stock:
        stock.quantity = _to_decimal(stock.quantity) + qty_received
    else:
        stock = InventoryStock(
            inventory_id=inv.id,
            ingredient_id=po.ingredient_id,
            quantity=qty_received,
        )
        db.add(stock)
        db.flush()
    _resolve_low_stock_alert_if_resolved(db, stock)


def _can_approve(user: User) -> bool:
    return user.role == RoleEnum.OWNER


def _can_cancel(user: User, po: PurchaseOrder) -> bool:
    if user.role == RoleEnum.OWNER:
        return True
    if (
        po.created_by == user.id
        and _status_value(po.status) == PurchaseOrderStatus.PENDING.value
    ):
        return True
    return False


# ---------------------------------------------------------------------------
# Supplier CRUD  (mounted at /suppliers)
# ---------------------------------------------------------------------------


@supplier_router.get("/", response_model=List[SupplierResponse])
async def list_suppliers(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    search: Optional[str] = None,
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(RoleEnum.OWNER, RoleEnum.PRODUCTION_MANAGER)
    ),
):
    query = db.query(Supplier)
    if search:
        query = query.filter(Supplier.name.ilike(f"%{search}%"))
    if is_active is not None:
        query = query.filter(Supplier.is_active == is_active)
    return (
        query.order_by(Supplier.created_at.desc()).offset(skip).limit(limit).all()
    )


@supplier_router.post(
    "/", response_model=SupplierResponse, status_code=status.HTTP_201_CREATED
)
async def create_supplier(
    body: SupplierCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(RoleEnum.OWNER, RoleEnum.PRODUCTION_MANAGER)
    ),
):
    existing = db.query(Supplier).filter(Supplier.name == body.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A supplier with this name already exists",
        )

    supplier = Supplier(
        name=body.name,
        contact_person=body.contact_person,
        phone=body.phone,
        email=body.email,
        address=body.address,
        lead_time_days=body.lead_time_days,
    )
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    return supplier


@supplier_router.get("/{supplier_id}", response_model=SupplierResponse)
async def get_supplier(
    supplier_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(RoleEnum.OWNER, RoleEnum.PRODUCTION_MANAGER)
    ),
):
    supplier = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if not supplier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found"
        )
    return supplier


@supplier_router.put("/{supplier_id}", response_model=SupplierResponse)
async def update_supplier(
    supplier_id: UUID,
    body: SupplierUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(RoleEnum.OWNER, RoleEnum.PRODUCTION_MANAGER)
    ),
):
    supplier = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if not supplier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found"
        )

    update_data = body.model_dump(exclude_unset=True)

    if "name" in update_data and update_data["name"] != supplier.name:
        other = (
            db.query(Supplier)
            .filter(
                Supplier.name == update_data["name"],
                Supplier.id != supplier_id,
            )
            .first()
        )
        if other:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A supplier with this name already exists",
            )

    for field, value in update_data.items():
        setattr(supplier, field, value)

    db.commit()
    db.refresh(supplier)
    return supplier


@supplier_router.delete("/{supplier_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_supplier(
    supplier_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(RoleEnum.OWNER, RoleEnum.PRODUCTION_MANAGER)
    ),
):
    supplier = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if not supplier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found"
        )
    supplier.is_active = False
    db.commit()
    return None


# ---------------------------------------------------------------------------
# Purchase Order lifecycle  (mounted at /purchase-orders)
# ---------------------------------------------------------------------------


@purchase_order_router.get("/", response_model=List[PurchaseOrderResponse])
async def list_purchase_orders(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    status_filter: Optional[PurchaseOrderStatus] = Query(None, alias="status"),
    supplier_id: Optional[UUID] = None,
    ingredient_id: Optional[UUID] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(RoleEnum.OWNER, RoleEnum.PRODUCTION_MANAGER)
    ),
):
    query = db.query(PurchaseOrder)
    if status_filter is not None:
        query = query.filter(PurchaseOrder.status == status_filter)
    if supplier_id:
        query = query.filter(PurchaseOrder.supplier_id == supplier_id)
    if ingredient_id:
        query = query.filter(PurchaseOrder.ingredient_id == ingredient_id)
    if date_from:
        query = query.filter(PurchaseOrder.order_date >= date_from)
    if date_to:
        query = query.filter(PurchaseOrder.order_date <= date_to)

    rows = (
        query.order_by(PurchaseOrder.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [_build_po_response(db, po) for po in rows]


@purchase_order_router.post(
    "/",
    response_model=PurchaseOrderResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_purchase_order(
    body: PurchaseOrderCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(RoleEnum.OWNER, RoleEnum.PRODUCTION_MANAGER)
    ),
):
    supplier = db.query(Supplier).filter(Supplier.id == body.supplier_id).first()
    if not supplier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found"
        )
    if not supplier.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot create a purchase order for an inactive supplier",
        )
    ingredient = (
        db.query(Ingredient).filter(Ingredient.id == body.ingredient_id).first()
    )
    if not ingredient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Ingredient not found"
        )

    qty = _to_decimal(body.quantity)
    unit_cost = _to_decimal(body.unit_cost)
    if qty <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Quantity must be greater than zero",
        )
    if unit_cost < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unit cost cannot be negative",
        )
    total_cost = (qty * unit_cost).quantize(Decimal("0.01"))

    po = PurchaseOrder(
        supplier_id=body.supplier_id,
        ingredient_id=body.ingredient_id,
        quantity=qty,
        unit_cost=unit_cost,
        total_cost=total_cost,
        expected_delivery=body.expected_delivery,
        status=PurchaseOrderStatus.PENDING,
        created_by=current_user.id,
    )
    db.add(po)
    db.commit()
    db.refresh(po)

    note_suffix = f" | note: {body.notes}" if body.notes else ""
    log_action(
        db,
        user_id=current_user.id,
        action="purchase_order_created",
        resource="purchase_order",
        resource_id=str(po.id),
        details=(
            f"PO created: supplier={supplier.name}, ingredient={ingredient.name}, "
            f"qty={qty}, unit_cost={unit_cost}, total={total_cost}{note_suffix}"
        ),
        ip_address=_client_ip(request),
    )
    return _build_po_response(db, po)


@purchase_order_router.get("/{po_id}", response_model=PurchaseOrderResponse)
async def get_purchase_order(
    po_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(RoleEnum.OWNER, RoleEnum.PRODUCTION_MANAGER)
    ),
):
    po = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).first()
    if not po:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Purchase order not found"
        )
    return _build_po_response(db, po)


@purchase_order_router.post(
    "/{po_id}/approve", response_model=PurchaseOrderResponse
)
async def approve_purchase_order(
    po_id: UUID,
    body: PurchaseOrderApprovePayload,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(RoleEnum.OWNER, RoleEnum.PRODUCTION_MANAGER)
    ),
):
    po = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).first()
    if not po:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Purchase order not found"
        )
    if not _can_approve(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the Owner can approve purchase orders",
        )
    if _status_value(po.status) != PurchaseOrderStatus.PENDING.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Cannot approve PO in status '{_status_value(po.status)}'. "
                "Only PENDING orders can be approved."
            ),
        )

    po.status = PurchaseOrderStatus.APPROVED
    db.commit()
    db.refresh(po)

    note_suffix = f" | note: {body.note}" if body.note else ""
    log_action(
        db,
        user_id=current_user.id,
        action="purchase_order_approved",
        resource="purchase_order",
        resource_id=str(po.id),
        details=f"PO approved by owner{note_suffix}",
        ip_address=_client_ip(request),
    )
    return _build_po_response(db, po)


@purchase_order_router.post("/{po_id}/send", response_model=PurchaseOrderResponse)
async def send_purchase_order(
    po_id: UUID,
    body: PurchaseOrderSendPayload,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(RoleEnum.OWNER, RoleEnum.PRODUCTION_MANAGER)
    ),
):
    po = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).first()
    if not po:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Purchase order not found"
        )
    if _status_value(po.status) != PurchaseOrderStatus.APPROVED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Cannot send PO in status '{_status_value(po.status)}'. "
                "Only APPROVED orders can be sent."
            ),
        )

    if body.expected_delivery is not None:
        po.expected_delivery = body.expected_delivery
    elif po.expected_delivery is None:
        supplier = db.query(Supplier).filter(Supplier.id == po.supplier_id).first()
        lead_time = (
            supplier.lead_time_days
            if supplier and supplier.lead_time_days
            else 0
        )
        po.expected_delivery = po.order_date + timedelta(days=lead_time)

    po.status = PurchaseOrderStatus.SENT
    db.commit()
    db.refresh(po)

    note_suffix = f" | note: {body.note}" if body.note else ""
    log_action(
        db,
        user_id=current_user.id,
        action="purchase_order_sent",
        resource="purchase_order",
        resource_id=str(po.id),
        details=(
            f"PO sent to supplier; expected_delivery={po.expected_delivery}{note_suffix}"
        ),
        ip_address=_client_ip(request),
    )
    return _build_po_response(db, po)


@purchase_order_router.post(
    "/{po_id}/receive", response_model=PurchaseOrderResponse
)
async def receive_purchase_order(
    po_id: UUID,
    body: PurchaseOrderReceivePayload,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(RoleEnum.OWNER, RoleEnum.PRODUCTION_MANAGER)
    ),
):
    po = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).first()
    if not po:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Purchase order not found"
        )
    if _status_value(po.status) != PurchaseOrderStatus.SENT.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Cannot receive PO in status '{_status_value(po.status)}'. "
                "Only SENT orders can be received."
            ),
        )

    po.status = PurchaseOrderStatus.RECEIVED
    po.actual_delivery = body.actual_delivery or date.today()
    _credit_inventory_for_received_po(db, po)

    db.commit()
    db.refresh(po)

    note_suffix = f" | note: {body.note}" if body.note else ""
    log_action(
        db,
        user_id=current_user.id,
        action="purchase_order_received",
        resource="purchase_order",
        resource_id=str(po.id),
        details=(
            f"PO received and inventory credited: qty={po.quantity}, "
            f"actual_delivery={po.actual_delivery}{note_suffix}"
        ),
        ip_address=_client_ip(request),
    )
    return _build_po_response(db, po)


@purchase_order_router.post(
    "/{po_id}/cancel", response_model=PurchaseOrderResponse
)
async def cancel_purchase_order(
    po_id: UUID,
    body: PurchaseOrderCancelPayload,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(RoleEnum.OWNER, RoleEnum.PRODUCTION_MANAGER)
    ),
):
    po = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).first()
    if not po:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Purchase order not found"
        )

    current_status = _status_value(po.status)
    terminal = {
        PurchaseOrderStatus.RECEIVED.value,
        PurchaseOrderStatus.CANCELLED.value,
    }
    if current_status in terminal:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel PO in terminal status '{current_status}'",
        )
    if not _can_cancel(current_user, po):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Only the Owner can cancel a non-PENDING purchase order. "
                "The original creator can cancel only while the PO is still PENDING."
            ),
        )

    previous_status = current_status
    po.status = PurchaseOrderStatus.CANCELLED
    db.commit()
    db.refresh(po)

    reason_suffix = f" | reason: {body.reason}" if body.reason else ""
    log_action(
        db,
        user_id=current_user.id,
        action="purchase_order_cancelled",
        resource="purchase_order",
        resource_id=str(po.id),
        details=f"PO cancelled from status '{previous_status}'{reason_suffix}",
        ip_address=_client_ip(request),
    )
    return _build_po_response(db, po)


# ---------------------------------------------------------------------------
# Reorder suggestions  (mounted at /reorder-suggestions)
# ---------------------------------------------------------------------------


def _rank_suppliers_for_ingredient(
    db: Session, ingredient_id: UUID
) -> List[ReorderSupplierOption]:
    """For one ingredient, return all active suppliers ranked by:
      1. has_history (suppliers who have shipped this ingredient before win)
      2. lead_time_days asc (faster delivery preferred; nulls treated as +inf)
      3. last_order_date desc (more recent vendor relationship preferred)
    """
    suppliers = (
        db.query(Supplier).filter(Supplier.is_active.is_(True)).all()
    )
    options: List[ReorderSupplierOption] = []
    for sup in suppliers:
        last_po = (
            db.query(PurchaseOrder)
            .filter(
                PurchaseOrder.supplier_id == sup.id,
                PurchaseOrder.ingredient_id == ingredient_id,
                PurchaseOrder.status != PurchaseOrderStatus.CANCELLED,
            )
            .order_by(desc(PurchaseOrder.order_date))
            .first()
        )
        options.append(
            ReorderSupplierOption(
                supplier_id=sup.id,
                supplier_name=sup.name,
                lead_time_days=sup.lead_time_days,
                last_unit_cost=_to_decimal(last_po.unit_cost) if last_po else None,
                last_order_date=last_po.order_date if last_po else None,
                has_history=last_po is not None,
            )
        )

    BIG = 10**9

    def sort_key(opt: ReorderSupplierOption):
        return (
            0 if opt.has_history else 1,
            opt.lead_time_days if opt.lead_time_days is not None else BIG,
            -(opt.last_order_date.toordinal()) if opt.last_order_date else 0,
        )

    options.sort(key=sort_key)
    return options


@reorder_router.get("/", response_model=ReorderSuggestionResponse)
async def get_reorder_suggestions(
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(RoleEnum.OWNER, RoleEnum.PRODUCTION_MANAGER)
    ),
):
    """Returns ingredients in the production inventory whose current quantity
    is below their min_threshold, with a suggested reorder quantity and a
    ranked list of supplier options for each.

    Algorithm:
      shortage_qty   = min_threshold - current_qty
      suggested_qty  = (2 * min_threshold) - current_qty
                       (i.e. refill to 2x min_threshold — classic min/max policy)
    """
    inv = (
        db.query(Inventory).filter(Inventory.location_type == "production").first()
    )
    if inv is None:
        return ReorderSuggestionResponse(items=[])

    low_stocks = (
        db.query(InventoryStock)
        .filter(
            InventoryStock.inventory_id == inv.id,
            InventoryStock.ingredient_id.isnot(None),
            InventoryStock.min_threshold.isnot(None),
            InventoryStock.quantity < InventoryStock.min_threshold,
        )
        .all()
    )

    items: List[ReorderSuggestionItem] = []
    for stock in low_stocks:
        ingredient = (
            db.query(Ingredient)
            .filter(Ingredient.id == stock.ingredient_id)
            .first()
        )
        if ingredient is None or not ingredient.is_active:
            continue

        current_qty = _to_decimal(stock.quantity)
        min_threshold = _to_decimal(stock.min_threshold)
        shortage_qty = max(Decimal("0"), min_threshold - current_qty)
        suggested_qty = (min_threshold * 2) - current_qty
        if suggested_qty < shortage_qty:
            suggested_qty = shortage_qty

        items.append(
            ReorderSuggestionItem(
                ingredient_id=ingredient.id,
                ingredient_name=ingredient.name,
                ingredient_unit=ingredient.unit,
                current_qty=current_qty,
                min_threshold=min_threshold,
                shortage_qty=shortage_qty.quantize(Decimal("0.001")),
                suggested_qty=suggested_qty.quantize(Decimal("0.001")),
                suppliers=_rank_suppliers_for_ingredient(db, ingredient.id),
            )
        )

    items.sort(key=lambda it: it.shortage_qty, reverse=True)
    return ReorderSuggestionResponse(items=items)
