"""Types for temporal DL path (real AIS only)."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Literal
import numpy as np
TemporalModelStatus = Literal["WAITING","NOT_READY","READY","FAILED","UNAVAILABLE"]
VALID_TEMPORAL_STATUSES = set(TemporalModelStatus.__args__)  # type: ignore
MINIMUM_TRACKS_FOR_DEEP_MODEL = 8
MINIMUM_POINTS_PER_TRACK = 4
DEFAULT_SEQUENCE_LENGTH = 32
TEMPORAL_FEATURE_NAMES = ("delta_lat","delta_lon","sog_knots","cog_sin","cog_cos","computed_speed_knots","heading_change","log_time_delta")
DEFAULT_INPUT_DIM = len(TEMPORAL_FEATURE_NAMES)
DEFAULT_HIDDEN_DIM, DEFAULT_LATENT_DIM, DEFAULT_NUM_LAYERS = 32, 16, 1
MAX_TIME_DELTA_SECONDS = 900.0
DEFAULT_EPOCHS_MAX, DEFAULT_LEARNING_RATE, DEFAULT_PATIENCE = 30, 1e-3, 5
DEFAULT_MAX_TRAINING_SECONDS, DEFAULT_SEED = 5.0, 42
DEFAULT_VALIDATION_FRACTION, MINIMUM_TRACKS_FOR_VALIDATION_SPLIT = 0.20, 10

@dataclass(frozen=True)
class TemporalScore:
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
        if arr.ndim != 2 or arr.shape[0] != self.sequence_length or arr.shape[1] != len(self.feature_names):
            raise ValueError("invalid TemporalSequence shape")

@dataclass
class TemporalFitResult:
    status: TemporalModelStatus
    reason: str
    n_tracks_seen: int = 0
    n_tracks_usable: int = 0
    n_points_min: int | None = None
    sequence_length: int = DEFAULT_SEQUENCE_LENGTH
    input_dim: int = DEFAULT_INPUT_DIM
    method: str = "GRU Temporal Autoencoder"
    scores: list = field(default_factory=list)
    sequences: list = field(default_factory=list)
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
    model_state: dict | None = None
    scaler_mean: np.ndarray | None = None
    scaler_scale: np.ndarray | None = None
    @property
    def ready(self) -> bool:
        return self.status == "READY"
    def score_for(self, mmsi: str):
        for item in self.scores:
            if item.mmsi == mmsi:
                return item
        return None
