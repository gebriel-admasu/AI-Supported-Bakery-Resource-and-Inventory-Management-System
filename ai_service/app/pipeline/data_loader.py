"""Unified data loading for the AI forecasting pipeline.

The rest of the pipeline (feature engineering, training, prediction) always
consumes the same canonical schema:

    pandas.DataFrame with columns:
        date           : datetime64[ns]
        store_ref      : str   (UUID for live data, "S{n}" for Kaggle/synthetic)
        product_ref    : str   (UUID for live data, "P{n}" for Kaggle/synthetic)
        quantity_sold  : int
        source         : str   ("live" | "kaggle" | "synthetic")

This module bridges the three real-world sources to that canonical shape via
the :func:`load_training_data` priority chain.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Optional

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Source descriptor
# ---------------------------------------------------------------------------


class DataSource(str, Enum):
    LIVE = "live"
    KAGGLE = "kaggle"
    SYNTHETIC = "synthetic"


@dataclass
class LoadResult:
    """Wraps the resulting DataFrame with metadata about which source produced
    it. Callers use ``source`` for MLOps logging and ``rows`` for the
    retraining volume threshold check."""

    df: pd.DataFrame
    source: DataSource
    rows: int
    description: str


CANONICAL_COLUMNS = ["date", "store_ref", "product_ref", "quantity_sold", "source"]


# ---------------------------------------------------------------------------
# Individual loaders
# ---------------------------------------------------------------------------


def load_kaggle_csv(path: Optional[Path] = None) -> Optional[pd.DataFrame]:
    """Reads the Store Item Demand Forecasting Challenge ``train.csv``.

    Native schema: ``date, store, item, sales`` where store and item are
    integer IDs in [1..10] and [1..50] respectively. Returns ``None`` if
    the file isn't present (caller falls back to the next source).
    """
    target = path or Path(settings.KAGGLE_DATA_PATH) / "train.csv"
    if not target.exists():
        logger.debug("Kaggle CSV not found at %s", target)
        return None

    df = pd.read_csv(target, parse_dates=["date"])
    df = df.rename(
        columns={
            "store": "store_ref",
            "item": "product_ref",
            "sales": "quantity_sold",
        }
    )
    # Normalise integer IDs to "S{n}" / "P{n}" so the canonical schema
    # uses strings everywhere (matches live UUIDs and synthetic IDs).
    df["store_ref"] = "S" + df["store_ref"].astype(str)
    df["product_ref"] = "P" + df["product_ref"].astype(str)
    df["source"] = DataSource.KAGGLE.value
    return df[CANONICAL_COLUMNS].copy()


def load_synthetic_csv(path: Optional[Path] = None) -> Optional[pd.DataFrame]:
    """Reads the synthetic generator output. Already in canonical shape
    (the generator was designed to match)."""
    target = path or Path(settings.SYNTHETIC_DATA_PATH)
    if not target.exists():
        logger.debug("Synthetic CSV not found at %s", target)
        return None

    df = pd.read_csv(target, parse_dates=["date"])
    df["source"] = DataSource.SYNTHETIC.value
    return df[CANONICAL_COLUMNS].copy()


def load_live_sales(
    db: Session,
    *,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
) -> pd.DataFrame:
    """Reads `sales_records` from the shared backend database.

    We use a raw SQL string (rather than the backend's SQLAlchemy models)
    to avoid the AI service depending on the backend package. The schema
    is stable enough — it's owned by the backend's Phase 7 migration —
    that hard-coding the column list here is safe.
    """
    sql = """
        SELECT
            date AS date,
            CAST(store_id AS TEXT) AS store_ref,
            CAST(product_id AS TEXT) AS product_ref,
            quantity_sold AS quantity_sold
        FROM sales_records
        WHERE 1=1
    """
    params: dict[str, object] = {}
    if since is not None:
        sql += " AND date >= :since"
        params["since"] = since.date() if isinstance(since, datetime) else since
    if until is not None:
        sql += " AND date <= :until"
        params["until"] = until.date() if isinstance(until, datetime) else until

    rows = db.execute(text(sql), params).fetchall()
    if not rows:
        return pd.DataFrame(columns=CANONICAL_COLUMNS)

    df = pd.DataFrame(rows, columns=["date", "store_ref", "product_ref", "quantity_sold"])
    df["date"] = pd.to_datetime(df["date"])
    df["source"] = DataSource.LIVE.value
    return df[CANONICAL_COLUMNS].copy()


def count_live_sales(db: Session, *, since: Optional[datetime] = None) -> int:
    """Light-weight counter used by the retraining trigger (Phase 12) to
    decide if enough new rows have arrived to fire a training run."""
    sql = "SELECT COUNT(*) FROM sales_records WHERE 1=1"
    params: dict[str, object] = {}
    if since is not None:
        sql += " AND date >= :since"
        params["since"] = since.date() if isinstance(since, datetime) else since
    return int(db.execute(text(sql), params).scalar() or 0)


# ---------------------------------------------------------------------------
# Priority chain
# ---------------------------------------------------------------------------


def load_training_data(
    db: Optional[Session] = None,
    *,
    prefer: Optional[DataSource] = None,
    min_live_rows: int = 500,
) -> LoadResult:
    """Picks the best available training source.

    Priority (when ``prefer`` is None):

    1. **Live sales** if we have ``min_live_rows`` rows in the backend DB
       (otherwise the resulting model has no signal worth learning).
    2. **Kaggle CSV** if downloaded.
    3. **Synthetic CSV** if generated.

    Passing ``prefer`` bypasses auto-selection — useful for bootstrap scripts
    that explicitly want Kaggle, and for unit tests that pin the synthetic
    source.
    """
    if prefer == DataSource.LIVE:
        if db is None:
            raise ValueError("LIVE source requires a database session.")
        df = load_live_sales(db)
        return LoadResult(df, DataSource.LIVE, len(df), "Live sales from backend DB")

    if prefer == DataSource.KAGGLE:
        df = load_kaggle_csv()
        if df is None:
            raise FileNotFoundError(
                f"Kaggle CSV not found at {settings.KAGGLE_DATA_PATH}/train.csv"
            )
        return LoadResult(df, DataSource.KAGGLE, len(df), "Kaggle Store Item Demand CSV")

    if prefer == DataSource.SYNTHETIC:
        df = load_synthetic_csv()
        if df is None:
            raise FileNotFoundError(
                f"Synthetic CSV not found at {settings.SYNTHETIC_DATA_PATH}. "
                "Run: python -m scripts.generate_synthetic_sales"
            )
        return LoadResult(df, DataSource.SYNTHETIC, len(df), "Generated synthetic sales")

    # Auto-select
    if db is not None and count_live_sales(db) >= min_live_rows:
        df = load_live_sales(db)
        logger.info("Auto-selected LIVE source (%d rows >= %d threshold)", len(df), min_live_rows)
        return LoadResult(df, DataSource.LIVE, len(df), "Live sales (auto)")

    kaggle_df = load_kaggle_csv()
    if kaggle_df is not None:
        logger.info("Auto-selected KAGGLE source (%d rows)", len(kaggle_df))
        return LoadResult(kaggle_df, DataSource.KAGGLE, len(kaggle_df), "Kaggle CSV (auto)")

    synth_df = load_synthetic_csv()
    if synth_df is not None:
        logger.info("Auto-selected SYNTHETIC source (%d rows)", len(synth_df))
        return LoadResult(synth_df, DataSource.SYNTHETIC, len(synth_df), "Synthetic CSV (auto)")

    raise RuntimeError(
        "No training data available. Either download the Kaggle dataset "
        f"to {settings.KAGGLE_DATA_PATH}/train.csv, run the synthetic "
        "generator (python -m scripts.generate_synthetic_sales), or "
        "accumulate sales records in the backend DB."
    )


def latest_date(df: pd.DataFrame) -> date:
    """Returns the maximum date present in the canonical dataframe."""
    return df["date"].max().date()
