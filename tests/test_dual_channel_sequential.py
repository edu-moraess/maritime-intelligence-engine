from datetime import datetime, timedelta, timezone

from src.analytics.dual_channel import sequence_for_track, vessels_in_bbox
from src.config.settings import AppSettings, DEFAULT_BBOX
from src.ingestion.models import AISObservation, VesselSnapshot


def _obs(mmsi: str, t: int, lat: float, lon: float, sog: float, cog: float) -> AISObservation:
    return AISObservation(
        mmsi=mmsi,
        latitude=lat,
        longitude=lon,
        received_at=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=t),
        sog_knots=sog,
        cog_degrees=cog,
        valid=True,
    )


def test_sequence_metrics_are_derived_from_ordered_real_observations():
    sequence = sequence_for_track(
        "123456789",
        [
            _obs("123456789", 20, 25.10, -80.10, 12.0, 90.0),
            _obs("123456789", 0, 25.00, -80.20, 10.0, 90.0),
            _obs("123456789", 10, 25.05, -80.15, 11.0, 120.0),
        ],
    )

    assert sequence.metrics.points == 3
    assert sequence.metrics.duration_seconds == 20
    assert sequence.metrics.average_sog_knots == 11.0
    assert sequence.metrics.max_sog_knots == 12.0
    assert sequence.metrics.speed_change_knots == 2.0
    assert sequence.metrics.course_change_degrees == 30.0
    assert sequence.metrics.course_change_events == 1
    assert sequence.samples[0]["elapsed_seconds"] == 0
    assert sequence.samples[-1]["elapsed_seconds"] == 20
    assert sequence.metrics.distance_nm > 0


def test_vessels_are_assigned_to_current_region_by_position():
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


def test_legacy_single_bbox_construction_stays_compatible():
    custom = ((10.0, 20.0), (11.0, 21.0))
    settings = AppSettings(aisstream_api_key="key", bbox=custom)

    assert settings.monitoring_bboxes == (custom,)
    assert settings.bbox_payload == [[[10.0, 20.0], [11.0, 21.0]]]


def test_dual_bbox_serialization_uses_one_subscription_payload():
    first = DEFAULT_BBOX
    second = ((49.8, -5.5), (51.5, 2.5))
    settings = AppSettings(
        aisstream_api_key="key",
        bbox=first,
        monitoring_bboxes=(first, second),
    )

    assert settings.bbox_payload == [
        [[25.603, -80.208], [25.835, -79.879]],
        [[49.8, -5.5], [51.5, 2.5]],
    ]
    ready, reason = settings.validate_for_connection()
    assert ready is True
    assert reason == "ready"
