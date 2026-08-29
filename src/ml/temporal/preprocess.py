"""Temporal sequence construction and scaling for real AIS tracks only."""
from __future__ import annotations

from typing import Iterable, Sequence

import numpy as np
import pandas as pd

from src.ingestion.models import AISObservation
from src.ml.temporal.types import (
    DEFAULT_SEQUENCE_LENGTH,
    MAX_TIME_DELTA_SECONDS,
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

    def fit(self, sequences: Sequence[np.ndarray]) -> TemporalSequenceScaler:
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
    def from_stats(cls, mean: np.ndarray, scale: np.ndarray) -> TemporalSequenceScaler:
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

    sog = frame["sog_knots"].to_numpy(dtype=np.float64) if "sog_knots" in frame.columns else np.zeros(len(frame))
    sog = np.where(np.isfinite(sog), sog, 0.0)
    sog = np.clip(sog, 0.0, 80.0)

    cog = frame["cog_degrees"].to_numpy(dtype=np.float64) if "cog_degrees" in frame.columns else np.zeros(len(frame))
    cog = np.where(np.isfinite(cog), cog, 0.0)
    cog = np.mod(cog, 360.0)
    cog_sin = np.sin(np.deg2rad(cog))
    cog_cos = np.cos(np.deg2rad(cog))

    delta_lat = np.zeros(len(frame), dtype=np.float64)
    delta_lon = np.zeros(len(frame), dtype=np.float64)
    delta_lat[1:] = np.diff(lat)
    delta_lon[1:] = np.diff(lon)

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
            delta_lat,
            delta_lon,
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
    n, f = mat.shape
    if n == target_length:
        return mat.astype(np.float32)
    if n == 1:
        return np.repeat(mat.astype(np.float32), target_length, axis=0)
    src_idx = np.linspace(0.0, n - 1, num=n)
    dst_idx = np.linspace(0.0, n - 1, num=target_length)
    out = np.empty((target_length, f), dtype=np.float64)
    for j in range(f):
        out[:, j] = np.interp(dst_idx, src_idx, mat[:, j])
    if not np.isfinite(out).all():
        raise ValueError("Non-finite values after interpolation.")
    return out.astype(np.float32)


def build_temporal_sequence(
    observations: Sequence[AISObservation] | Iterable[AISObservation],
    *,
    sequence_length: int = DEFAULT_SEQUENCE_LENGTH,
    minimum_points: int = MINIMUM_POINTS_PER_TRACK,
    mmsi: str | None = None,
) -> TemporalSequence | None:
    obs_list = list(observations)
    if len(obs_list) < minimum_points:
        return None
    mmsi_val = mmsi or str(obs_list[0].mmsi)
    try:
        frame = enrich_track(track_to_frame(obs_list))
    except Exception:
        return None
    if frame is None or len(frame) < minimum_points:
        return None
    mat = _build_feature_matrix(frame)
    if mat is None or mat.shape[0] < minimum_points:
        return None
    try:
        seq = _resample_to_length(mat, int(sequence_length))
    except Exception:
        return None
    if seq.shape != (sequence_length, FEATURE_DIM) or not np.isfinite(seq).all():
        return None
    return TemporalSequence(
        mmsi=str(mmsi_val),
        sequence=seq,
        sequence_length=int(sequence_length),
        feature_names=FEATURE_NAMES,
        n_source_points=int(mat.shape[0]),
    )


def build_temporal_sequences(
    tracks: dict[str, list[AISObservation]] | Sequence[tuple[str, list[AISObservation]]],
    *,
    sequence_length: int = DEFAULT_SEQUENCE_LENGTH,
    minimum_points: int = MINIMUM_POINTS_PER_TRACK,
) -> list[TemporalSequence]:
    if isinstance(tracks, dict):
        items = list(tracks.items())
    else:
        items = list(tracks)
    result: list[TemporalSequence] = []
    for mmsi, obs in items:
        seq = build_temporal_sequence(
            obs,
            sequence_length=sequence_length,
            minimum_points=minimum_points,
            mmsi=str(mmsi),
        )
        if seq is not None:
            result.append(seq)
    return result


def sequences_to_batch(sequences: Sequence[TemporalSequence]) -> np.ndarray:
    if not sequences:
        return np.zeros((0, DEFAULT_SEQUENCE_LENGTH, FEATURE_DIM), dtype=np.float32)
    arrays = [np.asarray(s.sequence, dtype=np.float32) for s in sequences]
    return np.stack(arrays, axis=0)
