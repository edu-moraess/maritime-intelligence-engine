"""Sequential comparison of two vessels observed through real AIS data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import asin, cos, radians, sin, sqrt

from src.ingestion.models import AISObservation, VesselSnapshot


@dataclass(frozen=True)
class VesselSequenceMetrics:
    """Metrics derived only from the ordered observations of one vessel."""

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
    """Ordered, session-relative samples suitable for synchronized UI charts."""

    mmsi: str
    samples: tuple[dict[str, float | int | None], ...]
    metrics: VesselSequenceMetrics


def point_in_bbox(latitude: float, longitude: float, bbox: tuple[tuple[float, float], tuple[float, float]]) -> bool:
    """Return whether a vessel's current position belongs to a monitoring region."""
    (min_lat, min_lon), (max_lat, max_lon) = bbox
    return min_lat <= latitude <= max_lat and min_lon <= longitude <= max_lon


def vessels_in_bbox(vessels: list[VesselSnapshot], bbox: tuple[tuple[float, float], tuple[float, float]]) -> list[VesselSnapshot]:
    """Filter live vessel snapshots by their current geographic region."""
    return [vessel for vessel in vessels if point_in_bbox(vessel.latitude, vessel.longitude, bbox)]


def sequence_for_track(mmsi: str, track: list[AISObservation]) -> VesselSequence:
    """Build deterministic temporal metrics from a vessel's real AIS track."""
    ordered = sorted(track, key=lambda observation: observation.received_at)
    if not ordered:
        return VesselSequence(mmsi=mmsi, samples=(), metrics=VesselSequenceMetrics(
            mmsi=mmsi, points=0, duration_seconds=0.0, distance_nm=0.0,
            average_sog_knots=None, max_sog_knots=None, speed_change_knots=None,
            course_change_degrees=None, course_change_events=0,
            mean_sample_interval_seconds=None,
        ))

    samples: list[dict[str, float | int | None]] = []
    distances: list[float] = []
    intervals: list[float] = []
    course_changes: list[float] = []
    speed_values = [obs.sog_knots for obs in ordered if obs.sog_knots is not None]
    t0 = ordered[0].received_at

    previous = None
    for index, observation in enumerate(ordered):
        elapsed = (observation.received_at - t0).total_seconds()
        samples.append({
            "index": index,
            "elapsed_seconds": elapsed,
            "sog_knots": observation.sog_knots,
            "cog_degrees": observation.cog_degrees,
            "latitude": observation.latitude,
            "longitude": observation.longitude,
        })
        if previous is not None:
            interval = max(0.0, (observation.received_at - previous.received_at).total_seconds())
            intervals.append(interval)
            distances.append(_haversine_nm(previous.latitude, previous.longitude, observation.latitude, observation.longitude))
            if previous.cog_degrees is not None and observation.cog_degrees is not None:
                delta = _circular_delta(previous.cog_degrees, observation.cog_degrees)
                course_changes.append(delta)
        previous = observation

    course_events = sum(1 for change in course_changes if change >= 15.0)
    metrics = VesselSequenceMetrics(
        mmsi=mmsi,
        points=len(ordered),
        duration_seconds=max(0.0, (ordered[-1].received_at - ordered[0].received_at).total_seconds()),
        distance_nm=sum(distances),
        average_sog_knots=(sum(speed_values) / len(speed_values)) if speed_values else None,
        max_sog_knots=max(speed_values) if speed_values else None,
        speed_change_knots=(speed_values[-1] - speed_values[0]) if len(speed_values) >= 2 else None,
        course_change_degrees=sum(course_changes) if course_changes else None,
        course_change_events=course_events,
        mean_sample_interval_seconds=(sum(intervals) / len(intervals)) if intervals else None,
    )
    return VesselSequence(mmsi=mmsi, samples=tuple(samples), metrics=metrics)


def compare_sequences(track_a: list[AISObservation], track_b: list[AISObservation]) -> tuple[VesselSequence, VesselSequence]:
    """Return two session-relative sequences for synchronized comparison."""
    mmsi_a = track_a[0].mmsi if track_a else ""
    mmsi_b = track_b[0].mmsi if track_b else ""
    return sequence_for_track(mmsi_a, track_a), sequence_for_track(mmsi_b, track_b)


def _circular_delta(previous: float, current: float) -> float:
    return abs((current - previous + 180.0) % 360.0 - 180.0)


def _haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_nm = 3440.065
    phi1, phi2 = radians(lat1), radians(lat2)
    d_phi = radians(lat2 - lat1)
    d_lambda = radians(lon2 - lon1)
    a = sin(d_phi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(d_lambda / 2) ** 2
    return radius_nm * 2 * asin(min(1.0, sqrt(a)))
