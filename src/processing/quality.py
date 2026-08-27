"""Validation and quality metrics for real AIS observations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite

from src.ingestion.models import AISObservation


@dataclass(frozen=True)
class QualityReport:
    messages_processed: int
    invalid_records: int
    duplicate_records: int
    missing_values: int
    timestamp_gaps: int
    invalid_mmsi: int
    impossible_speeds: int
    impossible_jumps: int
    stale_records: int
    quality_percent: float


def validate_observation(observation: AISObservation) -> list[str]:
    errors: list[str] = []
    if not observation.mmsi.isdigit() or len(observation.mmsi) != 9:
        errors.append("invalid_mmsi")
    if not isfinite(observation.latitude) or not -90 <= observation.latitude <= 90:
        errors.append("invalid_coordinates")
    if not isfinite(observation.longitude) or not -180 <= observation.longitude <= 180:
        errors.append("invalid_coordinates")
    if observation.sog_knots is not None and (not isfinite(observation.sog_knots) or not 0 <= observation.sog_knots <= 102.2):
        errors.append("impossible_speed")
    if observation.cog_degrees is not None and (not isfinite(observation.cog_degrees) or not 0 <= observation.cog_degrees < 360):
        errors.append("invalid_course")
    if observation.heading_degrees is not None and (not isfinite(observation.heading_degrees) or not 0 <= observation.heading_degrees < 360):
        errors.append("invalid_heading")
    if not observation.valid:
        errors.append("provider_invalid")
    return errors


def build_quality_report(observations: list[AISObservation], stale_after_seconds: int = 180, duplicate_records: int | None = None) -> QualityReport:
    if not observations:
        return QualityReport(0, 0, 0, 0, 0, 0, 0, 0, 0, 100.0)
    invalid = duplicate = missing = gaps = invalid_mmsi = impossible_speeds = impossible_jumps = stale = 0
    seen: set[tuple[str, datetime, float, float]] = set()
    by_mmsi: dict[str, list[AISObservation]] = {}
    now = datetime.now(timezone.utc)
    for obs in observations:
        errors = validate_observation(obs)
        invalid += int(bool(errors))
        invalid_mmsi += int("invalid_mmsi" in errors)
        impossible_speeds += int("impossible_speed" in errors)
        missing += int(obs.sog_knots is None or obs.cog_degrees is None)
        key = (obs.mmsi, obs.timestamp, obs.latitude, obs.longitude)
        duplicate += int(key in seen)
        seen.add(key)
        stale += int((now - obs.timestamp).total_seconds() > stale_after_seconds)
        by_mmsi.setdefault(obs.mmsi, []).append(obs)
    for track in by_mmsi.values():
        ordered = sorted(track, key=lambda item: item.timestamp)
        for previous, current in zip(ordered, ordered[1:]):
            delta_seconds = (current.timestamp - previous.timestamp).total_seconds()
            if delta_seconds > 900:
                gaps += 1
            distance_km = haversine_km(previous.latitude, previous.longitude, current.latitude, current.longitude)
            if delta_seconds > 0 and distance_km / (delta_seconds / 3600) > 100:
                impossible_jumps += 1
    if duplicate_records is not None:
        duplicate = max(duplicate, int(duplicate_records))
    total_issues = invalid + duplicate + missing + gaps + impossible_jumps
    quality = max(0.0, 100.0 * (1.0 - total_issues / max(1, len(observations))))
    return QualityReport(
        messages_processed=len(observations),
        invalid_records=invalid,
        duplicate_records=duplicate,
        missing_values=missing,
        timestamp_gaps=gaps,
        invalid_mmsi=invalid_mmsi,
        impossible_speeds=impossible_speeds,
        impossible_jumps=impossible_jumps,
        stale_records=stale,
        quality_percent=quality,
    )


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    from math import asin, cos, radians, sin, sqrt

    earth_radius_km = 6371.0088
    lat_delta = radians(lat2 - lat1)
    lon_delta = radians(lon2 - lon1)
    a = sin(lat_delta / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(lon_delta / 2) ** 2
    return earth_radius_km * 2 * asin(sqrt(max(0.0, min(1.0, a))))
