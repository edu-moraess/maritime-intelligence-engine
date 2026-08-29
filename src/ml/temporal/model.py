"""GRU Temporal Autoencoder."""
from __future__ import annotations
try:
    import torch
    from torch import nn
except ImportError:
    torch = None
    nn = None

def torch_available() -> bool:
    return torch is not None

def _require_torch():
    if torch is None or nn is None:
        raise RuntimeError("PyTorch is not available.")
    return torch, nn

class GRUTemporalAutoencoder(nn.Module if nn is not None else object):
    def __init__(self, input_dim=8, hidden_dim=32, latent_dim=16, num_layers=1):
        _, nn_mod = _require_torch()
        super().__init__()
        if min(input_dim, hidden_dim, latent_dim, num_layers) < 1:
            raise ValueError("dims >= 1 required")
        self.input_dim, self.hidden_dim, self.latent_dim, self.num_layers = map(int, (input_dim, hidden_dim, latent_dim, num_layers))
        self.encoder = nn_mod.GRU(self.input_dim, self.hidden_dim, self.num_layers, batch_first=True)
        self.to_latent = nn_mod.Linear(self.hidden_dim, self.latent_dim)
        self.from_latent = nn_mod.Linear(self.latent_dim, self.hidden_dim)
        self.decoder = nn_mod.GRU(self.hidden_dim, self.hidden_dim, self.num_layers, batch_first=True)
        self.to_output = nn_mod.Linear(self.hidden_dim, self.input_dim)
    def encode(self, x):
        _, h = self.encoder(x)
        return self.to_latent(h[-1])
    def decode(self, z, T):
        h = self.from_latent(z)
        out, _ = self.decoder(h.unsqueeze(1).expand(z.shape[0], T, self.hidden_dim))
        return self.to_output(out)
    def forward(self, x):
        if x.dim() != 3 or x.shape[-1] != self.input_dim:
            raise ValueError("bad input shape")
        z = self.encode(x)
        return self.decode(z, int(x.shape[1])), z
