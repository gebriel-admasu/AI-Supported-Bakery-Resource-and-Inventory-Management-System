from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.core.constants import RoleEnum, WastageReason, WastageSourceType
from app.database import get_db
from app.models.ingredient import Ingredient
from app.models.inventory import InventoryStock
from app.models.product import Product
from app.models.recipe import Recipe
from app.models.sales import SalesRecord
from app.models.user import User
from app.models.wastage import WastageRecord
from app.schemas.finance import FinanceSummaryResponse, PnlTrendResponse, ProductMarginResponse
from app.services.recipe_costing import resolve_recipe_unit_cost

router = APIRouter()


def _to_decimal(value: object) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _to_money_float(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _resolve_date_range(date_from: Optional[date], date_to: Optional[date]) -> tuple[date, date]:
    today = date.today()
    resolved_to = date_to or today
    resolved_from = date_from or (resolved_to - timedelta(days=29))
    if resolved_from > resolved_to:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="date_from cannot be after date_to",
        )
    return resolved_from, resolved_to


def _sales_rows(
    db: Session,
    date_from: date,
    date_to: date,
    store_id: Optional[UUID],
    product_id: Optional[UUID],
    finalized_only: bool,
):
    query = (
        db.query(
            SalesRecord.date.label("sales_date"),
            SalesRecord.product_id.label("product_id"),
            Product.recipe_id.label("recipe_id"),
            Product.name.label("product_name"),
            Product.sku.label("product_sku"),
            SalesRecord.quantity_sold.label("quantity_sold"),
            SalesRecord.total_amount.label("total_amount"),
            SalesRecord.cogs_amount.label("cogs_amount"),
            SalesRecord.unit_cogs_snapshot.label("unit_cogs_snapshot"),
            Recipe.cost_per_unit.label("fallback_unit_cogs"),
        )
        .join(Product, Product.id == SalesRecord.product_id)
        .outerjoin(Recipe, Recipe.id == Product.recipe_id)
        .filter(
            SalesRecord.date >= date_from,
            SalesRecord.date <= date_to,
        )
    )
    if finalized_only:
        query = query.filter(SalesRecord.is_closed == True)
    if store_id:
        query = query.filter(SalesRecord.store_id == store_id)
    if product_id:
        query = query.filter(SalesRecord.product_id == product_id)
    return query.all()


def _wastage_rows(
    db: Session,
    date_from: date,
    date_to: date,
    store_id: Optional[UUID],
    product_id: Optional[UUID],
):
    query = (
        db.query(
            WastageRecord.date.label("wastage_date"),
            WastageRecord.source_type.label("source_type"),
            WastageRecord.quantity.label("quantity"),
            WastageRecord.product_id.label("product_id"),
            Product.recipe_id.label("product_recipe_id"),
            WastageRecord.ingredient_id.label("ingredient_id"),
            WastageRecord.total_price_snapshot.label("total_price_snapshot"),
            WastageRecord.unit_price_snapshot.label("unit_price_snapshot"),
            WastageRecord.total_cost_snapshot.label("total_cost_snapshot"),
            WastageRecord.unit_cost_snapshot.label("unit_cost_snapshot"),
            WastageRecord.is_estimated_cost.label("is_estimated_cost"),
            Product.sale_price.label("product_sale_price"),
            Ingredient.unit_cost.label("ingredient_unit_cost"),
            Recipe.cost_per_unit.label("product_unit_cogs"),
        )
        .outerjoin(Product, Product.id == WastageRecord.product_id)
        .outerjoin(Recipe, Recipe.id == Product.recipe_id)
        .outerjoin(Ingredient, Ingredient.id == WastageRecord.ingredient_id)
        .filter(
            WastageRecord.date >= date_from,
            WastageRecord.date <= date_to,
        )
    )
    if product_id:
        query = query.filter(WastageRecord.product_id == product_id)
    if store_id:
        query = query.filter(
            WastageRecord.source_type == WastageSourceType.STORE,
            WastageRecord.store_id == store_id,
        )
    return query.all()


