"""Temporal deep-learning path for real AIS trajectories."""
from src.ml.temporal.adapter import TemporalAnomalyAdapter
from src.ml.temporal.benchmark import BenchmarkResult, compare_if_vs_deep, compare_snapshot, if_scores_from_embeddings
from src.ml.temporal.inference import InferenceResult, score_sequences
from src.ml.temporal.model import GRUTemporalAutoencoder, TCNAutoencoder, TemporalResidualBlock, torch_available
from src.ml.temporal.preprocess import FEATURE_DIM, FEATURE_NAMES, TemporalSequenceScaler, build_temporal_sequence, build_temporal_sequences, sequences_to_batch
from src.ml.temporal.trainer import TemporalTrainer, TrainingConfig, TrainingResult
from src.ml.temporal.types import DEFAULT_SEQUENCE_LENGTH, MINIMUM_POINTS_PER_TRACK, MINIMUM_TRACKS_FOR_DEEP_MODEL, TEMPORAL_FEATURE_NAMES, TemporalFitResult, TemporalScore, TemporalSequence, VALID_TEMPORAL_STATUSES

__all__ = [
    "TemporalAnomalyAdapter", "TCNAutoencoder", "TemporalResidualBlock", "GRUTemporalAutoencoder", "torch_available",
    "score_sequences", "InferenceResult", "compare_snapshot", "compare_if_vs_deep", "if_scores_from_embeddings", "BenchmarkResult",
    "TemporalFitResult", "TemporalScore", "TemporalSequence", "TemporalSequenceScaler", "TemporalTrainer", "TrainingConfig", "TrainingResult",
    "build_temporal_sequence", "build_temporal_sequences", "sequences_to_batch", "FEATURE_DIM", "FEATURE_NAMES", "TEMPORAL_FEATURE_NAMES",
    "MINIMUM_TRACKS_FOR_DEEP_MODEL", "MINIMUM_POINTS_PER_TRACK", "DEFAULT_SEQUENCE_LENGTH", "VALID_TEMPORAL_STATUSES",
]
