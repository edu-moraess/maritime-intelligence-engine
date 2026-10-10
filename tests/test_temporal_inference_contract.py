import numpy as np
import pytest

from src.ml.temporal.inference import score_sequences
from src.ml.temporal.model import torch_available
from src.ml.temporal.types import TEMPORAL_FEATURE_NAMES, TemporalSequence


@pytest.mark.skipif(not torch_available(), reason="PyTorch is not installed")
def test_inference_rejects_masked_window_before_model_execution():
    sequence = TemporalSequence(
        mmsi="123456789",
        sequence=np.zeros((4, len(TEMPORAL_FEATURE_NAMES)), dtype=np.float32),
        sequence_length=4,
        feature_names=TEMPORAL_FEATURE_NAMES,
        n_source_points=4,
        mask=np.array([1.0, 1.0, 0.0, 1.0], dtype=np.float32),
    )

    result = score_sequences(
        [sequence],
        model_state={},
        scaler_mean=np.zeros(len(TEMPORAL_FEATURE_NAMES), dtype=np.float64),
        scaler_scale=np.ones(len(TEMPORAL_FEATURE_NAMES), dtype=np.float64),
        input_dim=len(TEMPORAL_FEATURE_NAMES),
    )

    assert not result.ok
    assert result.reason.startswith("INVALID_MASK:")
    assert result.scores == []