def _expired_ingredient_rows(
    db: Session,
    date_from: date,
    date_to: date,
    store_id: Optional[UUID],
    product_id: Optional[UUID],
):
    if store_id is not None or product_id is not None:
        return []

    logged_expiry_keys = {
        (row.ingredient_id, row.date)
        for row in (
            db.query(WastageRecord.ingredient_id, WastageRecord.date)
            .filter(
                WastageRecord.ingredient_id.isnot(None),
                WastageRecord.reason == WastageReason.EXPIRY,
                WastageRecord.date >= date_from,
                WastageRecord.date <= date_to,
            )
            .distinct()
            .all()
        )
    }

    rows = (
        db.query(
            Ingredient.id.label("ingredient_id"),
            Ingredient.expiry_date.label("expiry_date"),
            Ingredient.unit_cost.label("ingredient_unit_cost"),
            func.coalesce(func.sum(InventoryStock.quantity), 0).label("expired_qty"),
        )
        .join(InventoryStock, InventoryStock.ingredient_id == Ingredient.id)
        .filter(
            Ingredient.is_active == True,
            Ingredient.expiry_date.isnot(None),
            Ingredient.expiry_date >= date_from,
            Ingredient.expiry_date <= date_to,
            InventoryStock.quantity > 0,
        )
        .group_by(Ingredient.id, Ingredient.expiry_date, Ingredient.unit_cost)
        .all()
    )

    result = []
    for row in rows:
        key = (row.ingredient_id, row.expiry_date)
        if key in logged_expiry_keys:
            continue

        qty = _to_decimal(row.expired_qty)
        if qty <= 0:
            continue

        unit_cost = _to_decimal(row.ingredient_unit_cost)
        total_cost = unit_cost * qty
        result.append(
            {
                "date": row.expiry_date,
                "total_cost": total_cost,
                "missing_cost": unit_cost <= 0,
                "estimated_cost": True,
            }
        )
    return result


def _resolve_sales_row_cogs(db: Session, row) -> tuple[Decimal, bool, bool]:
    quantity_sold = int(row.quantity_sold or 0)
    cogs_amount_snapshot = _to_decimal(row.cogs_amount) if row.cogs_amount is not None else None
    if cogs_amount_snapshot is not None and (cogs_amount_snapshot > 0 or quantity_sold == 0):
        missing_cost = quantity_sold > 0 and cogs_amount_snapshot <= 0
        return cogs_amount_snapshot, missing_cost, False

    if row.unit_cogs_snapshot is not None:
        unit_cogs_snapshot = _to_decimal(row.unit_cogs_snapshot)
        if unit_cogs_snapshot > 0 or quantity_sold == 0:
            cogs = unit_cogs_snapshot * quantity_sold
            missing_cost = quantity_sold > 0 and unit_cogs_snapshot <= 0
            # If stored total COGS is non-positive, use per-unit snapshot and flag as estimated.
            estimated_cost = cogs_amount_snapshot is not None and cogs_amount_snapshot <= 0
            return cogs, missing_cost, estimated_cost

    unit_cogs = _to_decimal(row.fallback_unit_cogs)
    if unit_cogs <= 0:
        unit_cogs = resolve_recipe_unit_cost(db, row.recipe_id)
    cogs = unit_cogs * quantity_sold
    missing_cost = quantity_sold > 0 and unit_cogs <= 0
    return cogs, missing_cost, True


