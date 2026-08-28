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
from src.historical.writer import PostgresHistoricalWriter, _database_url_for_connection, observation_payload_hash
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
    assert before <= observation.received_at <= after
    assert observation.received_at >= before
    assert observation.received_at.tzinfo is timezone.utc
    assert observation.observed_at is None



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
    assert provider.status.last_received_at is not None
    assert provider.status.latency_seconds is None


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
    assert readiness.trajectory_status == "READY"
    assert readiness.multitrack_status == "READY"


def test_region_presets_are_valid_real_monitoring_boxes():
    assert {"Miami", "Santos", "Singapore", "Rotterdam", "English Channel"} <= set(REGION_PRESETS)
    for bbox in REGION_PRESETS.values():
        _validate_bbox(bbox)


def test_speed_distribution_does_not_replace_missing_sog_with_zero():
    vessel = VesselSnapshot("368207620", 25.7, -80.2, datetime.now(timezone.utc), None, None, None, None, 1)
    assert speed_distribution([vessel]).empty


@pytest.mark.parametrize(
    ("tracks_with_history", "expected"),
    [(0, "WAITING"), (2, "PARTIAL"), (3, "READY"), (5, "READY")],
)
def test_readiness_multitrack_status_is_explicit(tracks_with_history, expected):
    from src.intelligence.engine import ReadinessSnapshot

    readiness = ReadinessSnapshot(
        distinct_vessels=tracks_with_history,
        tracks_with_history=tracks_with_history,
        trajectory_ready=tracks_with_history > 0,
        embeddings_ready=tracks_with_history >= 3,
        embedding_status="READY" if tracks_with_history >= 3 else "WAITING",
        anomaly_count=0,
    )
    assert readiness.multitrack_status == expected


@pytest.mark.parametrize(
    ("vessel_name", "expected_name"),
    [(None, "UNKNOWN"), ("", "UNKNOWN"), ("   ", "UNKNOWN"), ("  MV REAL AIS  ", "MV REAL AIS")],
)
def test_vessel_label_handles_missing_or_blank_name_without_mutating_snapshot(vessel_name, expected_name):
    vessel = VesselSnapshot(
        mmsi="368207620",
        latitude=25.7617,
        longitude=-80.1918,
        last_received=datetime.now(timezone.utc),
        sog_knots=12.4,
        cog_degrees=86.7,
        heading_degrees=87.0,
        vessel_name=vessel_name,
        message_count=1,
    )
    original_name = vessel.vessel_name

    label = _vessel_label(vessel.mmsi, [vessel])

    assert label == f"368207620 · {expected_name}"
    assert vessel.vessel_name == original_name


@pytest.mark.parametrize("timestamp_second", [0, 59, 60, 61, 62, 63])
def test_ais_timestamp_second_is_preserved_without_absolute_observation_time(timestamp_second):
    provider = AISStreamProvider("server-side-key", [[[10.0, -20.0], [11.0, -19.0]]])

    observation = provider._parse_frame(position_payload(timestamp_second=timestamp_second))

    assert observation is not None
    assert observation.ais_timestamp_second == timestamp_second
    assert observation.observed_at is None


def test_metadata_time_utc_is_not_promoted_to_observation_time():
    payload = json.loads(position_payload(timestamp_second=31))
    payload["MetaData"]["time_utc"] = "2026-08-28T00:04:31Z"
    provider = AISStreamProvider("server-side-key", [[[10.0, -20.0], [11.0, -19.0]]])

    observation = provider._parse_frame(json.dumps(payload))

    assert observation is not None
    assert observation.observed_at is None
    assert observation.received_at.tzinfo is timezone.utc
    assert observation.raw["MetaData"]["time_utc"] == "2026-08-28T00:04:31Z"



def test_region_timezone_catalog_and_policies_are_explicit():
    assert REGION_TIMEZONES == {
        "Miami": "America/New_York",
        "Santos": "America/Sao_Paulo",
        "Singapore": "Asia/Singapore",
        "Rotterdam": "Europe/Amsterdam",
        "English Channel": "UTC",
        "Custom": "UTC",
    }
    assert region_timezone_for_bbox(REGION_PRESETS["Miami"]) == "America/New_York"
    assert region_timezone_for_bbox(REGION_PRESETS["Rotterdam"]) == "Europe/Amsterdam"
    assert region_timezone_for_bbox(((0.0, 0.0), (1.0, 1.0))) == "UTC"


@pytest.mark.parametrize(
    ("ais_second", "expected"),
    [(None, "UNAVAILABLE"), (0, "00"), (59, "59"), (60, "60 (AIS special state)"), (63, "63 (AIS special state)")],
)
def test_ais_second_display_never_infers_absolute_time(ais_second, expected):
    assert format_ais_second(ais_second) == expected
    assert format_observation_time(None) == "UNAVAILABLE"


