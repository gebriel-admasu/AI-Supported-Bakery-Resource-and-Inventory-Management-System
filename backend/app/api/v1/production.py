from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.deps import require_role
from app.core.constants import BatchStatus, RoleEnum, AlertStatus
from app.models.production import ProductionBatch
from app.models.recipe import Recipe, RecipeIngredient
from app.models.ingredient import Ingredient
from app.models.product import Product
from app.models.inventory import Inventory, InventoryStock, StockAlert
from app.models.user import User
from app.schemas.production import BatchCreate, BatchUpdate, BatchResponse

router = APIRouter()


def _batch_response(db: Session, batch: ProductionBatch) -> dict:
    recipe = db.query(Recipe).filter(Recipe.id == batch.recipe_id).first()
    product = db.query(Product).filter(Product.id == batch.product_id).first()
    return {
        "id": batch.id,
        "recipe_id": batch.recipe_id,
        "recipe_name": recipe.name if recipe else None,
        "product_id": batch.product_id,
        "product_name": product.name if product else None,
        "batch_size": batch.batch_size,
        "actual_yield": batch.actual_yield,
        "waste_qty": batch.waste_qty,
        "production_date": batch.production_date,
        "status": batch.status.value if batch.status else "planned",
        "created_by": batch.created_by,
        "created_at": batch.created_at,
        "updated_at": batch.updated_at,
    }


def _get_production_inventory(db: Session) -> Inventory:
    inv = db.query(Inventory).filter(Inventory.location_type == "production").first()
    if not inv:
        inv = Inventory(location_type="production", location_id=None)
        db.add(inv)
        db.flush()
    return inv


def _deduct_ingredients(db: Session, recipe_id: UUID, multiplier: int) -> None:
    """Deduct ingredient quantities from production inventory based on recipe."""
    inv = _get_production_inventory(db)
    recipe_ingredients = (
        db.query(RecipeIngredient)
        .filter(RecipeIngredient.recipe_id == recipe_id)
        .all()
    )

    for ri in recipe_ingredients:
        ingredient = db.query(Ingredient).filter(Ingredient.id == ri.ingredient_id).first()
        ing_name = ingredient.name if ingredient else str(ri.ingredient_id)

        required = Decimal(str(ri.quantity_required)) * multiplier
        stock = (
            db.query(InventoryStock)
            .filter(
                InventoryStock.inventory_id == inv.id,
                InventoryStock.ingredient_id == ri.ingredient_id,
            )
            .first()
        )
        if not stock:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No stock entry for '{ing_name}'. "
                       f"Add it to inventory before starting production.",
            )
        if Decimal(str(stock.quantity)) < required:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Insufficient stock for '{ing_name}'. "
                       f"Need {required}, have {stock.quantity}.",
            )
        stock.quantity = Decimal(str(stock.quantity)) - required

        if stock.min_threshold is not None and stock.quantity < stock.min_threshold:
            existing_alert = (
                db.query(StockAlert)
                .filter(
                    StockAlert.inventory_stock_id == stock.id,
                    StockAlert.status == AlertStatus.ACTIVE,
                )
                .first()
            )
            if not existing_alert:
                db.add(StockAlert(
                    inventory_stock_id=stock.id,
                    ingredient_id=stock.ingredient_id,
                    current_qty=stock.quantity,
                    min_qty=stock.min_threshold,
                    status=AlertStatus.ACTIVE,
                ))


@router.get("/batches", response_model=List[BatchResponse])
async def list_batches(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(RoleEnum.OWNER, RoleEnum.PRODUCTION_MANAGER)
    ),
):
    query = db.query(ProductionBatch)
    if status_filter:
        try:
            batch_status = BatchStatus(status_filter)
            query = query.filter(ProductionBatch.status == batch_status)
        except ValueError:
            pass
    batches = (
        query.order_by(ProductionBatch.production_date.desc(), ProductionBatch.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [_batch_response(db, b) for b in batches]


@router.get("/batches/{batch_id}", response_model=BatchResponse)
async def get_batch(
    batch_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(RoleEnum.OWNER, RoleEnum.PRODUCTION_MANAGER)
    ),
):
    batch = db.query(ProductionBatch).filter(ProductionBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found")
    return _batch_response(db, batch)


@router.post("/batches", response_model=BatchResponse, status_code=status.HTTP_201_CREATED)
async def create_batch(
    body: BatchCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(RoleEnum.OWNER, RoleEnum.PRODUCTION_MANAGER)
    ),
):
    recipe = db.query(Recipe).filter(Recipe.id == body.recipe_id, Recipe.is_active == True).first()
    if not recipe:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Active recipe not found")

    product = db.query(Product).filter(Product.id == body.product_id, Product.is_active == True).first()
    if not product:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Active product not found")

    batch = ProductionBatch(
        recipe_id=body.recipe_id,
        product_id=body.product_id,
        batch_size=body.batch_size,
        production_date=body.production_date,
        status=BatchStatus.PLANNED,
        created_by=current_user.id,
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return _batch_response(db, batch)


@router.put("/batches/{batch_id}", response_model=BatchResponse)
async def update_batch(
    batch_id: UUID,
    body: BatchUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(RoleEnum.OWNER, RoleEnum.PRODUCTION_MANAGER)
    ),
):
    batch = db.query(ProductionBatch).filter(ProductionBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found")

    update_data = body.model_dump(exclude_unset=True)

    if "status" in update_data:
        new_status_str = update_data["status"]
        try:
            new_status = BatchStatus(new_status_str)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {new_status_str}",
            )

        old_status = batch.status

        if new_status == BatchStatus.IN_PROGRESS and old_status == BatchStatus.PLANNED:
            _deduct_ingredients(db, batch.recipe_id, batch.batch_size)
            batch.status = new_status
        elif new_status == BatchStatus.COMPLETED and old_status == BatchStatus.IN_PROGRESS:
            batch.status = new_status
            recipe = db.query(Recipe).filter(Recipe.id == batch.recipe_id).first()
            expected_output = batch.batch_size * (recipe.yield_qty if recipe and recipe.yield_qty else 1)

            if "actual_yield" in update_data:
                batch.actual_yield = update_data["actual_yield"]
            else:
                batch.actual_yield = expected_output

            if "waste_qty" in update_data:
                batch.waste_qty = update_data["waste_qty"]
            else:
                batch.waste_qty = max(0, expected_output - (batch.actual_yield or 0))
        elif new_status == BatchStatus.CANCELLED and old_status == BatchStatus.PLANNED:
            batch.status = new_status
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot transition from {old_status.value} to {new_status.value}",
            )
    else:
        if "actual_yield" in update_data:
            batch.actual_yield = update_data["actual_yield"]
        if "waste_qty" in update_data:
            batch.waste_qty = update_data["waste_qty"]

    db.commit()
    db.refresh(batch)
    return _batch_response(db, batch)
