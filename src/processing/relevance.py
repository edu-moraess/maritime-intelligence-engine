"""Operational relevance filtering for expensive vessel-model processing.

The filter is deliberately conservative: raw AIS observations remain in the
session store and historical sink. It only selects tracks that are useful
candidates for trajectory/temporal models.
"""

from __future__ import annotations

from math import asin, cos, radians, sin, sqrt
from typing import Sequence

from src.ingestion.models import AISObservation


DEFAULT_MIN_TRACK_POINTS = 2
DEFAULT_MIN_SPEED_KNOTS = 1.0
DEFAULT_MIN_DISPLACEMENT_KM = 0.25


def _distance_km(a: AISObservation, b: AISObservation) -> float:
    """Approximate great-circle distance between two real AIS positions."""
    lat1, lon1, lat2, lon2 = map(
        radians,
        (a.latitude, a.longitude, b.latitude, b.longitude),
    )
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    hav = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 6371.0088 * 2 * asin(min(1.0, sqrt(hav)))


def track_is_relevant(
    track: Sequence[AISObservation],
    *,
    min_track_points: int = DEFAULT_MIN_TRACK_POINTS,
    min_speed_knots: float = DEFAULT_MIN_SPEED_KNOTS,
    min_displacement_km: float = DEFAULT_MIN_DISPLACEMENT_KM,
) -> bool:
    """Return whether a track has enough movement information for model input.

    A track is retained when it has enough observations and demonstrates either
    meaningful AIS speed or measurable displacement. Tracks that only repeat a
    nearly stationary position are kept in the raw store but do not consume
    trajectory-model capacity.
    """
    if len(track) < min_track_points:
        return False
    if any(
        observation.sog_knots is not None
        and float(observation.sog_knots) >= min_speed_knots
        for observation in track
    ):
        return True
    ordered = sorted(track, key=lambda observation: observation.received_at)
    displacement = _distance_km(ordered[0], ordered[-1])
    return displacement >= min_displacement_km


def select_relevant_tracks(
    tracks: dict[str, list[AISObservation]],
    *,
    min_track_points: int = DEFAULT_MIN_TRACK_POINTS,
    min_speed_knots: float = DEFAULT_MIN_SPEED_KNOTS,
    min_displacement_km: float = DEFAULT_MIN_DISPLACEMENT_KM,
) -> dict[str, list[AISObservation]]:
    """Select model candidates while preserving the original track mapping."""
    return {
        mmsi: track
        for mmsi, track in tracks.items()
        if track_is_relevant(
            track,
            min_track_points=min_track_points,
            min_speed_knots=min_speed_knots,
            min_displacement_km=min_displacement_km,
        )
    }
