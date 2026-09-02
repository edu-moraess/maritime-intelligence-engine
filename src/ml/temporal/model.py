"""Temporal models for real AIS trajectory anomaly detection."""
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


class TemporalResidualBlock(nn.Module if nn is not None else object):  # type: ignore[misc]
    """Causal dilated residual block used by the TCN encoder/decoder."""

    def __init__(self, channels: int, dilation: int, dropout: float = 0.05) -> None:
        _, nn_mod = _require_torch()
        super().__init__()
        padding = (3 - 1) * dilation
        self.conv1 = nn_mod.Conv1d(channels, channels, kernel_size=3, padding=padding, dilation=dilation)
        self.conv2 = nn_mod.Conv1d(channels, channels, kernel_size=3, padding=padding, dilation=dilation)
        self.norm1 = nn_mod.BatchNorm1d(channels)
        self.norm2 = nn_mod.BatchNorm1d(channels)
        self.dropout = nn_mod.Dropout(dropout)
        self.activation = nn_mod.GELU()

    @staticmethod
    def _causal_trim(x: Any, padding: int) -> Any:
        return x[..., :-padding] if padding else x

    def forward(self, x: Any) -> Any:
        padding = self.conv1.padding[0]
        residual = x
        y = self._causal_trim(self.conv1(x), padding)
        y = self.activation(self.norm1(y))
        y = self.dropout(y)
        y = self._causal_trim(self.conv2(y), padding)
        y = self.activation(self.norm2(y))
        y = self.dropout(y)
        return self.activation(y + residual)


class TCNAutoencoder(nn.Module if nn is not None else object):  # type: ignore[misc]
    """Compact causal/dilated TCN autoencoder for temporal AIS windows."""

    def __init__(
        self,
        input_dim: int = 8,
        hidden_dim: int = 32,
        latent_dim: int = 16,
        num_layers: int = 3,
        max_sequence_length: int = 128,
    ) -> None:
        _, nn_mod = _require_torch()
        super().__init__()
        if min(input_dim, hidden_dim, latent_dim, num_layers, max_sequence_length) < 1:
            raise ValueError("model dimensions must be >= 1")
        self.input_dim = int(input_dim)
        self.hidden_dim = int(hidden_dim)
        self.latent_dim = int(latent_dim)
        self.num_layers = int(num_layers)
        self.max_sequence_length = int(max_sequence_length)
        self.input_projection = nn_mod.Conv1d(self.input_dim, self.hidden_dim, kernel_size=1)
        dilations = [2**i for i in range(self.num_layers)]
        self.encoder = nn_mod.Sequential(
            *(TemporalResidualBlock(self.hidden_dim, d) for d in dilations)
        )
        self.to_latent = nn_mod.Linear(self.hidden_dim, self.latent_dim)
        self.from_latent = nn_mod.Linear(self.latent_dim, self.hidden_dim)
        self.position_embedding = nn_mod.Parameter(torch.zeros(1, self.hidden_dim, self.max_sequence_length))
        self.decoder = nn_mod.Sequential(
            *(TemporalResidualBlock(self.hidden_dim, d) for d in reversed(dilations))
        )
        self.output_projection = nn_mod.Conv1d(self.hidden_dim, self.input_dim, kernel_size=1)

    def encode(self, x: Any) -> Any:
        y = self.input_projection(x.transpose(1, 2))
        y = self.encoder(y)
        # Causal TCNs encode the full history into the final state. Using the
        # last state preserves temporal order instead of averaging it away.
        pooled = y[..., -1]
        return self.to_latent(pooled)

    def decode(self, z: Any, sequence_length: int) -> Any:
        if sequence_length > self.max_sequence_length:
            raise ValueError("sequence_length exceeds model positional capacity")
        hidden = self.from_latent(z).unsqueeze(-1).expand(-1, -1, sequence_length)
        hidden = hidden + self.position_embedding[..., :sequence_length]
        y = self.decoder(hidden)
        return self.output_projection(y).transpose(1, 2)

    def forward(self, x: Any) -> tuple[Any, Any]:
        if x.dim() != 3:
            raise ValueError(f"Expected (batch, T, F), got {tuple(x.shape)}")
        if x.shape[-1] != self.input_dim:
            raise ValueError(f"Expected input_dim={self.input_dim}, got {x.shape[-1]}")
        z = self.encode(x)
        return self.decode(z, int(x.shape[1])), z


class GRUTemporalAutoencoder(nn.Module if nn is not None else object):  # type: ignore[misc]
    """Legacy recurrent model retained for checkpoint/backward compatibility."""

    def __init__(self, input_dim: int = 8, hidden_dim: int = 32, latent_dim: int = 16, num_layers: int = 1) -> None:
        _, nn_mod = _require_torch()
        super().__init__()
        if min(input_dim, hidden_dim, latent_dim, num_layers) < 1:
            raise ValueError("model dimensions must be >= 1")
        self.input_dim, self.hidden_dim, self.latent_dim, self.num_layers = map(int, (input_dim, hidden_dim, latent_dim, num_layers))
        self.encoder = nn_mod.GRU(input_size=self.input_dim, hidden_size=self.hidden_dim, num_layers=self.num_layers, batch_first=True)
        self.to_latent = nn_mod.Linear(self.hidden_dim, self.latent_dim)
        self.from_latent = nn_mod.Linear(self.latent_dim, self.hidden_dim)
        self.decoder = nn_mod.GRU(input_size=self.hidden_dim, hidden_size=self.hidden_dim, num_layers=self.num_layers, batch_first=True)
        self.to_output = nn_mod.Linear(self.hidden_dim, self.input_dim)

    def encode(self, x: Any) -> Any:
        _, h_n = self.encoder(x)
        return self.to_latent(h_n[-1])

    def decode(self, z: Any, sequence_length: int) -> Any:
        hidden = self.from_latent(z)
        decoder_input = hidden.unsqueeze(1).expand(z.shape[0], sequence_length, self.hidden_dim)
        decoded, _ = self.decoder(decoder_input)
        return self.to_output(decoded)

    def forward(self, x: Any) -> tuple[Any, Any]:
        if x.dim() != 3 or x.shape[-1] != self.input_dim:
            raise ValueError(f"Expected (batch, T, {self.input_dim}), got {x.shape}")
        z = self.encode(x)
        return self.decode(z, int(x.shape[1])), z
