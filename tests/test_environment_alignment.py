from datetime import datetime, timedelta, timezone

from src.environment.alignment import EnvironmentalStateAlignmentEngine
from src.environment.context import EnvironmentalContext
from src.ingestion.models import AISObservation, EnvironmentalObservation


BASE = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)


def _ais(**kwargs) -> AISObservation:
    values = {
        "mmsi": "123456789",
        "latitude": 25.7000,
        "longitude": -80.0000,
        "received_at": BASE,
    }
    values.update(kwargs)
    return AISObservation(**values)


def _env(source: str, *, when=BASE, lat=25.7005, lon=-80.0005, retrieved_at=None) -> EnvironmentalObservation:
    return EnvironmentalObservation(
        source=source,
        observed_at=when,
        latitude=lat,
        longitude=lon,
        region="region_1",
        wave_height_m=0.8,
        ocean_current_velocity=0.4,
        retrieved_at=retrieved_at,
    )


def test_alignment_selects_nearest_temporal_state_per_source() -> None:
    context = EnvironmentalContext(
        region="region_1",
        observations=(
            _env("open-meteo-marine", when=BASE - timedelta(minutes=20)),
            _env("open-meteo-marine", when=BASE - timedelta(minutes=2)),
            _env("open-meteo-weather", when=BASE - timedelta(minutes=1)),
        ),
    )

    result = EnvironmentalStateAlignmentEngine().align(_ais(), context)

    marine = next(item for item in result if item.source == "open-meteo-marine")
    weather = next(item for item in result if item.source == "open-meteo-weather")

    assert marine.status == "ALIGNED"
    assert marine.temporal_age_seconds == 120.0
    assert marine.temporal_offset_seconds == -120.0
    assert weather.status == "ALIGNED"
    assert weather.temporal_age_seconds == 60.0
    assert weather.temporal_offset_seconds == -60.0


def test_alignment_marks_stale_state_without_discarding_provenance() -> None:
    context = EnvironmentalContext(
        region="region_1",
        observations=(_env("copernicus-marine", when=BASE - timedelta(hours=2)),),
    )

    result = EnvironmentalStateAlignmentEngine(max_temporal_age_seconds=3600).align(
        _ais(), context, source="copernicus-marine"
    )[0]

    assert result.status == "STALE"
    assert result.observation is not None
    assert result.usable is False
    assert result.temporal_age_seconds == 7200.0
    assert result.temporal_offset_seconds == -7200.0


def test_alignment_marks_spatial_mismatch_as_out_of_bounds() -> None:
    context = EnvironmentalContext(
        region="region_1",
        observations=(
            _env("open-meteo-marine", lat=26.5, lon=-80.0),
        ),
    )

    result = EnvironmentalStateAlignmentEngine(max_spatial_distance_km=10).align(
        _ais(), context, source="open-meteo-marine"
    )[0]

    assert result.status == "OUT_OF_BOUNDS"
    assert result.observation is not None
    assert result.spatial_distance_km is not None
    assert result.spatial_distance_km > 10.0


def test_alignment_uses_environment_valid_time_not_retrieval_time() -> None:
    context = EnvironmentalContext(
        region="region_1",
        observations=(
            _env(
                "open-meteo-marine",
                when=BASE - timedelta(minutes=1),
                retrieved_at=BASE + timedelta(hours=3),
            ),
        ),
    )

    result = EnvironmentalStateAlignmentEngine().align(
        _ais(), context, source="open-meteo-marine"
    )[0]

    assert result.status == "ALIGNED"
    assert result.temporal_age_seconds == 60.0
    assert result.temporal_offset_seconds == -60.0


def test_alignment_exposes_future_valid_time_as_signed_offset() -> None:
    context = EnvironmentalContext(
        region="region_1",
        observations=(_env("open-meteo-marine", when=BASE + timedelta(minutes=1)),),
    )

    result = EnvironmentalStateAlignmentEngine().align(
        _ais(), context, source="open-meteo-marine"
    )[0]

    assert result.status == "ALIGNED"
    assert result.temporal_age_seconds == 60.0
    assert result.temporal_offset_seconds == 60.0


def test_alignment_reports_unavailable_source_without_synthetic_data() -> None:
    context = EnvironmentalContext(region="region_1", observations=())

    result = EnvironmentalStateAlignmentEngine().align(
        _ais(), context, source="copernicus-marine"
    )[0]

    assert result.status == "UNAVAILABLE"
    assert result.observation is None
    assert result.temporal_age_seconds is None
    assert result.spatial_distance_km is None
