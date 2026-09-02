import pytest

from src.ml.temporal.model import TCNAutoencoder, torch_available


pytestmark = pytest.mark.skipif(not torch_available(), reason="PyTorch is not installed")


def test_tcn_supports_all_adaptive_sequence_lengths() -> None:
    import torch

    model = TCNAutoencoder(input_dim=8, hidden_dim=16, latent_dim=8, num_layers=4)
    model.eval()

    for length in (8, 16, 32):
        x = torch.randn(2, length, 8)
        reconstructed, latent = model(x)
        assert reconstructed.shape == x.shape
        assert latent.shape == (2, 8)
        assert torch.isfinite(reconstructed).all()
        assert torch.isfinite(latent).all()


def test_tcn_rejects_sequence_beyond_positional_capacity() -> None:
    import torch

    model = TCNAutoencoder(input_dim=8, hidden_dim=16, latent_dim=8, num_layers=4, max_sequence_length=32)
    with pytest.raises(ValueError, match="positional capacity"):
        model(torch.randn(1, 33, 8))
