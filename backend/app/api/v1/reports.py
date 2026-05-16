"""Phase 10 — Reports & Dashboards.

A single router exposing six aggregation endpoints used by the rewritten
DashboardPage and the tabbed ReportsPage on the frontend.
"""

from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.core.constants import (
    AlertStatus,
    BatchStatus,
    PurchaseOrderStatus,
    RoleEnum,
    WastageReason,
    WastageSourceType,
)
from app.database import get_db
from app.models.ingredient import Ingredient
from app.models.inventory import InventoryStock, StockAlert
from app.models.product import Product
from app.models.production import ProductionBatch
from app.models.recipe import Recipe, RecipeIngredient
from app.models.sales import SalesRecord
from app.models.store import Store
from app.models.supplier import PurchaseOrder
from app.models.user import User
from app.models.wastage import WastageRecord
from app.schemas.reports import (
    DashboardActivityItem,
    DashboardResponse,
    DashboardTopProduct,
    IngredientConsumptionItem,
    IngredientConsumptionResponse,
    ProductionByRecipeItem,
    ProductionEfficiencyResponse,
    SalesTrendPoint,
    SalesTrendsResponse,
    SparklinePoint,
    TopSellerItem,
    TopSellersResponse,
    WastageTrendBucket,
    WastageTrendsResponse,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _to_decimal(value: object) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _to_float(value: object) -> float:
    """Coerce ``None`` / ``Decimal`` / numeric values to ``float`` so that
    Pydantic's response models — which type money fields as ``float`` — both
    accept the value cleanly *and* serialise it as a JSON number rather than
    a JSON string. (See [backend/app/schemas/reports.py](backend/app/schemas/reports.py)
    for the rationale.)"""
    if value is None:
        return 0.0
    return float(value)


def _normalise_range(date_from: Optional[date], date_to: Optional[date]) -> tuple[date, date]:
    """Default to the last 30 days when nothing is supplied. Ensures from <= to."""
    today = date.today()
    if date_to is None:
        date_to = today
    if date_from is None:
        date_from = date_to - timedelta(days=29)
    if date_from > date_to:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="date_from cannot be after date_to",
        )
    return date_from, date_to


def _resolve_store_scope(
    current_user: User, requested_store_id: Optional[UUID]
) -> Optional[UUID]:
    """Store managers are always pinned to their own store; everyone else can
    pass an explicit store_id or get all-stores aggregation."""
    if current_user.role == RoleEnum.STORE_MANAGER:
        return current_user.store_id
    return requested_store_id


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


def _build_revenue_sparkline(
    db: Session, *, store_id: Optional[UUID], days: int = 7
) -> List[SparklinePoint]:
    today = date.today()
    start = today - timedelta(days=days - 1)
    q = (
        db.query(
            SalesRecord.date.label("d"),
            func.coalesce(func.sum(SalesRecord.total_amount), 0).label("revenue"),
        )
        .filter(SalesRecord.date >= start, SalesRecord.date <= today)
    )
    if store_id is not None:
        q = q.filter(SalesRecord.store_id == store_id)
    q = q.group_by(SalesRecord.date).order_by(SalesRecord.date.asc())
    by_date = {row.d: float(row.revenue or 0) for row in q.all()}
    return [
        SparklinePoint(date=start + timedelta(days=i), value=by_date.get(start + timedelta(days=i), 0.0))
        for i in range(days)
    ]


def _build_batches_sparkline(db: Session, *, days: int = 7) -> List[SparklinePoint]:
    today = date.today()
    start = today - timedelta(days=days - 1)
    rows = (
        db.query(
            ProductionBatch.production_date.label("d"),
            func.count(ProductionBatch.id).label("c"),
        )
        .filter(
            ProductionBatch.production_date >= start,
            ProductionBatch.production_date <= today,
            ProductionBatch.status != BatchStatus.CANCELLED,
        )
        .group_by(ProductionBatch.production_date)
        .all()
    )
    by_date = {row.d: float(row.c or 0) for row in rows}
    return [
        SparklinePoint(date=start + timedelta(days=i), value=by_date.get(start + timedelta(days=i), 0.0))
        for i in range(days)
    ]


