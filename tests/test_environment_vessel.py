from datetime import datetime, timezone

from src.config.settings import RegionBBox
from src.environment.context import EnvironmentalContext
from src.ingestion.models import EnvironmentalObservation, VesselSnapshot
from src.intelligence.environment_vessel import resolve_vessel_environment


UTC = timezone.utc
BBOXES: tuple[RegionBBox, RegionBBox] = (
    ((0.0, 0.0), (10.0, 10.0)),
    ((20.0, 20.0), (30.0, 30.0)),
)


def _vessel(lat: float, lon: float) -> VesselSnapshot:
    return VesselSnapshot(
        mmsi="123456789",
        latitude=lat,
        longitude=lon,
        last_received=datetime(2026, 9, 27, 1, 0, tzinfo=UTC),
        sog_knots=10.0,
        cog_degrees=90.0,
        heading_degrees=90.0,
        vessel_name="TEST VESSEL",
        message_count=1,
        observed_at=datetime(2026, 9, 27, 1, 0, tzinfo=UTC),
    )


def _context(region: str) -> EnvironmentalContext:
    observation = EnvironmentalObservation(
        source="test-real-provider",
        observed_at=datetime(2026, 9, 27, 0, 59, tzinfo=UTC),
        latitude=5.0,
        longitude=5.0,
        region=region,
        wave_height_m=1.2,
        wave_period_s=7.0,
        ocean_current_velocity=0.4,
    )
    return EnvironmentalContext(region=region).add(observation)


def test_resolves_exclusive_region_environment():
    result = resolve_vessel_environment(
        _vessel(5.0, 5.0),
        {"region_1": _context("region_1")},
        BBOXES,
    )

    assert result.status == "AVAILABLE"
    assert result.region == "region_1"
    assert result.observation is not None
    assert result.observation.wave_height_m == 1.2
    assert result.environment_age_seconds == 60.0


def test_does_not_assign_environment_when_outside_regions():
    result = resolve_vessel_environment(
        _vessel(15.0, 15.0),
        {"region_1": _context("region_1")},
        BBOXES,
    )

    assert result.status == "OUTSIDE_MONITORED_REGIONS"
    assert result.observation is None


def test_does_not_assign_ambiguous_overlap():
    overlapping = (
        ((0.0, 0.0), (10.0, 10.0)),
        ((5.0, 5.0), (15.0, 15.0)),
    )
    result = resolve_vessel_environment(
        _vessel(7.0, 7.0),
        {"region_1": _context("region_1"), "region_2": _context("region_2")},
        overlapping,
    )

    assert result.status == "AMBIGUOUS_REGION"
    assert result.observation is None


def test_reports_unavailable_region_without_fabricating_values():
    result = resolve_vessel_environment(
        _vessel(5.0, 5.0),
        {},
        BBOXES,
    )

    assert result.status == "UNAVAILABLE"
    assert result.region == "region_1"
    assert result.observation is None
