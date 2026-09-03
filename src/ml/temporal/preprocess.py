"""Temporal sequence construction and scaling for real AIS tracks only."""
from __future__ import annotations

from typing import Iterable, Sequence

import numpy as np
import pandas as pd

from src.ingestion.models import AISObservation
from src.ml.temporal.types import (
    DEFAULT_SEQUENCE_LENGTH,
    MAX_TIME_DELTA_SECONDS,
    MAX_TRACK_GAP_SECONDS,
    MINIMUM_POINTS_PER_TRACK,
    TEMPORAL_FEATURE_NAMES,
    TemporalSequence,
)
from src.trajectory.features import enrich_track, track_to_frame

FEATURE_NAMES: tuple[str, ...] = TEMPORAL_FEATURE_NAMES
FEATURE_DIM: int = len(FEATURE_NAMES)
_EPS = 1e-9


class TemporalSequenceScaler:
    """Per-feature mean/std scaler. Fit only on training sequences."""

    def __init__(self) -> None:
        self.mean_: np.ndarray | None = None
        self.scale_: np.ndarray | None = None
        self.n_features_: int | None = None

    def fit(self, sequences: Sequence[np.ndarray]) -> "TemporalSequenceScaler":
        if not sequences:
            raise ValueError("Cannot fit scaler on empty sequence list.")
        stacked = np.concatenate([np.asarray(s, dtype=np.float64).reshape(-1, s.shape[-1]) for s in sequences], axis=0)
        if stacked.ndim != 2 or stacked.shape[0] == 0:
            raise ValueError("Invalid sequences for scaler fit.")
        if not np.isfinite(stacked).all():
            raise ValueError("Non-finite values in training sequences.")
        self.mean_ = stacked.mean(axis=0)
        std = stacked.std(axis=0)
        self.scale_ = np.where(std < _EPS, 1.0, std)
        self.n_features_ = int(stacked.shape[1])
        return self

    def transform(self, sequences: Sequence[np.ndarray]) -> np.ndarray:
        if self.mean_ is None or self.scale_ is None:
            raise RuntimeError("Scaler has not been fit.")
        out = []
        for s in sequences:
            arr = np.asarray(s, dtype=np.float64)
            if arr.ndim != 2 or arr.shape[1] != self.n_features_:
                raise ValueError(f"Expected (T, {self.n_features_}), got {arr.shape}")
            scaled = (arr - self.mean_) / self.scale_
            out.append(scaled.astype(np.float32))
        return np.stack(out, axis=0)

    def fit_transform(self, sequences: Sequence[np.ndarray]) -> np.ndarray:
        self.fit(sequences)
        return self.transform(sequences)

    @classmethod
    def from_stats(cls, mean: np.ndarray, scale: np.ndarray) -> "TemporalSequenceScaler":
        mean_a = np.asarray(mean, dtype=np.float64).reshape(-1)
        scale_a = np.asarray(scale, dtype=np.float64).reshape(-1)
        if mean_a.shape != scale_a.shape or mean_a.size == 0:
            raise ValueError("Invalid scaler stats.")
        if not np.isfinite(mean_a).all() or not np.isfinite(scale_a).all():
            raise ValueError("Non-finite scaler stats.")
        if (scale_a <= 0).any():
            raise ValueError("Scale must be positive.")
        obj = cls()
        obj.mean_ = mean_a
        obj.scale_ = scale_a
        obj.n_features_ = int(mean_a.size)
        return obj


def _circular_diff_degrees(values: np.ndarray) -> np.ndarray:
    v = np.asarray(values, dtype=np.float64)
    if v.size == 0:
        return v
    out = np.zeros_like(v)
    if v.size == 1:
        return out
    delta = np.diff(v)
    delta = (delta + 180.0) % 360.0 - 180.0
    out[1:] = delta
    return out


