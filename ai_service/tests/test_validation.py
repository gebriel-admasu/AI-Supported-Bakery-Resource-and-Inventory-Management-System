"""Validation gate decision-matrix tests.

We don't always need the heavy LightGBM forecaster path — many gate cases
can be exercised by stubbing the per-row error arrays directly. For the
real integration case we train two tiny models and let the gate compare them
end-to-end.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.config import settings
from app.db.models import ModelStatus
from app.ml.registry import promote_candidate, register_candidate
from app.ml.validation import ValidationResult, validate_candidate


def _make_registry_row(db, version: int, mae: float, model_path: str = "fake.joblib"):
    return register_candidate(
        db,
        version=version,
        model_path=model_path,
        holdout_mae=mae,
        training_rows_used=100,
        training_source="synthetic",
        feature_columns=["a", "b"],
    )


# ---------------------------------------------------------------------------
# Cold-start branch
# ---------------------------------------------------------------------------


def test_cold_start_auto_promotes_when_no_champion(db_session):
    candidate = _make_registry_row(db_session, version=1, mae=2.0)

    result = validate_candidate(db_session, candidate=candidate)
    assert result.decision == "PROMOTE_COLD_START"
    assert result.should_promote is True
    assert result.candidate_mae == pytest.approx(2.0)
    assert result.champion_mae is None


# ---------------------------------------------------------------------------
# Same-version branch
# ---------------------------------------------------------------------------


def test_same_version_is_noop_reject(db_session):
    candidate = _make_registry_row(db_session, version=1, mae=2.0)
    promote_candidate(db_session, candidate_version=1, reason="bootstrap")
    db_session.refresh(candidate)
    assert candidate.status == ModelStatus.CHAMPION.value

    result = validate_candidate(db_session, candidate=candidate)
    assert result.decision == "REJECT"
    assert "same model version" in result.reason.lower()


# ---------------------------------------------------------------------------
# Real comparison (stubbed error arrays)
# ---------------------------------------------------------------------------


@pytest.fixture
def stub_error_arrays(monkeypatch):
    """Bypass the heavy forecaster path by monkey-patching
    ``_compute_error_arrays`` to return whatever the test specifies.
    Also stubs ``_load_evaluation_window`` so we don't need real data."""
    from app.ml import validation as validation_module

    def install(champ_errors, cand_errors):
        import pandas as pd

        monkeypatch.setattr(
            validation_module,
            "_load_evaluation_window",
            lambda _db, _days: pd.DataFrame({"date": [pd.Timestamp("2024-01-01")]}),
        )
        monkeypatch.setattr(
            validation_module,
            "_compute_error_arrays",
            lambda *_a, **_kw: (np.array(champ_errors), np.array(cand_errors)),
        )

    return install


def test_promote_when_candidate_clearly_better(db_session, stub_error_arrays):
    _make_registry_row(db_session, version=1, mae=5.0)
    promote_candidate(db_session, candidate_version=1, reason="bootstrap")

    candidate = _make_registry_row(db_session, version=2, mae=2.0)
    stub_error_arrays(
        champ_errors=[5.0] * 30,
        cand_errors=[2.0] * 30,
    )

    result = validate_candidate(db_session, candidate=candidate)
    assert result.decision == "PROMOTE"
    assert result.relative_improvement == pytest.approx(0.6, abs=0.01)
    assert result.p_value is not None
    assert result.p_value < settings.TTEST_P_VALUE_MAX


def test_reject_when_mae_improvement_below_threshold(db_session, stub_error_arrays):
    _make_registry_row(db_session, version=1, mae=5.0)
    promote_candidate(db_session, candidate_version=1, reason="bootstrap")

    candidate = _make_registry_row(db_session, version=2, mae=4.95)
    # 1% improvement, below the 2% threshold
    stub_error_arrays(
        champ_errors=[5.0] * 30,
        cand_errors=[4.95] * 30,
    )

    result = validate_candidate(db_session, candidate=candidate)
    assert result.decision == "REJECT"
    assert result.should_promote is False
    assert "below threshold" in result.reason.lower()


def test_reject_when_pvalue_not_significant(db_session, stub_error_arrays):
    _make_registry_row(db_session, version=1, mae=5.0)
    promote_candidate(db_session, candidate_version=1, reason="bootstrap")

    candidate = _make_registry_row(db_session, version=2, mae=4.0)
    # Big MAE delta but noisy errors -> high p-value
    rng = np.random.default_rng(123)
    cand_errors = rng.normal(loc=4.0, scale=10, size=10)
    champ_errors = rng.normal(loc=5.0, scale=10, size=10)
    stub_error_arrays(champ_errors=champ_errors, cand_errors=cand_errors)

    result = validate_candidate(db_session, candidate=candidate)
    # With high variance + small N the gate should reject for either MAE or t-test reason.
    assert result.decision == "REJECT"


def test_reject_when_eval_window_empty(db_session, monkeypatch):
    _make_registry_row(db_session, version=1, mae=5.0)
    promote_candidate(db_session, candidate_version=1, reason="bootstrap")
    candidate = _make_registry_row(db_session, version=2, mae=4.0)

    from app.ml import validation as validation_module

    monkeypatch.setattr(
        validation_module, "_load_evaluation_window", lambda _db, _days: None
    )

    result = validate_candidate(db_session, candidate=candidate)
    assert result.decision == "REJECT"
    assert "no data" in result.reason.lower()
