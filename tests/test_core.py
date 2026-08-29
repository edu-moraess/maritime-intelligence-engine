import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.anomaly.detector import detect_anomalies
from src.analytics.traffic import speed_distribution
from src.config.regions import REGION_PRESETS, REGION_TIMEZONES, region_timezone_for_bbox
from src.config.settings import COLLECTION_DURATION_OPTIONS, DEFAULT_BBOX, AppSettings, _validate_bbox
from src.ingestion.aisstream import AISStreamProvider
from src.historical import HistoricalWriteResult, create_historical_writer
from src.historical.writer import NullHistoricalWriter, PostgresHistoricalWriter, _database_url_for_connection, observation_payload_hash
from src.ingestion.models import AISObservation, VesselSnapshot
from src.intelligence.engine import MaritimeIntelligenceEngine
from src.ml.embeddings import TrajectoryEmbeddingAdapter
from src.processing.quality import build_quality_report, haversine_km, validate_observation
from src.storage.memory import ObservationStore
from src.trajectory.features import summarize_track, trajectory_vector
from src.ui.pages import _vessel_label
from src.ui.temporal import format_ais_second, format_observation_time, format_received, format_region_or_operator


def position_payload(*, mmsi: int = 368207620, timestamp_second: int = 42, latitude: float = 25.7617, longitude: float = -80.1918) -> str:
    """Return a documented AISStream envelope for parser-contract tests only."""
    return json.dumps(
        {
            "MessageType": "PositionReport",
            "MetaData": {"MMSI": mmsi, "ShipName": "EXAMPLE VESSEL", "Latitude": latitude, "Longitude": longitude},
            "Message": {
                "PositionReport": {
                    "UserID": mmsi,
                    "Sog": 12.4,
                    "Cog": 86.7,
                    "TrueHeading": 87,
                    "Valid": True,
                    "Timestamp": timestamp_second,
                }
            },
        }
    )


def test_default_bbox_is_semantically_min_max():
    _validate_bbox(DEFAULT_BBOX)
    assert DEFAULT_BBOX[0][0] < DEFAULT_BBOX[1][0]
    assert DEFAULT_BBOX[0][1] < DEFAULT_BBOX[1][1]


@pytest.mark.parametrize(
    "bbox",
    [
        ((-91.0, 0.0), (10.0, 1.0)),
        ((-10.0, -181.0), (10.0, 1.0)),
        ((0.0, 0.0), (91.0, 1.0)),
        ((0.0, 0.0), (1.0, 181.0)),
        ((10.0, 0.0), (10.0, 1.0)),
        ((0.0, 1.0), (1.0, 1.0)),
        ((10.0, 0.0), (1.0, 1.0)),
        ((0.0, 1.0), (1.0, 0.0)),
    ],
)
def test_invalid_bbox_is_rejected(bbox):
    with pytest.raises(ValueError):
        _validate_bbox(bbox)


def test_quality_flags_invalid_provider_record():
    observation = AISObservation(
        "000000001",
        120.0,
        200.0,
        datetime.now(timezone.utc),
        120.0,
        361.0,
        361.0,
        valid=False,
    )
    errors = validate_observation(observation)
    assert "invalid_coordinates" in errors
    assert "impossible_speed" in errors
    assert "provider_invalid" in errors
    assert "invalid_heading" in errors
    with pytest.raises(ValueError, match="Invalid AIS MMSI"):
        AISObservation("bad", 25.0, -80.0, datetime.now(timezone.utc))


def test_store_counts_exact_duplicates():
    store = ObservationStore(max_messages=5)
    observation = AISObservation("368207620", 25.7617, -80.1918, datetime.now(timezone.utc), ais_timestamp_second=42, raw={"MessageType": "PositionReport", "id": 1})
    store.extend([observation, observation])
    assert len(store.all()) == 1
    assert store.duplicate_count == 1


def test_engine_without_key_starts_in_explicit_disconnected_state():
    engine = MaritimeIntelligenceEngine(AppSettings(aisstream_api_key="", bbox=DEFAULT_BBOX))
    status = engine.snapshot().status
    assert status.state == "DISCONNECTED"
    assert "not configured" in status.reason.lower()
