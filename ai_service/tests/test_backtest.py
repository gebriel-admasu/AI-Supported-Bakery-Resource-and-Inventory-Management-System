"""Unit tests for ``pipeline/backtest.py``."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pandas as pd
import pytest

from app.db.models import Forecast, ForecastActual, MlopsEventType, MlopsLog
from app.ml.registry import register_candidate
from app.pipeline.backtest import run_backtest


@pytest.fixture(autouse=True)
def _seed_model_registry(db_session):
    """Backtest tests insert forecasts that reference ``model_version=1``;
    the FK requires a registry row to exist first."""
    register_candidate(
        db_session,
        version=1,
        model_path="fake.joblib",
        holdout_mae=1.0,
        training_rows_used=100,
        training_source="synthetic",
        feature_columns=["a"],
    )


@pytest.fixture
def seed_actuals(monkeypatch):
    """Patch the data loader so the backtest sees a deterministic actuals
    table without touching the shared backend DB."""
    from app.pipeline import backtest as backtest_module
    from app.pipeline.data_loader import DataSource, LoadResult

    def _build_actuals(rows: list[tuple[str, str, date, float]]) -> pd.DataFrame:
        df = pd.DataFrame(rows, columns=["store_ref", "product_ref", "date", "quantity_sold"])
        df["source"] = "synthetic"
        df["date"] = pd.to_datetime(df["date"])
        return df

    def install(rows):
        df = _build_actuals(rows)
        monkeypatch.setattr(
            backtest_module,
            "load_training_data",
            lambda **_: LoadResult(df=df, source=DataSource.SYNTHETIC, rows=len(df), description="test"),
        )

    return install


def test_backtest_scores_matched_forecasts(db_session, seed_actuals):
    yesterday = date.today() - timedelta(days=1)
    seed_actuals(
        [
            ("S1", "P1", yesterday, 10.0),
            ("S1", "P2", yesterday, 20.0),
        ]
    )

    fc1 = Forecast(
        id=uuid.uuid4(),
        model_version=1,
        store_ref="S1",
        product_ref="P1",
        target_date=yesterday,
        horizon="day",
        predicted_qty=8.0,
    )
    fc2 = Forecast(
        id=uuid.uuid4(),
        model_version=1,
        store_ref="S1",
        product_ref="P2",
        target_date=yesterday,
        horizon="day",
        predicted_qty=25.0,
    )
    db_session.add_all([fc1, fc2])
    db_session.commit()

    result = run_backtest(db_session)
    assert result.rows_scored == 2
    assert result.forecasts_skipped_no_actual == 0
    # |8-10| = 2, |25-20| = 5, mean = 3.5
    assert result.mean_abs_error == pytest.approx(3.5)

    actuals_count = db_session.query(ForecastActual).count()
    assert actuals_count == 2


def test_backtest_skips_forecasts_without_actuals(db_session, seed_actuals):
    yesterday = date.today() - timedelta(days=1)
    seed_actuals([("S1", "P1", yesterday, 10.0)])

    fc_matched = Forecast(
        id=uuid.uuid4(),
        model_version=1,
        store_ref="S1",
        product_ref="P1",
        target_date=yesterday,
        horizon="day",
        predicted_qty=12.0,
    )
    fc_unmatched = Forecast(
        id=uuid.uuid4(),
        model_version=1,
        store_ref="S99",
        product_ref="P99",
        target_date=yesterday,
        horizon="day",
        predicted_qty=5.0,
    )
    db_session.add_all([fc_matched, fc_unmatched])
    db_session.commit()

    result = run_backtest(db_session)
    assert result.rows_scored == 1
    assert result.forecasts_skipped_no_actual == 1


def test_backtest_is_idempotent(db_session, seed_actuals):
    yesterday = date.today() - timedelta(days=1)
    seed_actuals([("S1", "P1", yesterday, 10.0)])

    fc = Forecast(
        id=uuid.uuid4(),
        model_version=1,
        store_ref="S1",
        product_ref="P1",
        target_date=yesterday,
        horizon="day",
        predicted_qty=12.0,
    )
    db_session.add(fc)
    db_session.commit()

    first = run_backtest(db_session)
    second = run_backtest(db_session)
    assert first.rows_scored == 1
    assert second.rows_scored == 0  # already matched, nothing to do
    assert db_session.query(ForecastActual).count() == 1


def test_backtest_writes_mlops_log_entry(db_session, seed_actuals):
    yesterday = date.today() - timedelta(days=1)
    seed_actuals([("S1", "P1", yesterday, 10.0)])

    fc = Forecast(
        id=uuid.uuid4(),
        model_version=1,
        store_ref="S1",
        product_ref="P1",
        target_date=yesterday,
        horizon="day",
        predicted_qty=10.0,
    )
    db_session.add(fc)
    db_session.commit()

    run_backtest(db_session)
    logs = (
        db_session.query(MlopsLog)
        .filter(MlopsLog.event_type == MlopsEventType.BACKTEST.value)
        .all()
    )
    assert len(logs) == 1
    assert "scored" in (logs[0].message or "").lower()


def test_backtest_empty_window_returns_zero(db_session, seed_actuals):
    seed_actuals([])
    result = run_backtest(db_session)
    assert result.rows_scored == 0
    assert result.mean_abs_error is None
