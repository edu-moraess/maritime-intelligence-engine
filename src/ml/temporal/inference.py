"""Inference and reconstruction-error scoring."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Sequence
import numpy as np
from src.ml.temporal.model import GRUTemporalAutoencoder, torch_available
from src.ml.temporal.preprocess import TemporalSequenceScaler
from src.ml.temporal.types import DEFAULT_HIDDEN_DIM, DEFAULT_INPUT_DIM, DEFAULT_LATENT_DIM, DEFAULT_NUM_LAYERS, TemporalScore, TemporalSequence
try:
    import torch
except ImportError:
    torch = None
EQUAL_ERROR_SCORE, EQUAL_ERROR_EPS = 0.5, 1e-12

@dataclass
class InferenceResult:
    ok: bool
    reason: str
    scores: list
    errors: list
    mmsis: list

def score_sequences(sequences, *, model_state, scaler_mean, scaler_scale, input_dim=DEFAULT_INPUT_DIM, hidden_dim=DEFAULT_HIDDEN_DIM, latent_dim=DEFAULT_LATENT_DIM, num_layers=DEFAULT_NUM_LAYERS, device=None):
    if not torch_available() or torch is None:
        return InferenceResult(False, "PyTorch is not available.", [], [], [])
    if not sequences or model_state is None or scaler_mean is None or scaler_scale is None:
        return InferenceResult(False, "Missing sequences, model_state, or scaler.", [], [], [])
    try:
        scaler = TemporalSequenceScaler.from_stats(scaler_mean, scaler_scale)
    except ValueError as e:
        return InferenceResult(False, str(e), [], [], [])
    arrays = [np.asarray(s.sequence, dtype=np.float32) for s in sequences]
    mmsis = [s.mmsi for s in sequences]
    if any(a.shape[-1] != input_dim for a in arrays) or any(not np.isfinite(a).all() for a in arrays):
        return InferenceResult(False, "NON_FINITE_INPUT", [], [], [])
    scaled = scaler.transform(arrays)
    if not np.isfinite(scaled).all():
        return InferenceResult(False, "NON_FINITE_INPUT", [], [], [])
    dev = device or ("cuda" if torch.cuda.is_available() else "cpu")
    try:
        model = GRUTemporalAutoencoder(input_dim, hidden_dim, latent_dim, num_layers)
        model.load_state_dict(model_state)
        model.to(torch.device(dev)); model.eval()
    except Exception as e:
        return InferenceResult(False, f"Failed to load model_state: {e}", [], [], [])
    try:
        with torch.no_grad():
            x = torch.from_numpy(scaled).to(torch.device(dev))
            rec, _ = model(x)
            if rec.shape != x.shape or not torch.isfinite(rec).all():
                return InferenceResult(False, "NON_FINITE_OUTPUT", [], [], [])
            err = ((rec - x) ** 2).reshape(x.shape[0], -1).mean(dim=1)
            errors = [float(v) for v in err.cpu().numpy().tolist()]
    except Exception as e:
        return InferenceResult(False, f"INFERENCE_EXCEPTION: {e}", [], [], [])
    if any(not np.isfinite(e) or e < 0 for e in errors):
        return InferenceResult(False, "NON_FINITE_OUTPUT", [], [], [])
    scores_v = _minmax(errors)
    scores = [TemporalScore(m, float(e), float(s), int(sequences[i].sequence_length), input_dim) for i, (m, e, s) in enumerate(zip(mmsis, errors, scores_v))]
    return InferenceResult(True, "Inference completed.", scores, errors, mmsis)

def _minmax(errors):
    if not errors:
        return []
    a = np.asarray(errors, dtype=np.float64)
    lo, hi = float(a.min()), float(a.max())
    if not np.isfinite(lo) or not np.isfinite(hi) or hi - lo < EQUAL_ERROR_EPS:
        return [EQUAL_ERROR_SCORE] * len(errors)
    return [float((e - lo) / (hi - lo)) for e in a]
