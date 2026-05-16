"""Pydantic schemas for the prediction-side endpoints.

Mirrors the wire format consumed by the backend proxy + frontend. Decimal-free
on purpose — the model outputs floats and the frontend chart libs expect
numbers, not strings.
"""

from __future__ import annotations

from datetime import date as Date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# /ai/predict — request + response
# ---------------------------------------------------------------------------


class PredictRequest(BaseModel):
    """Inputs for an ad-hoc forecast.

    Either a single (store_ref, product_ref) plus a date, or omit the pair to
    forecast every combo present in recent history. ``days=1`` returns a
    single-day forecast; ``days=7`` returns a weekly horizon.
    """

    store_ref: Optional[str] = Field(default=None, description="Store identifier (UUID or 'S{n}').")
    product_ref: Optional[str] = Field(default=None, description="Product identifier (UUID or 'P{n}').")
    target_date: Optional[Date] = Field(
        default=None,
        description="First day to forecast. Defaults to tomorrow.",
    )
    days: int = Field(default=1, ge=1, le=14, description="Horizon length in days (1..14).")

    model_config = ConfigDict(extra="forbid")


class ForecastItem(BaseModel):
    """One predicted (store, product, date, qty) row."""

    store_ref: str
    product_ref: str
    target_date: Date
    predicted_qty: float
    horizon: str = "day"


class PredictResponse(BaseModel):
    model_version: int
    generated_at: datetime
    horizon_days: int
    items: list[ForecastItem]


# ---------------------------------------------------------------------------
# /ai/forecasts — archived forecast listing
# ---------------------------------------------------------------------------


class ForecastListItem(BaseModel):
    """A row from ``ai_forecasts`` enriched with the matching actual if we
    have one (backtest job fills it in for past dates)."""

    id: str
    model_version: int
    store_ref: str
    product_ref: str
    target_date: Date
    horizon: str
    predicted_qty: float
    actual_qty: Optional[float] = None
    abs_error: Optional[float] = None
    generated_at: datetime


class ForecastListResponse(BaseModel):
    items: list[ForecastListItem]
    total: int


# ---------------------------------------------------------------------------
# /ai/optimal-batches — production planning suggestion
# ---------------------------------------------------------------------------


class OptimalBatchItem(BaseModel):
    """A suggested batch size for a single product on a single day."""

    product_ref: str
    target_date: Date
    forecasted_demand: float
    suggested_batch_qty: int = Field(
        description="Recommended production quantity (forecast rounded up to the nearest unit, "
        "with optional safety stock applied)."
    )
    confidence: str = Field(
        default="medium",
        description="One of 'low' | 'medium' | 'high', derived from how recent the forecast is.",
    )


class OptimalBatchResponse(BaseModel):
    model_version: int
    generated_at: datetime
    horizon_days: int
    items: list[OptimalBatchItem]


# ---------------------------------------------------------------------------
# /ai/models — registry listing + performance summary
# ---------------------------------------------------------------------------


class ModelRegistryItem(BaseModel):
    """A serialisable view of one ``ai_model_registry`` row."""

    id: str
    version: int
    status: str
    trained_at: datetime
    training_rows_used: int
    training_source: Optional[str] = None
    holdout_mae: Optional[float] = None
    model_path: str
    promoted_at: Optional[datetime] = None
    archived_at: Optional[datetime] = None
    notes: Optional[str] = None


class ModelRegistryListResponse(BaseModel):
    champion_version: Optional[int]
    items: list[ModelRegistryItem]


class ModelPerformancePoint(BaseModel):
    """One ``(date, mae, predictions_count)`` data point for the perf chart."""

    bucket_date: Date
    mae: float
    predictions: int


class ModelPerformanceResponse(BaseModel):
    model_version: int
    window_days: int
    overall_mae: Optional[float]
    daily: list[ModelPerformancePoint]


# ---------------------------------------------------------------------------
# /ai/retrain — manual trigger
# ---------------------------------------------------------------------------


class RetrainRequest(BaseModel):
    source: Optional[str] = Field(
        default=None,
        description="Force a specific data source ('kaggle' | 'synthetic' | 'live'). "
        "Defaults to auto-selection.",
    )
    reason: str = Field(default="manual", description="Free-form note stored on the registry row.")

    @field_validator("source")
    @classmethod
    def _normalise_source(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.lower().strip()
        if v not in {"kaggle", "synthetic", "live"}:
            raise ValueError("source must be one of 'kaggle' | 'synthetic' | 'live'")
        return v


class RetrainResponse(BaseModel):
    candidate_version: int
    status: str  # "candidate" | "champion" | "rejected"
    holdout_mae: float
    training_rows: int
    training_source: str
    promoted: bool
    message: str