def _build_feature_matrix(frame: pd.DataFrame) -> np.ndarray | None:
    if frame is None or len(frame) < 2:
        return None
    lat = frame["latitude"].to_numpy(dtype=np.float64)
    lon = frame["longitude"].to_numpy(dtype=np.float64)
    if not np.isfinite(lat).all() or not np.isfinite(lon).all():
        return None
    if np.any(np.abs(lat) > 90.0) or np.any(np.abs(lon) > 180.0):
        return None

    lat_rad = np.deg2rad(lat)
    mean_lat_rad = float(np.mean(lat_rad))
    meters_per_degree_lat = 111_132.0
    meters_per_degree_lon = 111_320.0 * max(np.cos(mean_lat_rad), 1e-6)
    delta_lat_m = np.zeros(len(frame), dtype=np.float64)
    delta_lon_m = np.zeros(len(frame), dtype=np.float64)
    delta_lat_m[1:] = np.diff(lat) * meters_per_degree_lat
    delta_lon_m[1:] = np.diff(lon) * meters_per_degree_lon

    sog = frame["sog_knots"].to_numpy(dtype=np.float64) if "sog_knots" in frame.columns else np.zeros(len(frame))
    sog = np.where(np.isfinite(sog), sog, 0.0)
    sog = np.clip(sog, 0.0, 80.0)

    cog = frame["cog_degrees"].to_numpy(dtype=np.float64) if "cog_degrees" in frame.columns else np.zeros(len(frame))
    cog = np.where(np.isfinite(cog), cog, 0.0)
    cog = np.mod(cog, 360.0)
    cog_sin = np.sin(np.deg2rad(cog))
    cog_cos = np.cos(np.deg2rad(cog))

    computed_speed = (
        frame["computed_speed_knots"].to_numpy(dtype=np.float64)
        if "computed_speed_knots" in frame.columns
        else np.zeros(len(frame))
    )
    computed_speed = np.where(np.isfinite(computed_speed), computed_speed, 0.0)
    computed_speed = np.clip(computed_speed, 0.0, 80.0)

    heading_change = (
        frame["heading_change"].to_numpy(dtype=np.float64)
        if "heading_change" in frame.columns
        else _circular_diff_degrees(cog)
    )
    heading_change = np.where(np.isfinite(heading_change), heading_change, 0.0)
    heading_change = np.clip(heading_change, -180.0, 180.0)

    td = (
        frame["time_delta_seconds"].to_numpy(dtype=np.float64)
        if "time_delta_seconds" in frame.columns
        else np.zeros(len(frame))
    )
    td = np.where(np.isfinite(td), td, 0.0)
    td = np.clip(td, 0.0, MAX_TIME_DELTA_SECONDS)
    log_td = np.log1p(td)

    mat = np.column_stack(
        [
            delta_lat_m,
            delta_lon_m,
            sog,
            cog_sin,
            cog_cos,
            computed_speed,
            heading_change,
            log_td,
        ]
    ).astype(np.float64)
    if mat.shape[1] != FEATURE_DIM:
        return None
    if not np.isfinite(mat).all():
        return None
    return mat


def _resample_to_length(mat: np.ndarray, target_length: int) -> np.ndarray:
    """Select the latest contiguous real observations; never interpolate AIS."""
    n, _ = mat.shape
    if target_length < 1:
        raise ValueError("target_length must be >= 1")
    if n < target_length:
        raise ValueError("Cannot build temporal window without enough real observations.")
    return mat[-target_length:].astype(np.float32)


def _split_track_on_gaps(
    observations: Sequence[AISObservation],
    *,
    gap_threshold_seconds: float = MAX_TRACK_GAP_SECONDS,
) -> list[list[AISObservation]]:
    """Split chronologically ordered AIS into contiguous real-observation segments."""
    cleaned = sorted(
        (obs for obs in observations if isinstance(obs, AISObservation) and obs.valid),
        key=lambda obs: obs.received_at,
    )
    if not cleaned:
        return []
    threshold = max(0.0, float(gap_threshold_seconds))
    segments: list[list[AISObservation]] = [[cleaned[0]]]
    for obs in cleaned[1:]:
        previous = segments[-1][-1]
        gap = (obs.received_at - previous.received_at).total_seconds()
        if gap > threshold:
            segments.append([obs])
        else:
            segments[-1].append(obs)
    return segments