@pytest.mark.parametrize(
    ("timezone_name", "expected_summer", "expected_winter"),
    [
        ("America/New_York", "EDT", "EST"),
        ("Europe/Amsterdam", "CEST", "CET"),
        ("Asia/Singapore", "+08" , "+08"),
        ("America/Sao_Paulo", "-03", "-03"),
    ],
)
def test_region_and_operator_timezones_use_zoneinfo_without_mutating_utc(timezone_name, expected_summer, expected_winter):
    summer = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)
    winter = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

    summer_local = format_region_or_operator(summer, timezone_name)
    winter_local = format_region_or_operator(winter, timezone_name)

    assert expected_summer in summer_local
    assert expected_winter in winter_local
    assert summer == datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)
    assert winter == datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def test_received_format_is_explicitly_utc_and_observation_is_unavailable():
    received_at = datetime(2026, 8, 28, 0, 4, 31, tzinfo=timezone.utc)
    assert format_received(received_at) == "2026-08-28 00:04:31 UTC"
    assert format_observation_time(None) == "UNAVAILABLE"


class _FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.result = None
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        self.executed.append((str(query), params))
        normalized = " ".join(str(query).split()).upper()
        self.result = None
        if "SELECT 1 FROM MIE_SCHEMA_MIGRATIONS" in normalized:
            version = str(params[0])
            self.result = (1,) if version in self.connection.migrations else None
        elif "INSERT INTO MIE_SCHEMA_MIGRATIONS" in normalized:
            self.connection.migrations.add(str(params[0]))
        elif "SELECT REGION_ID FROM REGIONS" in normalized:
            self.result = (7,)
        elif "INSERT INTO AIS_OBSERVATIONS" in normalized:
            payload_hash = str(params[-1])
            if payload_hash in self.connection.payload_hashes:
                self.result = None
            else:
                self.connection.payload_hashes.add(payload_hash)
                self.result = (len(self.connection.payload_hashes),)

    def fetchone(self):
        result, self.result = self.result, None
        return result


class _FakeConnection:
    def __init__(self):
        self.migrations = set()
        self.payload_hashes = set()
        self.closed = False
        self.commits = 0
        self.rollbacks = 0
        self.last_cursor = None

    def cursor(self):
        cursor = _FakeCursor(self)
        self.last_cursor = cursor
        return cursor

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


def _historical_observation(payload_id=1, valid=True):
    return AISObservation(
        mmsi="368207620",
        latitude=25.7617,
        longitude=-80.1918,
        received_at=datetime(2026, 8, 28, 0, 4, 31, tzinfo=timezone.utc),
        sog_knots=12.4,
        cog_degrees=86.7,
        ais_timestamp_second=42,
        valid=valid,
        raw={"MessageType": "PositionReport", "Message": {"PositionReport": {"UserID": 368207620, "Timestamp": 42}}, "payload_id": payload_id},
    )


def test_database_url_absent_is_live_only_noop():
    writer = create_historical_writer(None)

    result = writer.persist_collection(
        [_historical_observation()],
        REGION_PRESETS["Miami"],
        60,
        datetime(2026, 8, 28, 0, 4, 0, tzinfo=timezone.utc),
        datetime(2026, 8, 28, 0, 5, 0, tzinfo=timezone.utc),
    )

    assert writer.enabled is False
    assert writer.status == "HISTORICAL DATABASE NOT CONFIGURED"
    assert result.session_id is None
    assert result.persisted_observations == 0
    assert "LIVE-ONLY" in result.reason


def test_database_failure_does_not_raise_or_change_live_sink():
    def failing_connect(_database_url):
        raise ConnectionError("password=must-not-be-exposed")

    writer = PostgresHistoricalWriter("postgresql://user:secret@db.example/mie", connect_fn=failing_connect)
    result = writer.persist_collection(
        [_historical_observation()],
        REGION_PRESETS["Miami"],
        60,
        datetime(2026, 8, 28, 0, 4, 0, tzinfo=timezone.utc),
        datetime(2026, 8, 28, 0, 5, 0, tzinfo=timezone.utc),
    )

    assert result.status == "HISTORICAL DATABASE UNAVAILABLE"
    assert result.persisted_observations == 0
    assert "secret" not in result.reason


