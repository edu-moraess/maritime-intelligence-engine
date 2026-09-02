"""Sequence analytics for the optional dual-channel page.

This module is deliberately independent from AppSettings and MaritimeIntelligenceEngine.
It consumes only already-validated real AIS observations.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import asin, cos, radians, sin, sqrt

from src.ingestion.models import AISObservation, VesselSnapshot


@dataclass(frozen=True)
class VesselSequenceMetrics:
    mmsi: str
    points: int
    duration_seconds: float
    distance_nm: float
    average_sog_knots: float | None
    max_sog_knots: float | None
    speed_change_knots: float | None
    course_change_degrees: float | None
    course_change_events: int
    mean_sample_interval_seconds: float | None


@dataclass(frozen=True)
class VesselSequence:
    mmsi: str
    samples: list[dict[str, float | str | None]]
    metrics: VesselSequenceMetrics


def point_in_bbox(latitude: float, longitude: float, bbox: tuple[tuple[float, float], tuple[float, float]]) -> bool:
    (min_lat, min_lon), (max_lat, max_lon) = bbox
    return min_lat <= latitude <= max_lat and min_lon <= longitude <= max_lon


def vessels_in_bbox(
    vessels: list[VesselSnapshot],
    bbox: tuple[tuple[float, float], tuple[float, float]],
) -> list[VesselSnapshot]:
    return [vessel for vessel in vessels if point_in_bbox(vessel.latitude, vessel.longitude, bbox)]


def _haversine_nm(a: AISObservation, b: AISObservation) -> float:
    radius_nm = 3440.065
    lat1, lon1, lat2, lon2 = map(radians, (a.latitude, a.longitude, b.latitude, b.longitude))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    value = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * radius_nm * asin(sqrt(max(0.0, min(1.0, value))))


def _circular_delta(a: float, b: float) -> float:
    return abs((b - a + 180.0) % 360.0 - 180.0)


def sequence_for_track(mmsi: str, observations: list[AISObservation]) -> VesselSequence:
    ordered = sorted((obs for obs in observations if obs.mmsi == mmsi), key=lambda obs: obs.received_at)
    if not ordered:
        metrics = VesselSequenceMetrics(mmsi, 0, 0.0, 0.0, None, None, None, None, 0, None)
        return VesselSequence(mmsi, [], metrics)

    start: datetime = ordered[0].received_at
    samples: list[dict[str, float | str | None]] = []
    distance_nm = 0.0
    intervals: list[float] = []
    course_changes: list[float] = []
    speeds = [obs.sog_knots for obs in ordered if obs.sog_knots is not None]

    for index, obs in enumerate(ordered):
        elapsed = (obs.received_at - start).total_seconds()
        if index:
            previous = ordered[index - 1]
            distance_nm += _haversine_nm(previous, obs)
            intervals.append(max(0.0, (obs.received_at - previous.received_at).total_seconds()))
            if previous.cog_degrees is not None and obs.cog_degrees is not None:
                course_changes.append(_circular_delta(previous.cog_degrees, obs.cog_degrees))
        samples.append(
            {
                "elapsed_seconds": elapsed,
                "sog_knots": obs.sog_knots,
                "cog_degrees": obs.cog_degrees,
                "latitude": obs.latitude,
                "longitude": obs.longitude,
                "received_at": obs.received_at.isoformat(),
            }
        )

    duration = (ordered[-1].received_at - start).total_seconds()
    average_sog = sum(speeds) / len(speeds) if speeds else None
    max_sog = max(speeds) if speeds else None
    speed_change = None
    first_speed = ordered[0].sog_knots
    last_speed = ordered[-1].sog_knots
    if first_speed is not None and last_speed is not None:
        speed_change = last_speed - first_speed
    course_change = sum(course_changes) if course_changes else None
    metrics = VesselSequenceMetrics(
        mmsi=mmsi,
        points=len(ordered),
        duration_seconds=duration,
        distance_nm=distance_nm,
        average_sog_knots=average_sog,
        max_sog_knots=max_sog,
        speed_change_knots=speed_change,
        course_change_degrees=course_change,
        course_change_events=sum(1 for change in course_changes if change >= 15.0),
        mean_sample_interval_seconds=(sum(intervals) / len(intervals)) if intervals else None,
    )
    return VesselSequence(mmsi, samples, metrics)


def compare_sequences(first: VesselSequence, second: VesselSequence) -> dict[str, float | int | None]:
    return {
        "points_delta": first.metrics.points - second.metrics.points,
        "duration_delta_seconds": first.metrics.duration_seconds - second.metrics.duration_seconds,
        "distance_delta_nm": first.metrics.distance_nm - second.metrics.distance_nm,
        "average_sog_delta_knots": _delta(first.metrics.average_sog_knots, second.metrics.average_sog_knots),
        "max_sog_delta_knots": _delta(first.metrics.max_sog_knots, second.metrics.max_sog_knots),
        "speed_change_delta_knots": _delta(first.metrics.speed_change_knots, second.metrics.speed_change_knots),
        "course_change_delta_degrees": _delta(first.metrics.course_change_degrees, second.metrics.course_change_degrees),
        "course_events_delta": first.metrics.course_change_events - second.metrics.course_change_events,
    }


def _delta(first: float | None, second: float | None) -> float | None:
    if first is None or second is None:
        return None
    return first - second
