"""Regression tests for versioned temporal checkpoint persistence."""
from __future__ import annotations

import numpy as np
import pytest

from src.ml.temporal.checkpoint import (
    feature_schema_sha256,
    load_temporal_checkpoint,
    save_temporal_checkpoint,
)
from src.ml.temporal.model import TCNAutoencoder, torch_available
from src.ml.temporal.types import TEMPORAL_FEATURE_NAMES


@pytest.mark.skipif(not torch_available(), reason="PyTorch unavailable")
def test_checkpoint_round_trip_preserves_model_scaler_and_provenance(tmp_path):
    import torch

    torch.manual_seed(7)
    model = TCNAutoencoder(
        input_dim=8, hidden_dim=8, latent_dim=4, num_layers=2, max_sequence_length=64
    ).eval()
    sample = torch.randn(2, 8, 8)
    with torch.no_grad():
        expected_reconstruction, expected_latent = model(sample)

    mean = np.arange(8, dtype=np.float64)
    scale = np.arange(1, 9, dtype=np.float64)
    path = tmp_path / "temporal.pt"
    save_temporal_checkpoint(
        path,
        model_state=model.state_dict(),
        scaler_mean=mean,
        scaler_scale=scale,
        architecture="tcn",
        sequence_length=8,
        input_dim=8,
        hidden_dim=8,
        latent_dim=4,
        num_layers=2,
        max_sequence_length=64,
        training_metadata={"seed": 7, "training_mode": "train_val", "dataset_sha256": "abc123"},
    )

    loaded = load_temporal_checkpoint(path)
    with torch.no_grad():
        actual_reconstruction, actual_latent = loaded.model(sample)

    assert loaded.architecture == "tcn"
    assert loaded.sequence_length == 8
    assert loaded.feature_names == TEMPORAL_FEATURE_NAMES
    assert loaded.feature_schema_sha256 == feature_schema_sha256(TEMPORAL_FEATURE_NAMES)
    np.testing.assert_array_equal(loaded.scaler_mean, mean)
    np.testing.assert_array_equal(loaded.scaler_scale, scale)
    assert loaded.training_metadata["seed"] == 7
    assert torch.allclose(actual_reconstruction, expected_reconstruction)
    assert torch.allclose(actual_latent, expected_latent)


@pytest.mark.skipif(not torch_available(), reason="PyTorch unavailable")
def test_checkpoint_rejects_reordered_or_different_features(tmp_path):
    import torch

    model = TCNAutoencoder(input_dim=8, hidden_dim=8, latent_dim=4, num_layers=2, max_sequence_length=64)
    path = tmp_path / "temporal.pt"
    save_temporal_checkpoint(
        path,
        model_state=model.state_dict(),
        scaler_mean=np.zeros(8),
        scaler_scale=np.ones(8),
        sequence_length=8,
        input_dim=8,
        hidden_dim=8,
        latent_dim=4,
        num_layers=2,
        max_sequence_length=64,
    )

    altered = list(TEMPORAL_FEATURE_NAMES)
    altered[0], altered[1] = altered[1], altered[0]
    with pytest.raises(ValueError, match="feature schema"):
        load_temporal_checkpoint(path, expected_feature_names=altered)


@pytest.mark.skipif(not torch_available(), reason="PyTorch unavailable")
def test_checkpoint_rejects_invalid_scaler_and_incompatible_weights(tmp_path):
    model = TCNAutoencoder(input_dim=8, hidden_dim=8, latent_dim=4, num_layers=2, max_sequence_length=64)
    with pytest.raises(ValueError, match="strictly positive"):
        save_temporal_checkpoint(
            tmp_path / "invalid.pt",
            model_state=model.state_dict(),
            scaler_mean=np.zeros(8),
            scaler_scale=np.array([1, 1, 1, 1, 1, 1, 1, 0]),
            sequence_length=8,
            input_dim=8,
            hidden_dim=8,
            latent_dim=4,
            num_layers=2,
            max_sequence_length=64,
        )

    with pytest.raises(ValueError, match="does not match declared architecture"):
        save_temporal_checkpoint(
            tmp_path / "bad-state.pt",
            model_state={},
            scaler_mean=np.zeros(8),
            scaler_scale=np.ones(8),
            sequence_length=8,
            input_dim=8,
            hidden_dim=8,
            latent_dim=4,
            num_layers=2,
            max_sequence_length=64,
        )
