"""Regression tests for the non-blocking finite AIS collection lifecycle."""

from __future__ import annotations

import time
from threading import Event

import pytest

from src.config.settings import AppSettings, DEFAULT_BBOX
from src.intelligence.engine import create_engine


def _engine():
    return create_engine(AppSettings(aisstream_api_key="test-key", bbox=DEFAULT_BBOX))


def test_finite_collection_rejects_unsupported_duration():
    engine = _engine()
    with pytest.raises(ValueError, match="one of"):
        engine.start_finite_collection(45)


def test_finite_collection_runs_outside_the_engine_state_lock(monkeypatch):
    engine = _engine()
    entered = Event()
    release = Event()

    def blocked_collect(seconds):
        entered.set()
        assert release.wait(timeout=2.0)
        return 3

    monkeypatch.setattr(engine, "collect", blocked_collect)
    assert engine.start_finite_collection(30)
    assert entered.wait(timeout=1.0)

    # The UI's polling/status path must remain responsive while collection waits.
    status = engine.finite_collection_status()
    assert status["state"] == "RUNNING"
    assert status["elapsed_seconds"] >= 0

    release.set()
    deadline = time.monotonic() + 2.0
    while engine.finite_collection_status()["state"] == "RUNNING":
        assert time.monotonic() < deadline
        time.sleep(0.005)

    completed = engine.finite_collection_status()
    assert completed["state"] == "COMPLETED"
    assert completed["received"] == 3


def test_live_start_and_clear_are_blocked_during_finite_collection(monkeypatch):
    engine = _engine()
    entered = Event()
    release = Event()

    def blocked_collect(seconds):
        entered.set()
        assert release.wait(timeout=2.0)
        return 0

    monkeypatch.setattr(engine, "collect", blocked_collect)
    assert engine.start_finite_collection(60)
    assert entered.wait(timeout=1.0)

    with pytest.raises(RuntimeError, match="finite AIS collection"):
        engine.start_live_monitoring()
    with pytest.raises(RuntimeError, match="finite AIS collection"):
        engine.clear_session_data()

    release.set()
    deadline = time.monotonic() + 2.0
    while engine.finite_collection_status()["state"] == "RUNNING":
        assert time.monotonic() < deadline
        time.sleep(0.005)
