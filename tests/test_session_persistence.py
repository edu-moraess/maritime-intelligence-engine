"""Session identity: page switches must not discard the live ObservationStore."""

from __future__ import annotations

from datetime import datetime, timezone

from src.config.settings import AppSettings, DEFAULT_BBOX
from src.ingestion.models import AISObservation
from src.intelligence.engine import create_engine
from app import _engine_signature, _normalize_bbox


def _obs(mmsi: str = "367000001") -> AISObservation:
    return AISObservation(
        mmsi=mmsi,
        latitude=25.76,
        longitude=-80.19,
        received_at=datetime.now(timezone.utc),
        sog_knots=8.0,
        cog_degrees=90.0,
        heading_degrees=90.0,
        vessel_name="TEST",
        ais_timestamp_second=10,
        observed_at=None,
        raw={"MetaData": {"MMSI": int(mmsi)}},
    )


def test_normalize_bbox_stabilizes_float_noise():
    a = ((25.603000001, -80.208), (25.835, -79.879))
    b = ((25.603, -80.208), (25.835, -79.879000004))
    assert _normalize_bbox(a) == _normalize_bbox(b)


def test_engine_signature_ignores_bbox_float_noise():
    s1 = AppSettings(aisstream_api_key="k", bbox=DEFAULT_BBOX)
    s2 = AppSettings(
        aisstream_api_key="k",
        bbox=(
            (DEFAULT_BBOX[0][0] + 1e-9, DEFAULT_BBOX[0][1]),
            (DEFAULT_BBOX[1][0], DEFAULT_BBOX[1][1] - 1e-9),
        ),
    )
    assert _engine_signature(s1) == _engine_signature(s2)


def test_engine_signature_ignores_historical_and_duration_toggles():
    s1 = AppSettings(
        aisstream_api_key="k",
        bbox=DEFAULT_BBOX,
        collection_seconds=60.0,
        historical_persistence_enabled=False,
    )
    s2 = AppSettings(
        aisstream_api_key="k",
        bbox=DEFAULT_BBOX,
        collection_seconds=120.0,
        historical_persistence_enabled=True,
    )
    assert _engine_signature(s1) == _engine_signature(s2)


def test_engine_signature_changes_on_real_region_change():
    s1 = AppSettings(aisstream_api_key="k", bbox=DEFAULT_BBOX)
    s2 = AppSettings(
        aisstream_api_key="k",
        bbox=((-24.2, -46.8), (-23.7, -46.0)),
    )
    assert _engine_signature(s1) != _engine_signature(s2)


def test_clear_session_data_is_only_explicit_wipe():
    engine = create_engine(AppSettings(aisstream_api_key="k", bbox=DEFAULT_BBOX))
    engine.store.extend([_obs()])
    assert len(engine.store.all()) == 1
    engine.clear_session_data()
    assert engine.store.all() == []
    assert engine.provider.status.messages_received == 0
    assert engine.findings == []
    assert engine.embeddings is None
    assert engine.temporal is None


def test_collect_extends_store_without_resetting_prior_observations():
    """A second collection must accumulate, not replace, prior real AIS data."""
    engine = create_engine(AppSettings(aisstream_api_key="k", bbox=DEFAULT_BBOX))
    first = _obs("367000001")
    second = _obs("367000002")
    engine.store.extend([first])
    engine.store.extend([second])
    tracks = engine.store.tracks()
    assert len(tracks) == 2
    assert len(engine.store.all()) == 2
