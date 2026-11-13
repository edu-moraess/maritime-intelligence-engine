"""Trajectory reconstruction and time-series features for real AIS tracks."""

from __future__ import annotations

from dataclasses import dataclass
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
    distance_km: float | None
    average_speed_knots: float | None
    max_speed_knots: float | None
    average_heading_change: float | None
    dwell_ratio: float | None


def track_to_frame(observations: Iterable[AISObservation]) -> pd.DataFrame:
    rows = [obs.as_dict() for obs in observations]
    if not rows:
        return pd.DataFrame(columns=["mmsi", "received_at", "latitude", "longitude", "sog_knots", "cog_degrees", "heading_degrees"])
    frame = pd.DataFrame(rows)
    frame["received_at"] = pd.to_datetime(frame["received_at"], utc=True)
    return frame.sort_values("received_at").reset_index(drop=True)


def enrich_track(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    result = frame.sort_values("received_at").reset_index(drop=True).copy()
    result["time_delta_seconds"] = result["received_at"].diff().dt.total_seconds().clip(lower=0)
    distances = [
        np.nan,
        *[
            _distance_if_valid(a, b, c, d)
            for a, b, c, d in zip(
                result["latitude"].iloc[:-1],
                result["longitude"].iloc[:-1],
                result["latitude"].iloc[1:],
                result["longitude"].iloc[1:],
            )
        ],
    ]
    result["distance_km"] = distances
    valid_delta = result["time_delta_seconds"].gt(0)
    result["computed_speed_knots"] = (
        result["distance_km"] / (result["time_delta_seconds"] / 3600) / 1.852
    ).where(valid_delta)
    result["heading_change"] = _circular_difference(
        result["cog_degrees"].to_numpy(dtype=float)
    )
    result["is_dwell"] = result["computed_speed_knots"].lt(0.5).where(
        result["computed_speed_knots"].notna(), pd.NA
    )
    return result


def _distance_if_valid(lat1, lon1, lat2, lon2) -> float:
    try:
        a, b, c, d = (float(value) for value in (lat1, lon1, lat2, lon2))
    except (TypeError, ValueError):
        return np.nan
    if not all(np.isfinite(value) for value in (a, b, c, d)):
        return np.nan
    if not (-90.0 <= a <= 90.0 and -90.0 <= c <= 90.0):
        return np.nan
    if not (-180.0 <= b <= 180.0 and -180.0 <= d <= 180.0):
        return np.nan
    return haversine_km(a, b, c, d)


def summarize_track(observations: Iterable[AISObservation]) -> TrajectorySummary | None:
    frame = enrich_track(track_to_frame(observations))
    if frame.empty:
        return None
    duration = max(0.0, (frame["received_at"].iloc[-1] - frame["received_at"].iloc[0]).total_seconds() / 60)
    speeds = frame["sog_knots"].where(
        frame["sog_knots"].between(0.0, 102.2)
    ).dropna()
    return TrajectorySummary(
        mmsi=str(frame["mmsi"].iloc[0]),
        points=len(frame),
        duration_minutes=duration,
        distance_km=float(frame["distance_km"].sum(min_count=1)) if frame["distance_km"].notna().any() else None,
        average_speed_knots=float(speeds.mean()) if not speeds.empty else None,
        max_speed_knots=float(speeds.max()) if not speeds.empty else None,
        average_heading_change=float(frame["heading_change"].mean()) if frame["heading_change"].notna().any() else None,
        dwell_ratio=float(frame["is_dwell"].dropna().mean()) if frame["is_dwell"].notna().any() else None,
    )


def trajectory_vector(observations: Iterable[AISObservation], length: int = 32) -> np.ndarray | None:
    """Encode only an exact window of complete, observed AIS rows.

    No missing-value filling, temporal interpolation, or synthetic padding is
    permitted. Tracks without enough complete source reports are not embedded.
    """
    if length < 2:
        raise ValueError("length must be >= 2")
    frame = track_to_frame(
        observation for observation in observations
        if isinstance(observation, AISObservation) and observation.valid
    )
    columns = ["latitude", "longitude", "sog_knots", "cog_degrees"]
    if len(frame) < length or any(column not in frame for column in columns):
        return None
    values = frame[columns].tail(length).to_numpy(dtype=float)
    if not np.isfinite(values).all():
        return None
    lat, lon, sog, cog = values.T
    if np.any(np.abs(lat) > 90.0) or np.any(np.abs(lon) > 180.0):
        return None
    if np.any((sog < 0.0) | (sog > 102.2)) or np.any((cog < 0.0) | (cog >= 360.0)):
        return None
    scale = values.std(axis=0)
    normalized = (values - values.mean(axis=0)) / np.where(scale < 1e-9, 1.0, scale)
    return normalized.astype(np.float32).ravel()


def _circular_difference(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    result = np.full(values.shape, np.nan, dtype=float)
    if len(values) < 2:
        return result
    previous, current = values[:-1], values[1:]
    valid = (
        np.isfinite(previous) & np.isfinite(current)
        & (previous >= 0.0) & (previous < 360.0)
        & (current >= 0.0) & (current < 360.0)
    )
    delta = (current[valid] - previous[valid] + 180.0) % 360.0 - 180.0
    result[np.flatnonzero(valid) + 1] = np.abs(delta)
    return result