def _sum_revenue_between(
    db: Session, *, start: date, end: date, store_id: Optional[UUID]
) -> Decimal:
    q = db.query(func.coalesce(func.sum(SalesRecord.total_amount), 0)).filter(
        SalesRecord.date >= start, SalesRecord.date <= end
    )
    if store_id is not None:
        q = q.filter(SalesRecord.store_id == store_id)
    return _to_decimal(q.scalar())


def _sum_gross_profit_between(
    db: Session, *, start: date, end: date, store_id: Optional[UUID]
) -> Decimal:
    q = db.query(
        func.coalesce(func.sum(SalesRecord.total_amount), 0),
        func.coalesce(func.sum(SalesRecord.cogs_amount), 0),
    ).filter(SalesRecord.date >= start, SalesRecord.date <= end)
    if store_id is not None:
        q = q.filter(SalesRecord.store_id == store_id)
    revenue, cogs = q.one()
    return _to_decimal(revenue) - _to_decimal(cogs)


def _sum_units_sold(
    db: Session, *, day: date, store_id: Optional[UUID]
) -> int:
    q = db.query(func.coalesce(func.sum(SalesRecord.quantity_sold), 0)).filter(
        SalesRecord.date == day
    )
    if store_id is not None:
        q = q.filter(SalesRecord.store_id == store_id)
    return int(q.scalar() or 0)


def _top_product_today(
    db: Session, *, day: date, store_id: Optional[UUID]
) -> Optional[DashboardTopProduct]:
    q = (
        db.query(
            SalesRecord.product_id.label("pid"),
            Product.name.label("pname"),
            func.coalesce(func.sum(SalesRecord.quantity_sold), 0).label("units"),
        )
        .join(Product, Product.id == SalesRecord.product_id)
        .filter(SalesRecord.date == day)
    )
    if store_id is not None:
        q = q.filter(SalesRecord.store_id == store_id)
    row = (
        q.group_by(SalesRecord.product_id, Product.name)
        .order_by(func.sum(SalesRecord.quantity_sold).desc())
        .first()
    )
    if row is None or (row.units or 0) <= 0:
        return None
    return DashboardTopProduct(
        product_id=row.pid, product_name=row.pname, units_sold=int(row.units)
    )


def _count_active_stock_alerts(db: Session) -> int:
    return (
        db.query(func.count(StockAlert.id))
        .filter(StockAlert.status == AlertStatus.ACTIVE)
        .scalar()
        or 0
    )


def _count_expiring_ingredients(db: Session, days: int = 7) -> int:
    cutoff = date.today() + timedelta(days=days)
    return (
        db.query(func.count(Ingredient.id))
        .filter(
            Ingredient.is_active == True,  # noqa: E712  (SQLAlchemy needs ==)
            Ingredient.expiry_date.isnot(None),
            Ingredient.expiry_date <= cutoff,
        )
        .scalar()
        or 0
    )


def _count_pending_purchase_orders(db: Session) -> int:
    return (
        db.query(func.count(PurchaseOrder.id))
        .filter(
            PurchaseOrder.status.in_(
                [PurchaseOrderStatus.PENDING, PurchaseOrderStatus.APPROVED]
            )
        )
        .scalar()
        or 0
    )


