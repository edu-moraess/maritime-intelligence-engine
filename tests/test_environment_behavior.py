"""Tests for deterministic environment × vessel × behavior context."""

from datetime import datetime, timedelta, timezone

from src.config.settings import RegionBBox
from src.environment.context import EnvironmentalContext
from src.ingestion.models import AISObservation, EnvironmentalObservation, VesselSnapshot
from src.intelligence.environment_behavior import resolve_environment_behavior


NOW = datetime(2026, 9, 27, 1, 0, tzinfo=timezone.utc)


def _bbox(name: str, min_lat: float, max_lat: float, min_lon: float, max_lon: float):
    return ((min_lat, min_lon), (max_lat, max_lon))


def _vessel(lat=0.5, lon=0.5):
    return VesselSnapshot(
        mmsi="123456789",
        latitude=lat,
        longitude=lon,
        last_received=NOW,
        sog_knots=10.0,
        cog_degrees=90.0,
        heading_degrees=90.0,
        vessel_name="TEST VESSEL",
        message_count=2,
        observed_at=NOW,
    )


def _observations(count=2):
    return [
        AISObservation(
            mmsi="123456789",
            latitude=0.5 + i * 0.01,
            longitude=0.5 + i * 0.01,
            received_at=NOW + timedelta(minutes=i),
            sog_knots=10.0 + i,
            cog_degrees=90.0,
            heading_degrees=90.0,
        )
        for i in range(count)
    ]


def _environment(observed_at=NOW):
    observation = EnvironmentalObservation(
        source="TEST_SOURCE",
        observed_at=observed_at,
        latitude=0.5,
        longitude=0.5,
        region="region_1",
        wave_height_m=1.2,
        wave_period_s=7.0,
        ocean_current_velocity=0.4,
    )
    return {"region_1": EnvironmentalContext(region="region_1", observations=(observation,))}


def test_available_environment_and_behavior_are_correlated():
    bbox = _bbox("test", 0.0, 1.0, 0.0, 1.0)
    result = resolve_environment_behavior(
        _vessel(),
        _observations(),
        _environment(NOW - timedelta(seconds=30)),
        (bbox,),
    )

    assert result.status == "AVAILABLE"
    assert result.region == "region_1"
    assert result.behavior.classification == "UNDERWAY"
    assert result.observation is not None
    assert result.observation.wave_height_m == 1.2


def test_insufficient_behavior_remains_explicit():
    bbox = _bbox("test", 0.0, 1.0, 0.0, 1.0)
    result = resolve_environment_behavior(
        _vessel(),
        _observations(count=1),
        _environment(),
        (bbox,),
    )

    assert result.status == "INSUFFICIENT_BEHAVIOR"
    assert result.behavior.classification == "INSUFFICIENT_DATA"


def test_environment_unavailable_is_not_fabricated():
    bbox = _bbox("test", 0.0, 1.0, 0.0, 1.0)
    result = resolve_environment_behavior(
        _vessel(),
        _observations(),
        {},
        (bbox,),
    )

    assert result.status == "ENVIRONMENT_UNAVAILABLE"
    assert result.observation is None
    assert result.behavior.classification == "UNDERWAY"


def test_overlapping_regions_are_not_arbitrarily_assigned():
    first = _bbox("first", 0.0, 1.0, 0.0, 1.0)
    second = _bbox("second", 0.0, 1.0, 0.0, 1.0)
    result = resolve_environment_behavior(
        _vessel(),
        _observations(),
        _environment(),
        (first, second),
    )

    assert result.status == "ENVIRONMENT_UNAVAILABLE"
    assert result.environment.status == "AMBIGUOUS_REGION"
    assert result.region is None
