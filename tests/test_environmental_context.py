from datetime import datetime, timezone

import pytest

from src.environment.context import EnvironmentalContext
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
