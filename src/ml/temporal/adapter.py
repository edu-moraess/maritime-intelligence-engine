"""Temporal anomaly adapter — parallel path to PCA/IF."""
from __future__ import annotations

from src.ml.temporal.checkpoint import load_temporal_checkpoint, save_temporal_checkpoint
from src.ml.temporal.diagnostics import select_adaptive_sequence_length
from src.ml.temporal.inference import score_sequences
from src.ml.temporal.model import torch_available
from src.ml.temporal.preprocess import FEATURE_DIM, build_temporal_sequences
from src.ml.temporal.trainer import TemporalTrainer, TrainingConfig
from src.ml.temporal.types import (
    DEFAULT_MAX_TRAINING_SECONDS, DEFAULT_SEQUENCE_LENGTH, DEFAULT_SEED,
    MINIMUM_POINTS_PER_TRACK, MINIMUM_TRACKS_FOR_DEEP_MODEL, TemporalFitResult,
)


class TemporalAnomalyAdapter:
    def __init__(self, minimum_tracks=MINIMUM_TRACKS_FOR_DEEP_MODEL, minimum_points_per_track=MINIMUM_POINTS_PER_TRACK,
                 sequence_length: int | None = None, input_dim=FEATURE_DIM,
                 max_training_seconds=DEFAULT_MAX_TRAINING_SECONDS, seed=DEFAULT_SEED, training_config=None):
        self.minimum_tracks = max(1, int(minimum_tracks))
        self.minimum_points_per_track = max(1, int(minimum_points_per_track))
        self.sequence_length = None if sequence_length is None else max(1, int(sequence_length))
        self.input_dim = max(1, int(input_dim))
        self.max_training_seconds = float(max_training_seconds)
        self.seed = int(seed)
        self.training_config = training_config
        self.result = None

    @staticmethod
    def _unique_mmsis(sequences):
        return {str(sequence.mmsi) for sequence in sequences}

    def _select_sequence_length(self, tracks) -> int | None:
        if self.sequence_length is not None:
            return self.sequence_length
        return select_adaptive_sequence_length(tracks, minimum_tracks=self.minimum_tracks)

    def fit(self, tracks, *, checkpoint_path=None):
        if not torch_available():
            self.result = TemporalFitResult(status="UNAVAILABLE", reason="PyTorch is not installed or cannot be imported.")
            return self.result
        if not tracks:
            self.result = TemporalFitResult(status="WAITING", reason="No real AIS tracks are available in the current session.")
            return self.result
        n_seen = len(tracks)
        try:
            selected_length = self._select_sequence_length(tracks)
        except Exception as e:
            self.result = TemporalFitResult(status="FAILED", reason=f"Temporal scale selection failed: {e}", n_tracks_seen=n_seen)
            return self.result
        if selected_length is None:
            self.result = TemporalFitResult(status="NOT_READY", reason="Insufficient real AIS temporal coverage for T=8, T=16, or T=32.", n_tracks_seen=n_seen)
            return self.result
        try:
            sequences = build_temporal_sequences(tracks, sequence_length=selected_length, minimum_points=selected_length)
        except Exception as e:
            self.result = TemporalFitResult(status="FAILED", reason=f"Preprocessing failed: {e}", n_tracks_seen=n_seen, sequence_length=selected_length)
            return self.result
        unique_mmsis = self._unique_mmsis(sequences)
        n_usable = len(unique_mmsis)
        n_points_min = min((s.n_source_points for s in sequences), default=None)
        if n_usable < self.minimum_tracks:
            self.result = TemporalFitResult(status="NOT_READY", reason=f"Insufficient usable tracks: {n_usable} < minimum {self.minimum_tracks}.", n_tracks_seen=n_seen, n_tracks_usable=n_usable, n_points_min=n_points_min, sequence_length=selected_length, sequences=list(sequences))
            return self.result
        cfg = self.training_config or TrainingConfig(input_dim=self.input_dim, max_training_seconds=self.max_training_seconds, seed=self.seed)
        if self.training_config is None:
            cfg.max_training_seconds, cfg.seed, cfg.input_dim = self.max_training_seconds, self.seed, self.input_dim
        tr = TemporalTrainer(cfg).train(sequences)
        base = dict(n_tracks_seen=n_seen, n_tracks_usable=n_usable, n_points_min=n_points_min, sequence_length=selected_length, input_dim=self.input_dim, sequences=list(sequences), n_train=tr.n_train, n_validation=tr.n_validation, epochs_completed=tr.epochs_completed, best_epoch=tr.best_epoch, best_loss=tr.best_loss, training_seconds=tr.training_seconds, device=tr.device, training_mode=tr.training_mode, seed=tr.seed, training_started=tr.training_started, training_completed=tr.training_completed, architecture=tr.architecture, method=f"{tr.architecture.upper()} Temporal Autoencoder")
        if not tr.ok:
            self.result = TemporalFitResult(status="FAILED", reason=tr.reason, scores=[], **base)
            return self.result
        if checkpoint_path is not None:
            try:
                save_temporal_checkpoint(
                    checkpoint_path,
                    model_state=tr.model_state,
                    scaler_mean=tr.scaler_mean,
                    scaler_scale=tr.scaler_scale,
                    architecture=tr.architecture,
                    sequence_length=selected_length,
                    input_dim=cfg.input_dim,
                    hidden_dim=cfg.hidden_dim,
                    latent_dim=cfg.latent_dim,
                    num_layers=cfg.num_layers,
                    training_metadata={
                        "seed": int(tr.seed),
                        "training_mode": str(tr.training_mode),
                        "epochs_completed": int(tr.epochs_completed),
                        "best_epoch": int(tr.best_epoch) if tr.best_epoch is not None else None,
                        "best_loss": float(tr.best_loss) if tr.best_loss is not None else None,
                    },
                )
            except Exception as e:
                self.result = TemporalFitResult(
                    status="FAILED",
                    reason=f"Checkpoint save failed: {e}",
                    scores=[],
                    model_state=tr.model_state,
                    scaler_mean=tr.scaler_mean,
                    scaler_scale=tr.scaler_scale,
                    **base,
                )
                return self.result
        inf = score_sequences(sequences, model_state=tr.model_state, scaler_mean=tr.scaler_mean, scaler_scale=tr.scaler_scale, input_dim=self.input_dim, hidden_dim=cfg.hidden_dim, latent_dim=cfg.latent_dim, num_layers=cfg.num_layers, device=tr.device, architecture=tr.architecture)
        if not inf.ok:
            self.result = TemporalFitResult(status="FAILED", reason=f"Inference failed after training: {inf.reason}", scores=[], model_state=tr.model_state, scaler_mean=tr.scaler_mean, scaler_scale=tr.scaler_scale, **base)
            return self.result
        self.result = TemporalFitResult(status="READY", reason=f"Trained and scored on real AIS (mode={tr.training_mode}, adaptive T={selected_length}). deep_anomaly_score is session-relative ranking, not probability.", scores=list(inf.scores), model_state=tr.model_state, scaler_mean=tr.scaler_mean, scaler_scale=tr.scaler_scale, inference_available=True, **base)
        return self.result

    def predict(self, tracks=None):
        if tracks is None:
            return self.result or TemporalFitResult(status="WAITING", reason="fit not called")
        if not self.result or not self.result.model_state or self.result.scaler_mean is None:
            return TemporalFitResult(status="FAILED", reason="No trained model/scaler")
        selected_length = self.result.sequence_length
        sequences = build_temporal_sequences(tracks, sequence_length=selected_length, minimum_points=selected_length)
        if not sequences:
            return TemporalFitResult(status="NOT_READY", reason="No eligible sequences", sequence_length=selected_length)
        cfg = self.training_config or TrainingConfig(input_dim=self.input_dim)
        inf = score_sequences(sequences, model_state=self.result.model_state, scaler_mean=self.result.scaler_mean, scaler_scale=self.result.scaler_scale, input_dim=self.input_dim, hidden_dim=cfg.hidden_dim, latent_dim=cfg.latent_dim, num_layers=cfg.num_layers, device=self.result.device, architecture=self.result.architecture)
        if not inf.ok:
            return TemporalFitResult(status="FAILED", reason=inf.reason, sequence_length=selected_length, architecture=self.result.architecture, method=self.result.method)
        return TemporalFitResult(status="READY", reason="Inference with prior model.", n_tracks_usable=len(self._unique_mmsis(sequences)), sequence_length=selected_length, scores=list(inf.scores), sequences=list(sequences), model_state=self.result.model_state, scaler_mean=self.result.scaler_mean, scaler_scale=self.result.scaler_scale, inference_available=True, architecture=self.result.architecture, method=self.result.method)

    def predict_from_checkpoint(self, tracks, checkpoint_path):
        """Run inference from a validated checkpoint without starting training."""
        if not torch_available():
            return TemporalFitResult(status="UNAVAILABLE", reason="PyTorch is not installed or cannot be imported.")
        try:
            checkpoint = load_temporal_checkpoint(checkpoint_path)
        except Exception as e:
            return TemporalFitResult(status="FAILED", reason=f"Checkpoint load failed: {e}")

        selected_length = checkpoint.sequence_length
        try:
            sequences = build_temporal_sequences(
                tracks,
                sequence_length=selected_length,
                minimum_points=selected_length,
            )
        except Exception as e:
            return TemporalFitResult(
                status="FAILED",
                reason=f"Preprocessing failed: {e}",
                sequence_length=selected_length,
                architecture=checkpoint.architecture,
            )
        if not sequences:
            return TemporalFitResult(
                status="NOT_READY",
                reason="No eligible sequences for the checkpoint sequence length.",
                sequence_length=selected_length,
                architecture=checkpoint.architecture,
                input_dim=len(checkpoint.feature_names),
            )
        if any(tuple(s.feature_names) != checkpoint.feature_names for s in sequences):
            return TemporalFitResult(
                status="FAILED",
                reason="Checkpoint feature schema does not match preprocessed sequences.",
                sequence_length=selected_length,
                architecture=checkpoint.architecture,
                input_dim=len(checkpoint.feature_names),
            )

        model = checkpoint.model
        try:
            inf = score_sequences(
                sequences,
                model_state=model.state_dict(),
                scaler_mean=checkpoint.scaler_mean,
                scaler_scale=checkpoint.scaler_scale,
                input_dim=int(model.input_dim),
                hidden_dim=int(model.hidden_dim),
                latent_dim=int(model.latent_dim),
                num_layers=int(model.num_layers),
                device="cpu",
                architecture=checkpoint.architecture,
            )
        except Exception as e:
            return TemporalFitResult(
                status="FAILED",
                reason=f"Checkpoint inference failed: {e}",
                sequence_length=selected_length,
                architecture=checkpoint.architecture,
                input_dim=len(checkpoint.feature_names),
            )
        if not inf.ok:
            return TemporalFitResult(
                status="FAILED",
                reason=f"Checkpoint inference failed: {inf.reason}",
                sequence_length=selected_length,
                architecture=checkpoint.architecture,
                input_dim=len(checkpoint.feature_names),
            )
        return TemporalFitResult(
            status="READY",
            reason="Inference completed from a validated checkpoint; no training was run.",
            n_tracks_seen=len(tracks),
            n_tracks_usable=len(self._unique_mmsis(sequences)),
            sequence_length=selected_length,
            input_dim=len(checkpoint.feature_names),
            method=f"{checkpoint.architecture.upper()} Temporal Autoencoder",
            architecture=checkpoint.architecture,
            scores=list(inf.scores),
            sequences=list(sequences),
            model_state=model.state_dict(),
            scaler_mean=checkpoint.scaler_mean.copy(),
            scaler_scale=checkpoint.scaler_scale.copy(),
            inference_available=True,
            training_mode=str(checkpoint.training_metadata.get("training_mode", "checkpoint")),
            seed=int(checkpoint.training_metadata.get("seed", self.seed)),
            training_completed=False,
            training_started=False,
        )

    @property
    def status(self):
        return "WAITING" if self.result is None else self.result.status
