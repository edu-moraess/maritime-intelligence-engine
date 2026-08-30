"""Types and contracts for the temporal deep-learning path (real AIS only)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np

TemporalModelStatus = Literal["WAITING", "NOT_READY", "READY", "FAILED", "UNAVAILABLE"]
VALID_TEMPORAL_STATUSES = {"WAITING", "NOT_READY", "READY", "FAILED", "UNAVAILABLE"}

MINIMUM_TRACKS_FOR_DEEP_MODEL = 8
MINIMUM_POINTS_PER_TRACK = 4
DEFAULT_SEQUENCE_LENGTH = 32

TEMPORAL_FEATURE_NAMES: tuple[str, ...] = (
    "delta_lat",
    "delta_lon",
    "sog_knots",
    "cog_sin",
    "cog_cos",
    "computed_speed_knots",
    "heading_change",
    "log_time_delta",
)
DEFAULT_INPUT_DIM = len(TEMPORAL_FEATURE_NAMES)
DEFAULT_HIDDEN_DIM = 32
DEFAULT_LATENT_DIM = 16
DEFAULT_NUM_LAYERS = 3
MAX_TIME_DELTA_SECONDS = 900.0

DEFAULT_EPOCHS_MAX = 30
DEFAULT_LEARNING_RATE = 1e-3
DEFAULT_PATIENCE = 5
DEFAULT_MAX_TRAINING_SECONDS = 5.0
DEFAULT_SEED = 42
DEFAULT_VALIDATION_FRACTION = 0.20
MINIMUM_TRACKS_FOR_VALIDATION_SPLIT = 10


@dataclass(frozen=True)
class TemporalScore:
    """Session-relative reconstruction signal. Not probability or confidence."""

    mmsi: str
    reconstruction_error: float
    deep_anomaly_score: float
    sequence_length: int = DEFAULT_SEQUENCE_LENGTH
    feature_count: int = DEFAULT_INPUT_DIM


@dataclass(frozen=True)
class TemporalSequence:
    mmsi: str
    sequence: np.ndarray
    sequence_length: int
    feature_names: tuple[str, ...]
    n_source_points: int

    def __post_init__(self) -> None:
        arr = np.asarray(self.sequence)
        if arr.ndim != 2:
            raise ValueError(f"sequence must be 2-D (T, F), got {arr.shape}")
        if arr.shape[0] != self.sequence_length:
            raise ValueError(f"sequence length {arr.shape[0]} != sequence_length {self.sequence_length}")
        if arr.shape[1] != len(self.feature_names):
            raise ValueError(f"feature dim {arr.shape[1]} != len(feature_names {self.feature_names})")


@dataclass
class TemporalFitResult:
    status: TemporalModelStatus
    reason: str
    n_tracks_seen: int = 0
    n_tracks_usable: int = 0
    n_points_min: int | None = None
    sequence_length: int = DEFAULT_SEQUENCE_LENGTH
    input_dim: int = DEFAULT_INPUT_DIM
    method: str = "TCN Temporal Autoencoder"
    scores: list[TemporalScore] = field(default_factory=list)
    sequences: list[TemporalSequence] = field(default_factory=list)
    latent: np.ndarray | None = None
    n_train: int = 0
    n_validation: int = 0
    epochs_completed: int = 0
    best_epoch: int | None = None
    best_loss: float | None = None
    training_seconds: float = 0.0
    device: str = "cpu"
    training_mode: str = "none"
    seed: int = DEFAULT_SEED
    model_state: dict[str, Any] | None = None
    scaler_mean: np.ndarray | None = None
    scaler_scale: np.ndarray | None = None
    training_started: bool = False
    training_completed: bool = False
    inference_available: bool = False

    @property
    def ready(self) -> bool:
        return self.status == "READY"

    def score_for(self, mmsi: str) -> TemporalScore | None:
        for item in self.scores:
            if item.mmsi == mmsi:
                return item
        return None