def _recent_activity(
    db: Session, *, store_id: Optional[UUID], limit: int = 5
) -> List[DashboardActivityItem]:
    items: List[tuple[datetime, DashboardActivityItem]] = []

    sales_q = db.query(SalesRecord, Product.name, Store.name).join(
        Product, Product.id == SalesRecord.product_id
    ).join(Store, Store.id == SalesRecord.store_id)
    if store_id is not None:
        sales_q = sales_q.filter(SalesRecord.store_id == store_id)
    for sale, pname, sname in sales_q.order_by(SalesRecord.updated_at.desc()).limit(limit).all():
        ts = sale.updated_at or datetime.combine(sale.date, datetime.min.time())
        items.append(
            (
                ts,
                DashboardActivityItem(
                    kind="sale",
                    summary=f"{sale.quantity_sold} x {pname} sold at {sname}",
                    occurred_at=sale.date,
                ),
            )
        )

    batches = (
        db.query(ProductionBatch, Product.name)
        .join(Product, Product.id == ProductionBatch.product_id)
        .order_by(ProductionBatch.updated_at.desc())
        .limit(limit)
        .all()
    )
    for batch, pname in batches:
        ts = batch.updated_at or datetime.combine(batch.production_date, datetime.min.time())
        status_value = batch.status.value if hasattr(batch.status, "value") else str(batch.status)
        items.append(
            (
                ts,
                DashboardActivityItem(
                    kind="production",
                    summary=f"Batch of {pname} — {status_value} ({batch.batch_size})",
                    occurred_at=batch.production_date,
                ),
            )
        )

    pos = (
        db.query(PurchaseOrder, Ingredient.name)
        .join(Ingredient, Ingredient.id == PurchaseOrder.ingredient_id)
        .order_by(PurchaseOrder.created_at.desc())
        .limit(limit)
        .all()
    )
    for po, iname in pos:
        ts = po.created_at or datetime.combine(po.order_date, datetime.min.time())
        status_value = po.status.value if hasattr(po.status, "value") else str(po.status)
        items.append(
            (
                ts,
                DashboardActivityItem(
                    kind="purchase_order",
                    summary=f"PO for {po.quantity} {iname} — {status_value}",
                    occurred_at=po.order_date,
                ),
            )
        )

    items.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in items[:limit]]


@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard(
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
    today = date.today()
    week_start = today - timedelta(days=6)
    month_start = today - timedelta(days=29)

    role = current_user.role
    store_scope = _resolve_store_scope(current_user, requested_store_id=None)
    store_name: Optional[str] = None
    if store_scope is not None:
        store = db.query(Store).filter(Store.id == store_scope).first()
        store_name = store.name if store else None

    show_financial = role in {
        RoleEnum.OWNER,
        RoleEnum.FINANCE_MANAGER,
        RoleEnum.STORE_MANAGER,
    }
    show_operational = role in {RoleEnum.OWNER, RoleEnum.PRODUCTION_MANAGER}
    show_profit = role in {RoleEnum.OWNER, RoleEnum.FINANCE_MANAGER}

    payload = DashboardResponse(
        role=role.value,
        scoped_store_id=store_scope,
        scoped_store_name=store_name,
    )

    if show_financial:
        payload.revenue_today = _to_float(
            _sum_revenue_between(db, start=today, end=today, store_id=store_scope)
        )
        payload.revenue_week = _to_float(
            _sum_revenue_between(db, start=week_start, end=today, store_id=store_scope)
        )
        payload.revenue_month = _to_float(
            _sum_revenue_between(db, start=month_start, end=today, store_id=store_scope)
        )
        payload.units_sold_today = _sum_units_sold(
            db, day=today, store_id=store_scope
        )
        payload.top_product_today = _top_product_today(
            db, day=today, store_id=store_scope
        )
        payload.revenue_sparkline = _build_revenue_sparkline(
            db, store_id=store_scope
        )

    if show_profit:
        payload.gross_profit_week = _to_float(
            _sum_gross_profit_between(
                db, start=week_start, end=today, store_id=store_scope
            )
        )

    if show_operational:
        payload.production_batches_today = (
            db.query(func.count(ProductionBatch.id))
            .filter(
                ProductionBatch.production_date == today,
                ProductionBatch.status != BatchStatus.CANCELLED,
            )
            .scalar()
            or 0
        )
        payload.active_stock_alerts = _count_active_stock_alerts(db)
        payload.expiring_ingredients = _count_expiring_ingredients(db)
        payload.pending_purchase_orders = _count_pending_purchase_orders(db)
        payload.batches_sparkline = _build_batches_sparkline(db)

    payload.recent_activity = _recent_activity(db, store_id=store_scope, limit=5)

    return payload


# ---------------------------------------------------------------------------
# Sales trends + Top sellers
# ---------------------------------------------------------------------------


_WEEK_ANCHOR = date(2024, 1, 1)  # Monday — used as a stable epoch for week bucketing


def _week_bucket_start(d: date) -> date:
    """Returns the Monday of the ISO week containing `d` (DB-agnostic)."""
    days_since_anchor = (d - _WEEK_ANCHOR).days
    weeks_since_anchor = days_since_anchor // 7
    return _WEEK_ANCHOR + timedelta(days=weeks_since_anchor * 7)


@router.get("/sales-trends", response_model=SalesTrendsResponse)
async def get_sales_trends(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    store_id: Optional[UUID] = None,
    product_id: Optional[UUID] = None,
    granularity: str = Query("day", pattern="^(day|week)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(
            RoleEnum.OWNER, RoleEnum.FINANCE_MANAGER, RoleEnum.STORE_MANAGER
        )
    ),
):
    date_from, date_to = _normalise_range(date_from, date_to)
    store_scope = _resolve_store_scope(current_user, store_id)

    q = (
        db.query(
            SalesRecord.date.label("d"),
            func.coalesce(func.sum(SalesRecord.quantity_sold), 0).label("units"),
            func.coalesce(func.sum(SalesRecord.total_amount), 0).label("revenue"),
            func.count(SalesRecord.id).label("txn"),
        )
        .filter(SalesRecord.date >= date_from, SalesRecord.date <= date_to)
    )
    if store_scope is not None:
        q = q.filter(SalesRecord.store_id == store_scope)
    if product_id is not None:
        q = q.filter(SalesRecord.product_id == product_id)
    rows = q.group_by(SalesRecord.date).order_by(SalesRecord.date.asc()).all()

    # Aggregate by week in Python if requested (works the same on SQLite + PG)
    if granularity == "week":
        weekly: dict[date, dict] = defaultdict(
            lambda: {"units": 0, "revenue": Decimal("0"), "txn": 0}
        )
        for r in rows:
            bucket = _week_bucket_start(r.d)
            weekly[bucket]["units"] += int(r.units or 0)
            weekly[bucket]["revenue"] += _to_decimal(r.revenue)
            weekly[bucket]["txn"] += int(r.txn or 0)
        points = [
            SalesTrendPoint(
                date=d,
                units_sold=v["units"],
                revenue=_to_float(v["revenue"]),
                transaction_count=v["txn"],
            )
            for d, v in sorted(weekly.items())
        ]
    else:
        points = [
            SalesTrendPoint(
                date=r.d,
                units_sold=int(r.units or 0),
                revenue=_to_float(r.revenue),
                transaction_count=int(r.txn or 0),
            )
            for r in rows
        ]

    total_units = sum(p.units_sold for p in points)
    total_revenue = sum((p.revenue for p in points), 0.0)
    return SalesTrendsResponse(
        granularity=granularity,
        points=points,
        total_units=total_units,
        total_revenue=total_revenue,
    )


