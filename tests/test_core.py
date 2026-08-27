import json
from datetime import datetime, timedelta, timezone

import pytest

from src.anomaly.detector import detect_anomalies
from src.analytics.traffic import speed_distribution
from src.config.regions import REGION_PRESETS
from src.config.settings import COLLECTION_DURATION_OPTIONS, DEFAULT_BBOX, AppSettings, _validate_bbox
from src.ingestion.aisstream import AISStreamProvider
from src.ingestion.models import AISObservation, VesselSnapshot
from src.intelligence.engine import MaritimeIntelligenceEngine
from src.ml.embeddings import TrajectoryEmbeddingAdapter
from src.processing.quality import build_quality_report, haversine_km, validate_observation
from src.storage.memory import ObservationStore
from src.trajectory.features import summarize_track, trajectory_vector


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


def test_runtime_bbox_values_are_used_in_provider_subscription():
    secrets = {
        "AISSTREAM_API_KEY": "server-side-key",
        "AIS_AREA_MIN_LAT": "10",
        "AIS_AREA_MIN_LON": "-20",
        "AIS_AREA_MAX_LAT": "11",
        "AIS_AREA_MAX_LON": "-19",
    }
    settings = AppSettings.from_runtime(secrets)
    engine = MaritimeIntelligenceEngine(settings)
    assert settings.config_error is None
    assert settings.bbox == ((10.0, -20.0), (11.0, -19.0))
    assert engine.provider.bbox == settings.bbox_payload
    assert engine.provider._subscription()["BoundingBoxes"] == settings.bbox_payload


def test_settings_without_secret_are_not_connectable():
    settings = AppSettings(aisstream_api_key="", bbox=DEFAULT_BBOX)
    ok, reason = settings.validate_for_connection()
    assert not ok
    assert "not configured" in reason


def test_invalid_provider_is_not_connectable():
    settings = AppSettings(aisstream_api_key="server-side-key", bbox=DEFAULT_BBOX, provider="other")
    ok, reason = settings.validate_for_connection()
    assert not ok
    assert "unsupported provider" in reason.lower()
    engine = MaritimeIntelligenceEngine(settings)
    assert engine.snapshot().status.reason == reason


def test_subscription_uses_current_bbox_and_position_filter_only():
    provider = AISStreamProvider("server-side-key", [[[10.0, -20.0], [11.0, -19.0]]])
    subscription = provider._subscription()
    assert subscription["APIKey"] == "server-side-key"
    assert subscription["BoundingBoxes"] == [[[10.0, -20.0], [11.0, -19.0]]]
    assert subscription["FilterMessageTypes"] == ["PositionReport"]


def test_partial_or_invalid_runtime_bbox_is_not_silently_accepted():
    partial = AppSettings.from_runtime({"AIS_AREA_MIN_LAT": "10"})
    assert partial.config_error is not None
    invalid = AppSettings.from_runtime(
        {"AIS_AREA_MIN_LAT": "11", "AIS_AREA_MIN_LON": "-20", "AIS_AREA_MAX_LAT": "10", "AIS_AREA_MAX_LON": "-19"}
    )
    assert invalid.config_error is not None


def test_aisstream_provider_parses_documented_position_payload():
    provider = AISStreamProvider("server-side-key", [[[10.0, -20.0], [11.0, -19.0]]])
    before = datetime.now(timezone.utc)
    observation = provider._parse_frame(position_payload().encode("utf-8"))
    after = datetime.now(timezone.utc)
    assert observation is not None
    assert observation.mmsi == "368207620"
    assert observation.latitude == 25.7617
    assert observation.sog_knots == 12.4
    assert observation.ais_timestamp_second == 42
    assert before <= observation.timestamp <= after
    assert observation.timestamp >= before



def test_invalid_json_and_utf8_are_ignored():
    provider = AISStreamProvider("server-side-key", [[[10.0, -20.0], [11.0, -19.0]]])
    assert provider._parse_frame("not-json") is None
    assert provider._parse_frame(b"\xff\xfe\xfd") is None


