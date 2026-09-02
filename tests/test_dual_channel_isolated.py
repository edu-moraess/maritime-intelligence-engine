from datetime import datetime, timedelta, timezone

from src.analytics.dual_channel import sequence_for_track, vessels_in_bbox
from src.config.settings import DEFAULT_BBOX
from src.ingestion.models import AISObservation, VesselSnapshot


def obs(mmsi: str, seconds: int, lat: float, lon: float, sog: float, cog: float) -> AISObservation:
    return AISObservation(
        mmsi=mmsi,
        latitude=lat,
        longitude=lon,
        received_at=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=seconds),
        sog_knots=sog,
        cog_degrees=cog,
        valid=True,
    )


def test_sequence_is_sorted_and_derived_from_real_observations():
    sequence = sequence_for_track(
        "123456789",
        [
            obs("123456789", 20, 25.10, -80.10, 12.0, 90.0),
            obs("123456789", 0, 25.00, -80.20, 10.0, 90.0),
            obs("123456789", 10, 25.05, -80.15, 11.0, 120.0),
        ],
    )
    assert sequence.metrics.points == 3
    assert sequence.samples[0]["elapsed_seconds"] == 0
    assert sequence.samples[-1]["elapsed_seconds"] == 20
    assert sequence.metrics.average_sog_knots == 11.0
    assert sequence.metrics.speed_change_knots == 2.0
    assert sequence.metrics.course_change_degrees == 30.0
    assert sequence.metrics.course_change_events == 1
    assert sequence.metrics.distance_nm > 0


def test_region_filter_uses_current_vessel_position():
    inside = VesselSnapshot(
        mmsi="123456789", latitude=25.70, longitude=-80.00,
        last_received=datetime.now(timezone.utc), sog_knots=10, cog_degrees=90,
        heading_degrees=90, vessel_name=None, message_count=2,
    )
    outside = VesselSnapshot(
        mmsi="987654321", latitude=40.0, longitude=-70.0,
        last_received=datetime.now(timezone.utc), sog_knots=10, cog_degrees=90,
        heading_degrees=90, vessel_name=None, message_count=2,
    )
    assert [v.mmsi for v in vessels_in_bbox([inside, outside], DEFAULT_BBOX)] == [inside.mmsi]
