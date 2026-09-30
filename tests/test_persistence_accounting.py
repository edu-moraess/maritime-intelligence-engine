"""Regression tests for historical persistence accounting."""

from src.historical.writer import HistoricalWriteResult


def test_persistence_accounting_balances_current_session():
    result = HistoricalWriteResult(
        status="HISTORICAL DATABASE AVAILABLE",
        session_id="session-1",
        persisted_observations=7,
        duplicate_observations=2,
        skipped_invalid=1,
        reason="ok",
        received_observations=10,
    )

    assert result.accounted_observations == 10
    assert result.accounting_balanced is True


def test_persistence_accounting_detects_unaccounted_observations():
    result = HistoricalWriteResult(
        status="HISTORICAL DATABASE UNAVAILABLE",
        session_id=None,
        persisted_observations=0,
        duplicate_observations=0,
        skipped_invalid=2,
        reason="failed",
        received_observations=10,
    )

    assert result.accounted_observations == 2
    assert result.accounting_balanced is False


def test_persistence_accounting_detects_overcount():
    result = HistoricalWriteResult(
        status="HISTORICAL DATABASE AVAILABLE",
        session_id="session-1",
        persisted_observations=8,
        duplicate_observations=3,
        skipped_invalid=0,
        reason="ok",
        received_observations=10,
    )

    assert result.accounted_observations == 11
    assert result.accounting_balanced is False