def test_non_position_messages_are_ignored():
    provider = AISStreamProvider("server-side-key", [[[10.0, -20.0], [11.0, -19.0]]])
    frame = '{"MessageType":"SubscriptionConfirmation","Message":{"CompressionEnabled":true}}'
    assert provider._parse_frame(frame) is None


@pytest.mark.parametrize(
    "payload",
    [
        position_payload(mmsi=0),
        position_payload(latitude=91.0),
        position_payload(longitude=-181.0),
        position_payload(timestamp_second=60),
        json.dumps({"MessageType": "PositionReport", "Message": {"PositionReport": {"UserID": 368207620, "Timestamp": 42}}}),
    ],
)
def test_invalid_position_fields_do_not_create_observations(payload):
    provider = AISStreamProvider("server-side-key", [[[10.0, -20.0], [11.0, -19.0]]])
    assert provider._parse_frame(payload) is None


def test_real_position_record_transitions_provider_to_live_ais():
    provider = AISStreamProvider("server-side-key", [[[10.0, -20.0], [11.0, -19.0]]])
    observation = provider._parse_frame(position_payload().encode("utf-8"))
    assert observation is not None
    provider._record(observation)
    assert provider.status.state == "LIVE AIS"
    assert provider.status.messages_received == 1
    assert provider.status.active_vessels == 1


def test_no_messages_after_open_are_real_data_unavailable(monkeypatch):
    class SilentSocket:
        def send(self, _payload):
            return None

        def settimeout(self, _timeout):
            return None

        def recv(self):
            raise TimeoutError("timed out")

        def close(self):
            return None

    provider = AISStreamProvider("server-side-key", [[[10.0, -20.0], [11.0, -19.0]]])
    monkeypatch.setattr("src.ingestion.aisstream.websocket.create_connection", lambda *args, **kwargs: SilentSocket())
    assert list(provider.stream(duration_seconds=0.1)) == []
    assert provider.status.state == "REAL AIS DATA UNAVAILABLE"
    assert provider.status.messages_received == 0


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
    observation = AISObservation("bad", 120.0, 200.0, datetime.now(timezone.utc), 120.0, 361.0, 361.0, valid=False)
    errors = validate_observation(observation)
    assert "invalid_mmsi" in errors
    assert "invalid_coordinates" in errors
    assert "impossible_speed" in errors
    assert "provider_invalid" in errors
    assert "invalid_heading" in errors


def test_store_counts_exact_duplicates():
    store = ObservationStore(max_messages=5)
    observation = AISObservation("368207620", 25.7617, -80.1918, datetime.now(timezone.utc), ais_timestamp_second=42, raw={"MessageType": "PositionReport", "id": 1})
    store.extend([observation, observation])
    assert len(store.all()) == 1
    assert store.duplicate_count == 1


def test_store_enforces_vessel_limit():
    store = ObservationStore(max_messages=10, max_vessels=1)
    first = AISObservation("368207620", 25.7617, -80.1918, datetime.now(timezone.utc))
    second = AISObservation("368207621", 25.7618, -80.1917, datetime.now(timezone.utc) + timedelta(seconds=1))
    store.extend([first, second])
    assert store.vessel_count == 1
    assert {item.mmsi for item in store.all()} == {"368207621"}


def test_store_is_bounded_and_clearable():
    store = ObservationStore(max_messages=1)
    first = AISObservation("368207620", 25.7617, -80.1918, datetime.now(timezone.utc))
    second = AISObservation("368207621", 25.7618, -80.1917, datetime.now(timezone.utc) + timedelta(seconds=1))
    store.extend([first, second])
    assert len(store.all()) == 1
    assert store.all()[0].mmsi == "368207621"
    store.clear()
    assert store.all() == []


def test_anomaly_engine_does_not_invent_findings_without_tracks():
    assert detect_anomalies({}) == []


