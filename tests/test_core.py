from datetime import datetime, timezone

from src.anomaly.detector import detect_anomalies
from src.config.settings import AppSettings
from src.ingestion.aisstream import AISStreamProvider
from src.ingestion.models import AISObservation
from src.intelligence.engine import MaritimeIntelligenceEngine
from src.ml.embeddings import TrajectoryEmbeddingAdapter
from src.processing.quality import build_quality_report, haversine_km, validate_observation
from src.trajectory.features import summarize_track, trajectory_vector


def test_settings_without_secret_are_not_connectable():
    settings = AppSettings(aisstream_api_key="", bbox=((25.8, -80.2), (25.6, -79.8)))
    ok, reason = settings.validate_for_connection()
    assert not ok
    assert "not configured" in reason


def test_aisstream_provider_parses_documented_position_payload():
    provider = AISStreamProvider("server-side-key", [[[25.8, -80.2], [25.6, -79.8]]])
    payload = b'''{"MessageType":"PositionReport","MetaData":{"MMSI":368207620,"ShipName":"EXAMPLE VESSEL","Latitude":25.7617,"Longitude":-80.1918},"Message":{"PositionReport":{"UserID":368207620,"Sog":12.4,"Cog":86.7,"TrueHeading":87,"Valid":true,"Timestamp":1735689600}}}'''
    observation = provider._parse_frame(payload)
    assert observation is not None
    assert observation.mmsi == "368207620"
    assert observation.latitude == 25.7617
    assert observation.sog_knots == 12.4
    assert observation.timestamp.tzinfo == timezone.utc


def test_non_position_messages_are_ignored():
    provider = AISStreamProvider("server-side-key", [[[25.8, -80.2], [25.6, -79.8]]])
    assert provider._parse_frame('{"MessageType":"SubscriptionConfirmation","Message":{"CompressionEnabled":true}}') is None


def test_trajectory_math_and_one_point_guard():
    assert haversine_km(0, 0, 0, 1) > 100
    observation = AISObservation("368207620", 25.7617, -80.1918, datetime.now(timezone.utc), 12.4, 86.7, 87.0)
    assert summarize_track([observation]).points == 1
    assert trajectory_vector([observation]) is None


def test_quality_empty_session_is_valid_and_explicit():
    report = build_quality_report([])
    assert report.messages_processed == 0
    assert report.quality_percent == 100.0


def test_quality_flags_invalid_provider_record():
    observation = AISObservation("bad", 120.0, 200.0, datetime.now(timezone.utc), 80.0, 361.0, None, valid=False)
    errors = validate_observation(observation)
    assert "invalid_mmsi" in errors
    assert "invalid_coordinates" in errors
    assert "impossible_speed" in errors
    assert "provider_invalid" in errors


def test_anomaly_engine_does_not_invent_findings_without_tracks():
    assert detect_anomalies({}) == []


def test_embedding_adapter_is_explicit_about_no_pretrained_checkpoint():
    adapter = TrajectoryEmbeddingAdapter()
    assert adapter.model_checkpoint.startswith("none:")
    assert adapter.fit({}) is None


def test_engine_without_key_starts_in_explicit_disconnected_state():
    settings = AppSettings(aisstream_api_key="", bbox=((25.8, -80.2), (25.6, -79.8)))
    engine = MaritimeIntelligenceEngine(settings)
    assert engine.snapshot().status.state == "DISCONNECTED"
    assert "not configured" in engine.snapshot().status.reason.lower()