def test_valid_observation_persists_and_duplicate_is_idempotent():
    connection = _FakeConnection()
    writer = PostgresHistoricalWriter("postgresql://localhost/mie", connect_fn=lambda _url: connection)
    started = datetime(2026, 8, 28, 0, 4, 0, tzinfo=timezone.utc)
    ended = datetime(2026, 8, 28, 0, 5, 0, tzinfo=timezone.utc)

    first = writer.persist_collection([_historical_observation()], REGION_PRESETS["Miami"], 60, started, ended)
    second = writer.persist_collection([_historical_observation()], REGION_PRESETS["Miami"], 60, started, ended)

    assert first.persisted_observations == 1
    assert first.duplicate_observations == 0
    assert second.persisted_observations == 0
    assert second.duplicate_observations == 1
    assert len(connection.payload_hashes) == 1
    assert connection.commits >= 2
    collection_insert = next(params for query, params in connection.last_cursor.executed if "INSERT INTO collection_sessions" in query)
    vessel_insert = next(params for query, params in connection.last_cursor.executed if "INSERT INTO vessels" in query)
    observation_insert = next(params for query, params in connection.last_cursor.executed if "INSERT INTO ais_observations" in query)
    assert collection_insert[1] == 7
    assert collection_insert[-1] == "AISSTREAM"
    assert vessel_insert[1] is None
    assert observation_insert[1] == "368207620"
    assert observation_insert[4] == _historical_observation().received_at
    assert observation_insert[5] == 42
    assert observation_insert[6] is None
    assert observation_insert[9] is None


def test_invalid_observation_is_not_persisted_or_connected():
    connect_calls = []
    connection = _FakeConnection()
    writer = PostgresHistoricalWriter("postgresql://localhost/mie", connect_fn=lambda url: (connect_calls.append(url), connection)[1])
    result = writer.persist_collection(
        [_historical_observation(valid=False)],
        REGION_PRESETS["Miami"],
        60,
        datetime(2026, 8, 28, 0, 4, 0, tzinfo=timezone.utc),
        datetime(2026, 8, 28, 0, 5, 0, tzinfo=timezone.utc),
    )

    assert result.persisted_observations == 0
    assert result.skipped_invalid == 1
    assert connect_calls == []
    assert connection.payload_hashes == set()



def test_database_url_is_optional_runtime_setting(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    without_database = AppSettings.from_runtime({})
    with_database = AppSettings.from_runtime({"DATABASE_URL": "postgresql://user:password@db.example/mie"})

    assert without_database.database_url is None
    assert with_database.database_url == "postgresql://user:password@db.example/mie"


def test_initial_migration_declares_postgis_schema_and_required_indexes():
    migration = Path(__file__).parents[1].joinpath("migrations", "001_initial_historical.sql").read_text(encoding="utf-8")

    assert "CREATE EXTENSION IF NOT EXISTS postgis" in migration
    assert "geom geometry(POINT, 4326) NOT NULL" in migration
    assert "bbox geometry(POLYGON, 4326) NOT NULL" in migration
    assert "received_at TIMESTAMPTZ NOT NULL" in migration
    assert "observed_at TIMESTAMPTZ NULL" in migration
    assert "payload_hash TEXT NOT NULL UNIQUE" in migration
    assert "idx_ais_observations_mmsi_received_at" in migration
    assert "idx_ais_observations_geom_gist" in migration
    assert "idx_ais_observations_session_id" in migration


def test_payload_hash_is_stable_for_same_real_provider_payload():
    first = _historical_observation(payload_id=1)
    second = _historical_observation(payload_id=1)
    changed = _historical_observation(payload_id=2)

    assert observation_payload_hash(first) == observation_payload_hash(second)
    assert observation_payload_hash(first) != observation_payload_hash(changed)


def test_remote_database_url_requires_ssl_without_changing_local_url():
    remote = _database_url_for_connection("postgresql://user:password@db.example/mie")
    remote_with_query = _database_url_for_connection("postgresql://user:password@db.example/mie?application_name=mie")
    remote_disable = _database_url_for_connection("postgresql://user:password@db.example/mie?sslmode=disable")
    local = _database_url_for_connection("postgresql://localhost/mie")

    assert "sslmode=require" in remote
    assert "application_name=mie" in remote_with_query
    assert "sslmode=require" in remote_with_query
    assert "sslmode=require" in remote_disable
    assert local == "postgresql://localhost/mie"



def test_engine_persists_only_after_real_collection_and_clear_keeps_writer_history():
    settings = AppSettings(aisstream_api_key="server-side-key", bbox=DEFAULT_BBOX)
    engine = MaritimeIntelligenceEngine(settings)
    observation = _historical_observation()

    class RecordingWriter:
        status = "HISTORICAL DATABASE AVAILABLE"

        def __init__(self):
            self.calls = []

        def persist_collection(self, observations, bbox, collection_seconds, started_at, ended_at):
            self.calls.append((list(observations), bbox, collection_seconds, started_at, ended_at))
            return HistoricalWriteResult("HISTORICAL DATABASE AVAILABLE", "session-1", len(self.calls[0][0]), 0, 0, "ok")

    writer = RecordingWriter()
    engine.historical_writer = writer
    engine.provider.stream = lambda stop_event, duration_seconds: iter([observation])

    assert engine.collect(seconds=30) == 1
    assert len(writer.calls) == 1
    assert writer.calls[0][0] == [observation]
    assert engine.snapshot().historical_result is not None

    engine.clear_session_data()

    assert len(writer.calls) == 1
    assert engine.snapshot().observations == []
    assert engine.snapshot().historical_result is None
