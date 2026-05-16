"""Pydantic schemas for the AI proxy endpoints (Phase 11 + 12 wiring).

These mirror the AI service's wire format (``ai_service/app/schemas/predictions.py``)
with two key differences:

1. **Enriched identifiers.** The AI service stores ``store_ref`` / ``product_ref``
   as opaque strings (live UUIDs or ``S{n}``/``P{n}`` for Kaggle warm-start).
   The proxy resolves them to backend ``Store``/``Product`` rows when possible
   and surfaces both the raw ref AND a human-readable ``name`` so the
   frontend can display "Whole Wheat Bread" instead of ``P1``.

2. **Backend-friendly types.** We type quantities as ``float`` (same as the AI
   schemas) so the React chart libs receive numbers, not strings.

Schemas live here rather than re-exported from the AI service so the backend
package has no install-time dependency on the AI service codebase.
"""

from __future__ import annotations

from datetime import date as Date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# Disable Pydantic v2's "protected_namespaces" guard for our AI schemas — we
# legitimately have fields named ``model_version`` / ``model_path`` that
# describe ML model metadata, not Pydantic's BaseModel internals. Suppressing
# the warning here once is cleaner than scattering ``model_config`` everywhere.
_AI_SCHEMA_CONFIG = ConfigDict(protected_namespaces=())


# ---------------------------------------------------------------------------
# Request — POST /api/v1/ai/predict
# ---------------------------------------------------------------------------


class PredictRequest(BaseModel):
    store_id: Optional[str] = Field(default=None, description="Store UUID or AI-side ref.")
    product_id: Optional[str] = Field(default=None, description="Product UUID or AI-side ref.")
    target_date: Optional[Date] = None
    days: int = Field(default=1, ge=1, le=14)

    model_config = ConfigDict(extra="forbid", protected_namespaces=())


# ---------------------------------------------------------------------------
# Response item enrichment helpers
# ---------------------------------------------------------------------------


class ForecastItem(BaseModel):
    """One predicted quantity, enriched with human-readable labels when the
    underlying ref maps to a real backend Store / Product."""

    store_ref: str
    product_ref: str
    store_name: Optional[str] = None
    product_name: Optional[str] = None
    target_date: Date
    predicted_qty: float
    horizon: str = "day"


class PredictResponse(BaseModel):
    model_config = _AI_SCHEMA_CONFIG

    model_version: int
    generated_at: datetime
    horizon_days: int
    items: list[ForecastItem]


# ---------------------------------------------------------------------------
# Response — GET /api/v1/ai/forecasts
# ---------------------------------------------------------------------------


class ForecastListItem(BaseModel):
    model_config = _AI_SCHEMA_CONFIG

    id: str
    model_version: int
    store_ref: str
    product_ref: str
    store_name: Optional[str] = None
    product_name: Optional[str] = None
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
# Response — GET /api/v1/ai/optimal-batches
# ---------------------------------------------------------------------------


class OptimalBatchItem(BaseModel):
    product_ref: str
    product_name: Optional[str] = None
    target_date: Date
    forecasted_demand: float
    suggested_batch_qty: int
    confidence: str = "medium"


class OptimalBatchResponse(BaseModel):
    model_config = _AI_SCHEMA_CONFIG

    model_version: int
    generated_at: datetime
    horizon_days: int
    items: list[OptimalBatchItem]


# ---------------------------------------------------------------------------
# Response — GET /api/v1/ai/models
# ---------------------------------------------------------------------------


class ModelRegistryItem(BaseModel):
    model_config = _AI_SCHEMA_CONFIG

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


# ---------------------------------------------------------------------------
# Response — GET /api/v1/ai/models/performance
# ---------------------------------------------------------------------------


class ModelPerformancePoint(BaseModel):
    bucket_date: Date
    mae: float
    predictions: int


class ModelPerformanceResponse(BaseModel):
    model_config = _AI_SCHEMA_CONFIG

    model_version: int
    window_days: int
    overall_mae: Optional[float]
    daily: list[ModelPerformancePoint]


# ---------------------------------------------------------------------------
# Request/Response — POST /api/v1/ai/retrain
# ---------------------------------------------------------------------------


class RetrainRequest(BaseModel):
    source: Optional[str] = Field(default=None)
    reason: str = Field(default="manual")

    @field_validator("source")
    @classmethod
    def _check_source(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.lower().strip()
        if v not in {"kaggle", "synthetic", "live"}:
            raise ValueError("source must be 'kaggle' | 'synthetic' | 'live'")
        return v


class RetrainResponse(BaseModel):
    candidate_version: int
    status: str
    holdout_mae: float
    training_rows: int
    training_source: str
    promoted: bool
    message: str


# ---------------------------------------------------------------------------
# Response — POST /api/v1/ai/backtest
# ---------------------------------------------------------------------------


class BacktestResponse(BaseModel):
    rows_scored: int
    forecasts_skipped_no_actual: int
    mean_abs_error: Optional[float] = None
    window_start: Optional[Date] = None
    window_end: Optional[Date] = None
