"""Regression tests for live-session analytical provenance."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.config.settings import AppSettings, DEFAULT_BBOX
from src.ingestion.models import AISObservation
from src.intelligence.engine import create_engine
from src.ml.embeddings import TrajectoryEmbeddingAdapter


def _obs(mmsi: str, seconds: int, *, lon: float) -> AISObservation:
    return AISObservation(
        mmsi=mmsi,
        latitude=25.7,
        longitude=lon,
        received_at=datetime(2026, 9, 25, 4, 0, 0, tzinfo=timezone.utc)
        + timedelta(seconds=seconds),
        sog_knots=10.0,
        cog_degrees=90.0,
        heading_degrees=90.0,
        vessel_name="TEST",
        ais_timestamp_second=seconds % 60,
        raw={"MessageType": "PositionReport"},
    )


def _tracks(prefix: str, offset: float = 0.0) -> dict[str, list[AISObservation]]:
    return {
        f"{prefix}{index:03d}": [
            _obs(f"{prefix}{index:03d}", 0, lon=-80.10 + offset + index * 0.01),
            _obs(f"{prefix}{index:03d}", 60, lon=-80.09 + offset + index * 0.01),
        ]
        for index in range(1, 4)
    }


def test_engine_keeps_historical_store_but_fits_live_analytics_only():
    engine = create_engine(AppSettings(aisstream_api_key="k", bbox=DEFAULT_BBOX))

    historical = _tracks("9", offset=0.20)
    current = _tracks("8")

    engine.store.extend([item for track in historical.values() for item in track])
    engine.current_session_observations = [
        observation
        for track in current.values()
        for observation in track
    ]

    engine._recompute()

    assert set(engine.store.tracks()) == set(historical) | set(current)
    assert engine.embeddings is not None
    assert set(engine.embeddings.mmsis) == set(current)
    assert {finding.mmsi for finding in engine.findings} <= set(current)

    snapshot = engine.snapshot()
    assert snapshot.readiness.distinct_vessels == len(current)
    assert snapshot.readiness.tracks_with_history == len(current)


def test_similarity_results_are_labeled_as_current_session():
    tracks = _tracks("8")
    adapter = TrajectoryEmbeddingAdapter()
    result = adapter.fit(tracks)

    assert result is not None

    current_mmsi = "8001"
    similar = adapter.similar_tracks(
        tracks[current_mmsi],
        tracks,
        current_mmsi=current_mmsi,
    )

    assert similar
    assert all(item.source_label == "REAL AIS CURRENT SESSION" for item in similar)
