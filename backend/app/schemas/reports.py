"""Pydantic response schemas for the Phase 10 Reports module.

Monetary fields are exposed as ``float`` to match the convention established in
[backend/app/schemas/finance.py](backend/app/schemas/finance.py) (Phase 8) — the
frontend TypeScript layer is already typed against numbers, and JSON-encoded
Decimals would otherwise come through as strings.
"""

from datetime import date
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


class SparklinePoint(BaseModel):
    date: date
    value: float


class DashboardTopProduct(BaseModel):
    product_id: UUID
    product_name: str
    units_sold: int


class DashboardActivityItem(BaseModel):
    kind: str  # "sale" | "production" | "purchase_order" | "wastage"
    summary: str
    occurred_at: date
    actor: Optional[str] = None


class DashboardResponse(BaseModel):
    """Adapts to the requesting user's role.

    Fields the user is not authorised to see are returned as null rather
    than being omitted (keeps the TypeScript surface stable across roles).
    """

    role: str

    # KPIs — financial (Owner, Finance Manager, Store Manager)
    revenue_today: Optional[float] = None
    revenue_week: Optional[float] = None
    revenue_month: Optional[float] = None
    gross_profit_week: Optional[float] = None
    units_sold_today: Optional[int] = None

    # KPIs — operational (Owner, Production Manager)
    production_batches_today: Optional[int] = None
    active_stock_alerts: Optional[int] = None
    expiring_ingredients: Optional[int] = None
    pending_purchase_orders: Optional[int] = None

    # Trend data — last 7 days
    revenue_sparkline: List[SparklinePoint] = []
    batches_sparkline: List[SparklinePoint] = []

    # Spotlight
    top_product_today: Optional[DashboardTopProduct] = None

    # Recent activity (latest 5 across sales/POs/batches/wastage)
    recent_activity: List[DashboardActivityItem] = []

    # Context echoed back so the UI can label everything correctly
    scoped_store_id: Optional[UUID] = None
    scoped_store_name: Optional[str] = None


# ---------------------------------------------------------------------------
# Sales trends + Top sellers
# ---------------------------------------------------------------------------


class SalesTrendPoint(BaseModel):
    date: date
    units_sold: int
    revenue: float
    transaction_count: int


class SalesTrendsResponse(BaseModel):
    granularity: str  # "day" | "week"
    points: List[SalesTrendPoint] = []
    total_units: int
    total_revenue: float


class TopSellerItem(BaseModel):
    product_id: UUID
    product_name: str
    sku: Optional[str] = None
    units_sold: int
    revenue: float
    avg_unit_price: float


class TopSellersResponse(BaseModel):
    order_by: str  # "units" | "revenue"
    items: List[TopSellerItem] = []


# ---------------------------------------------------------------------------
# Wastage trends
# ---------------------------------------------------------------------------


class WastageTrendBucket(BaseModel):
    """Generic bucket — `key` is a string regardless of group_by so the UI
    can render all three modes uniformly (date / reason / source)."""

    key: str
    label: str  # human-friendly version of `key`
    total_qty: int
    total_cost: float
    record_count: int


class WastageTrendsResponse(BaseModel):
    group_by: str  # "date" | "reason" | "source"
    buckets: List[WastageTrendBucket] = []
    total_qty: int
    total_cost: float


# ---------------------------------------------------------------------------
# Ingredient consumption
# ---------------------------------------------------------------------------


class IngredientConsumptionItem(BaseModel):
    ingredient_id: UUID
    ingredient_name: str
    unit: str
    total_qty_consumed: float
    total_cost: float
    batch_count: int


class IngredientConsumptionResponse(BaseModel):
    items: List[IngredientConsumptionItem] = []
    total_cost: float


# ---------------------------------------------------------------------------
# Production efficiency
# ---------------------------------------------------------------------------


class ProductionByRecipeItem(BaseModel):
    recipe_id: UUID
    recipe_name: str
    planned_batches: int
    completed_batches: int
    cancelled_batches: int
    total_planned_qty: int
    total_actual_qty: int
    avg_yield_variance_pct: float


class ProductionEfficiencyResponse(BaseModel):
    planned_count: int
    in_progress_count: int
    completed_count: int
    cancelled_count: int
    total_batches: int
    completion_rate: float
    avg_yield_variance_pct: float
    by_recipe: List[ProductionByRecipeItem] = []
