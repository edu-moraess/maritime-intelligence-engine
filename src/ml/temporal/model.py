"""GRU Temporal Autoencoder (PyTorch)."""
from __future__ import annotations

from typing import Any

try:
    import torch
    from torch import nn
except ImportError:  # pragma: no cover
    torch = None  # type: ignore[assignment]
    nn = None  # type: ignore[assignment]


def torch_available() -> bool:
    return torch is not None


def _require_torch() -> Any:
    if torch is None or nn is None:
        raise RuntimeError("PyTorch is not available.")
    return torch, nn


class GRUTemporalAutoencoder(nn.Module if nn is not None else object):  # type: ignore[misc]
    def __init__(
        self,
        input_dim: int = 8,
        hidden_dim: int = 32,
        latent_dim: int = 16,
        num_layers: int = 1,
    ) -> None:
        _, nn_mod = _require_torch()
        super().__init__()
        if min(input_dim, hidden_dim, latent_dim, num_layers) < 1:
            raise ValueError("model dimensions must be >= 1")
        self.input_dim = int(input_dim)
        self.hidden_dim = int(hidden_dim)
        self.latent_dim = int(latent_dim)
        self.num_layers = int(num_layers)
        self.encoder = nn_mod.GRU(
            input_size=self.input_dim,
            hidden_size=self.hidden_dim,
            num_layers=self.num_layers,
            batch_first=True,
        )
        self.to_latent = nn_mod.Linear(self.hidden_dim, self.latent_dim)
        self.from_latent = nn_mod.Linear(self.latent_dim, self.hidden_dim)
        self.decoder = nn_mod.GRU(
            input_size=self.hidden_dim,
            hidden_size=self.hidden_dim,
            num_layers=self.num_layers,
            batch_first=True,
        )
        self.to_output = nn_mod.Linear(self.hidden_dim, self.input_dim)

    def encode(self, x: Any) -> Any:
        _, h_n = self.encoder(x)
        return self.to_latent(h_n[-1])

    def decode(self, z: Any, sequence_length: int) -> Any:
        batch = z.shape[0]
        hidden = self.from_latent(z)
        decoder_input = hidden.unsqueeze(1).expand(batch, sequence_length, self.hidden_dim)
        decoded, _ = self.decoder(decoder_input)
        return self.to_output(decoded)

    def forward(self, x: Any) -> tuple[Any, Any]:
        if x.dim() != 3:
            raise ValueError(f"Expected (batch, T, F), got {tuple(x.shape)}")
        if x.shape[-1] != self.input_dim:
            raise ValueError(f"Expected input_dim={self.input_dim}, got {x.shape[-1]}")
        z = self.encode(x)
        return self.decode(z, int(x.shape[1])), z
