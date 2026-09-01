"""Deep Temporal production regression."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.config.settings import DEFAULT_BBOX, AppSettings
from src.ingestion.models import AISObservation
from src.intelligence.engine import MaritimeIntelligenceEngine
from src.ml.temporal import (
    FEATURE_DIM, MINIMUM_POINTS_PER_TRACK, MINIMUM_TRACKS_FOR_DEEP_MODEL,
    TCNAutoencoder, TemporalAnomalyAdapter, TemporalTrainer, TrainingConfig,
    build_temporal_sequence, build_temporal_sequences, compare_if_vs_deep,
    compare_snapshot, torch_available,
)
from src.ml.temporal.types import DEFAULT_SEQUENCE_LENGTH


def _track(mmsi: str, n: int, base_lat: float = 25.0):
    base = datetime(2026, 8, 28, 12, 0, 0, tzinfo=timezone.utc)
    return [
        AISObservation(mmsi, base_lat + i * 0.001, -80.19 + i * 0.001, base + timedelta(seconds=i * 30), sog_knots=8 + (i % 5) * 0.2, cog_degrees=(90 + i * 7) % 360, heading_degrees=(90 + i * 7) % 360)
        for i in range(n)
    ]


def test_contract():
    assert FEATURE_DIM == 8 and DEFAULT_SEQUENCE_LENGTH == 32
    assert MINIMUM_TRACKS_FOR_DEEP_MODEL == 8 and MINIMUM_POINTS_PER_TRACK == 4


def test_preprocess_shape():
    s = build_temporal_sequence(_track("368207620", 6))
    assert s is not None and s.sequence.shape == (32, 8)
    assert s.sequence_length == 32 and s.feature_names is not None


def test_preprocess_rejects_short_track():
    assert build_temporal_sequence(_track("368207620", 3)) is None


def test_waiting():
    assert TemporalAnomalyAdapter().fit({}).status == "WAITING"


def test_not_ready():
    r = TemporalAnomalyAdapter().fit({f"3682076{i:02d}": _track(f"3682076{i:02d}", 6, 25 + i * 0.01) for i in range(3)})
    assert r.status == "NOT_READY" and r.scores == []
    assert r.n_tracks_seen == 3 and r.sequence_length is None


@pytest.mark.skipif(not torch_available(), reason="no torch")
def test_tcn_forward_contract():
    import torch
    model = TCNAutoencoder(input_dim=FEATURE_DIM, hidden_dim=16, latent_dim=8, num_layers=3)
    x = torch.randn(2, DEFAULT_SEQUENCE_LENGTH, FEATURE_DIM)
    rec, latent = model(x)
    assert rec.shape == x.shape
    assert latent.shape == (2, 8)
    assert torch.isfinite(rec).all() and torch.isfinite(latent).all()


@pytest.mark.skipif(not torch_available(), reason="no torch")
def test_adapter_ready():
    tracks = {f"3682076{i:02d}": _track(f"3682076{i:02d}", 8, 25 + i * 0.02) for i in range(MINIMUM_TRACKS_FOR_DEEP_MODEL)}
    r = TemporalAnomalyAdapter().fit(tracks)
    assert r.status == "READY" and r.training_completed and r.inference_available
    assert r.method == "TCN Temporal Autoencoder"
    assert r.sequence_length == 8
    assert r.model_state is not None and r.scaler_mean is not None and r.scaler_scale is not None
    assert len(r.scores) == MINIMUM_TRACKS_FOR_DEEP_MODEL
    assert all(0.0 <= s.deep_anomaly_score <= 1.0 for s in r.scores)
    assert all(s.reconstruction_error >= 0 for s in r.scores)


@pytest.mark.skipif(not torch_available(), reason="no torch")
def test_engine_ready():
    e = MaritimeIntelligenceEngine(AppSettings(aisstream_api_key="k", bbox=DEFAULT_BBOX))
    rows = []
    for v in range(MINIMUM_TRACKS_FOR_DEEP_MODEL):
        rows.extend(_track(f"3682076{v:02d}", 8, 25 + v * 0.02))
    e.store.extend(rows); e._recompute(); s = e.snapshot()
    assert s.temporal is not None and s.temporal.status == "READY"
    assert s.temporal.method == "TCN Temporal Autoencoder"
    assert s.temporal.sequence_length == 8
    assert s.temporal.training_completed and s.temporal.inference_available and s.temporal.model_state is not None
    assert all(0 <= x.deep_anomaly_score <= 1 for x in s.temporal.scores)
    assert s.embeddings is not None and s.readiness.temporal_status == "READY"
    prev = e.temporal; e._recompute(); assert e.temporal is prev
    bench = compare_snapshot(s)
    assert bench.status in {"COMPLEMENTAR", "REDUNDANTE", "INCONCLUSIVO"}


def test_clear():
    e = MaritimeIntelligenceEngine(AppSettings(aisstream_api_key="k", bbox=DEFAULT_BBOX))
    e.store.extend(_track("368207620", 5)); e._recompute(); e.clear_session_data()
    assert e.temporal is None


def test_unavailable(monkeypatch):
    from src.ml.temporal import model as m
    monkeypatch.setattr(m, "torch", None)
    r = TemporalAnomalyAdapter().fit({f"3682076{i:02d}": _track(f"3682076{i:02d}", 5) for i in range(8)})
    assert r.status == "UNAVAILABLE"


def test_temporal_failure_does_not_break_classical(monkeypatch):
    e = MaritimeIntelligenceEngine(AppSettings(aisstream_api_key="k", bbox=DEFAULT_BBOX))
    rows = []
    for v in range(5): rows.extend(_track(f"3682076{v:02d}", 6, 25 + v * 0.02))
    e.store.extend(rows)
    monkeypatch.setattr(e.temporal_adapter, "fit", lambda _tracks: (_ for _ in ()).throw(RuntimeError("forced temporal failure")))
    e._recompute()
    assert e.temporal is not None and e.temporal.status == "FAILED" and e.embeddings is not None


@pytest.mark.skipif(not torch_available(), reason="no torch")
def test_trainer_direct():
    tracks = {f"3682076{i:02d}": _track(f"3682076{i:02d}", 6, 25 + i * 0.02) for i in range(MINIMUM_TRACKS_FOR_DEEP_MODEL)}
    seqs = build_temporal_sequences(tracks)
    tr = TemporalTrainer(TrainingConfig(max_training_seconds=3.0, seed=42)).train(seqs)
    assert len(seqs) >= MINIMUM_TRACKS_FOR_DEEP_MODEL and tr.ok and tr.model_state is not None
    assert tr.training_completed and tr.architecture == "tcn" and tr.best_loss is not None and tr.best_loss >= 0


def test_benchmark_inconclusivo_sparse():
    from src.ml.temporal.types import TemporalScore
    r = compare_if_vs_deep({"368207620": 0.9}, [TemporalScore("368207620", 0.1, 0.9)])
    assert r.status == "INCONCLUSIVO" and r.n_common == 1
