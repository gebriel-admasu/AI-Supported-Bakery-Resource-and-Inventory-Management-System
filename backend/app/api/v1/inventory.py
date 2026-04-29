from decimal import Decimal
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.deps import require_role
from app.core.constants import AlertStatus, RoleEnum
from app.models.inventory import Inventory, InventoryStock, StockAlert
from app.models.ingredient import Ingredient
from app.models.product import Product
from app.models.user import User
from app.schemas.inventory import (
    InventoryStockResponse,
    StockAlertResponse,
    StockUpdatePayload,
)

router = APIRouter()


class StockCreatePayload(BaseModel):
    ingredient_id: UUID
    quantity: Decimal
    min_threshold: Optional[Decimal] = None


def get_or_create_production_inventory(db: Session) -> Inventory:
    inv = db.query(Inventory).filter(Inventory.location_type == "production").first()
    if inv:
        return inv
    inv = Inventory(location_type="production", location_id=None)
    db.add(inv)
    db.commit()
    db.refresh(inv)
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

    is_low_stock = (
        stock.min_threshold is not None
        and stock.quantity < stock.min_threshold
    )

    if is_low_stock:
        if active_alerts:
            for alert in active_alerts:
                alert.current_qty = stock.quantity
                alert.min_qty = stock.min_threshold
                alert.timestamp = datetime.now(timezone.utc)
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
        alert.min_qty = stock.min_threshold if stock.min_threshold is not None else alert.min_qty


@router.get("/stocks", response_model=List[InventoryStockResponse])
async def list_stocks(
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(RoleEnum.OWNER, RoleEnum.PRODUCTION_MANAGER)
    ),
):
    inv = get_or_create_production_inventory(db)
    rows = (
        db.query(InventoryStock, Ingredient.name, Product.name)
        .outerjoin(Ingredient, InventoryStock.ingredient_id == Ingredient.id)
        .outerjoin(Product, InventoryStock.product_id == Product.id)
        .filter(InventoryStock.inventory_id == inv.id)
        .order_by(InventoryStock.updated_at.desc())
        .all()
    )
    result: List[InventoryStockResponse] = []
    for stock, ingredient_name, product_name in rows:
        result.append(
            InventoryStockResponse(
                id=stock.id,
                inventory_id=stock.inventory_id,
                ingredient_id=stock.ingredient_id,
                product_id=stock.product_id,
                quantity=Decimal(stock.quantity),
                min_threshold=(
                    Decimal(stock.min_threshold) if stock.min_threshold is not None else None
                ),
                ingredient_name=ingredient_name,
                product_name=product_name,
                updated_at=stock.updated_at,
            )
        )
    return result


@router.put("/stocks/{stock_id}", response_model=InventoryStockResponse)
async def update_stock(
    stock_id: UUID,
    body: StockUpdatePayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(RoleEnum.OWNER, RoleEnum.PRODUCTION_MANAGER)
    ),
):
    inv = get_or_create_production_inventory(db)
    stock = db.query(InventoryStock).filter(InventoryStock.id == stock_id).first()
    if not stock or stock.inventory_id != inv.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stock not found")

    stock.quantity = body.quantity
    update_data = body.model_dump(exclude_unset=True)
    if "min_threshold" in update_data:
        stock.min_threshold = update_data["min_threshold"]

    _sync_low_stock_alert(db, stock)
    db.commit()
    db.refresh(stock)

    ing_name = None
    if stock.ingredient_id:
        ing = db.query(Ingredient).filter(Ingredient.id == stock.ingredient_id).first()
        if ing:
            ing_name = ing.name
    prod_name = None
    if stock.product_id:
        prod = db.query(Product).filter(Product.id == stock.product_id).first()
        if prod:
            prod_name = prod.name

    return InventoryStockResponse(
        id=stock.id,
        inventory_id=stock.inventory_id,
        ingredient_id=stock.ingredient_id,
        product_id=stock.product_id,
        quantity=Decimal(stock.quantity),
        min_threshold=Decimal(stock.min_threshold) if stock.min_threshold is not None else None,
        ingredient_name=ing_name,
        product_name=prod_name,
        updated_at=stock.updated_at,
    )


@router.post("/stocks", response_model=InventoryStockResponse, status_code=status.HTTP_201_CREATED)
async def create_stock(
    body: StockCreatePayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(RoleEnum.OWNER, RoleEnum.PRODUCTION_MANAGER)
    ),
):
    ingredient = db.query(Ingredient).filter(Ingredient.id == body.ingredient_id).first()
    if not ingredient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ingredient not found",
        )

    inv = get_or_create_production_inventory(db)
    duplicate = (
        db.query(InventoryStock)
        .filter(
            InventoryStock.inventory_id == inv.id,
            InventoryStock.ingredient_id == body.ingredient_id,
        )
        .first()
    )
    if duplicate:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A stock entry for this ingredient already exists in production inventory",
        )

    stock = InventoryStock(
        inventory_id=inv.id,
        ingredient_id=body.ingredient_id,
        quantity=body.quantity,
        min_threshold=body.min_threshold,
    )
    db.add(stock)
    db.flush()
    _sync_low_stock_alert(db, stock)
    db.commit()
    db.refresh(stock)

    return InventoryStockResponse(
        id=stock.id,
        inventory_id=stock.inventory_id,
        ingredient_id=stock.ingredient_id,
        product_id=stock.product_id,
        quantity=Decimal(stock.quantity),
        min_threshold=Decimal(stock.min_threshold) if stock.min_threshold is not None else None,
        ingredient_name=ingredient.name,
        product_name=None,
        updated_at=stock.updated_at,
    )


@router.get("/alerts", response_model=List[StockAlertResponse])
async def list_active_alerts(
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(RoleEnum.OWNER, RoleEnum.PRODUCTION_MANAGER)
    ),
):
    rows = (
        db.query(StockAlert, Ingredient.name)
        .outerjoin(Ingredient, StockAlert.ingredient_id == Ingredient.id)
        .filter(StockAlert.status == AlertStatus.ACTIVE)
        .order_by(StockAlert.timestamp.desc())
        .all()
    )
    result: List[StockAlertResponse] = []
    for alert, ingredient_name in rows:
        result.append(
            StockAlertResponse(
                id=alert.id,
                inventory_stock_id=alert.inventory_stock_id,
                ingredient_id=alert.ingredient_id,
                current_qty=Decimal(alert.current_qty),
                min_qty=Decimal(alert.min_qty),
                status=alert.status.value,
                timestamp=alert.timestamp,
                ingredient_name=ingredient_name,
            )
        )
    return result