def _resolve_wastage_row_cost(db: Session, row) -> tuple[Decimal, bool, bool]:
    qty = int(row.quantity or 0)
    if qty <= 0:
        return Decimal("0"), False, False
    if row.total_cost_snapshot is not None:
        total_cost = _to_decimal(row.total_cost_snapshot)
        missing_cost = total_cost <= 0
        estimated_cost = bool(row.is_estimated_cost)
        return total_cost, missing_cost, estimated_cost

    if row.unit_cost_snapshot is not None:
        unit_cost = _to_decimal(row.unit_cost_snapshot)
        total_cost = unit_cost * qty
        missing_cost = unit_cost <= 0
        estimated_cost = bool(row.is_estimated_cost)
        return total_cost, missing_cost, estimated_cost

    unit_cost = _to_decimal(row.ingredient_unit_cost)
    if unit_cost <= 0:
        unit_cost = _to_decimal(row.product_unit_cogs)
    if unit_cost <= 0:
        unit_cost = resolve_recipe_unit_cost(db, row.product_recipe_id)
    total_cost = unit_cost * qty
    missing_cost = unit_cost <= 0
    return total_cost, missing_cost, True


def _resolve_wastage_row_price(row) -> tuple[Decimal, bool, bool]:
    qty = int(row.quantity or 0)
    if qty <= 0 or row.product_id is None:
        return Decimal("0"), False, False
    if row.total_price_snapshot is not None:
        total_price = _to_decimal(row.total_price_snapshot)
        missing_price = total_price <= 0
        return total_price, missing_price, False

    if row.unit_price_snapshot is not None:
        unit_price = _to_decimal(row.unit_price_snapshot)
        total_price = unit_price * qty
        missing_price = unit_price <= 0
        return total_price, missing_price, False

    unit_price = _to_decimal(row.product_sale_price)
    total_price = unit_price * qty
    missing_price = unit_price <= 0
    return total_price, missing_price, True


def _calc_summary(db: Session, sales_rows, wastage_rows, expired_ingredient_rows) -> Dict[str, object]:
    total_revenue = Decimal("0")
    total_cogs = Decimal("0")
    store_wastage_cost = Decimal("0")
    ingredient_wastage_cost = Decimal("0")
    production_product_wastage_cost = Decimal("0")
    production_wastage_cost = Decimal("0")
    total_wastage_cost = Decimal("0")
    total_units_sold = 0
    total_wastage_units = 0
    missing_cost_rows = 0
    estimated_cost_rows = 0

    for row in sales_rows:
        quantity_sold = int(row.quantity_sold or 0)
        revenue = _to_decimal(row.total_amount)
        cogs, missing_cost, estimated_cost = _resolve_sales_row_cogs(db, row)

        total_units_sold += quantity_sold
        total_revenue += revenue
        total_cogs += cogs
        if missing_cost:
            missing_cost_rows += 1
        if estimated_cost:
            estimated_cost_rows += 1

    for row in wastage_rows:
        quantity = int(row.quantity or 0)
        if quantity <= 0:
            continue
        total_wastage_units += quantity
        wastage_cost = Decimal("0")
        missing_cost = False
        estimated_cost = False
        if row.source_type == WastageSourceType.STORE:
            wastage_cost, missing_cost, estimated_cost = _resolve_wastage_row_price(row)
            store_wastage_cost += wastage_cost
        else:
            if row.ingredient_id is not None:
                wastage_cost, missing_cost, estimated_cost = _resolve_wastage_row_cost(db, row)
                ingredient_wastage_cost += wastage_cost
            elif row.product_id is not None:
                wastage_cost, missing_cost, estimated_cost = _resolve_wastage_row_price(row)
                production_product_wastage_cost += wastage_cost
            else:
                wastage_cost, missing_cost, estimated_cost = _resolve_wastage_row_cost(db, row)
            production_wastage_cost += wastage_cost
        total_wastage_cost += wastage_cost
        if missing_cost:
            missing_cost_rows += 1
        if estimated_cost:
            estimated_cost_rows += 1

    for row in expired_ingredient_rows:
        total_cost = _to_decimal(row["total_cost"])
        ingredient_wastage_cost += total_cost
        production_wastage_cost += total_cost
        total_wastage_cost += total_cost
        if row["missing_cost"]:
            missing_cost_rows += 1
        if row["estimated_cost"]:
            estimated_cost_rows += 1

    gross_profit = total_revenue - total_cogs
    estimated_net_profit = gross_profit - total_wastage_cost
    gross_margin_pct = Decimal("0")
    if total_revenue > 0:
        gross_margin_pct = (gross_profit / total_revenue) * Decimal("100")

    return {
        "total_revenue": total_revenue,
        "total_cogs": total_cogs,
        "gross_profit": gross_profit,
        "gross_margin_pct": gross_margin_pct,
        "store_wastage_cost": store_wastage_cost,
        "ingredient_wastage_cost": ingredient_wastage_cost,
        "production_product_wastage_cost": production_product_wastage_cost,
        "production_wastage_cost": production_wastage_cost,
        "total_wastage_cost": total_wastage_cost,
        "estimated_net_profit": estimated_net_profit,
        "total_units_sold": total_units_sold,
        "total_wastage_units": total_wastage_units,
        "missing_cost_rows": missing_cost_rows,
        "estimated_cost_rows": estimated_cost_rows,
    }


