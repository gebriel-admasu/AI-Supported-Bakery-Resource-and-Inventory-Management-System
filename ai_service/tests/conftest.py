"""Shared pytest fixtures for the AI service test suite.

Strategy: every test runs against an **in-memory SQLite database** so we never
touch the real shared bakery_dev.db. We achieve this by:

1. Setting ``AI_DATABASE_URL=sqlite:///:memory:`` BEFORE the app modules
   import. Pytest's `conftest.py` is loaded before any test module, so as long
   as we set the env var at the top of this file the AI service's `Settings`
   object picks it up.
2. Creating all four AI tables on the in-memory engine.
3. Patching ``app.api.predictions._load_recent_history`` and
   ``app.pipeline.data_loader.load_training_data`` callers via fixtures so
   they read from in-memory frames rather than the shared DB.

The synthetic data fixture builds a small but realistic frame so trainer +
forecaster paths exercise real LightGBM behaviour, not mocks.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Must be set before any `from app...` import — Settings reads env on import.
os.environ.setdefault("AI_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("DEMO_MODE", "true")

# Make the ai_service/ directory importable as "app.*" when tests run from repo root.
_AI_SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(_AI_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_AI_SERVICE_ROOT))

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

import app.database as ai_database  # noqa: E402
from app.db.models import Base  # noqa: E402


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_engine():
    """A fresh in-memory SQLite engine with the AI schema applied.

    We use ``StaticPool`` so the same connection is reused across the session,
    otherwise an `:memory:` database disappears between connections.
    """
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _set_pragma(dbapi_connection, _record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    Session = sessionmaker(bind=db_engine, autocommit=False, autoflush=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def patch_app_engine(monkeypatch, db_engine):
    """Point ``app.database.engine`` and ``SessionLocal`` at the test engine
    so the FastAPI ``get_db`` dependency yields sessions bound to the in-memory
    schema."""
    Session = sessionmaker(bind=db_engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(ai_database, "engine", db_engine)
    monkeypatch.setattr(ai_database, "SessionLocal", Session)
    yield


# ---------------------------------------------------------------------------
# Synthetic dataset fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def synthetic_sales() -> pd.DataFrame:
    """A canonical-schema sales DataFrame: 3 stores x 4 products x 120 days
    of stationary-ish demand with a weekly seasonality. Enough rows to
    fit a tiny LightGBM model in well under a second.
    """
    rng = np.random.default_rng(42)
    start = pd.Timestamp("2024-01-01")
    days = 120
    stores = [f"S{i}" for i in range(1, 4)]
    products = [f"P{i}" for i in range(1, 5)]

    records = []
    for store in stores:
        store_base = 20 + 5 * int(store[1:])
        for product in products:
            product_base = 5 + 2 * int(product[1:])
            for d in range(days):
                date = start + pd.Timedelta(days=d)
                dow = date.dayofweek
                weekly = 5 if dow in (5, 6) else 0  # weekend bump
                noise = rng.normal(loc=0, scale=2)
                qty = max(0, round(store_base + product_base + weekly + noise))
                records.append(
                    {
                        "date": date,
                        "store_ref": store,
                        "product_ref": product,
                        "quantity_sold": qty,
                        "source": "synthetic",
                    }
                )
    return pd.DataFrame(records)


@pytest.fixture
def trained_model(synthetic_sales, tmp_path):
    """Train a tiny LightGBM model on the synthetic fixture and return the
    :class:`TrainingResult`. Cached per-test to avoid duplicate training when
    multiple fixtures want a trained artifact.
    """
    from app.ml.trainer import train_model

    return train_model(
        synthetic_sales,
        model_dir=tmp_path / "models",
        version=1,
        holdout_days=14,
        num_rounds=120,             # keep tests fast
        early_stopping_rounds=20,
    )


@pytest.fixture
def trained_forecaster(trained_model):
    """A :class:`Forecaster` loaded straight from the test artifact."""
    from app.ml.forecaster import Forecaster

    return Forecaster.from_artifact(trained_model.model_path)
