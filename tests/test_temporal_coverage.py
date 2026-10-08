from datetime import datetime, timedelta, timezone

import numpy as np

from src.ingestion.models import AISObservation
from src.ml.temporal.calibration import HistoricalScoreBaseline, calibrate_anomaly
from src.ml.temporal.coverage import build_masked_windows, resample_track, stitch_track


def _obs(mmsi: str, seconds: int, lat: float = 25.7) -> AISObservation:
    return AISObservation(
        mmsi=mmsi,
        latitude=lat + seconds * 0.00001,
        longitude=-80.1 + seconds * 0.00001,
        received_at=datetime(2026, 10, 8, tzinfo=timezone.utc) + timedelta(seconds=seconds),
        sog_knots=10.0,
        cog_degrees=90.0,
        heading_degrees=90.0,
        ais_timestamp_second=seconds % 60,
    )


def test_stitch_track_breaks_only_after_five_minutes():
    observations = [_obs("123456789", 0), _obs("123456789", 240), _obs("123456789", 301)]
    segments = stitch_track(observations)
    assert [len(segment) for segment in segments] == [2, 1]


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
        0.5,
        baseline=baseline,
        persistent_windows=3,
    )
    assert result.percentile > 90
    assert result.baseline_threshold == 0.5
    assert result.alert is True