@router.get("/summary", response_model=FinanceSummaryResponse)
async def finance_summary(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    store_id: Optional[UUID] = Query(None),
    product_id: Optional[UUID] = Query(None),
    finalized_only: bool = Query(True),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(RoleEnum.OWNER, RoleEnum.FINANCE_MANAGER)),
):
    resolved_from, resolved_to = _resolve_date_range(date_from, date_to)
    sales_rows = _sales_rows(db, resolved_from, resolved_to, store_id, product_id, finalized_only)
    wastage_rows = _wastage_rows(db, resolved_from, resolved_to, store_id, product_id)
    expired_ingredient_rows = _expired_ingredient_rows(
        db, resolved_from, resolved_to, store_id, product_id
    )
    summary = _calc_summary(db, sales_rows, wastage_rows, expired_ingredient_rows)

    return {
        "date_from": resolved_from,
        "date_to": resolved_to,
        "total_revenue": _to_money_float(summary["total_revenue"]),
        "total_cogs": _to_money_float(summary["total_cogs"]),
        "gross_profit": _to_money_float(summary["gross_profit"]),
        "gross_margin_pct": _to_money_float(summary["gross_margin_pct"]),
        "store_wastage_cost": _to_money_float(summary["store_wastage_cost"]),
        "ingredient_wastage_cost": _to_money_float(summary["ingredient_wastage_cost"]),
        "production_product_wastage_cost": _to_money_float(summary["production_product_wastage_cost"]),
        "production_wastage_cost": _to_money_float(summary["production_wastage_cost"]),
        "total_wastage_cost": _to_money_float(summary["total_wastage_cost"]),
        "estimated_net_profit": _to_money_float(summary["estimated_net_profit"]),
        "total_units_sold": int(summary["total_units_sold"]),
        "total_wastage_units": int(summary["total_wastage_units"]),
        "missing_cost_rows": int(summary["missing_cost_rows"]),
        "estimated_cost_rows": int(summary["estimated_cost_rows"]),
    }


