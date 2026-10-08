from datetime import datetime, timezone

from src.environment.alignment import EnvironmentalAlignmentEngine
from src.environment.context import EnvironmentalContext
from src.environment.features import derive_environmental_features
from src.ingestion.models import AISObservation, EnvironmentalObservation


def _ais() -> AISObservation:
    return AISObservation(
        mmsi="123456789",
        latitude=25.7,
        longitude=-80.0,
        received_at=datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc),
        sog_knots=10.0,
        cog_degrees=90.0,
    )


def test_features_derive_relative_current_and_direction() -> None:
    ais = _ais()
    env = EnvironmentalObservation(
        source="open-meteo-marine",
        observed_at=ais.received_at,
        latitude=25.7,
        longitude=-80.0,
        region="region_1",
        ocean_current_velocity=2.0,
        ocean_current_direction_deg=0.0,
        wave_height_m=1.2,
        wave_period_s=6.0,
    )
    alignment = EnvironmentalAlignmentEngine().align(
        ais, EnvironmentalContext(region="region_1", observations=(env,))
    )[0]

    features = derive_environmental_features(
        alignment,
        vessel_sog_knots=ais.sog_knots,
        vessel_cog_degrees=ais.cog_degrees,
    )

    assert features is not None
    assert features.relative_current_speed_knots is not None
    assert abs(features.relative_current_speed_knots - (104.0**0.5)) < 1e-9
    assert features.current_alignment_deg == 90.0
    assert features.wave_height_m == 1.2


def test_features_do_not_derive_from_stale_evidence() -> None:
    ais = _ais()
    env = EnvironmentalObservation(
        source="copernicus-marine",
        observed_at=ais.received_at.replace(hour=10),
        latitude=25.7,
        longitude=-80.0,
        region="region_1",
        ocean_current_velocity=2.0,
        ocean_current_direction_deg=0.0,
    )
    alignment = EnvironmentalAlignmentEngine(max_temporal_age_seconds=3600).align(
        ais, EnvironmentalContext(region="region_1", observations=(env,))
    )[0]

    assert alignment.status == "STALE"
    assert derive_environmental_features(
        alignment,
        vessel_sog_knots=ais.sog_knots,
        vessel_cog_degrees=ais.cog_degrees,
    ) is None