def _build_sequence_from_observations(
    observations: Sequence[AISObservation],
    *,
    sequence_length: int,
    minimum_points: int,
    mmsi: str,
) -> TemporalSequence | None:
    if len(observations) < minimum_points or len(observations) < sequence_length:
        return None
    try:
        frame = enrich_track(track_to_frame(observations))
    except Exception:
        return None
    if frame is None or len(frame) < minimum_points or len(frame) < sequence_length:
        return None
    window_frame = frame.iloc[-int(sequence_length):].copy()
    mat = _build_feature_matrix(window_frame)
    if mat is None or mat.shape[0] != sequence_length:
        return None
    try:
        seq = _resample_to_length(mat, int(sequence_length))
    except Exception:
        return None
    if seq.shape != (sequence_length, FEATURE_DIM) or not np.isfinite(seq).all():
        return None
    return TemporalSequence(
        mmsi=str(mmsi),
        sequence=seq,
        sequence_length=int(sequence_length),
        feature_names=FEATURE_NAMES,
        n_source_points=int(len(observations)),
    )


def build_temporal_sequence(
    observations: Sequence[AISObservation] | Iterable[AISObservation],
    *,
    sequence_length: int = DEFAULT_SEQUENCE_LENGTH,
    minimum_points: int = MINIMUM_POINTS_PER_TRACK,
    mmsi: str | None = None,
) -> TemporalSequence | None:
    """Build the latest valid window from one contiguous real-AIS segment."""
    obs_list = list(observations)
    mmsi_val = mmsi or (str(obs_list[0].mmsi) if obs_list else "")
    segments = _split_track_on_gaps(obs_list)
    if not segments:
        return None
    return _build_sequence_from_observations(
        segments[-1],
        sequence_length=int(sequence_length),
        minimum_points=int(minimum_points),
        mmsi=mmsi_val,
    )


def build_temporal_sequences(
    tracks: dict[str, list[AISObservation]] | Sequence[tuple[str, list[AISObservation]]],
    *,
    sequence_length: int = DEFAULT_SEQUENCE_LENGTH,
    minimum_points: int = MINIMUM_POINTS_PER_TRACK,
    max_windows_per_track: int = 8,
) -> list[TemporalSequence]:
    """Build multiple non-overlapping windows from contiguous real-AIS segments.

    Windows never cross a large receive-time gap and never overlap. Non-overlap
    avoids overweighting long tracks and keeps future train/validation grouping
    by MMSI meaningful. Only complete windows of real observations are emitted.
    """
    if isinstance(tracks, dict):
        items = list(tracks.items())
    else:
        items = list(tracks)
    result: list[TemporalSequence] = []
    window = int(sequence_length)
    minimum = int(minimum_points)
    cap = max(1, int(max_windows_per_track))
    for mmsi, obs in items:
        emitted = 0
        for segment in _split_track_on_gaps(obs):
            if len(segment) < max(window, minimum):
                continue
            # Keep the newest complete windows when a long segment exceeds the
            # cap. This preserves the most recent real operational context.
            starts = list(range(0, len(segment) - window + 1, window))
            if len(starts) > cap:
                starts = starts[-cap:]
            for start in starts:
                seq = _build_sequence_from_observations(
                    segment[start : start + window],
                    sequence_length=window,
                    minimum_points=minimum,
                    mmsi=str(mmsi),
                )
                if seq is not None:
                    result.append(seq)
                    emitted += 1
                    if emitted >= cap:
                        break
            if emitted >= cap:
                break
    return result


def sequences_to_batch(sequences: Sequence[TemporalSequence]) -> np.ndarray:
    if not sequences:
        return np.zeros((0, DEFAULT_SEQUENCE_LENGTH, FEATURE_DIM), dtype=np.float32)
    arrays = [np.asarray(s.sequence, dtype=np.float32) for s in sequences]
    return np.stack(arrays, axis=0)
