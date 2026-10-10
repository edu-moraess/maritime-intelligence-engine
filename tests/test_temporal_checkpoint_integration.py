"""End-to-end integration tests for temporal checkpoint persistence and inference."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.ingestion.models import AISObservation
from src.ml.temporal.adapter import TemporalAnomalyAdapter
from src.ml.temporal.model import torch_available
from src.ml.temporal.trainer import TemporalTrainer


def _track(mmsi: str, n: int, base_lat: float):
    base = datetime(2026, 8, 28, 12, 0, 0, tzinfo=timezone.utc)
    return [
        AISObservation(
            mmsi,
            base_lat + i * 0.001,
            -80.19 + i * 0.001,
            base + timedelta(seconds=i * 30),
            sog_knots=8 + (i % 5) * 0.2,
            cog_degrees=(90 + i * 7) % 360,
            heading_degrees=(90 + i * 7) % 360,
        )
        for i in range(n)
    ]


@pytest.mark.skipif(not torch_available(), reason="PyTorch unavailable")
def test_adapter_saves_checkpoint_and_fresh_adapter_infers_without_training(tmp_path, monkeypatch):
    tracks = {
        f"3682076{i:02d}": _track(f"3682076{i:02d}", 8, 25 + i * 0.02)
        for i in range(8)
    }
    checkpoint_path = tmp_path / "temporal.pt"
    trainer = TemporalAnomalyAdapter(
        sequence_length=8,
        max_training_seconds=2.0,
        seed=17,
    )

    trained = trainer.fit(tracks, checkpoint_path=checkpoint_path)

    assert trained.status == "READY", trained.reason
    assert trained.training_completed and trained.inference_available
    assert checkpoint_path.is_file()

    # A checkpoint-only prediction must not silently retrain.
    def fail_if_training_is_called(*args, **kwargs):
        raise AssertionError("predict_from_checkpoint must not start training")

    monkeypatch.setattr(TemporalTrainer, "train", fail_if_training_is_called)
    fresh_adapter = TemporalAnomalyAdapter(sequence_length=32)
    restored = fresh_adapter.predict_from_checkpoint(tracks, checkpoint_path)

    assert restored.status == "READY", restored.reason
    assert restored.inference_available
    assert restored.sequence_length == trained.sequence_length == 8
    assert restored.architecture == trained.architecture == "tcn"
    assert not restored.training_started
    assert not restored.training_completed
    assert {score.mmsi for score in restored.scores} == {score.mmsi for score in trained.scores}

    trained_by_mmsi = {score.mmsi: score for score in trained.scores}
    restored_by_mmsi = {score.mmsi: score for score in restored.scores}
    for mmsi, expected in trained_by_mmsi.items():
        actual = restored_by_mmsi[mmsi]
        assert actual.reconstruction_error == pytest.approx(expected.reconstruction_error, rel=1e-6, abs=1e-8)
        assert actual.deep_anomaly_score == pytest.approx(expected.deep_anomaly_score, rel=1e-6, abs=1e-8)


@pytest.mark.skipif(not torch_available(), reason="PyTorch unavailable")
def test_adapter_checkpoint_inference_rejects_missing_checkpoint(tmp_path):
    adapter = TemporalAnomalyAdapter(sequence_length=8)
    result = adapter.predict_from_checkpoint({}, tmp_path / "missing.pt")
    assert result.status == "FAILED"
    assert result.reason.startswith("Checkpoint load failed:")
