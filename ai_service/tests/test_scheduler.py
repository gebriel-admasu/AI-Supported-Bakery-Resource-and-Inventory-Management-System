"""Tests for the APScheduler-based retrain scheduler.

We don't wait for the cron triggers to fire (that would couple tests to
wall-clock time). Instead we invoke the job functions directly with a
patched orchestrator, which is what the cron callbacks ultimately do."""

from __future__ import annotations

import pytest

from app.scheduler import retrain_scheduler as sched


def test_volume_check_does_nothing_below_threshold(db_session, monkeypatch):
    """With no live sales yet (default = 0) and the default threshold,
    the volume check should NOT trigger a retrain."""
    monkeypatch.setattr(sched, "count_live_sales", lambda _db: 5)
    monkeypatch.setattr(sched, "_latest_training_row_count", lambda _db: 0)
    monkeypatch.setattr(sched, "SessionLocal", lambda: db_session)

    monkeypatch.setattr(sched.settings, "DEMO_MODE", True)  # threshold = 20

    triggered = {"called": False}
    monkeypatch.setattr(
        sched, "_trigger_retrain", lambda **_: triggered.update(called=True)
    )

    sched._job_volume_check()
    assert triggered["called"] is False


def test_volume_check_triggers_when_delta_exceeds_threshold(db_session, monkeypatch):
    monkeypatch.setattr(sched, "count_live_sales", lambda _db: 50)
    monkeypatch.setattr(sched, "_latest_training_row_count", lambda _db: 0)
    monkeypatch.setattr(sched, "SessionLocal", lambda: db_session)

    monkeypatch.setattr(sched.settings, "DEMO_MODE", True)  # threshold = 20

    triggered = {"calls": 0, "reason": None}

    def _stub_trigger(*, reason):
        triggered["calls"] += 1
        triggered["reason"] = reason

    monkeypatch.setattr(sched, "_trigger_retrain", _stub_trigger)

    sched._job_volume_check()
    assert triggered["calls"] == 1
    assert "volume_threshold" in triggered["reason"]
    assert "delta=50" in triggered["reason"]


def test_trigger_retrain_uses_module_lock(db_session, monkeypatch):
    """The module-level lock guards against accidental concurrent retrains.
    We force `run_retrain` to raise so we can confirm the lock is released
    even on failure."""

    calls = {"count": 0}

    def _stub_run(_db, **_kw):
        calls["count"] += 1
        raise RuntimeError("forced failure for test")

    monkeypatch.setattr(sched, "run_retrain", _stub_run)
    monkeypatch.setattr(sched, "SessionLocal", lambda: db_session)

    # First call: lock acquired, run_retrain raises, error logged, lock released.
    sched._trigger_retrain(reason="test.failure")
    assert calls["count"] == 1
    assert sched._retrain_lock.locked() is False

    # Second call: lock should be free; run_retrain should be called again.
    sched._trigger_retrain(reason="test.retry")
    assert calls["count"] == 2


def test_latest_training_row_count_returns_zero_when_no_models(db_session):
    assert sched._latest_training_row_count(db_session) == 0


def test_start_stop_scheduler_is_idempotent(monkeypatch):
    """Starting twice shouldn't blow up, and stopping when nothing's running
    is a no-op.

    We replace every job body with a no-op BEFORE starting so the
    ``next_run_time=now`` warm-up tick can't accidentally hit the real
    shared DB or fire a retrain."""
    monkeypatch.setattr(sched, "_job_daily_backtest", lambda: None)
    monkeypatch.setattr(sched, "_job_weekly_retrain", lambda: None)
    monkeypatch.setattr(sched, "_job_volume_check", lambda: None)

    instance = sched.start_scheduler()
    try:
        again = sched.start_scheduler()
        assert again is instance
        assert instance.running is True
        # All three jobs should be registered.
        job_ids = {job.id for job in instance.get_jobs()}
        assert {"daily_backtest", "weekly_retrain", "hourly_volume_check"} <= job_ids
    finally:
        sched.stop_scheduler()
        sched.stop_scheduler()  # second stop should be a silent no-op
