from datetime import date
from typing import List
from uuid import UUID

from pydantic import BaseModel


class FinanceSummaryResponse(BaseModel):
    date_from: date
    date_to: date
    total_revenue: float
    total_cogs: float
    gross_profit: float
    gross_margin_pct: float
    store_wastage_cost: float
    ingredient_wastage_cost: float
    production_product_wastage_cost: float
    production_wastage_cost: float
    total_wastage_cost: float
    estimated_net_profit: float
    total_units_sold: int
    total_wastage_units: int
    missing_cost_rows: int
    estimated_cost_rows: int


class ProductMarginItem(BaseModel):
    product_id: UUID
    product_name: str
    sku: str
    units_sold: int
    revenue: float
    cogs: float
    gross_profit: float
    gross_margin_pct: float
    avg_selling_price: float
    unit_cogs: float
    missing_cost: bool
    estimated_cost: bool


class ProductMarginResponse(BaseModel):
    date_from: date
    date_to: date
    items: List[ProductMarginItem]


class PnlTrendPoint(BaseModel):
    date: date
    revenue: float
    cogs: float
    gross_profit: float
    store_wastage_cost: float
    ingredient_wastage_cost: float
    production_product_wastage_cost: float
    production_wastage_cost: float
    wastage_cost: float
    estimated_net_profit: float


class PnlTrendResponse(BaseModel):
    date_from: date
    date_to: date
    points: List[PnlTrendPoint]
    total_revenue: float
    total_cogs: float
    gross_profit: float
    total_store_wastage_cost: float
    total_ingredient_wastage_cost: float
    total_production_product_wastage_cost: float
    total_production_wastage_cost: float
    total_wastage_cost: float
    estimated_net_profit: float
