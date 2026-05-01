from typing import List, Optional
from uuid import UUID
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.deps import require_role
from app.core.constants import RoleEnum, WastageReason, WastageSourceType, AlertStatus
from app.models.wastage import WastageRecord
from app.models.product import Product
from app.models.ingredient import Ingredient
from app.models.store import Store
from app.models.user import User
from app.models.inventory import Inventory, InventoryStock, StockAlert
from app.services.recipe_costing import resolve_recipe_unit_cost
from app.schemas.wastage import WastageCreate, WastageResponse

router = APIRouter()


def _to_decimal(value: object) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _resolve_product_unit_cost(db: Session, product_id: Optional[UUID]) -> Optional[Decimal]:
    if not product_id:
        return None
    recipe_id_row = db.query(Product.recipe_id).filter(Product.id == product_id).first()
    if not recipe_id_row:
        return None
    return resolve_recipe_unit_cost(db, recipe_id_row[0])


def _resolve_wastage_cost_snapshot(
    db: Session,
    source_type: WastageSourceType,
    product_id: Optional[UUID],
    ingredient_id: Optional[UUID],
) -> dict:
    unit_cost = Decimal("0")
    cost_source = "fallback_zero"
    is_estimated = True

    if ingredient_id:
        ingredient = db.query(Ingredient).filter(Ingredient.id == ingredient_id).first()
        if ingredient and ingredient.unit_cost is not None:
            unit_cost = _to_decimal(ingredient.unit_cost)
            cost_source = "ingredient_unit_cost"
            is_estimated = False
    elif source_type == WastageSourceType.STORE or product_id:
        product_cost = _resolve_product_unit_cost(db, product_id)
        if product_cost is not None:
            unit_cost = _to_decimal(product_cost)
            cost_source = "product_recipe_cost"
            is_estimated = False

    return {
        "unit_cost_snapshot": unit_cost,
        "cost_source": cost_source,
        "is_estimated_cost": is_estimated or unit_cost <= 0,
    }


def _wastage_response(db: Session, record: WastageRecord) -> dict:
    store = db.query(Store).filter(Store.id == record.store_id).first()
    product = db.query(Product).filter(Product.id == record.product_id).first()
    ingredient = (
        db.query(Ingredient).filter(Ingredient.id == record.ingredient_id).first()
        if record.ingredient_id
        else None
    )
    recorder = db.query(User).filter(User.id == record.recorded_by).first() if record.recorded_by else None
    unit_price = _to_decimal(record.unit_price_snapshot) if record.unit_price_snapshot is not None else None
    if unit_price is None and product and product.sale_price is not None:
        unit_price = _to_decimal(product.sale_price)
    total_price = _to_decimal(record.total_price_snapshot) if record.total_price_snapshot is not None else None
    if total_price is None and unit_price is not None:
        total_price = unit_price * Decimal(record.quantity)
    return {
        "id": record.id,
        "source_type": record.source_type.value if record.source_type else "store",
        "store_id": record.store_id,
        "store_name": store.name if store else None,
        "product_id": record.product_id,
        "product_name": product.name if product else None,
        "product_unit": product.unit if product else None,
        "ingredient_id": record.ingredient_id,
        "ingredient_name": ingredient.name if ingredient else None,
        "ingredient_unit": ingredient.unit if ingredient else None,
        "date": record.date,
        "quantity": record.quantity,
        "unit_price": float(unit_price) if unit_price is not None else None,
        "total_price": float(total_price) if total_price is not None else None,
        "unit_cost_snapshot": float(record.unit_cost_snapshot or 0) if record.unit_cost_snapshot is not None else None,
        "total_cost_snapshot": float(record.total_cost_snapshot or 0) if record.total_cost_snapshot is not None else None,
        "cost_source": record.cost_source,
        "is_estimated_cost": bool(record.is_estimated_cost),
        "reason": record.reason.value if record.reason else record.reason,
        "notes": record.notes,
        "recorded_by": record.recorded_by,
        "recorded_by_name": recorder.full_name if recorder else None,
        "created_at": record.created_at,
    }


