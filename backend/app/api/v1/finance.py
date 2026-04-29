from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.core.constants import RoleEnum, WastageSourceType
from app.database import get_db
from app.models.ingredient import Ingredient
from app.models.product import Product
from app.models.recipe import Recipe
from app.models.sales import SalesRecord
from app.models.user import User
from app.models.wastage import WastageRecord
from app.schemas.finance import (
    FinanceSummaryResponse,
    PnlTrendResponse,
    ProductMarginResponse,
)

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
):
    query = (
        db.query(
            SalesRecord.date.label("sales_date"),
            SalesRecord.product_id.label("product_id"),
            Product.name.label("product_name"),
            Product.sku.label("product_sku"),
            SalesRecord.quantity_sold.label("quantity_sold"),
            SalesRecord.total_amount.label("total_amount"),
            Recipe.cost_per_unit.label("unit_cogs"),
        )
        .join(Product, Product.id == SalesRecord.product_id)
        .outerjoin(Recipe, Recipe.id == Product.recipe_id)
        .filter(
            SalesRecord.date >= date_from,
            SalesRecord.date <= date_to,
        )
    )
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
            Recipe.cost_per_unit.label("product_unit_cogs"),
            Ingredient.unit_cost.label("ingredient_unit_cost"),
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


def _calc_summary(
    sales_rows,
    wastage_rows,
) -> Dict[str, object]:
    total_revenue = Decimal("0")
    total_cogs = Decimal("0")
    total_wastage_cost = Decimal("0")
    total_units_sold = 0
    total_wastage_units = 0
    missing_cost_rows = 0

    for row in sales_rows:
        quantity_sold = int(row.quantity_sold or 0)
        revenue = _to_decimal(row.total_amount)
        unit_cogs_raw = row.unit_cogs
        unit_cogs = _to_decimal(unit_cogs_raw)
        cogs = unit_cogs * quantity_sold

        total_units_sold += quantity_sold
        total_revenue += revenue
        total_cogs += cogs
        if quantity_sold > 0 and unit_cogs_raw is None:
            missing_cost_rows += 1

    for row in wastage_rows:
        quantity = int(row.quantity or 0)
        if quantity <= 0:
            continue
        total_wastage_units += quantity
        unit_cost = _to_decimal(row.ingredient_unit_cost)
        if unit_cost == 0:
            unit_cost = _to_decimal(row.product_unit_cogs)
        if unit_cost == 0:
            missing_cost_rows += 1
        total_wastage_cost += unit_cost * quantity

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
        "total_wastage_cost": total_wastage_cost,
        "estimated_net_profit": estimated_net_profit,
        "total_units_sold": total_units_sold,
        "total_wastage_units": total_wastage_units,
        "missing_cost_rows": missing_cost_rows,
    }


@router.get("/summary", response_model=FinanceSummaryResponse)
async def finance_summary(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    store_id: Optional[UUID] = Query(None),
    product_id: Optional[UUID] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(RoleEnum.OWNER, RoleEnum.FINANCE_MANAGER)),
):
    resolved_from, resolved_to = _resolve_date_range(date_from, date_to)
    sales_rows = _sales_rows(db, resolved_from, resolved_to, store_id, product_id)
    wastage_rows = _wastage_rows(db, resolved_from, resolved_to, store_id, product_id)
    summary = _calc_summary(sales_rows, wastage_rows)

    return {
        "date_from": resolved_from,
        "date_to": resolved_to,
        "total_revenue": _to_money_float(summary["total_revenue"]),
        "total_cogs": _to_money_float(summary["total_cogs"]),
        "gross_profit": _to_money_float(summary["gross_profit"]),
        "gross_margin_pct": _to_money_float(summary["gross_margin_pct"]),
        "total_wastage_cost": _to_money_float(summary["total_wastage_cost"]),
        "estimated_net_profit": _to_money_float(summary["estimated_net_profit"]),
        "total_units_sold": int(summary["total_units_sold"]),
        "total_wastage_units": int(summary["total_wastage_units"]),
        "missing_cost_rows": int(summary["missing_cost_rows"]),
    }