@router.get("/top-sellers", response_model=TopSellersResponse)
async def get_top_sellers(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    store_id: Optional[UUID] = None,
    limit: int = Query(10, ge=1, le=50),
    order_by: str = Query("units", pattern="^(units|revenue)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(
            RoleEnum.OWNER, RoleEnum.FINANCE_MANAGER, RoleEnum.STORE_MANAGER
        )
    ),
):
    date_from, date_to = _normalise_range(date_from, date_to)
    store_scope = _resolve_store_scope(current_user, store_id)

    units_expr = func.coalesce(func.sum(SalesRecord.quantity_sold), 0).label("units")
    revenue_expr = func.coalesce(func.sum(SalesRecord.total_amount), 0).label("revenue")

    q = (
        db.query(
            SalesRecord.product_id.label("pid"),
            Product.name.label("pname"),
            Product.sku.label("psku"),
            units_expr,
            revenue_expr,
        )
        .join(Product, Product.id == SalesRecord.product_id)
        .filter(SalesRecord.date >= date_from, SalesRecord.date <= date_to)
    )
    if store_scope is not None:
        q = q.filter(SalesRecord.store_id == store_scope)

    order_col = revenue_expr if order_by == "revenue" else units_expr
    rows = (
        q.group_by(SalesRecord.product_id, Product.name, Product.sku)
        .order_by(order_col.desc())
        .limit(limit)
        .all()
    )

    items: List[TopSellerItem] = []
    for r in rows:
        units = int(r.units or 0)
        revenue = _to_float(r.revenue)
        avg_price = round(revenue / units, 2) if units > 0 else 0.0
        items.append(
            TopSellerItem(
                product_id=r.pid,
                product_name=r.pname,
                sku=r.psku,
                units_sold=units,
                revenue=revenue,
                avg_unit_price=avg_price,
            )
        )

    return TopSellersResponse(order_by=order_by, items=items)


# ---------------------------------------------------------------------------
# Wastage trends
# ---------------------------------------------------------------------------