@router.get("/product-margins", response_model=ProductMarginResponse)
async def product_margins(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    store_id: Optional[UUID] = Query(None),
    product_id: Optional[UUID] = Query(None),
    finalized_only: bool = Query(True),
    limit: int = Query(100, ge=1, le=300),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(RoleEnum.OWNER, RoleEnum.FINANCE_MANAGER)),
):
    resolved_from, resolved_to = _resolve_date_range(date_from, date_to)
    sales_rows = _sales_rows(db, resolved_from, resolved_to, store_id, product_id, finalized_only)

    per_product: Dict[UUID, dict] = {}
    for row in sales_rows:
        row_product_id = row.product_id
        if row_product_id not in per_product:
            per_product[row_product_id] = {
                "product_id": row_product_id,
                "product_name": row.product_name or "Unknown",
                "sku": row.product_sku or "N/A",
                "units_sold": 0,
                "revenue": Decimal("0"),
                "cogs": Decimal("0"),
                "missing_cost": False,
                "estimated_cost": False,
            }

        item = per_product[row_product_id]
        sold_qty = int(row.quantity_sold or 0)
        revenue = _to_decimal(row.total_amount)
        cogs, missing_cost, estimated_cost = _resolve_sales_row_cogs(db, row)

        item["units_sold"] += sold_qty
        item["revenue"] += revenue
        item["cogs"] += cogs
        item["missing_cost"] = item["missing_cost"] or missing_cost
        item["estimated_cost"] = item["estimated_cost"] or estimated_cost

    ordered = sorted(per_product.values(), key=lambda item: item["revenue"], reverse=True)[:limit]

    items = []
    for item in ordered:
        gross_profit = item["revenue"] - item["cogs"]
        gross_margin_pct = Decimal("0")
        if item["revenue"] > 0:
            gross_margin_pct = (gross_profit / item["revenue"]) * Decimal("100")
        avg_price = Decimal("0")
        unit_cogs = Decimal("0")
        if item["units_sold"] > 0:
            avg_price = item["revenue"] / item["units_sold"]
            unit_cogs = item["cogs"] / item["units_sold"]

        items.append(
            {
                "product_id": item["product_id"],
                "product_name": item["product_name"],
                "sku": item["sku"],
                "units_sold": item["units_sold"],
                "revenue": _to_money_float(item["revenue"]),
                "cogs": _to_money_float(item["cogs"]),
                "gross_profit": _to_money_float(gross_profit),
                "gross_margin_pct": _to_money_float(gross_margin_pct),
                "avg_selling_price": _to_money_float(avg_price),
                "unit_cogs": _to_money_float(unit_cogs),
                "missing_cost": bool(item["missing_cost"]),
                "estimated_cost": bool(item["estimated_cost"]),
            }
        )

    return {
        "date_from": resolved_from,
        "date_to": resolved_to,
        "items": items,
    }


