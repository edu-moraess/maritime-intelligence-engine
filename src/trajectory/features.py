"""Trajectory reconstruction and time-series features for real AIS tracks."""

from __future__ import annotations

from dataclasses import dataclass
from math import fmod
from typing import Iterable

import numpy as np
import pandas as pd

from src.ingestion.models import AISObservation
from src.processing.quality import haversine_km


@dataclass(frozen=True)
class TrajectorySummary:
    mmsi: str
    points: int
    duration_minutes: float
    distance_km: float
    average_speed_knots: float
    max_speed_knots: float
    average_heading_change: float
    dwell_ratio: float


def track_to_frame(observations: Iterable[AISObservation]) -> pd.DataFrame:
    rows = [obs.as_dict() for obs in observations]
    if not rows:
        return pd.DataFrame(columns=["mmsi", "timestamp", "latitude", "longitude", "sog_knots", "cog_degrees", "heading_degrees"])
    frame = pd.DataFrame(rows)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    return frame.sort_values("timestamp").reset_index(drop=True)


def enrich_track(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    result = frame.sort_values("timestamp").reset_index(drop=True).copy()
    result["time_delta_seconds"] = result["timestamp"].diff().dt.total_seconds().fillna(0).clip(lower=0)
    result["distance_km"] = [
        0.0,
        *[
            haversine_km(a, b, c, d)
            for a, b, c, d in zip(
                result["latitude"].iloc[:-1],
                result["longitude"].iloc[:-1],
                result["latitude"].iloc[1:],
                result["longitude"].iloc[1:],
            )
        ],
    ]
    result["computed_speed_knots"] = np.where(
        result["time_delta_seconds"] > 0,
        result["distance_km"] / (result["time_delta_seconds"] / 3600) / 1.852,
        0.0,
    )
    result["heading_change"] = _circular_difference(result["cog_degrees"].fillna(0).to_numpy())
    result["is_dwell"] = result["computed_speed_knots"] < 0.5
    return result


def summarize_track(observations: Iterable[AISObservation]) -> TrajectorySummary | None:
    frame = enrich_track(track_to_frame(observations))
    if frame.empty:
        return None
    duration = max(0.0, (frame["timestamp"].iloc[-1] - frame["timestamp"].iloc[0]).total_seconds() / 60)
    speeds = frame["sog_knots"].dropna()
    return TrajectorySummary(
        mmsi=str(frame["mmsi"].iloc[0]),
        points=len(frame),
        duration_minutes=duration,
        distance_km=float(frame["distance_km"].sum()),
        average_speed_knots=float(speeds.mean()) if not speeds.empty else 0.0,
        max_speed_knots=float(speeds.max()) if not speeds.empty else 0.0,
        average_heading_change=float(frame["heading_change"].mean()),
        dwell_ratio=float(frame["is_dwell"].mean()),
    )


def trajectory_vector(observations: Iterable[AISObservation], length: int = 32) -> np.ndarray | None:
    """Create a deterministic numeric representation; it is not a pretrained model."""
    frame = enrich_track(track_to_frame(observations))
    if len(frame) < 2:
        return None
    cols = ["latitude", "longitude", "sog_knots", "cog_degrees", "computed_speed_knots", "heading_change", "time_delta_seconds", "distance_km"]
    values = frame[cols].fillna(0.0).to_numpy(dtype=float)
    if len(values) != length:
        source = np.linspace(0.0, 1.0, len(values))
        target = np.linspace(0.0, 1.0, length)
        values = np.column_stack([np.interp(target, source, values[:, idx]) for idx in range(values.shape[1])])
    scale = np.nanstd(values, axis=0)
    values = (values - np.nanmean(values, axis=0)) / np.where(scale == 0, 1, scale)
    return values.astype(np.float32).ravel()


def _circular_difference(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    if len(values) == 0:
        return values
    diff = np.diff(values, prepend=values[0])
    return np.abs((diff + 180) % 360 - 180)
