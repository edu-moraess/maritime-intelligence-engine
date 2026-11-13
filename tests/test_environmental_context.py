from datetime import datetime, timezone
from dataclasses import replace

import pytest

from src.environment.context import EnvironmentalContext
from src.environment.open_meteo_marine import classify_environmental_failure
from src.ingestion.models import EnvironmentalObservation


def make_observation(region: str, minute: int, wave_height: float) -> EnvironmentalObservation:
    return EnvironmentalObservation(
        source="test-source",
        observed_at=datetime(2026, 9, 25, 2, minute, tzinfo=timezone.utc),
        latitude=51.0,
        longitude=1.5,
        region=region,
        wave_height_m=wave_height,
    )


def test_empty_context_is_unavailable() -> None:
    context = EnvironmentalContext(region="B")

    assert context.status == "UNAVAILABLE"
    assert context.latest is None
    assert context.observed_at is None
    assert context.as_dict()["latest"] is None


def test_context_exposes_latest_real_observation() -> None:
    older = make_observation("B", 1, 0.8)
    newer = make_observation("B", 5, 1.2)

    context = EnvironmentalContext(
        region="B",
        observations=(newer, older),
    )

    assert context.status == "AVAILABLE"
    assert context.latest == newer
    assert context.observed_at == newer.observed_at
    assert context.as_dict()["observation_count"] == 2


def test_add_returns_new_context_without_mutating_original() -> None:
    context = EnvironmentalContext(region="B")
    observation = make_observation("B", 5, 1.2)

    updated = context.add(observation)

    assert context.observations == ()
    assert updated.observations == (observation,)
    assert updated.status == "AVAILABLE"


def test_add_rejects_wrong_region() -> None:
    context = EnvironmentalContext(region="B")
    observation = make_observation("A", 5, 1.2)

    with pytest.raises(ValueError, match="does not match"):
        context.add(observation)

def test_failed_context_preserves_failure_class_and_attempt_time():
    attempted_at = datetime(2026, 11, 13, 3, 0, tzinfo=timezone.utc)
    context = EnvironmentalContext(
        region="B",
        failure_code="TIMEOUT",
        failure_reason="TimeoutError: request timed out",
        attempted_at=attempted_at,
    )

    assert context.status == "FAILED"
    payload = context.as_dict()
    assert payload["failure_code"] == "TIMEOUT"
    assert payload["failure_reason"] == "TimeoutError: request timed out"
    assert payload["attempted_at"] == attempted_at.isoformat()


def test_adding_successful_observation_clears_failure_state():
    failed = EnvironmentalContext(
        region="B",
        failure_code="NETWORK_ERROR",
        failure_reason="connection reset",
    )
    updated = failed.add(make_observation("B", 5, 1.2))

    assert updated.status == "AVAILABLE"
    assert updated.failure_code is None
    assert updated.failure_reason is None

def test_environmental_failure_classifier_distinguishes_failure_domains():
    from urllib.error import URLError

    assert classify_environmental_failure(TimeoutError("timeout")) == "TIMEOUT"
    assert classify_environmental_failure(URLError("offline")) == "NETWORK_ERROR"
    assert classify_environmental_failure(ValueError("invalid payload")) == "INVALID_RESPONSE"
    assert classify_environmental_failure(RuntimeError("unexpected")) == "PROVIDER_ERROR"

def test_failed_refresh_preserves_last_valid_observation_and_marks_degraded():
    valid = make_observation("B", 5, 1.2)
    context = EnvironmentalContext(region="B", observations=(valid,))
    failed = replace(
        context,
        failure_code="TIMEOUT",
        failure_reason="TimeoutError: request timed out",
        attempted_at=datetime(2026, 11, 13, 3, 0, tzinfo=timezone.utc),
    )

    assert failed.status == "DEGRADED"
    assert failed.latest == valid
    assert failed.observations == (valid,)
    assert failed.failure_code == "TIMEOUT"
    recovered = failed.add(make_observation("B", 6, 1.4))
    assert recovered.status == "AVAILABLE"
    assert recovered.failure_code is None
