"""Deep Temporal production regression."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import pytest
from src.config.settings import DEFAULT_BBOX, AppSettings
from src.ingestion.models import AISObservation
from src.intelligence.engine import MaritimeIntelligenceEngine
from src.ml.temporal import (
    FEATURE_DIM, MINIMUM_POINTS_PER_TRACK, MINIMUM_TRACKS_FOR_DEEP_MODEL,
    TemporalAnomalyAdapter, build_temporal_sequence, compare_snapshot, torch_available,
)
from src.ml.temporal.types import DEFAULT_SEQUENCE_LENGTH

def _track(mmsi, n, base_lat=25.0):
    base = datetime(2026, 8, 28, 12, 0, 0, tzinfo=timezone.utc)
    return [AISObservation(mmsi, base_lat+i*0.001, -80.19+i*0.001, base+timedelta(seconds=i*30),
        sog_knots=8+(i%5)*0.2, cog_degrees=(90+i*7)%360, heading_degrees=(90+i*7)%360) for i in range(n)]

def test_contract():
    assert FEATURE_DIM == 8 and DEFAULT_SEQUENCE_LENGTH == 32
    assert MINIMUM_TRACKS_FOR_DEEP_MODEL == 8 and MINIMUM_POINTS_PER_TRACK == 4

def test_preprocess_shape():
    s = build_temporal_sequence(_track("368207620", 6))
    assert s is not None and s.sequence.shape == (32, 8)

def test_waiting():
    assert TemporalAnomalyAdapter().fit({}).status == "WAITING"

def test_not_ready():
    r = TemporalAnomalyAdapter().fit({f"3682076{i:02d}": _track(f"3682076{i:02d}", 6, 25+i*0.01) for i in range(3)})
    assert r.status == "NOT_READY" and r.scores == []

@pytest.mark.skipif(not torch_available(), reason="no torch")
def test_engine_ready():
    e = MaritimeIntelligenceEngine(AppSettings(aisstream_api_key="k", bbox=DEFAULT_BBOX))
    rows = []
    for v in range(MINIMUM_TRACKS_FOR_DEEP_MODEL):
        rows.extend(_track(f"3682076{v:02d}", 6, 25+v*0.02))
    e.store.extend(rows); e._recompute()
    s = e.snapshot()
    assert s.temporal.status == "READY"
    assert s.temporal.training_completed and s.temporal.inference_available
    assert s.temporal.model_state is not None
    assert all(0 <= x.deep_anomaly_score <= 1 for x in s.temporal.scores)
    assert s.embeddings is not None
    prev = e.temporal; e._recompute(); assert e.temporal is prev
    assert compare_snapshot(s).status == "READY"

def test_clear():
    e = MaritimeIntelligenceEngine(AppSettings(aisstream_api_key="k", bbox=DEFAULT_BBOX))
    e.store.extend(_track("368207620", 5)); e._recompute(); e.clear_session_data()
    assert e.temporal is None

def test_unavailable(monkeypatch):
    from src.ml.temporal import model as m
    monkeypatch.setattr(m, "torch", None)
    assert TemporalAnomalyAdapter().fit({f"3682076{i:02d}": _track(f"3682076{i:02d}", 5) for i in range(8)}).status == "UNAVAILABLE"
