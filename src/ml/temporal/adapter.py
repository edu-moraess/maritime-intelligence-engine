"""Temporal anomaly adapter — parallel path to PCA/IF."""
from __future__ import annotations
from src.ml.temporal.inference import score_sequences
from src.ml.temporal.model import torch_available
from src.ml.temporal.preprocess import FEATURE_DIM, build_temporal_sequences, sequences_to_batch
from src.ml.temporal.trainer import TemporalTrainer, TrainingConfig
from src.ml.temporal.types import (
    DEFAULT_MAX_TRAINING_SECONDS, DEFAULT_SEQUENCE_LENGTH, DEFAULT_SEED,
    MINIMUM_POINTS_PER_TRACK, MINIMUM_TRACKS_FOR_DEEP_MODEL, TemporalFitResult,
)

class TemporalAnomalyAdapter:
    def __init__(self, minimum_tracks=MINIMUM_TRACKS_FOR_DEEP_MODEL, minimum_points_per_track=MINIMUM_POINTS_PER_TRACK,
                 sequence_length=DEFAULT_SEQUENCE_LENGTH, input_dim=FEATURE_DIM,
                 max_training_seconds=DEFAULT_MAX_TRAINING_SECONDS, seed=DEFAULT_SEED, training_config=None):
        self.minimum_tracks = max(1, int(minimum_tracks))
        self.minimum_points_per_track = max(1, int(minimum_points_per_track))
        self.sequence_length = max(1, int(sequence_length))
        self.input_dim = max(1, int(input_dim))
        self.max_training_seconds = float(max_training_seconds)
        self.seed = int(seed)
        self.training_config = training_config
        self.result = None

    def fit(self, tracks):
        if not torch_available():
            self.result = TemporalFitResult(status="UNAVAILABLE", reason="PyTorch is not installed or cannot be imported.")
            return self.result
        if not tracks:
            self.result = TemporalFitResult(status="WAITING", reason="No real AIS tracks are available in the current session.")
            return self.result
        n_seen = len(tracks)
        try:
            sequences = build_temporal_sequences(tracks, sequence_length=self.sequence_length, minimum_points=self.minimum_points_per_track)
        except Exception as e:
            self.result = TemporalFitResult(status="FAILED", reason=f"Preprocessing failed: {e}", n_tracks_seen=n_seen)
            return self.result
        n_usable = len(sequences)
        n_points_min = min((s.n_source_points for s in sequences), default=None)
        if n_usable == 0:
            self.result = TemporalFitResult(status="NOT_READY", reason=f"No valid temporal sequence (need ≥{self.minimum_points_per_track} points).", n_tracks_seen=n_seen)
            return self.result
        if n_usable < self.minimum_tracks:
            self.result = TemporalFitResult(status="NOT_READY", reason=f"Insufficient usable tracks: {n_usable} < minimum {self.minimum_tracks}.", n_tracks_seen=n_seen, n_tracks_usable=n_usable, n_points_min=n_points_min, sequences=list(sequences))
            return self.result
        cfg = self.training_config or TrainingConfig(input_dim=self.input_dim, max_training_seconds=self.max_training_seconds, seed=self.seed)
        if self.training_config is None:
            cfg.max_training_seconds, cfg.seed, cfg.input_dim = self.max_training_seconds, self.seed, self.input_dim
        tr = TemporalTrainer(cfg).train(sequences)
        base = dict(n_tracks_seen=n_seen, n_tracks_usable=n_usable, n_points_min=n_points_min, sequence_length=self.sequence_length, input_dim=self.input_dim, sequences=list(sequences), n_train=tr.n_train, n_validation=tr.n_validation, epochs_completed=tr.epochs_completed, best_epoch=tr.best_epoch, best_loss=tr.best_loss, training_seconds=tr.training_seconds, device=tr.device, training_mode=tr.training_mode, seed=tr.seed, training_started=tr.training_started, training_completed=tr.training_completed)
        if not tr.ok:
            self.result = TemporalFitResult(status="FAILED", reason=tr.reason, scores=[], **base)
            return self.result
        inf = score_sequences(sequences, model_state=tr.model_state, scaler_mean=tr.scaler_mean, scaler_scale=tr.scaler_scale, input_dim=self.input_dim, hidden_dim=cfg.hidden_dim, latent_dim=cfg.latent_dim, num_layers=cfg.num_layers, device=tr.device)
        if not inf.ok:
            self.result = TemporalFitResult(status="FAILED", reason=f"Inference failed after training: {inf.reason}", scores=[], model_state=tr.model_state, scaler_mean=tr.scaler_mean, scaler_scale=tr.scaler_scale, **base)
            return self.result
        self.result = TemporalFitResult(status="READY", reason=f"Trained and scored on real AIS (mode={tr.training_mode}). deep_anomaly_score is session-relative ranking, not probability.", scores=list(inf.scores), model_state=tr.model_state, scaler_mean=tr.scaler_mean, scaler_scale=tr.scaler_scale, inference_available=True, **base)
        return self.result

    def predict(self, tracks=None):
        if tracks is None:
            return self.result or TemporalFitResult(status="WAITING", reason="fit not called")
        if not self.result or not self.result.model_state or self.result.scaler_mean is None:
            return TemporalFitResult(status="FAILED", reason="No trained model/scaler")
        sequences = build_temporal_sequences(tracks, sequence_length=self.sequence_length, minimum_points=self.minimum_points_per_track)
        if not sequences:
            return TemporalFitResult(status="NOT_READY", reason="No eligible sequences")
        cfg = self.training_config or TrainingConfig(input_dim=self.input_dim)
        inf = score_sequences(sequences, model_state=self.result.model_state, scaler_mean=self.result.scaler_mean, scaler_scale=self.result.scaler_scale, input_dim=self.input_dim, hidden_dim=cfg.hidden_dim, latent_dim=cfg.latent_dim, num_layers=cfg.num_layers, device=self.result.device)
        if not inf.ok:
            return TemporalFitResult(status="FAILED", reason=inf.reason)
        return TemporalFitResult(status="READY", reason="Inference with prior model.", n_tracks_usable=len(sequences), scores=list(inf.scores), sequences=list(sequences), model_state=self.result.model_state, scaler_mean=self.result.scaler_mean, scaler_scale=self.result.scaler_scale, inference_available=True)

    @property
    def status(self):
        return "WAITING" if self.result is None else self.result.status
