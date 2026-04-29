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
    total_wastage_cost: float
    estimated_net_profit: float
    total_units_sold: int
    total_wastage_units: int
    missing_cost_rows: int


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


class ProductMarginResponse(BaseModel):
    date_from: date
    date_to: date
    items: List[ProductMarginItem]


class PnlTrendPoint(BaseModel):
    date: date
    revenue: float
    cogs: float
    gross_profit: float
    wastage_cost: float
    estimated_net_profit: float


class PnlTrendResponse(BaseModel):
    date_from: date
    date_to: date
    points: List[PnlTrendPoint]
    total_revenue: float
    total_cogs: float
    gross_profit: float
    total_wastage_cost: float
    estimated_net_profit: float