@router.get("/product-margins", response_model=ProductMarginResponse)
async def product_margins(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    store_id: Optional[UUID] = Query(None),
    limit: int = Query(100, ge=1, le=300),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(RoleEnum.OWNER, RoleEnum.FINANCE_MANAGER)),
):
    resolved_from, resolved_to = _resolve_date_range(date_from, date_to)
    sales_rows = _sales_rows(db, resolved_from, resolved_to, store_id, product_id=None)

    per_product: Dict[UUID, dict] = {}
    for row in sales_rows:
        product_id = row.product_id
        if product_id not in per_product:
            per_product[product_id] = {
                "product_id": product_id,
                "product_name": row.product_name or "Unknown",
                "sku": row.product_sku or "N/A",
                "units_sold": 0,
                "revenue": Decimal("0"),
                "cogs": Decimal("0"),
                "unit_cogs": _to_decimal(row.unit_cogs),
                "missing_cost": row.unit_cogs is None,
            }

        item = per_product[product_id]
        sold_qty = int(row.quantity_sold or 0)
        revenue = _to_decimal(row.total_amount)
        unit_cogs = _to_decimal(row.unit_cogs)

        item["units_sold"] += sold_qty
        item["revenue"] += revenue
        item["cogs"] += (unit_cogs * sold_qty)
        item["missing_cost"] = item["missing_cost"] or row.unit_cogs is None

    ordered = sorted(
        per_product.values(),
        key=lambda item: item["revenue"],
        reverse=True,
    )[:limit]

    items = []
    for item in ordered:
        gross_profit = item["revenue"] - item["cogs"]
        gross_margin_pct = Decimal("0")
        if item["revenue"] > 0:
            gross_margin_pct = (gross_profit / item["revenue"]) * Decimal("100")
        avg_price = Decimal("0")
        if item["units_sold"] > 0:
            avg_price = item["revenue"] / item["units_sold"]

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
                "unit_cogs": _to_money_float(item["unit_cogs"]),
                "missing_cost": bool(item["missing_cost"]),
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
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(RoleEnum.OWNER, RoleEnum.FINANCE_MANAGER)),
):
    resolved_from, resolved_to = _resolve_date_range(date_from, date_to)
    sales_rows = _sales_rows(db, resolved_from, resolved_to, store_id, product_id)
    wastage_rows = _wastage_rows(db, resolved_from, resolved_to, store_id, product_id)

    daily: Dict[date, dict] = defaultdict(
        lambda: {
            "revenue": Decimal("0"),
            "cogs": Decimal("0"),
            "wastage_cost": Decimal("0"),
        }
    )

    for row in sales_rows:
        sold_qty = int(row.quantity_sold or 0)
        revenue = _to_decimal(row.total_amount)
        cogs = _to_decimal(row.unit_cogs) * sold_qty
        daily[row.sales_date]["revenue"] += revenue
        daily[row.sales_date]["cogs"] += cogs

    for row in wastage_rows:
        qty = int(row.quantity or 0)
        if qty <= 0:
            continue
        unit_cost = _to_decimal(row.ingredient_unit_cost)
        if unit_cost == 0:
            unit_cost = _to_decimal(row.product_unit_cogs)
        daily[row.wastage_date]["wastage_cost"] += (unit_cost * qty)

    points = []
    cursor = resolved_from
    totals = {
        "total_revenue": Decimal("0"),
        "total_cogs": Decimal("0"),
        "gross_profit": Decimal("0"),
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
        totals["total_wastage_cost"] += day["wastage_cost"]
        totals["estimated_net_profit"] += net_profit

        points.append(
            {
                "date": cursor,
                "revenue": _to_money_float(day["revenue"]),
                "cogs": _to_money_float(day["cogs"]),
                "gross_profit": _to_money_float(gross_profit),
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
        "total_wastage_cost": _to_money_float(totals["total_wastage_cost"]),
        "estimated_net_profit": _to_money_float(totals["estimated_net_profit"]),
    }
