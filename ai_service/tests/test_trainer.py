"""Trainer + Forecaster integration tests."""

from __future__ import annotations

from datetime import timedelta

from app.ml.forecaster import Forecaster
from app.ml.trainer import next_version_number, train_model


def test_trainer_produces_artifact_and_reasonable_mae(synthetic_sales, tmp_path):
    result = train_model(
        synthetic_sales,
        model_dir=tmp_path / "models",
        version=1,
        holdout_days=14,
        num_rounds=100,
        early_stopping_rounds=20,
    )
    assert result.model_path.exists()
    assert result.training_rows > 0
    assert result.holdout_rows > 0
    assert result.feature_count > 0
    # Synthetic data has noise of ~stddev 2 so any sane model should hit MAE < 5.
    assert result.holdout_mae < 5.0


def test_next_version_number_is_monotonic():
    assert next_version_number([]) == 1
    assert next_version_number([1, 2, 3]) == 4
    assert next_version_number([5]) == 6


def test_forecaster_loads_and_predicts(trained_model, synthetic_sales):
    forecaster = Forecaster.from_artifact(trained_model.model_path)

    history = synthetic_sales.copy()
    last_date = history["date"].max().date()
    future_day = last_date + timedelta(days=1)

    points = forecaster.predict_daily(history, target_date=future_day)
    assert len(points) > 0
    for p in points:
        assert p.target_date == future_day
        assert p.predicted_qty >= 0  # non-negative clip


def test_forecaster_horizon_returns_one_point_per_day_per_pair(trained_model, synthetic_sales):
    forecaster = Forecaster.from_artifact(trained_model.model_path)

    history = synthetic_sales.copy()
    last_date = history["date"].max().date()
    start_date = last_date + timedelta(days=1)
    n_pairs = synthetic_sales[["store_ref", "product_ref"]].drop_duplicates().shape[0]

    points = forecaster.predict_horizon(history, start_date=start_date, days=7)
    assert len(points) == 7 * n_pairs


def test_artifact_round_trip_preserves_state(trained_model):
    forecaster = Forecaster.from_artifact(trained_model.model_path)
    # The forecaster's state.feature_columns must match what the trainer recorded.
    assert forecaster.state.feature_columns == trained_model.state.feature_columns
    assert forecaster.version == 1
    assert forecaster.best_iteration > 0
