from decimal import Decimal
from datetime import date
from typing import Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.deps import require_role
from app.core.constants import AlertStatus, BatchStatus, RoleEnum, WastageReason, WastageSourceType
from app.models.production import ProductionBatch
from app.models.recipe import Recipe, RecipeIngredient
from app.models.ingredient import Ingredient
from app.models.product import Product
from app.models.distribution import DistributionItem
from app.models.inventory import Inventory, InventoryStock, StockAlert
from app.models.user import User
from app.models.wastage import WastageRecord
from app.services.recipe_costing import resolve_recipe_unit_cost
from app.schemas.production import (
    BatchCreate,
    BatchUpdate,
    BatchResponse,
    ProductionStockSummaryItem,
)

router = APIRouter()


def _to_decimal(value: object) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _resolve_product_wastage_unit_cost(db: Session, product_id: UUID) -> tuple[Decimal, str, bool]:
    recipe_id_row = db.query(Product.recipe_id).filter(Product.id == product_id).first()
    if not recipe_id_row:
        return Decimal("0"), "fallback_zero", True
    unit_cost = resolve_recipe_unit_cost(db, recipe_id_row[0])
    if unit_cost <= 0:
        return Decimal("0"), "fallback_zero", True
    return unit_cost, "product_recipe_cost", False


def _resolve_product_wastage_unit_price(db: Session, product_id: UUID) -> Decimal:
    row = (
        db.query(Product.sale_price)
        .filter(Product.id == product_id)
        .first()
    )
    if not row or row[0] is None:
        return Decimal("0")
    return _to_decimal(row[0])


def _sync_production_product_wastage(
    db: Session,
    batch: ProductionBatch,
    recorded_by: Optional[UUID],
) -> bool:
    waste_qty = int(batch.waste_qty or 0)
    if waste_qty <= 0:
        return False

    auto_note = f"Auto-created from production batch {batch.id}"
    unit_price_snapshot = _resolve_product_wastage_unit_price(db, batch.product_id)
    unit_cost_snapshot, cost_source, is_estimated_cost = _resolve_product_wastage_unit_cost(
        db, batch.product_id
    )
    total_price_snapshot = unit_price_snapshot * Decimal(waste_qty)
    total_cost_snapshot = unit_cost_snapshot * Decimal(waste_qty)

    existing = (
        db.query(WastageRecord)
        .filter(
            WastageRecord.source_type == WastageSourceType.PRODUCTION,
            WastageRecord.product_id == batch.product_id,
            WastageRecord.ingredient_id.is_(None),
            WastageRecord.date == batch.production_date,
            WastageRecord.reason == WastageReason.PRODUCTION_LOSS,
            WastageRecord.notes == auto_note,
        )
        .first()
    )
    if existing:
        changed = False
        if existing.quantity != waste_qty:
            existing.quantity = waste_qty
            changed = True
        if _to_decimal(existing.unit_price_snapshot) != unit_price_snapshot:
            existing.unit_price_snapshot = unit_price_snapshot
            changed = True
        if _to_decimal(existing.total_price_snapshot) != total_price_snapshot:
            existing.total_price_snapshot = total_price_snapshot
            changed = True
        if _to_decimal(existing.unit_cost_snapshot) != unit_cost_snapshot:
            existing.unit_cost_snapshot = unit_cost_snapshot
            changed = True
        if _to_decimal(existing.total_cost_snapshot) != total_cost_snapshot:
            existing.total_cost_snapshot = total_cost_snapshot
            changed = True
        if (existing.cost_source or "") != cost_source:
            existing.cost_source = cost_source
            changed = True
        if bool(existing.is_estimated_cost) != is_estimated_cost:
            existing.is_estimated_cost = is_estimated_cost
            changed = True
        if recorded_by and not existing.recorded_by:
            existing.recorded_by = recorded_by
            changed = True
        return changed

    db.add(
        WastageRecord(
            source_type=WastageSourceType.PRODUCTION,
            store_id=None,
            product_id=batch.product_id,
            ingredient_id=None,
            date=batch.production_date,
            quantity=waste_qty,
            unit_price_snapshot=unit_price_snapshot,
            total_price_snapshot=total_price_snapshot,
            unit_cost_snapshot=unit_cost_snapshot,
            total_cost_snapshot=total_cost_snapshot,
            cost_source=cost_source,
            is_estimated_cost=is_estimated_cost,
            reason=WastageReason.PRODUCTION_LOSS,
            notes=auto_note,
            recorded_by=recorded_by,
        )
    )
    return True


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
        if ingredient and ingredient.expiry_date and ingredient.expiry_date < date.today():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot use expired ingredient '{ing_name}'. Expired on {ingredient.expiry_date}",
            )

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
    has_changes = False
    for batch in batches:
        if batch.status == BatchStatus.COMPLETED:
            has_changes = _sync_production_product_wastage(db, batch, batch.created_by) or has_changes
    if has_changes:
        db.commit()
    return [_batch_response(db, b) for b in batches]


@router.get("/stock-summary", response_model=List[ProductionStockSummaryItem])
async def production_stock_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(RoleEnum.OWNER, RoleEnum.PRODUCTION_MANAGER)
    ),
):
    produced_rows = (
        db.query(
            ProductionBatch.product_id.label("product_id"),
            Product.name.label("product_name"),
            Product.sku.label("product_sku"),
            func.coalesce(func.sum(ProductionBatch.actual_yield), 0).label("produced_qty"),
        )
        .join(Product, Product.id == ProductionBatch.product_id)
        .filter(ProductionBatch.status == BatchStatus.COMPLETED)
        .group_by(ProductionBatch.product_id, Product.name, Product.sku)
        .all()
    )
    dispatched_rows = (
        db.query(
            DistributionItem.product_id.label("product_id"),
            func.coalesce(func.sum(DistributionItem.quantity_sent), 0).label("dispatched_qty"),
        )
        .group_by(DistributionItem.product_id)
        .all()
    )

    summary_by_product: Dict[UUID, dict] = {}
    for row in produced_rows:
        summary_by_product[row.product_id] = {
            "product_id": row.product_id,
            "product_name": row.product_name,
            "product_sku": row.product_sku,
            "produced_qty": int(row.produced_qty or 0),
            "dispatched_qty": 0,
            "remaining_qty": int(row.produced_qty or 0),
        }

    for row in dispatched_rows:
        product_id = row.product_id
        dispatched_qty = int(row.dispatched_qty or 0)
        if product_id not in summary_by_product:
            product = db.query(Product).filter(Product.id == product_id).first()
            summary_by_product[product_id] = {
                "product_id": product_id,
                "product_name": product.name if product else "Unknown",
                "product_sku": product.sku if product else None,
                "produced_qty": 0,
                "dispatched_qty": dispatched_qty,
                "remaining_qty": -dispatched_qty,
            }
            continue

        summary_by_product[product_id]["dispatched_qty"] = dispatched_qty
        summary_by_product[product_id]["remaining_qty"] = (
            summary_by_product[product_id]["produced_qty"] - dispatched_qty
        )

    return sorted(
        summary_by_product.values(),
        key=lambda item: ((item["product_name"] or "").lower(), item["product_sku"] or ""),
    )


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
    if batch.status == BatchStatus.COMPLETED:
        if _sync_production_product_wastage(db, batch, batch.created_by):
            db.commit()
            db.refresh(batch)
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
            _sync_production_product_wastage(db, batch, current_user.id)
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
