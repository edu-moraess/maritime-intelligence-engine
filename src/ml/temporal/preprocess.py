"""Temporal sequence construction and scaling for real AIS tracks only."""
from __future__ import annotations

from typing import Iterable, Sequence

import numpy as np
import pandas as pd

from src.ingestion.models import AISObservation
from src.ml.temporal.types import (
    DEFAULT_SEQUENCE_LENGTH,
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


def _build_feature_matrix(frame: pd.DataFrame) -> np.ndarray | None:
    """Build transition features without imputing absent AIS attributes.

    Each output row represents a transition between two real reports. The
    first report is only the origin of the transition and therefore does not
    receive fabricated zero deltas.
    """
    if frame is None or len(frame) < 2:
        return None
    required = ("latitude", "longitude", "sog_knots", "cog_degrees", "time_delta_seconds")
    if any(column not in frame.columns for column in required):
        return None

    lat = frame["latitude"].to_numpy(dtype=np.float64)
    lon = frame["longitude"].to_numpy(dtype=np.float64)
    sog = frame["sog_knots"].to_numpy(dtype=np.float64)
    cog = frame["cog_degrees"].to_numpy(dtype=np.float64)
    td = frame["time_delta_seconds"].to_numpy(dtype=np.float64)

    if not all(np.isfinite(values).all() for values in (lat, lon, sog, cog)):
        return None
    if np.any(np.abs(lat) > 90.0) or np.any(np.abs(lon) > 180.0):
        return None
    if np.any((sog < 0.0) | (sog > 102.2)) or np.any((cog < 0.0) | (cog >= 360.0)):
        return None
    if not np.isfinite(td[1:]).all() or np.any(td[1:] <= 0.0):
        return None
    if np.any(td[1:] > MAX_TRACK_GAP_SECONDS):
        return None

    meters_per_degree_lat = 111_132.0
    mean_lat_rad = float(np.mean(np.deg2rad(lat)))
    meters_per_degree_lon = 111_320.0 * max(np.cos(mean_lat_rad), 1e-6)
    delta_lat_m = np.diff(lat) * meters_per_degree_lat
    delta_lon_m = np.diff(lon) * meters_per_degree_lon
    distance_km = np.asarray(
        [
            _haversine_km_pair(lat[i], lon[i], lat[i + 1], lon[i + 1])
            for i in range(len(lat) - 1)
        ],
        dtype=np.float64,
    )
    computed_speed = distance_km / (td[1:] / 3600.0) / 1.852
    course_delta = _circular_diff_degrees(cog)[1:]
    log_td = np.log1p(td[1:])

    mat = np.column_stack(
        [
            delta_lat_m,
            delta_lon_m,
            sog[1:],
            np.sin(np.deg2rad(cog[1:])),
            np.cos(np.deg2rad(cog[1:])),
            computed_speed,
            course_delta,
            log_td,
        ]
    ).astype(np.float64)
    if mat.shape != (len(frame) - 1, FEATURE_DIM) or not np.isfinite(mat).all():
        return None
    return mat


def _haversine_km_pair(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth_radius_km = 6371.0088
    lat_delta = np.deg2rad(lat2 - lat1)
    lon_delta = np.deg2rad(lon2 - lon1)
    a = (
        np.sin(lat_delta / 2.0) ** 2
        + np.cos(np.deg2rad(lat1))
        * np.cos(np.deg2rad(lat2))
        * np.sin(lon_delta / 2.0) ** 2
    )
    return float(earth_radius_km * 2.0 * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0))))


def _circular_diff_degrees(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64)
    if values.size < 2 or not np.isfinite(values).all():
        return np.array([], dtype=np.float64)
    delta = np.diff(values)
    return np.abs((delta + 180.0) % 360.0 - 180.0)


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
    if len(observations) < minimum_points or len(observations) < sequence_length + 1:
        return None
    try:
        frame = enrich_track(track_to_frame(observations))
    except Exception:
        return None
    if frame is None or len(frame) < minimum_points or len(frame) < sequence_length:
        return None
    window_frame = frame.iloc[-(int(sequence_length) + 1):].copy()
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
    """Build windows from contiguous real-AIS transitions.

    Each window requires N+1 real reports to represent N transitions. Adjacent
    windows may share one endpoint report, but never interpolate, duplicate,
    or fabricate an AIS observation.
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
        # Visit newest segments and newest complete windows first. This makes
        # the per-track cap preserve the most recent real operational context.
        collected: list[TemporalSequence] = []
        for segment in reversed(_split_track_on_gaps(obs)):
            if len(segment) < max(window + 1, minimum):
                continue
            # Anchor windows at the segment end; only the oldest remainder can
            # be excluded when the segment length is not divisible by window.
            for end in range(len(segment), window, -window):
                if len(collected) >= cap:
                    break
                start = end - (window + 1)
                if start < 0:
                    continue
                seq = _build_sequence_from_observations(
                    segment[start:end],
                    sequence_length=window,
                    minimum_points=minimum,
                    mmsi=str(mmsi),
                )
                if seq is not None:
                    collected.append(seq)
            if len(collected) >= cap:
                break
        result.extend(reversed(collected))
    return result


def sequences_to_batch(sequences: Sequence[TemporalSequence]) -> np.ndarray:
    if not sequences:
        return np.zeros((0, DEFAULT_SEQUENCE_LENGTH, FEATURE_DIM), dtype=np.float32)
    arrays = [np.asarray(s.sequence, dtype=np.float32) for s in sequences]
    return np.stack(arrays, axis=0)
