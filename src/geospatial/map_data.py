"""Map-ready rows and lightweight geospatial helpers."""

from __future__ import annotations

from math import cos, radians, sin

from src.ingestion.models import AISObservation, VesselSnapshot


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
                "last_update": vessel.last_update,
                "stale": vessel.stale,
                "end_latitude": end_lat,
                "end_longitude": end_lon,
            }
        )
    return rows


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
        {"latitude": obs.latitude, "longitude": obs.longitude, "timestamp": obs.timestamp, "mmsi": obs.mmsi}
        for obs in sorted(observations, key=lambda item: item.timestamp)
    ]
