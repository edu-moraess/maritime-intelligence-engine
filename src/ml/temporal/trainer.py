"""Time-bounded GRU Temporal Autoencoder training on real AIS sequences."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np

from src.ml.temporal.model import GRUTemporalAutoencoder, TCNAutoencoder, torch_available
from src.ml.temporal.preprocess import TemporalSequenceScaler
from src.ml.temporal.types import (
    DEFAULT_EPOCHS_MAX, DEFAULT_HIDDEN_DIM, DEFAULT_INPUT_DIM, DEFAULT_LATENT_DIM,
    DEFAULT_LEARNING_RATE, DEFAULT_MAX_TRAINING_SECONDS, DEFAULT_NUM_LAYERS,
    DEFAULT_PATIENCE, DEFAULT_SEED, DEFAULT_VALIDATION_FRACTION,
    MINIMUM_TRACKS_FOR_VALIDATION_SPLIT, TemporalSequence,
)

try:
    import torch
    from torch import nn
except ImportError:  # pragma: no cover
    torch = None  # type: ignore[assignment]
    nn = None  # type: ignore[assignment]


@dataclass
class TrainingConfig:
    input_dim: int = DEFAULT_INPUT_DIM
    hidden_dim: int = DEFAULT_HIDDEN_DIM
    latent_dim: int = DEFAULT_LATENT_DIM
    num_layers: int = DEFAULT_NUM_LAYERS
    epochs_max: int = DEFAULT_EPOCHS_MAX
    learning_rate: float = DEFAULT_LEARNING_RATE
    patience: int = DEFAULT_PATIENCE
    max_training_seconds: float = DEFAULT_MAX_TRAINING_SECONDS
    seed: int = DEFAULT_SEED
    validation_fraction: float = DEFAULT_VALIDATION_FRACTION
    # Short AIS windows and a bounded CPU budget favor a compact recurrent
    # autoencoder. TCN remains accepted for backward-compatible states/tests.
    architecture: str = "gru"


@dataclass
class TrainingResult:
    ok: bool
    reason: str
    model_state: dict[str, Any] | None = None
    scaler_mean: np.ndarray | None = None
    scaler_scale: np.ndarray | None = None
    n_train: int = 0
    n_validation: int = 0
    epochs_completed: int = 0
    best_epoch: int | None = None
    best_loss: float | None = None
    training_seconds: float = 0.0
    device: str = "cpu"
    training_mode: str = "none"
    seed: int = DEFAULT_SEED
    training_started: bool = False
    training_completed: bool = False
    architecture: str = "gru"


class TemporalTrainer:
    """Fit the temporal autoencoder under a hard wall-clock budget."""

    def __init__(self, config: TrainingConfig | None = None) -> None:
        self.config = config or TrainingConfig()

    def train(self, sequences: Sequence[TemporalSequence]) -> TrainingResult:
        cfg = self.config
        architecture = cfg.architecture.lower()
        if not torch_available() or torch is None or nn is None:
            return TrainingResult(ok=False, reason="PyTorch is not available.", seed=cfg.seed, architecture=architecture)
        if architecture not in {"gru", "tcn"}:
            return TrainingResult(ok=False, reason=f"Unsupported temporal architecture: {cfg.architecture}.", seed=cfg.seed, architecture=architecture)
        if not sequences:
            return TrainingResult(ok=False, reason="No sequences provided for training.", seed=cfg.seed, architecture=architecture)

        arrays = [np.asarray(s.sequence, dtype=np.float32) for s in sequences]
        if any(a.ndim != 2 or a.shape[1] != cfg.input_dim for a in arrays):
            return TrainingResult(ok=False, reason="Invalid sequence shapes.", seed=cfg.seed, architecture=architecture)
        if any(not np.isfinite(a).all() for a in arrays):
            return TrainingResult(ok=False, reason="Non-finite values in sequences.", seed=cfg.seed, architecture=architecture)

        # Split by vessel, not by window. A vessel may now contribute several
        # windows, so random window splitting would leak the same trajectory
        # into both training and validation sets.
        groups: dict[str, list[int]] = {}
        for index, sequence in enumerate(sequences):
            groups.setdefault(str(sequence.mmsi), []).append(index)
        vessel_ids = np.asarray(list(groups), dtype=object)
        rng = np.random.default_rng(cfg.seed)
        rng.shuffle(vessel_ids)
        use_val = len(vessel_ids) >= MINIMUM_TRACKS_FOR_VALIDATION_SPLIT
        if use_val:
            n_val_vessels = min(max(1, int(round(len(vessel_ids) * cfg.validation_fraction))), len(vessel_ids) - 1)
            val_vessels = set(vessel_ids[:n_val_vessels].tolist())
            val_idx = np.asarray([i for vessel in val_vessels for i in groups[vessel]], dtype=int)
            train_idx = np.asarray([i for vessel in vessel_ids[n_val_vessels:] for i in groups[vessel]], dtype=int)
        else:
            train_idx = np.arange(len(arrays), dtype=int)
            val_idx = np.array([], dtype=int)
        train_arrays = [arrays[i] for i in train_idx]
        val_arrays = [arrays[i] for i in val_idx] if len(val_idx) else []

        try:
            scaler = TemporalSequenceScaler()
            scaler.fit(train_arrays)
            x_train = scaler.transform(train_arrays)
            x_val = scaler.transform(val_arrays) if val_arrays else None
        except Exception as exc:
            return TrainingResult(ok=False, reason=f"Scaler fit failed: {exc}", seed=cfg.seed, architecture=architecture)
        if not np.isfinite(x_train).all():
            return TrainingResult(ok=False, reason="Non-finite values after scaling.", seed=cfg.seed, architecture=architecture)

        device_str = "cuda" if torch.cuda.is_available() else "cpu"
        device = torch.device(device_str)
        torch.manual_seed(cfg.seed)
        if device_str == "cuda":
            torch.cuda.manual_seed_all(cfg.seed)

        model_cls = GRUTemporalAutoencoder if architecture == "gru" else TCNAutoencoder
        model = model_cls(cfg.input_dim, cfg.hidden_dim, cfg.latent_dim, cfg.num_layers).to(device)
        optimizer = torch.optim.Adam(model.parameters(), lr=cfg.learning_rate)
        criterion = nn.MSELoss()
        x_train_t = torch.from_numpy(x_train).to(device)
        x_val_t = torch.from_numpy(x_val).to(device) if x_val is not None else None

        started = time.monotonic()
        best_loss = float("inf")
        best_state: dict[str, Any] | None = None
        best_epoch: int | None = None
        epochs_done = 0
        patience_left = cfg.patience
        mode = "train_val" if use_val else "train_only"

        try:
            for epoch in range(1, cfg.epochs_max + 1):
                if time.monotonic() - started >= cfg.max_training_seconds:
                    break
                model.train()
                optimizer.zero_grad()
                rec, _ = model(x_train_t)
                loss = criterion(rec, x_train_t)
                if not torch.isfinite(loss):
                    return TrainingResult(False, "Non-finite training loss.", n_train=len(train_idx), n_validation=len(val_idx), epochs_completed=epochs_done, training_seconds=time.monotonic()-started, device=device_str, training_mode=mode, seed=cfg.seed, training_started=True, architecture=architecture)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=5.0)
                optimizer.step()
                epochs_done = epoch
                model.eval()
                with torch.no_grad():
                    monitor = float(criterion(model(x_val_t)[0], x_val_t).item()) if x_val_t is not None else float(loss.item())
                if monitor < best_loss and np.isfinite(monitor):
                    best_loss, best_epoch = monitor, epoch
                    best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
                    patience_left = cfg.patience
                else:
                    patience_left -= 1
                    if patience_left <= 0:
                        break
        except Exception as exc:
            return TrainingResult(False, f"Training exception: {exc}", n_train=len(train_idx), n_validation=len(val_idx), epochs_completed=epochs_done, training_seconds=time.monotonic()-started, device=device_str, training_mode=mode, seed=cfg.seed, training_started=True, architecture=architecture)

        elapsed = time.monotonic() - started
        if best_state is None:
            return TrainingResult(False, "No valid model state produced.", n_train=len(train_idx), n_validation=len(val_idx), epochs_completed=epochs_done, training_seconds=elapsed, device=device_str, training_mode=mode, seed=cfg.seed, training_started=True, architecture=architecture)
        for tensor in best_state.values():
            if not torch.isfinite(tensor).all():
                return TrainingResult(False, "Non-finite weights in best model state.", n_train=len(train_idx), n_validation=len(val_idx), epochs_completed=epochs_done, best_epoch=best_epoch, best_loss=best_loss if np.isfinite(best_loss) else None, training_seconds=elapsed, device=device_str, training_mode=mode, seed=cfg.seed, training_started=True, architecture=architecture)
        return TrainingResult(True, f"{architecture.upper()} training completed on real AIS sequences.", model_state=best_state, scaler_mean=np.asarray(scaler.mean_, dtype=np.float64), scaler_scale=np.asarray(scaler.scale_, dtype=np.float64), n_train=len(train_idx), n_validation=len(val_idx), epochs_completed=epochs_done, best_epoch=best_epoch, best_loss=float(best_loss), training_seconds=elapsed, device=device_str, training_mode=mode, seed=cfg.seed, training_started=True, training_completed=True, architecture=architecture)