_REASON_LABELS = {
    WastageReason.SPOILAGE.value: "Spoilage",
    WastageReason.DAMAGE.value: "Damage",
    WastageReason.EXPIRY.value: "Expiry",
    WastageReason.PRODUCTION_LOSS.value: "Production loss",
    WastageReason.OTHER.value: "Other",
}

_SOURCE_LABELS = {
    WastageSourceType.STORE.value: "Store",
    WastageSourceType.PRODUCTION.value: "Production",
}


@router.get("/wastage-trends", response_model=WastageTrendsResponse)
async def get_wastage_trends(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    group_by: str = Query("date", pattern="^(date|reason|source)$"),
    store_id: Optional[UUID] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(
            RoleEnum.OWNER, RoleEnum.FINANCE_MANAGER, RoleEnum.PRODUCTION_MANAGER
        )
    ),
):
    date_from, date_to = _normalise_range(date_from, date_to)

    qty_expr = func.coalesce(func.sum(WastageRecord.quantity), 0).label("qty")
    cost_expr = func.coalesce(func.sum(WastageRecord.total_cost_snapshot), 0).label("cost")
    count_expr = func.count(WastageRecord.id).label("c")

    base_filters = [WastageRecord.date >= date_from, WastageRecord.date <= date_to]
    if store_id is not None:
        base_filters.append(WastageRecord.store_id == store_id)

    if group_by == "date":
        rows = (
            db.query(WastageRecord.date.label("k"), qty_expr, cost_expr, count_expr)
            .filter(*base_filters)
            .group_by(WastageRecord.date)
            .order_by(WastageRecord.date.asc())
            .all()
        )
        buckets = [
            WastageTrendBucket(
                key=r.k.isoformat(),
                label=r.k.isoformat(),
                total_qty=int(r.qty or 0),
                total_cost=_to_float(r.cost),
                record_count=int(r.c or 0),
            )
            for r in rows
        ]
    elif group_by == "reason":
        rows = (
            db.query(WastageRecord.reason.label("k"), qty_expr, cost_expr, count_expr)
            .filter(*base_filters)
            .group_by(WastageRecord.reason)
            .order_by(cost_expr.desc())
            .all()
        )
        buckets = []
        for r in rows:
            key_value = r.k.value if hasattr(r.k, "value") else str(r.k)
            buckets.append(
                WastageTrendBucket(
                    key=key_value,
                    label=_REASON_LABELS.get(key_value, key_value),
                    total_qty=int(r.qty or 0),
                    total_cost=_to_float(r.cost),
                    record_count=int(r.c or 0),
                )
            )
    else:  # source
        rows = (
            db.query(WastageRecord.source_type.label("k"), qty_expr, cost_expr, count_expr)
            .filter(*base_filters)
            .group_by(WastageRecord.source_type)
            .order_by(cost_expr.desc())
            .all()
        )
        buckets = []
        for r in rows:
            key_value = r.k.value if hasattr(r.k, "value") else str(r.k)
            buckets.append(
                WastageTrendBucket(
                    key=key_value,
                    label=_SOURCE_LABELS.get(key_value, key_value),
                    total_qty=int(r.qty or 0),
                    total_cost=_to_float(r.cost),
                    record_count=int(r.c or 0),
                )
            )

    total_qty = sum(b.total_qty for b in buckets)
    total_cost = sum((b.total_cost for b in buckets), 0.0)
    return WastageTrendsResponse(
        group_by=group_by,
        buckets=buckets,
        total_qty=total_qty,
        total_cost=total_cost,
    )


# ---------------------------------------------------------------------------
# Ingredient consumption
# ---------------------------------------------------------------------------


