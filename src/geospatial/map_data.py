"""Map-ready rows and lightweight geospatial helpers."""

from __future__ import annotations

from math import cos, radians, sin
from typing import Sequence

from src.ingestion.models import AISObservation, VesselSnapshot

RegionBBox = tuple[tuple[float, float], tuple[float, float]]


def vessel_rows(vessels: list[VesselSnapshot]) -> list[dict]:
    rows: list[dict] = []
    for vessel in vessels:
        heading = vessel.heading_degrees if vessel.heading_degrees is not None else vessel.cog_degrees
        heading = float(heading) if heading is not None else None
        end_lat, end_lon = heading_endpoint(vessel.latitude, vessel.longitude, heading) if heading is not None else (None, None)
        rows.append(
            {
                "mmsi": vessel.mmsi,
                "name": vessel.vessel_name or "UNKNOWN VESSEL",
                "latitude": vessel.latitude,
                "longitude": vessel.longitude,
                "sog_knots": vessel.sog_knots,
                "cog_degrees": vessel.cog_degrees,
                "heading_degrees": heading,
                "last_received": vessel.last_received,
                "ais_timestamp_second": vessel.ais_timestamp_second,
                "observed_at": vessel.observed_at,
                "stale": vessel.stale,
                "end_latitude": end_lat,
                "end_longitude": end_lon,
            }
        )
    return rows


def live_vessel_rows(vessels: list[VesselSnapshot]) -> list[dict]:
    """Return only operationally live vessel targets without touching session history."""
    return vessel_rows([vessel for vessel in vessels if not vessel.stale])


def filter_rows_to_bboxes(rows: list[dict], bboxes: Sequence[RegionBBox]) -> list[dict]:
    """Keep map targets whose coordinates fall inside at least one monitoring box.

    This is a presentation guard for hydrated historical/session state. AISStream
    already applies the same geographic subscription, but persisted observations
    can outlive a subscription and must never make a dual-region map drift toward
    an unrelated location.
    """
    normalized = tuple(bboxes)
    if not normalized:
        return []
    return [
        row
        for row in rows
        if any(
            min_lat <= float(row["latitude"]) <= max_lat
            and min_lon <= float(row["longitude"]) <= max_lon
            for (min_lat, min_lon), (max_lat, max_lon) in normalized
        )
    ]


def heading_endpoint(latitude: float, longitude: float, heading: float, distance_degrees: float = 0.045) -> tuple[float, float]:
    """Return a short visual heading segment; it is not a navigation projection."""
    angle = radians(heading)
    end_lat = max(-90.0, min(90.0, latitude + distance_degrees * cos(angle)))
    lon_scale = max(0.1, cos(radians(latitude)))
    end_lon = max(-180.0, min(180.0, longitude + distance_degrees * sin(angle) / lon_scale))
    return end_lat, end_lon


def filter_viewport(rows: list[dict], min_lat: float, min_lon: float, max_lat: float, max_lon: float) -> list[dict]:
    return [
        row
        for row in rows
        if min_lat <= row["latitude"] <= max_lat and min_lon <= row["longitude"] <= max_lon
    ]


def selected_trail(observations: list[AISObservation]) -> list[dict]:
    return [
        {"latitude": obs.latitude, "longitude": obs.longitude, "received_at": obs.received_at, "mmsi": obs.mmsi}
        for obs in sorted(observations, key=lambda item: item.received_at)
    ]
