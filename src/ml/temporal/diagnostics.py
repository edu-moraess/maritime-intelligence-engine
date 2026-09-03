"""Diagnostics for the temporal quality of real AIS tracks.

This module measures source coverage and provides a conservative selector for
temporal model scales. It never fabricates observations or interpolates a
track unless the selected scale has enough real source points.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, median
from typing import Sequence

from src.ingestion.models import AISObservation
from src.ml.temporal.types import MAX_TRACK_GAP_SECONDS

DEFAULT_POINT_THRESHOLDS: tuple[int, ...] = (4, 8, 16, 32)
DEFAULT_WINDOW_LENGTHS: tuple[int, ...] = (8, 16, 32)
ADAPTIVE_SEQUENCE_LENGTHS: tuple[int, ...] = (32, 16, 8)


@dataclass(frozen=True)
class TemporalTrackDiagnostics:
    """Aggregate temporal coverage statistics for a collection of AIS tracks."""

    total_tracks: int = 0
    nonempty_tracks: int = 0
    point_counts: tuple[int, ...] = ()
    tracks_by_min_points: dict[int, int] | None = None
    median_points: float | None = None
    max_points: int = 0
    duration_seconds: tuple[float, ...] = ()
    median_duration_seconds: float | None = None
    max_duration_seconds: float | None = None
    interval_seconds: tuple[float, ...] = ()
    mean_interval_seconds: float | None = None
    median_interval_seconds: float | None = None
    max_interval_seconds: float | None = None
    gaps_over_threshold: int = 0
    max_gap_seconds: float | None = None
    sliding_windows: dict[int, int] | None = None
    non_overlapping_windows: dict[int, int] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "tracks_by_min_points", dict(self.tracks_by_min_points or {}))
        object.__setattr__(self, "sliding_windows", dict(self.sliding_windows or {}))
        object.__setattr__(self, "non_overlapping_windows", dict(self.non_overlapping_windows or {}))


def _clean_track(observations: Sequence[AISObservation]) -> list[AISObservation]:
    """Return valid observations ordered by trusted receive time."""
    return sorted(
        (obs for obs in observations if isinstance(obs, AISObservation) and obs.valid),
        key=lambda obs: obs.received_at,
    )


def _contiguous_segment_lengths(track: Sequence[AISObservation], gap_threshold_seconds: float) -> list[int]:
    if not track:
        return []
    threshold = max(0.0, float(gap_threshold_seconds))
    lengths = [1]
    for previous, current in zip(track, track[1:]):
        gap = (current.received_at - previous.received_at).total_seconds()
        if gap > threshold:
            lengths.append(1)
        else:
            lengths[-1] += 1
    return lengths


def analyze_temporal_tracks(
    tracks: dict[str, list[AISObservation]] | Sequence[tuple[str, list[AISObservation]]],
    *,
    point_thresholds: Sequence[int] = DEFAULT_POINT_THRESHOLDS,
    window_lengths: Sequence[int] = DEFAULT_WINDOW_LENGTHS,
    gap_threshold_seconds: float = MAX_TRACK_GAP_SECONDS,
) -> TemporalTrackDiagnostics:
    """Summarize temporal coverage without modifying the supplied tracks."""
    items = list(tracks.items()) if isinstance(tracks, dict) else list(tracks)
    thresholds = tuple(sorted({int(value) for value in point_thresholds if int(value) > 0}))
    lengths = tuple(sorted({int(value) for value in window_lengths if int(value) > 0}))
    gap_threshold = max(0.0, float(gap_threshold_seconds))

    point_counts: list[int] = []
    durations: list[float] = []
    intervals: list[float] = []
    gap_count = 0
    max_gap: float | None = None
    segment_lengths_by_track: list[list[int]] = []

    for _mmsi, observations in items:
        track = _clean_track(observations)
        if not track:
            continue
        n = len(track)
        point_counts.append(n)
        durations.append(max(0.0, float((track[-1].received_at - track[0].received_at).total_seconds())))
        segment_lengths = _contiguous_segment_lengths(track, gap_threshold)
        segment_lengths_by_track.append(segment_lengths)
        for previous, current in zip(track, track[1:]):
            delta = (current.received_at - previous.received_at).total_seconds()
            if delta < 0:
                continue
            delta = float(delta)
            intervals.append(delta)
            if delta > gap_threshold:
                gap_count += 1
                max_gap = delta if max_gap is None else max(max_gap, delta)

    by_threshold = {threshold: sum(n >= threshold for n in point_counts) for threshold in thresholds}
    sliding = {
        length: sum(max(0, segment_length - length + 1) for segments in segment_lengths_by_track for segment_length in segments)
        for length in lengths
    }
    non_overlapping = {
        length: sum(segment_length // length for segments in segment_lengths_by_track for segment_length in segments)
        for length in lengths
    }

    return TemporalTrackDiagnostics(
        total_tracks=len(items),
        nonempty_tracks=len(point_counts),
        point_counts=tuple(point_counts),
        tracks_by_min_points=by_threshold,
        median_points=median(point_counts) if point_counts else None,
        max_points=max(point_counts, default=0),
        duration_seconds=tuple(durations),
        median_duration_seconds=median(durations) if durations else None,
        max_duration_seconds=max(durations, default=None),
        interval_seconds=tuple(intervals),
        mean_interval_seconds=mean(intervals) if intervals else None,
        median_interval_seconds=median(intervals) if intervals else None,
        max_interval_seconds=max(intervals, default=None),
        gaps_over_threshold=gap_count,
        max_gap_seconds=max_gap,
        sliding_windows=sliding,
        non_overlapping_windows=non_overlapping,
    )


def select_adaptive_sequence_length(
    tracks: dict[str, list[AISObservation]] | Sequence[tuple[str, list[AISObservation]]],
    *,
    minimum_tracks: int,
    candidate_lengths: Sequence[int] = ADAPTIVE_SEQUENCE_LENGTHS,
) -> int | None:
    """Choose the longest scale supported by enough contiguous real AIS tracks."""
    items = list(tracks.items()) if isinstance(tracks, dict) else list(tracks)
    required = max(1, int(minimum_tracks))
    for length in sorted({int(value) for value in candidate_lengths if int(value) > 0}, reverse=True):
        eligible_vessels = 0
        for _mmsi, observations in items:
            track = _clean_track(observations)
            if max(_contiguous_segment_lengths(track, MAX_TRACK_GAP_SECONDS), default=0) >= length:
                eligible_vessels += 1
        if eligible_vessels >= required:
            return length
    return None
