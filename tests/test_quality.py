from datetime import datetime, timedelta, timezone

from src.ingestion.models import AISObservation
from src.processing.quality import RECEIVE_GAP_SECONDS, build_quality_report


UTC = timezone.utc
BASE = datetime(2026, 8, 31, 19, 0, tzinfo=UTC)


def observation(
    mmsi: str = "123456789",
    *,
    seconds: int = 0,
    lat: float = 50.7,
    lon: float = -0.4,
    sog: float | None = 10.0,
    cog: float | None = 90.0,
    valid: bool = True,
) -> AISObservation:
    return AISObservation(
        mmsi=mmsi,
        latitude=lat,
        longitude=lon,
        received_at=BASE + timedelta(seconds=seconds),
        sog_knots=sog,
        cog_degrees=cog,
        valid=valid,
    )


def test_empty_session_is_waiting_and_perfect_by_definition() -> None:
    report = build_quality_report([], reference_time=BASE)
    assert report.messages_processed == 0
    assert report.quality_percent == 100.0
    assert report.coverage_status == "WAITING"


def test_normal_session_reports_vessel_and_track_coverage() -> None:
    observations = [
        observation(seconds=0),
        observation(seconds=30),
        observation(mmsi="987654321", seconds=10),
    ]
    report = build_quality_report(observations, reference_time=BASE + timedelta(seconds=31))
    assert report.messages_processed == 3
    assert report.valid_records == 3
    assert report.distinct_vessels == 2
    assert report.tracks_with_history == 1
    assert report.coverage_status == "READY"
    assert report.quality_percent == 100.0


def test_duplicate_and_missing_values_are_counted() -> None:
    observations = [
        observation(seconds=0),
        observation(seconds=0),
        observation(seconds=1, sog=None),
    ]
    report = build_quality_report(observations, reference_time=BASE + timedelta(seconds=2))
    assert report.duplicate_records == 1
    assert report.missing_values == 1
    assert report.quality_percent < 100.0


def test_receive_gap_is_detected_with_explicit_threshold() -> None:
    observations = [
        observation(seconds=0),
        observation(seconds=RECEIVE_GAP_SECONDS + 1),
    ]
    report = build_quality_report(observations, reference_time=BASE + timedelta(seconds=RECEIVE_GAP_SECONDS + 2))
    assert report.receive_time_gaps == 1


def test_impossible_geographic_jump_is_detected() -> None:
    observations = [
        observation(seconds=0, lat=50.0, lon=-0.5),
        observation(seconds=10, lat=51.0, lon=1.0),
    ]
    report = build_quality_report(observations, reference_time=BASE + timedelta(seconds=11))
    assert report.impossible_jumps == 1


def test_provider_invalid_record_is_not_counted_as_valid() -> None:
    report = build_quality_report(
        [observation(valid=False)],
        reference_time=BASE + timedelta(seconds=1),
    )
    assert report.invalid_records == 1
    assert report.valid_records == 0