@router.get("/ingredient-consumption", response_model=IngredientConsumptionResponse)
async def get_ingredient_consumption(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    ingredient_id: Optional[UUID] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(
            RoleEnum.OWNER, RoleEnum.FINANCE_MANAGER, RoleEnum.PRODUCTION_MANAGER
        )
    ),
):
    """Aggregates ingredient consumption from COMPLETED production batches
    in the date range.

    For each completed batch:
      consumed_qty(ing) = recipe_ingredient.quantity_required
                          * (batch.actual_yield OR batch.batch_size)
                          / recipe.yield_qty

    cost = consumed_qty * ingredient.unit_cost.
    """
    date_from, date_to = _normalise_range(date_from, date_to)

    # Pull every completed batch with its recipe's ingredient lines in one go.
    q = (
        db.query(
            ProductionBatch.id.label("batch_id"),
            ProductionBatch.batch_size,
            ProductionBatch.actual_yield,
            Recipe.id.label("recipe_id"),
            Recipe.yield_qty.label("recipe_yield"),
            RecipeIngredient.ingredient_id.label("ing_id"),
            RecipeIngredient.quantity_required.label("ing_qty"),
            Ingredient.name.label("ing_name"),
            Ingredient.unit.label("ing_unit"),
            Ingredient.unit_cost.label("ing_unit_cost"),
        )
        .join(Recipe, Recipe.id == ProductionBatch.recipe_id)
        .join(RecipeIngredient, RecipeIngredient.recipe_id == Recipe.id)
        .join(Ingredient, Ingredient.id == RecipeIngredient.ingredient_id)
        .filter(
            ProductionBatch.status == BatchStatus.COMPLETED,
            ProductionBatch.production_date >= date_from,
            ProductionBatch.production_date <= date_to,
        )
    )
    if ingredient_id is not None:
        q = q.filter(RecipeIngredient.ingredient_id == ingredient_id)

    rows = q.all()

    by_ing: dict[UUID, dict] = {}
    for r in rows:
        recipe_yield = int(r.recipe_yield or 0)
        if recipe_yield <= 0:
            continue
        produced = int(r.actual_yield if r.actual_yield is not None else r.batch_size or 0)
        qty_per_unit = _to_decimal(r.ing_qty)
        consumed = (qty_per_unit * Decimal(produced) / Decimal(recipe_yield)).quantize(
            Decimal("0.001")
        )
        unit_cost = _to_decimal(r.ing_unit_cost)
        cost = (consumed * unit_cost).quantize(Decimal("0.01"))

        entry = by_ing.setdefault(
            r.ing_id,
            {
                "name": r.ing_name,
                "unit": r.ing_unit,
                "qty": Decimal("0"),
                "cost": Decimal("0"),
                "batches": set(),
            },
        )
        entry["qty"] += consumed
        entry["cost"] += cost
        entry["batches"].add(r.batch_id)

    items: List[IngredientConsumptionItem] = [
        IngredientConsumptionItem(
            ingredient_id=ing_id,
            ingredient_name=entry["name"],
            unit=entry["unit"],
            total_qty_consumed=_to_float(entry["qty"].quantize(Decimal("0.001"))),
            total_cost=_to_float(entry["cost"].quantize(Decimal("0.01"))),
            batch_count=len(entry["batches"]),
        )
        for ing_id, entry in by_ing.items()
    ]
    items.sort(key=lambda i: i.total_cost, reverse=True)

    total_cost = sum((i.total_cost for i in items), 0.0)
    return IngredientConsumptionResponse(items=items, total_cost=total_cost)


# ---------------------------------------------------------------------------
# Production efficiency
# ---------------------------------------------------------------------------


