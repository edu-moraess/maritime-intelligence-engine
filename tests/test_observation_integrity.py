from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from src.ingestion.models import AISObservation
from src.trajectory.features import enrich_track, track_to_frame, trajectory_vector


def _obs(index: int, *, sog: float | None = 8.0, cog: float | None = 90.0) -> AISObservation:
    return AISObservation(
        mmsi="123456789",
        latitude=25.0 + index * 0.001,
        longitude=-80.0 + index * 0.001,
        received_at=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=index * 60),
        sog_knots=sog,
        cog_degrees=cog,
        heading_degrees=None,
    )


def test_first_transition_is_unknown_not_zero() -> None:
    frame = enrich_track(track_to_frame([_obs(0), _obs(1)]))
    first = frame.iloc[0]
    assert pd.isna(first["time_delta_seconds"])
    assert pd.isna(first["distance_km"])
    assert pd.isna(first["computed_speed_knots"])
    assert pd.isna(first["heading_change"])
    assert pd.isna(first["is_dwell"])


def test_missing_sog_and_cog_are_not_filled() -> None:
    frame = enrich_track(track_to_frame([_obs(0, sog=None), _obs(1, cog=None)]))
    assert pd.isna(frame.loc[0, "sog_knots"])
    assert pd.isna(frame.loc[1, "cog_degrees"])
    assert pd.isna(frame.loc[1, "heading_change"])


def test_embedding_vector_requires_exact_complete_real_window() -> None:
    short_track = [_obs(i) for i in range(31)]
    complete_track = [_obs(i) for i in range(32)]
    missing_track = [_obs(i) for i in range(32)]
    missing_track[-1] = _obs(31, sog=None)

    assert trajectory_vector(short_track, length=32) is None
    assert trajectory_vector(missing_track, length=32) is None
    vector = trajectory_vector(complete_track, length=32)
    assert vector is not None
    assert vector.shape == (32 * 4,)
    assert np.isfinite(vector).all()


def test_temporal_sequence_features_are_transition_only() -> None:
    import pandas as pd
    from src.ml.temporal.preprocess import _build_feature_matrix

    frame = pd.DataFrame(
        {
            "latitude": [25.0, 25.001, 25.002],
            "longitude": [-80.0, -80.0, -80.001],
            "sog_knots": [8.0, 8.1, 8.2],
            "cog_degrees": [90.0, 91.0, 92.0],
            "time_delta_seconds": [np.nan, 60.0, 60.0],
        }
    )
    matrix = _build_feature_matrix(frame)
    assert matrix is not None
    assert matrix.shape == (2, 8)
    assert np.isfinite(matrix).all()


def test_rule_anomaly_score_is_not_reported_as_confidence() -> None:
    from src.anomaly.detector import detect_anomalies

    findings = detect_anomalies(
        {
            "123456789": [
                _obs(0, sog=60.0, cog=90.0),
                _obs(1, sog=60.0, cog=90.0),
            ]
        }
    )
    speed_findings = [item for item in findings if item.category == "speed anomaly"]
    assert len(speed_findings) == 2
    assert all(item.confidence is None for item in speed_findings)
    assert all(0.0 <= item.score <= 1.0 for item in speed_findings)


def test_unobserved_interval_does_not_become_zero_distance() -> None:
    from src.intelligence.behavior_rest import extract_movement_features

    first = _obs(0)
    second = AISObservation(
        mmsi="123456789",
        latitude=25.01,
        longitude=-80.0,
        received_at=first.received_at,
        sog_knots=8.0,
        cog_degrees=90.0,
    )
    movement = extract_movement_features([first, second])
    assert movement.traveled_distance_km is None
    assert movement.trajectory_efficiency is None


def test_invalid_position_is_not_used_for_derived_distance() -> None:
    frame = enrich_track(
        track_to_frame(
            [
                _obs(0),
                AISObservation(
                    mmsi="123456789",
                    latitude=999.0,
                    longitude=-80.0,
                    received_at=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=60),
                    sog_knots=8.0,
                    cog_degrees=90.0,
                ),
            ]
        )
    )
    assert pd.isna(frame.loc[1, "distance_km"])
    assert pd.isna(frame.loc[1, "computed_speed_knots"])


def test_embedding_vector_rejects_gap_spanning_windows() -> None:
    track = [_obs(i) for i in range(32)]
    track[-1] = AISObservation(
        mmsi="123456789",
        latitude=25.031,
        longitude=-79.969,
        received_at=track[-2].received_at + timedelta(hours=1),
        sog_knots=8.0,
        cog_degrees=90.0,
    )
    assert trajectory_vector(track, length=32) is None