def _get_production_inventory(db: Session) -> Inventory:
    inv = db.query(Inventory).filter(Inventory.location_type == "production").first()
    if inv:
        return inv
    inv = Inventory(location_type="production", location_id=None)
    db.add(inv)
    db.flush()
    return inv


def _sync_low_stock_alert(db: Session, stock: InventoryStock) -> None:
    active_alerts = (
        db.query(StockAlert)
        .filter(
            StockAlert.inventory_stock_id == stock.id,
            StockAlert.status == AlertStatus.ACTIVE,
        )
        .all()
    )
    is_low_stock = stock.min_threshold is not None and stock.quantity < stock.min_threshold
    if is_low_stock:
        if active_alerts:
            for alert in active_alerts:
                alert.current_qty = stock.quantity
                alert.min_qty = stock.min_threshold
            return
        db.add(
            StockAlert(
                inventory_stock_id=stock.id,
                ingredient_id=stock.ingredient_id,
                current_qty=stock.quantity,
                min_qty=stock.min_threshold,
                status=AlertStatus.ACTIVE,
            )
        )
        return
    for alert in active_alerts:
        alert.status = AlertStatus.RESOLVED
        alert.current_qty = stock.quantity
        if stock.min_threshold is not None:
            alert.min_qty = stock.min_threshold


