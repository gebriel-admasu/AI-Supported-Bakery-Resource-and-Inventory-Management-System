from typing import List, Optional
from uuid import UUID

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
from app.schemas.wastage import WastageCreate, WastageResponse

router = APIRouter()


def _wastage_response(db: Session, record: WastageRecord) -> dict:
    store = db.query(Store).filter(Store.id == record.store_id).first()
    product = db.query(Product).filter(Product.id == record.product_id).first()
    ingredient = (
        db.query(Ingredient).filter(Ingredient.id == record.ingredient_id).first()
        if record.ingredient_id
        else None
    )
    recorder = db.query(User).filter(User.id == record.recorded_by).first() if record.recorded_by else None
    return {
        "id": record.id,
        "source_type": record.source_type.value if record.source_type else "store",
        "store_id": record.store_id,
        "store_name": store.name if store else None,
        "product_id": record.product_id,
        "product_name": product.name if product else None,
        "ingredient_id": record.ingredient_id,
        "ingredient_name": ingredient.name if ingredient else None,
        "date": record.date,
        "quantity": record.quantity,
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
        record = WastageRecord(
            source_type=source_type,
            store_id=body.store_id,
            product_id=body.product_id,
            ingredient_id=None,
            date=body.date,
            quantity=body.quantity,
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

        record = WastageRecord(
            source_type=source_type,
            store_id=None,
            product_id=body.product_id,
            ingredient_id=body.ingredient_id,
            date=body.date,
            quantity=body.quantity,
            reason=WastageReason(body.reason),
            notes=body.notes,
            recorded_by=current_user.id,
        )
    db.add(record)
    db.commit()
    db.refresh(record)
    return _wastage_response(db, record)
