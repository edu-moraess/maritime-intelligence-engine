from datetime import datetime, timezone

from src.environment.alignment import EnvironmentalStateAlignmentEngine
from src.environment.context import EnvironmentalContext
from src.ingestion.models import AISObservation, EnvironmentalObservation
from src.intelligence.engine import MaritimeIntelligenceEngine


def _ais() -> AISObservation:
    return AISObservation(
        mmsi="123456789",
        latitude=25.7,
        longitude=-80.0,
        received_at=datetime(2026, 10, 8, 10, 0, tzinfo=timezone.utc),
        sog_knots=10.0,
        cog_degrees=90.0,
    )


def _environment() -> EnvironmentalObservation:
    return EnvironmentalObservation(
        source="open-meteo-marine",
        observed_at=datetime(2026, 10, 8, 9, 59, tzinfo=timezone.utc),
        latitude=25.7,
        longitude=-80.0,
        ocean_current_velocity=1.0,
        ocean_current_direction_deg=45.0,
    )


def test_environmental_feature_refresh_exposes_alignment_telemetry() -> None:
    engine = MaritimeIntelligenceEngine.__new__(MaritimeIntelligenceEngine)
    engine.current_session_observations = [_ais()]
    engine.settings = type(
        "Settings",
        (),
        {"monitoring_bboxes": [((25.0, -81.0), (26.0, -79.0))]},
    )()
    engine.environmental_contexts = {
        "region_1": EnvironmentalContext(
            region="region_1",
            observations=(_environment(),),
        )
    }
    engine.environmental_alignment = EnvironmentalStateAlignmentEngine()
    engine.environmental_features = {}

    MaritimeIntelligenceEngine._refresh_environmental_features(engine)

    telemetry = engine.environmental_telemetry
    assert telemetry["ais_considered"] == 1
    assert telemetry["alignments"] == 1
    assert telemetry["aligned"] == 1
    assert telemetry["features_produced"] == 1
    assert telemetry["temporal_offset_count"] == 1
    assert telemetry["temporal_offset_min_seconds"] == -60.0
    assert telemetry["temporal_offset_max_seconds"] == -60.0
    assert telemetry["source_open-meteo-marine"] == 1
    assert telemetry["spatial_distance_max_km"] == 0.0


def test_environmental_feature_refresh_counts_unusable_future_state() -> None:
    engine = MaritimeIntelligenceEngine.__new__(MaritimeIntelligenceEngine)
    engine.current_session_observations = [_ais()]
    engine.settings = type(
        "Settings",
        (),
        {"monitoring_bboxes": [((25.0, -81.0), (26.0, -79.0))]},
    )()
    future = EnvironmentalObservation(
        source="open-meteo-weather",
        observed_at=datetime(2026, 10, 8, 10, 1, tzinfo=timezone.utc),
        latitude=25.7,
        longitude=-80.0,
        forecast=True,
    )
    engine.environmental_contexts = {
        "region_1": EnvironmentalContext(
            region="region_1",
            observations=(future,),
        )
    }
    engine.environmental_alignment = EnvironmentalStateAlignmentEngine()
    engine.environmental_features = {}

    MaritimeIntelligenceEngine._refresh_environmental_features(engine)

    telemetry = engine.environmental_telemetry
    assert telemetry["alignments"] == 1
    assert telemetry["future"] == 1
    assert telemetry["features_produced"] == 0
