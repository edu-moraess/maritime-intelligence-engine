"""Multi-channel analytics isolated from the stable MIE core.

The module consumes only real AIS observations already produced by normal engines.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import asin, cos, radians, sin, sqrt

from src.ingestion.models import AISObservation, VesselSnapshot

RegionBBox = tuple[tuple[float, float], tuple[float, float]]


@dataclass(frozen=True)
class ChannelSnapshot:
    name: str
    bbox: RegionBBox
    observations: list[AISObservation]
    vessels: list[VesselSnapshot]
    findings: list[object]
    engine_snapshot: object


def point_in_bbox(latitude: float, longitude: float, bbox: RegionBBox) -> bool:
    (min_lat, min_lon), (max_lat, max_lon) = bbox
    return min_lat <= latitude <= max_lat and min_lon <= longitude <= max_lon


def filter_observations(observations: list[AISObservation], bbox: RegionBBox) -> list[AISObservation]:
    return [o for o in observations if point_in_bbox(o.latitude, o.longitude, bbox)]


def filter_vessels(vessels: list[VesselSnapshot], bbox: RegionBBox) -> list[VesselSnapshot]:
    return [v for v in vessels if point_in_bbox(v.latitude, v.longitude, bbox)]


def sequence_for_track(mmsi: str, observations: list[AISObservation]) -> list[dict[str, float | str | None]]:
    ordered = sorted((o for o in observations if o.mmsi == mmsi), key=lambda o: o.received_at)
    if not ordered:
        return []
    start: datetime = ordered[0].received_at
    samples: list[dict[str, float | str | None]] = []
    for obs in ordered:
        samples.append({
            "elapsed_seconds": (obs.received_at - start).total_seconds(),
            "sog_knots": obs.sog_knots,
            "cog_degrees": obs.cog_degrees,
            "latitude": obs.latitude,
            "longitude": obs.longitude,
            "received_at": obs.received_at.isoformat(),
        })
    return samples


def sequence_metrics(mmsi: str, observations: list[AISObservation]) -> dict[str, float | int | None]:
    ordered = sorted((o for o in observations if o.mmsi == mmsi), key=lambda o: o.received_at)
    if not ordered:
        return {"mmsi": mmsi, "points": 0, "duration_seconds": 0.0, "distance_nm": 0.0,
                "average_sog_knots": None, "max_sog_knots": None, "speed_change_knots": None,
                "course_change_degrees": None, "course_change_events": 0}
    speeds = [o.sog_knots for o in ordered if o.sog_knots is not None]
    distance = sum(_haversine_nm(a, b) for a, b in zip(ordered, ordered[1:]))
    course_changes = [_circular_delta(a.cog_degrees, b.cog_degrees)
                      for a, b in zip(ordered, ordered[1:])
                      if a.cog_degrees is not None and b.cog_degrees is not None]
    return {
        "mmsi": mmsi,
        "points": len(ordered),
        "duration_seconds": (ordered[-1].received_at - ordered[0].received_at).total_seconds(),
        "distance_nm": distance,
        "average_sog_knots": sum(speeds) / len(speeds) if speeds else None,
        "max_sog_knots": max(speeds) if speeds else None,
        "speed_change_knots": (ordered[-1].sog_knots - ordered[0].sog_knots)
        if ordered[0].sog_knots is not None and ordered[-1].sog_knots is not None else None,
        "course_change_degrees": sum(course_changes) if course_changes else None,
        "course_change_events": sum(change >= 15.0 for change in course_changes),
    }


def _haversine_nm(a: AISObservation, b: AISObservation) -> float:
    radius_nm = 3440.065
    lat1, lon1, lat2, lon2 = map(radians, (a.latitude, a.longitude, b.latitude, b.longitude))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    value = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * radius_nm * asin(sqrt(max(0.0, min(1.0, value))))


def _circular_delta(a: float, b: float) -> float:
    return abs((b - a + 180.0) % 360.0 - 180.0)
