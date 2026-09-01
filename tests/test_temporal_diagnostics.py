"""Focused tests for temporal track diagnostics."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.ingestion.models import AISObservation
from src.ml.temporal.diagnostics import analyze_temporal_tracks


def _track(mmsi: str, n: int, spacing_seconds: int = 30):
    base = datetime(2026, 9, 1, 20, 0, tzinfo=timezone.utc)
    return [
        AISObservation(
            mmsi,
            54.5 + i * 0.001,
            8.0 + i * 0.001,
            base + timedelta(seconds=i * spacing_seconds),
            sog_knots=8.0,
            cog_degrees=90.0,
        )
        for i in range(n)
    ]


def test_temporal_diagnostics_counts_thresholds_and_windows():
    tracks = {
        "111111111": _track("111111111", 4),
        "222222222": _track("222222222", 8),
        "333333333": _track("333333333", 16),
        "444444444": _track("444444444", 40),
        "555555555": [],
    }

    result = analyze_temporal_tracks(tracks)

    assert result.total_tracks == 5
    assert result.nonempty_tracks == 4
    assert result.tracks_by_min_points == {4: 4, 8: 3, 16: 2, 32: 1}
    assert result.median_points == 12.0
    assert result.max_points == 40
    assert result.sliding_windows == {8: 45, 16: 18, 32: 9}
    assert result.non_overlapping_windows == {8: 8, 16: 3, 32: 1}


def test_temporal_diagnostics_uses_received_time_and_detects_gaps():
    track = _track("123456789", 4, spacing_seconds=30)
    track[-1] = AISObservation(
        track[-1].mmsi,
        track[-1].latitude,
        track[-1].longitude,
        track[-1].received_at + timedelta(seconds=1000),
        sog_knots=track[-1].sog_knots,
        cog_degrees=track[-1].cog_degrees,
    )

    result = analyze_temporal_tracks({"123456789": track}, gap_threshold_seconds=900)

    assert result.median_duration_seconds == 1090.0
    assert result.mean_interval_seconds == (30 + 30 + 1030) / 3
    assert result.median_interval_seconds == 30.0
    assert result.max_interval_seconds == 1030.0
    assert result.gaps_over_threshold == 1
    assert result.max_gap_seconds == 1030.0


def test_temporal_diagnostics_ignores_invalid_observations_safely():
    track = _track("987654321", 4)
    invalid = AISObservation(
        track[0].mmsi,
        track[0].latitude,
        track[0].longitude,
        track[0].received_at + timedelta(seconds=15),
        valid=False,
    )

    result = analyze_temporal_tracks({"987654321": [track[0], invalid, *track[1:]]})

    assert result.total_tracks == 1
    assert result.nonempty_tracks == 1
    assert result.point_counts == (4,)
    assert result.tracks_by_min_points[4] == 1


def test_temporal_diagnostics_empty_input():
    result = analyze_temporal_tracks({})

    assert result.total_tracks == 0
    assert result.nonempty_tracks == 0
    assert result.median_points is None
    assert result.median_duration_seconds is None
    assert result.mean_interval_seconds is None
    assert result.sliding_windows == {8: 0, 16: 0, 32: 0}