@router.get("/production-efficiency", response_model=ProductionEfficiencyResponse)
async def get_production_efficiency(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(
            RoleEnum.OWNER, RoleEnum.FINANCE_MANAGER, RoleEnum.PRODUCTION_MANAGER
        )
    ),
):
    date_from, date_to = _normalise_range(date_from, date_to)

    # Overall status counts
    status_rows = (
        db.query(ProductionBatch.status, func.count(ProductionBatch.id))
        .filter(
            ProductionBatch.production_date >= date_from,
            ProductionBatch.production_date <= date_to,
        )
        .group_by(ProductionBatch.status)
        .all()
    )
    counts = {BatchStatus.PLANNED: 0, BatchStatus.IN_PROGRESS: 0, BatchStatus.COMPLETED: 0, BatchStatus.CANCELLED: 0}
    for st, c in status_rows:
        key = st if isinstance(st, BatchStatus) else BatchStatus(st)
        counts[key] = int(c or 0)

    total = sum(counts.values())
    terminal = counts[BatchStatus.COMPLETED] + counts[BatchStatus.CANCELLED]
    completion_rate = (
        counts[BatchStatus.COMPLETED] / terminal * 100.0 if terminal > 0 else 0.0
    )

    # Avg yield variance across completed batches
    completed_batches = (
        db.query(ProductionBatch.batch_size, ProductionBatch.actual_yield)
        .filter(
            ProductionBatch.status == BatchStatus.COMPLETED,
            ProductionBatch.production_date >= date_from,
            ProductionBatch.production_date <= date_to,
        )
        .all()
    )
    variances: List[float] = []
    for planned, actual in completed_batches:
        planned_int = int(planned or 0)
        if planned_int <= 0:
            continue
        actual_int = int(actual if actual is not None else planned_int)
        variances.append((actual_int - planned_int) / planned_int * 100.0)
    avg_variance = sum(variances) / len(variances) if variances else 0.0

    # Per-recipe breakdown
    by_recipe_rows = (
        db.query(
            Recipe.id.label("rid"),
            Recipe.name.label("rname"),
            ProductionBatch.status.label("st"),
            func.coalesce(func.sum(ProductionBatch.batch_size), 0).label("planned_qty"),
            func.coalesce(
                func.sum(
                    func.coalesce(ProductionBatch.actual_yield, ProductionBatch.batch_size)
                ),
                0,
            ).label("actual_qty"),
            func.count(ProductionBatch.id).label("c"),
        )
        .join(Recipe, Recipe.id == ProductionBatch.recipe_id)
        .filter(
            ProductionBatch.production_date >= date_from,
            ProductionBatch.production_date <= date_to,
        )
        .group_by(Recipe.id, Recipe.name, ProductionBatch.status)
        .all()
    )

    recipe_map: dict[UUID, dict] = {}
    for r in by_recipe_rows:
        entry = recipe_map.setdefault(
            r.rid,
            {
                "name": r.rname,
                "planned": 0,
                "completed": 0,
                "cancelled": 0,
                "planned_qty": 0,
                "actual_qty": 0,
                "variances": [],
            },
        )
        key = r.st if isinstance(r.st, BatchStatus) else BatchStatus(r.st)
        c = int(r.c or 0)
        if key == BatchStatus.PLANNED:
            entry["planned"] += c
        elif key == BatchStatus.COMPLETED:
            entry["completed"] += c
        elif key == BatchStatus.CANCELLED:
            entry["cancelled"] += c
        entry["planned_qty"] += int(r.planned_qty or 0)
        entry["actual_qty"] += int(r.actual_qty or 0)

    # Compute per-recipe variance from the completed batches only
    completed_per_recipe = (
        db.query(
            ProductionBatch.recipe_id,
            ProductionBatch.batch_size,
            ProductionBatch.actual_yield,
        )
        .filter(
            ProductionBatch.status == BatchStatus.COMPLETED,
            ProductionBatch.production_date >= date_from,
            ProductionBatch.production_date <= date_to,
        )
        .all()
    )
    for rid, planned, actual in completed_per_recipe:
        planned_int = int(planned or 0)
        if planned_int <= 0 or rid not in recipe_map:
            continue
        actual_int = int(actual if actual is not None else planned_int)
        recipe_map[rid]["variances"].append(
            (actual_int - planned_int) / planned_int * 100.0
        )

    by_recipe = [
        ProductionByRecipeItem(
            recipe_id=rid,
            recipe_name=entry["name"],
            planned_batches=entry["planned"],
            completed_batches=entry["completed"],
            cancelled_batches=entry["cancelled"],
            total_planned_qty=entry["planned_qty"],
            total_actual_qty=entry["actual_qty"],
            avg_yield_variance_pct=(
                sum(entry["variances"]) / len(entry["variances"])
                if entry["variances"]
                else 0.0
            ),
        )
        for rid, entry in recipe_map.items()
    ]
    by_recipe.sort(key=lambda i: i.completed_batches, reverse=True)

    return ProductionEfficiencyResponse(
        planned_count=counts[BatchStatus.PLANNED],
        in_progress_count=counts[BatchStatus.IN_PROGRESS],
        completed_count=counts[BatchStatus.COMPLETED],
        cancelled_count=counts[BatchStatus.CANCELLED],
        total_batches=total,
        completion_rate=completion_rate,
        avg_yield_variance_pct=avg_variance,
        by_recipe=by_recipe,
    )
