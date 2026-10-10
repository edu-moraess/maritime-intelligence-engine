from datetime import datetime, timedelta, timezone

import numpy as np

from src.ingestion.models import AISObservation
from src.ml.temporal.calibration import HistoricalScoreBaseline, calibrate_anomaly
from src.ml.temporal.coverage import build_masked_windows, resample_track, stitch_track
from src.ml.temporal.preprocess import build_temporal_sequences


def _obs(mmsi: str, seconds: int, lat: float = 25.7, sog: float = 10.0) -> AISObservation:
    return AISObservation(
        mmsi=mmsi,
        latitude=lat + seconds * 0.00001,
        longitude=-80.1 + seconds * 0.00001,
        received_at=datetime(2026, 10, 8, tzinfo=timezone.utc) + timedelta(seconds=seconds),
        sog_knots=sog,
        cog_degrees=90.0,
        heading_degrees=90.0,
        ais_timestamp_second=seconds % 60,
    )


def test_stitch_track_breaks_only_after_five_minutes():
    observations = [_obs("123456789", 0), _obs("123456789", 240), _obs("123456789", 301)]
    segments = stitch_track(observations)
    assert [len(segment) for segment in segments] == [3]


def test_resample_track_marks_long_missing_interval():
    observations = [_obs("123456789", 0), _obs("123456789", 60), _obs("123456789", 360)]
    track = resample_track(observations, interval_seconds=60, max_interpolation_gap_seconds=120)
    assert track is not None
    assert len(track.timestamps) == 7
    assert track.missing_fraction > 0
    assert track.mask[1] == 1
    assert track.mask[2] == 0


def test_masked_windows_allow_at_most_twenty_percent_missing():
    observations = [_obs("123456789", i * 60) for i in range(20)]
    track = resample_track(observations)
    assert track is not None
    windows = build_masked_windows(track, sequence_length=16, max_missing_fraction=0.20)
    assert windows
    values, mask = windows[0]
    assert values.shape[0] == 16
    assert mask.shape == (16,)
    assert np.isfinite(values).all()


def test_calibration_requires_percentile_absolute_threshold_and_persistence():
    baseline = HistoricalScoreBaseline([0.1, 0.2, 0.3, 0.4, 0.5])
    result = calibrate_anomaly(
        "123456789",
        0.6,
        baseline=baseline,
        persistent_windows=3,
    )
    assert result.percentile >= 99
    assert result.baseline_threshold == 0.5
    assert result.alert is True


def test_temporal_preprocess_can_build_t16_from_fixed_minute_grid():
    observations = [_obs("123456789", i * 60) for i in range(20)]
    sequences = build_temporal_sequences({"123456789": observations}, sequence_length=16)
    assert sequences
    assert sequences[0].sequence.shape == (16, 8)
    assert sequences[0].mask is not None


def test_resampled_windows_are_non_overlapping_and_keep_newest_cap():
    observations = [_obs("123456789", i * 60, sog=float(i)) for i in range(80)]
    sequences = build_temporal_sequences(
        {"123456789": observations}, sequence_length=10, max_windows_per_track=3
    )

    assert len(sequences) == 3
    starts = [float(sequence.sequence[0, 2]) for sequence in sequences]
    np.testing.assert_allclose(starts, [50.0, 60.0, 70.0], atol=1e-5)
    for sequence, start in zip(sequences, [50.0, 60.0, 70.0]):
        np.testing.assert_allclose(
            sequence.sequence[:, 2], np.arange(start, start + 10.0), atol=1e-5
        )


def test_temporal_windows_reject_and_split_at_invalid_interpolation_gaps():
    # A 180-second outage is below the old 300-second stitching limit but
    # above the 120-second interpolation-validity limit.
    observations = [
        _obs("123456789", i * 60, sog=float(i))
        if i < 3
        else _obs("123456789", (i + 2) * 60, sog=float(i))
        for i in range(80)
    ]

    sequences = build_temporal_sequences(
        {"123456789": observations},
        sequence_length=32,
        max_windows_per_track=10,
    )

    assert sequences, "The continuous post-gap segment should still yield windows."
    assert all(sequence.mask is not None for sequence in sequences)
    assert all(np.all(np.asarray(sequence.mask) == 1.0) for sequence in sequences)
    # The first three observations are too short to form a 32-step window;
    # every returned window must come from the continuous segment after the gap.
    assert all(float(sequence.sequence[0, 2]) >= 3.0 for sequence in sequences)