@router.get("/pnl-trend", response_model=PnlTrendResponse)
async def pnl_trend(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    store_id: Optional[UUID] = Query(None),
    product_id: Optional[UUID] = Query(None),
    finalized_only: bool = Query(True),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(RoleEnum.OWNER, RoleEnum.FINANCE_MANAGER)),
):
    resolved_from, resolved_to = _resolve_date_range(date_from, date_to)
    sales_rows = _sales_rows(db, resolved_from, resolved_to, store_id, product_id, finalized_only)
    wastage_rows = _wastage_rows(db, resolved_from, resolved_to, store_id, product_id)
    expired_ingredient_rows = _expired_ingredient_rows(
        db, resolved_from, resolved_to, store_id, product_id
    )

    daily: Dict[date, dict] = defaultdict(
        lambda: {
            "revenue": Decimal("0"),
            "cogs": Decimal("0"),
            "store_wastage_cost": Decimal("0"),
            "ingredient_wastage_cost": Decimal("0"),
            "production_product_wastage_cost": Decimal("0"),
            "production_wastage_cost": Decimal("0"),
            "wastage_cost": Decimal("0"),
        }
    )

    for row in sales_rows:
        revenue = _to_decimal(row.total_amount)
        cogs, _, _ = _resolve_sales_row_cogs(db, row)
        daily[row.sales_date]["revenue"] += revenue
        daily[row.sales_date]["cogs"] += cogs

    for row in wastage_rows:
        wastage_cost = Decimal("0")
        if row.source_type == WastageSourceType.STORE:
            wastage_cost, _, _ = _resolve_wastage_row_price(row)
            daily[row.wastage_date]["store_wastage_cost"] += wastage_cost
        else:
            if row.ingredient_id is not None:
                wastage_cost, _, _ = _resolve_wastage_row_cost(db, row)
                daily[row.wastage_date]["ingredient_wastage_cost"] += wastage_cost
            elif row.product_id is not None:
                wastage_cost, _, _ = _resolve_wastage_row_price(row)
                daily[row.wastage_date]["production_product_wastage_cost"] += wastage_cost
            else:
                wastage_cost, _, _ = _resolve_wastage_row_cost(db, row)
            daily[row.wastage_date]["production_wastage_cost"] += wastage_cost
        daily[row.wastage_date]["wastage_cost"] += wastage_cost

    for row in expired_ingredient_rows:
        expiry_date = row["date"]
        if expiry_date is None:
            continue
        total_cost = _to_decimal(row["total_cost"])
        daily[expiry_date]["ingredient_wastage_cost"] += total_cost
        daily[expiry_date]["production_wastage_cost"] += total_cost
        daily[expiry_date]["wastage_cost"] += total_cost

    points = []
    cursor = resolved_from
    totals = {
        "total_revenue": Decimal("0"),
        "total_cogs": Decimal("0"),
        "gross_profit": Decimal("0"),
        "total_store_wastage_cost": Decimal("0"),
        "total_ingredient_wastage_cost": Decimal("0"),
        "total_production_product_wastage_cost": Decimal("0"),
        "total_production_wastage_cost": Decimal("0"),
        "total_wastage_cost": Decimal("0"),
        "estimated_net_profit": Decimal("0"),
    }

    while cursor <= resolved_to:
        day = daily[cursor]
        gross_profit = day["revenue"] - day["cogs"]
        net_profit = gross_profit - day["wastage_cost"]
        totals["total_revenue"] += day["revenue"]
        totals["total_cogs"] += day["cogs"]
        totals["gross_profit"] += gross_profit
        totals["total_store_wastage_cost"] += day["store_wastage_cost"]
        totals["total_ingredient_wastage_cost"] += day["ingredient_wastage_cost"]
        totals["total_production_product_wastage_cost"] += day["production_product_wastage_cost"]
        totals["total_production_wastage_cost"] += day["production_wastage_cost"]
        totals["total_wastage_cost"] += day["wastage_cost"]
        totals["estimated_net_profit"] += net_profit

        points.append(
            {
                "date": cursor,
                "revenue": _to_money_float(day["revenue"]),
                "cogs": _to_money_float(day["cogs"]),
                "gross_profit": _to_money_float(gross_profit),
                "store_wastage_cost": _to_money_float(day["store_wastage_cost"]),
                "ingredient_wastage_cost": _to_money_float(day["ingredient_wastage_cost"]),
                "production_product_wastage_cost": _to_money_float(day["production_product_wastage_cost"]),
                "production_wastage_cost": _to_money_float(day["production_wastage_cost"]),
                "wastage_cost": _to_money_float(day["wastage_cost"]),
                "estimated_net_profit": _to_money_float(net_profit),
            }
        )
        cursor += timedelta(days=1)

    return {
        "date_from": resolved_from,
        "date_to": resolved_to,
        "points": points,
        "total_revenue": _to_money_float(totals["total_revenue"]),
        "total_cogs": _to_money_float(totals["total_cogs"]),
        "gross_profit": _to_money_float(totals["gross_profit"]),
        "total_store_wastage_cost": _to_money_float(totals["total_store_wastage_cost"]),
        "total_ingredient_wastage_cost": _to_money_float(totals["total_ingredient_wastage_cost"]),
        "total_production_product_wastage_cost": _to_money_float(
            totals["total_production_product_wastage_cost"]
        ),
        "total_production_wastage_cost": _to_money_float(totals["total_production_wastage_cost"]),
        "total_wastage_cost": _to_money_float(totals["total_wastage_cost"]),
        "estimated_net_profit": _to_money_float(totals["estimated_net_profit"]),
    }
