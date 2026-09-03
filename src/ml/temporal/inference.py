"""Temporal autoencoder inference and reconstruction-error scoring."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Sequence

import numpy as np

from src.ml.temporal.model import GRUTemporalAutoencoder, TCNAutoencoder, torch_available
from src.ml.temporal.preprocess import TemporalSequenceScaler
from src.ml.temporal.types import DEFAULT_HIDDEN_DIM, DEFAULT_INPUT_DIM, DEFAULT_LATENT_DIM, DEFAULT_NUM_LAYERS, TemporalScore, TemporalSequence

try:
    import torch
except ImportError:  # pragma: no cover
    torch = None

EQUAL_ERROR_SCORE, EQUAL_ERROR_EPS = 0.5, 1e-12


@dataclass
class InferenceResult:
    ok: bool
    reason: str
    scores: list
    errors: list
    mmsis: list


def score_sequences(
    sequences: Sequence[TemporalSequence], *, model_state, scaler_mean, scaler_scale,
    input_dim=DEFAULT_INPUT_DIM, hidden_dim=DEFAULT_HIDDEN_DIM, latent_dim=DEFAULT_LATENT_DIM,
    num_layers=DEFAULT_NUM_LAYERS, device=None, architecture="gru",
):
    if not torch_available() or torch is None:
        return InferenceResult(False, "PyTorch is not available.", [], [], [])
    if not sequences or model_state is None or scaler_mean is None or scaler_scale is None:
        return InferenceResult(False, "Missing sequences, model_state, or scaler.", [], [], [])
    try:
        scaler = TemporalSequenceScaler.from_stats(scaler_mean, scaler_scale)
    except ValueError as exc:
        return InferenceResult(False, str(exc), [], [], [])
    arrays = [np.asarray(s.sequence, dtype=np.float32) for s in sequences]
    mmsis = [s.mmsi for s in sequences]
    if any(a.ndim != 2 or a.shape[-1] != input_dim for a in arrays) or any(not np.isfinite(a).all() for a in arrays):
        return InferenceResult(False, "NON_FINITE_INPUT", [], [], [])
    scaled = scaler.transform(arrays)
    if not np.isfinite(scaled).all():
        return InferenceResult(False, "NON_FINITE_INPUT", [], [], [])
    dev = device or ("cuda" if torch.cuda.is_available() else "cpu")
    architecture = architecture.lower()
    try:
        if architecture == "gru":
            model = GRUTemporalAutoencoder(input_dim, hidden_dim, latent_dim, num_layers)
        elif architecture == "tcn":
            model = TCNAutoencoder(input_dim, hidden_dim, latent_dim, num_layers)
        else:
            return InferenceResult(False, f"Unsupported temporal architecture: {architecture}.", [], [], [])
        model.load_state_dict(model_state)
        model.to(torch.device(dev))
        model.eval()
    except Exception as exc:
        return InferenceResult(False, f"Failed to load {architecture.upper()} model_state: {exc}", [], [], [])
    try:
        with torch.no_grad():
            x = torch.from_numpy(scaled).to(torch.device(dev))
            rec, _ = model(x)
            if rec.shape != x.shape or not torch.isfinite(rec).all():
                return InferenceResult(False, "NON_FINITE_OUTPUT", [], [], [])
            err = ((rec - x) ** 2).reshape(x.shape[0], -1).mean(dim=1)
            errors = [float(v) for v in err.cpu().numpy().tolist()]
    except Exception as exc:
        return InferenceResult(False, f"INFERENCE_EXCEPTION: {exc}", [], [], [])
    if any(not np.isfinite(e) or e < 0 for e in errors):
        return InferenceResult(False, "NON_FINITE_OUTPUT", [], [], [])

    # A vessel can now have several windows. Publish one comparable vessel-level
    # score using its worst reconstruction error; this preserves the strongest
    # observed deviation without counting a long track multiple times.
    grouped: dict[str, list[float]] = defaultdict(list)
    for mmsi, error in zip(mmsis, errors):
        grouped[str(mmsi)].append(float(error))
    vessel_mmsis = list(grouped)
    vessel_errors = [max(grouped[mmsi]) for mmsi in vessel_mmsis]
    scores_v = _minmax(vessel_errors)
    scores = [
        TemporalScore(mmsi, float(error), float(score), int(sequences[next(i for i, seq in enumerate(sequences) if seq.mmsi == mmsi)].sequence_length), input_dim)
        for mmsi, error, score in zip(vessel_mmsis, vessel_errors, scores_v)
    ]
    return InferenceResult(True, f"{architecture.upper()} inference completed.", scores, vessel_errors, vessel_mmsis)


def _minmax(errors):
    if not errors:
        return []
    a = np.asarray(errors, dtype=np.float64)
    lo, hi = float(a.min()), float(a.max())
    if not np.isfinite(lo) or not np.isfinite(hi) or hi - lo < EQUAL_ERROR_EPS:
        return [EQUAL_ERROR_SCORE] * len(errors)
    return [float((e - lo) / (hi - lo)) for e in a]