@router.get("/", response_model=List[WastageResponse])
async def list_wastage(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    store_id: Optional[UUID] = None,
    product_id: Optional[UUID] = None,
    ingredient_id: Optional[UUID] = None,
    source_type: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(
            RoleEnum.OWNER,
            RoleEnum.FINANCE_MANAGER,
            RoleEnum.PRODUCTION_MANAGER,
            RoleEnum.STORE_MANAGER,
        )
    ),
):
    query = db.query(WastageRecord)
    if current_user.role == RoleEnum.STORE_MANAGER:
        query = query.filter(WastageRecord.source_type == WastageSourceType.STORE)
        if current_user.store_id:
            query = query.filter(WastageRecord.store_id == current_user.store_id)
    elif current_user.role == RoleEnum.PRODUCTION_MANAGER:
        query = query.filter(WastageRecord.source_type == WastageSourceType.PRODUCTION)

    if source_type:
        try:
            source_enum = WastageSourceType(source_type)
            query = query.filter(WastageRecord.source_type == source_enum)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid source_type: {source_type}",
            )
    if store_id:
        query = query.filter(WastageRecord.store_id == store_id)
    if product_id:
        query = query.filter(WastageRecord.product_id == product_id)
    if ingredient_id:
        query = query.filter(WastageRecord.ingredient_id == ingredient_id)
    records = (
        query.order_by(WastageRecord.date.desc(), WastageRecord.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [_wastage_response(db, r) for r in records]


@router.post("/", response_model=WastageResponse, status_code=status.HTTP_201_CREATED)
async def create_wastage(
    body: WastageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(RoleEnum.OWNER, RoleEnum.PRODUCTION_MANAGER, RoleEnum.STORE_MANAGER)
    ),
):
    if body.quantity < 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Quantity must be positive")

    try:
        source_type = WastageSourceType(body.source_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid source_type: {body.source_type}. Must be one of: {[s.value for s in WastageSourceType]}",
        )

    try:
        WastageReason(body.reason)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid reason: {body.reason}. Must be one of: {[r.value for r in WastageReason]}",
        )

    if current_user.role == RoleEnum.STORE_MANAGER and source_type != WastageSourceType.STORE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Store manager can only record store wastage",
        )
    if current_user.role == RoleEnum.PRODUCTION_MANAGER and source_type != WastageSourceType.PRODUCTION:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Production manager can only record production wastage",
        )

    if source_type == WastageSourceType.STORE:
        if not body.store_id or not body.product_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="store_id and product_id are required for store wastage",
            )
        if current_user.role == RoleEnum.STORE_MANAGER and current_user.store_id != body.store_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Store manager can only record wastage for own store",
            )
        store = db.query(Store).filter(Store.id == body.store_id, Store.is_active == True).first()
        if not store:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Active store not found")
        product = db.query(Product).filter(Product.id == body.product_id, Product.is_active == True).first()
        if not product:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Active product not found")
        unit_price_snapshot = _to_decimal(product.sale_price)
        cost_snapshot = _resolve_wastage_cost_snapshot(
            db=db,
            source_type=source_type,
            product_id=body.product_id,
            ingredient_id=None,
        )
        total_price_snapshot = unit_price_snapshot * Decimal(body.quantity)
        total_cost_snapshot = cost_snapshot["unit_cost_snapshot"] * Decimal(body.quantity)
        record = WastageRecord(
            source_type=source_type,
            store_id=body.store_id,
            product_id=body.product_id,
            ingredient_id=None,
            date=body.date,
            quantity=body.quantity,
            unit_price_snapshot=unit_price_snapshot,
            total_price_snapshot=total_price_snapshot,
            unit_cost_snapshot=cost_snapshot["unit_cost_snapshot"],
            total_cost_snapshot=total_cost_snapshot,
            cost_source=cost_snapshot["cost_source"],
            is_estimated_cost=cost_snapshot["is_estimated_cost"],
            reason=WastageReason(body.reason),
            notes=body.notes,
            recorded_by=current_user.id,
        )
    else:
        if not body.ingredient_id and not body.product_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either ingredient_id or product_id is required for production wastage",
            )
        if body.ingredient_id and body.product_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Provide either ingredient_id or product_id, not both, for production wastage",
            )

        unit_price_snapshot: Optional[Decimal] = None
        total_price_snapshot: Optional[Decimal] = None
        if body.ingredient_id:
            ingredient = (
                db.query(Ingredient)
                .filter(Ingredient.id == body.ingredient_id, Ingredient.is_active == True)
                .first()
            )
            if not ingredient:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Active ingredient not found")
            production_inv = _get_production_inventory(db)
            stock = (
                db.query(InventoryStock)
                .filter(
                    InventoryStock.inventory_id == production_inv.id,
                    InventoryStock.ingredient_id == body.ingredient_id,
                )
                .first()
            )
            if not stock:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"No production inventory stock found for ingredient '{ingredient.name}'",
                )
            if stock.quantity < body.quantity:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Insufficient ingredient stock for '{ingredient.name}'. Have {stock.quantity}, need {body.quantity}",
                )
            stock.quantity = stock.quantity - body.quantity
            _sync_low_stock_alert(db, stock)
        else:
            product = (
                db.query(Product)
                .filter(Product.id == body.product_id, Product.is_active == True)
                .first()
            )
            if not product:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Active product not found")
            unit_price_snapshot = _to_decimal(product.sale_price)
            total_price_snapshot = unit_price_snapshot * Decimal(body.quantity)

        cost_snapshot = _resolve_wastage_cost_snapshot(
            db=db,
            source_type=source_type,
            product_id=body.product_id,
            ingredient_id=body.ingredient_id,
        )
        total_cost_snapshot = cost_snapshot["unit_cost_snapshot"] * Decimal(body.quantity)
        record = WastageRecord(
            source_type=source_type,
            store_id=None,
            product_id=body.product_id,
            ingredient_id=body.ingredient_id,
            date=body.date,
            quantity=body.quantity,
            unit_price_snapshot=unit_price_snapshot,
            total_price_snapshot=total_price_snapshot,
            unit_cost_snapshot=cost_snapshot["unit_cost_snapshot"],
            total_cost_snapshot=total_cost_snapshot,
            cost_source=cost_snapshot["cost_source"],
            is_estimated_cost=cost_snapshot["is_estimated_cost"],
            reason=WastageReason(body.reason),
            notes=body.notes,
            recorded_by=current_user.id,
        )
    db.add(record)
    db.commit()
    db.refresh(record)
    return _wastage_response(db, record)