def test_embedding_adapter_is_explicit_about_no_pretrained_checkpoint():
    adapter = TrajectoryEmbeddingAdapter()
    assert adapter.model_checkpoint.startswith("none:")
    assert adapter.fit({}) is None


def test_engine_without_key_starts_in_explicit_disconnected_state():
    engine = MaritimeIntelligenceEngine(AppSettings(aisstream_api_key="", bbox=DEFAULT_BBOX))
    status = engine.snapshot().status
    assert status.state == "DISCONNECTED"
    assert "not configured" in status.reason.lower()


def test_engine_config_error_blocks_connection_and_data():
    settings = AppSettings(aisstream_api_key="server-side-key", bbox=DEFAULT_BBOX, config_error="invalid region")
    engine = MaritimeIntelligenceEngine(settings)
    snapshot = engine.snapshot()
    assert snapshot.status.state == "DISCONNECTED"
    assert snapshot.status.reason == "invalid region"
    assert snapshot.observations == []
    assert snapshot.vessels == []


@pytest.mark.parametrize("seconds", COLLECTION_DURATION_OPTIONS)
def test_collection_duration_options_are_preserved(seconds):
    settings = AppSettings.from_runtime({"AISSTREAM_API_KEY": "server-side-key", "AIS_COLLECTION_SECONDS": str(seconds)})
    assert settings.collection_seconds == float(seconds)


def test_collection_duration_is_bounded_to_operational_window():
    too_short = AppSettings.from_runtime({"AIS_COLLECTION_SECONDS": "10"})
    too_long = AppSettings.from_runtime({"AIS_COLLECTION_SECONDS": "999"})
    assert too_short.collection_seconds == 30.0
    assert too_long.collection_seconds == 180.0


def test_engine_passes_selected_collection_duration_to_provider(monkeypatch):
    engine = MaritimeIntelligenceEngine(AppSettings(aisstream_api_key="server-side-key", bbox=DEFAULT_BBOX))
    durations = []

    def stream(stop_event=None, duration_seconds=None):
        durations.append(duration_seconds)
        if False:
            yield None

    monkeypatch.setattr(engine.provider, "stream", stream)
    assert engine.collect(seconds=120) == 0
    assert durations == [120.0]


def test_readiness_uses_real_tracks_and_embedding_guard():
    engine = MaritimeIntelligenceEngine(AppSettings(aisstream_api_key="server-side-key", bbox=DEFAULT_BBOX))
    base = datetime.now(timezone.utc)
    for index in range(3):
        mmsi = f"36820762{index}"
        engine.store.extend(
            [
                AISObservation(mmsi, 25.70 + index * 0.01, -80.20, base + timedelta(seconds=index * 30), 8.0 + index, 80.0),
                AISObservation(mmsi, 25.715 + index * 0.01, -80.18, base + timedelta(seconds=index * 30 + 10), 11.0 + index * 2, 95.0 + index * 5),
                AISObservation(mmsi, 25.72 + index * 0.01, -80.195, base + timedelta(seconds=index * 30 + 25), 9.0 + index, 82.0 + index * 4),
            ]
        )
    engine._recompute()
    readiness = engine.snapshot().readiness
    assert readiness.distinct_vessels == 3
    assert readiness.tracks_with_history == 3
    assert readiness.trajectory_ready
    assert readiness.embeddings_ready
    assert readiness.embedding_status == "READY"


def test_region_presets_are_valid_real_monitoring_boxes():
    assert {"Miami", "Santos", "Singapore", "Rotterdam", "English Channel"} <= set(REGION_PRESETS)
    for bbox in REGION_PRESETS.values():
        _validate_bbox(bbox)


def test_speed_distribution_does_not_replace_missing_sog_with_zero():
    vessel = VesselSnapshot("368207620", 25.7, -80.2, datetime.now(timezone.utc), None, None, None, None, 1)
    assert speed_distribution([vessel]).empty
