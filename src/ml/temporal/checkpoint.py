"""Safe, versioned persistence for trained MIE temporal models.

The checkpoint stores weights, feature-schema identity, scaling statistics, and
training provenance together. It never stores arbitrary Python objects.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from src.ml.temporal.model import GRUTemporalAutoencoder, TCNAutoencoder, torch_available
from src.ml.temporal.types import (
    DEFAULT_HIDDEN_DIM,
    DEFAULT_INPUT_DIM,
    DEFAULT_LATENT_DIM,
    DEFAULT_NUM_LAYERS,
    DEFAULT_SEQUENCE_LENGTH,
    TEMPORAL_FEATURE_NAMES,
)

CHECKPOINT_FORMAT = "mie.temporal.checkpoint"
CHECKPOINT_VERSION = 1
DEFAULT_MAX_SEQUENCE_LENGTH = 128


@dataclass(frozen=True)
class LoadedTemporalCheckpoint:
    """Validated model and preprocessing state loaded from a checkpoint."""

    model: Any
    architecture: str
    sequence_length: int
    feature_names: tuple[str, ...]
    scaler_mean: np.ndarray
    scaler_scale: np.ndarray
    training_metadata: dict[str, Any]
    feature_schema_sha256: str


def feature_schema_sha256(feature_names: Sequence[str]) -> str:
    """Hash the ordered feature names using a stable JSON representation."""
    canonical = json.dumps(list(feature_names), ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_scaler(mean: Any, scale: Any, input_dim: int) -> tuple[np.ndarray, np.ndarray]:
    mean_array = np.asarray(mean, dtype=np.float64).reshape(-1)
    scale_array = np.asarray(scale, dtype=np.float64).reshape(-1)
    if mean_array.shape != (input_dim,) or scale_array.shape != (input_dim,):
        raise ValueError(f"Scaler vectors must both have shape ({input_dim},).")
    if not np.isfinite(mean_array).all() or not np.isfinite(scale_array).all():
        raise ValueError("Scaler statistics must be finite.")
    if np.any(scale_array <= 0):
        raise ValueError("Scaler scales must be strictly positive.")
    return mean_array, scale_array


def _make_model(
    architecture: str,
    *,
    input_dim: int,
    hidden_dim: int,
    latent_dim: int,
    num_layers: int,
    max_sequence_length: int,
) -> Any:
    if not torch_available():
        raise RuntimeError("PyTorch is required to load a temporal checkpoint.")
    if architecture == "tcn":
        return TCNAutoencoder(
            input_dim=input_dim,
            hidden_dim=hidden_dim,
            latent_dim=latent_dim,
            num_layers=num_layers,
            max_sequence_length=max_sequence_length,
        )
    if architecture == "gru":
        return GRUTemporalAutoencoder(
            input_dim=input_dim,
            hidden_dim=hidden_dim,
            latent_dim=latent_dim,
            num_layers=num_layers,
        )
    raise ValueError(f"Unsupported temporal architecture: {architecture!r}.")


def save_temporal_checkpoint(
    path: str | Path,
    *,
    model_state: Mapping[str, Any],
    scaler_mean: Any,
    scaler_scale: Any,
    architecture: str = "tcn",
    sequence_length: int = DEFAULT_SEQUENCE_LENGTH,
    input_dim: int = DEFAULT_INPUT_DIM,
    hidden_dim: int = DEFAULT_HIDDEN_DIM,
    latent_dim: int = DEFAULT_LATENT_DIM,
    num_layers: int = DEFAULT_NUM_LAYERS,
    max_sequence_length: int = DEFAULT_MAX_SEQUENCE_LENGTH,
    feature_names: Sequence[str] = TEMPORAL_FEATURE_NAMES,
    training_metadata: Mapping[str, Any] | None = None,
) -> Path:
    """Validate and atomically save a self-describing temporal checkpoint."""
    if not torch_available():
        raise RuntimeError("PyTorch is required to save a temporal checkpoint.")
    import torch

    architecture = str(architecture).lower()
    dims = (int(input_dim), int(hidden_dim), int(latent_dim), int(num_layers))
    if min(dims) < 1 or int(sequence_length) < 1 or int(max_sequence_length) < int(sequence_length):
        raise ValueError("Model dimensions and sequence length must be positive and consistent.")
    names = tuple(str(name) for name in feature_names)
    if len(names) != int(input_dim) or len(set(names)) != len(names):
        raise ValueError("Feature names must be unique and match input_dim.")
    mean, scale = _validate_scaler(scaler_mean, scaler_scale, int(input_dim))
    metadata = dict(training_metadata or {})
    try:
        # Limit provenance to JSON primitives; no arbitrary objects in bundle.
        metadata_json = json.dumps(metadata, sort_keys=True, allow_nan=False)
        metadata = json.loads(metadata_json)
    except (TypeError, ValueError) as exc:
        raise ValueError("training_metadata must contain only finite JSON-compatible values.") from exc

    model = _make_model(
        architecture,
        input_dim=int(input_dim),
        hidden_dim=int(hidden_dim),
        latent_dim=int(latent_dim),
        num_layers=int(num_layers),
        max_sequence_length=int(max_sequence_length),
    )
    try:
        model.load_state_dict(dict(model_state), strict=True)
    except Exception as exc:
        raise ValueError(f"Model state does not match declared architecture: {exc}") from exc
    clean_state: dict[str, Any] = {}
    for key, value in model.state_dict().items():
        tensor = value.detach().cpu().contiguous()
        if not torch.isfinite(tensor).all():
            raise ValueError(f"Non-finite model tensor: {key}")
        clean_state[key] = tensor.clone()

    bundle = {
        "format": CHECKPOINT_FORMAT,
        "version": CHECKPOINT_VERSION,
        "architecture": architecture,
        "dimensions": {
            "input_dim": int(input_dim),
            "hidden_dim": int(hidden_dim),
            "latent_dim": int(latent_dim),
            "num_layers": int(num_layers),
            "max_sequence_length": int(max_sequence_length),
        },
        "sequence_length": int(sequence_length),
        "feature_names": list(names),
        "feature_schema_sha256": feature_schema_sha256(names),
        "scaler_mean": torch.tensor(mean, dtype=torch.float64),
        "scaler_scale": torch.tensor(scale, dtype=torch.float64),
        "model_state": clean_state,
        "training_metadata": metadata,
    }

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=str(destination.parent))
    os.close(fd)
    try:
        torch.save(bundle, temporary_name)
        os.replace(temporary_name, destination)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)
    return destination


def load_temporal_checkpoint(
    path: str | Path,
    *,
    expected_feature_names: Sequence[str] = TEMPORAL_FEATURE_NAMES,
) -> LoadedTemporalCheckpoint:
    """Load a checkpoint using weights-only deserialization and strict checks."""
    if not torch_available():
        raise RuntimeError("PyTorch is required to load a temporal checkpoint.")
    import torch

    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    try:
        bundle = torch.load(source, map_location="cpu", weights_only=True)
    except Exception as exc:
        raise ValueError(f"Checkpoint could not be safely deserialized: {exc}") from exc
    if not isinstance(bundle, dict):
        raise ValueError("Checkpoint root must be a dictionary.")
    if bundle.get("format") != CHECKPOINT_FORMAT or bundle.get("version") != CHECKPOINT_VERSION:
        raise ValueError("Unsupported temporal checkpoint format/version.")

    names = tuple(bundle.get("feature_names", ()))
    expected = tuple(str(name) for name in expected_feature_names)
    actual_hash = feature_schema_sha256(names)
    if actual_hash != bundle.get("feature_schema_sha256"):
        raise ValueError("Checkpoint feature-schema hash is invalid.")
    if names != expected:
        raise ValueError("Checkpoint feature schema does not match the expected ordered features.")

    dims = bundle.get("dimensions")
    if not isinstance(dims, dict):
        raise ValueError("Checkpoint dimensions are missing.")
    input_dim = int(dims.get("input_dim", 0))
    if input_dim != len(names):
        raise ValueError("Checkpoint input_dim does not match feature schema.")
    sequence_length = int(bundle.get("sequence_length", 0))
    if sequence_length < 1 or sequence_length > int(dims.get("max_sequence_length", 0)):
        raise ValueError("Checkpoint sequence length is outside model capacity.")
    mean, scale = _validate_scaler(bundle.get("scaler_mean"), bundle.get("scaler_scale"), input_dim)

    model = _make_model(
        str(bundle.get("architecture", "")),
        input_dim=input_dim,
        hidden_dim=int(dims.get("hidden_dim", 0)),
        latent_dim=int(dims.get("latent_dim", 0)),
        num_layers=int(dims.get("num_layers", 0)),
        max_sequence_length=int(dims.get("max_sequence_length", 0)),
    )
    state = bundle.get("model_state")
    if not isinstance(state, dict):
        raise ValueError("Checkpoint model_state is missing.")
    try:
        model.load_state_dict(state, strict=True)
    except Exception as exc:
        raise ValueError(f"Checkpoint weights do not match architecture: {exc}") from exc
    for key, tensor in model.state_dict().items():
        if not torch.isfinite(tensor).all():
            raise ValueError(f"Non-finite model tensor after load: {key}")
    metadata = bundle.get("training_metadata", {})
    if not isinstance(metadata, dict):
        raise ValueError("Checkpoint training_metadata must be a dictionary.")
    model.eval()
    return LoadedTemporalCheckpoint(
        model=model,
        architecture=str(bundle["architecture"]),
        sequence_length=sequence_length,
        feature_names=names,
        scaler_mean=mean,
        scaler_scale=scale,
        training_metadata=metadata,
        feature_schema_sha256=actual_hash,
    )
