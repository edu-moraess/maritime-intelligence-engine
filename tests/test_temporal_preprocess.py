import numpy as np

from src.ml.temporal.preprocess import _build_feature_matrix, _resample_to_length


def test_temporal_window_selects_real_rows_without_interpolation() -> None:
    matrix = np.arange(12 * 2, dtype=np.float64).reshape(12, 2)

    result = _resample_to_length(matrix, 8)

    assert result.shape == (8, 2)
    assert all(any(np.array_equal(row, source) for source in matrix) for row in result)


def test_temporal_window_rejects_insufficient_real_points() -> None:
    matrix = np.arange(7 * 2, dtype=np.float64).reshape(7, 2)

    try:
        _resample_to_length(matrix, 8)
    except ValueError as exc:
        assert "enough real observations" in str(exc)
    else:
        raise AssertionError("Expected insufficient observations to be rejected")


def test_motion_deltas_are_converted_from_degrees_to_metres() -> None:
    import pandas as pd

    frame = pd.DataFrame(
        {
            "latitude": [29.0, 29.001],
            "longitude": [-95.0, -95.0],
            "sog_knots": [5.0, 5.0],
            "cog_degrees": [90.0, 90.0],
            "computed_speed_knots": [0.0, 5.0],
            "heading_change": [0.0, 0.0],
            "time_delta_seconds": [0.0, 60.0],
        }
    )

    result = _build_feature_matrix(frame)

    assert result is not None
    assert np.isclose(result[1, 0], 111.132, atol=0.5)
    assert np.isclose(result[1, 1], 0.0, atol=1e-6)
