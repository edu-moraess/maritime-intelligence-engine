"""Validation and quality metrics for real AIS observations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import asin, cos, isfinite, radians, sin, sqrt

from src.ingestion.models import AISObservation


# Operational thresholds are deliberately explicit and conservative. They are
# diagnostics, not claims that the underlying AIS message is fraudulent.
RECEIVE_GAP_SECONDS = 900
MAX_REALISTIC_SPEED_KMH = 100.0


@dataclass(frozen=True)
class QualityReport:
    messages_processed: int
    valid_records: int
    invalid_records: int
    duplicate_records: int
    missing_values: int
    receive_time_gaps: int
    invalid_mmsi: int
    impossible_speeds: int
    impossible_jumps: int
    stale_records: int
    distinct_vessels: int
    tracks_with_history: int
    quality_percent: float

    @property
    def coverage_status(self) -> str:
        if self.messages_processed == 0:
            return "WAITING"
        if self.tracks_with_history == 0:
            return "PARTIAL"
        return "READY"


def validate_observation(observation: AISObservation) -> list[str]:
    errors: list[str] = []
    if not observation.mmsi.isdigit() or len(observation.mmsi) != 9:
        errors.append("invalid_mmsi")
    if not isfinite(observation.latitude) or not -90 <= observation.latitude <= 90:
        errors.append("invalid_coordinates")
    if not isfinite(observation.longitude) or not -180 <= observation.longitude <= 180:
        errors.append("invalid_coordinates")
    if observation.sog_knots is not None and (
        not isfinite(observation.sog_knots) or not 0 <= observation.sog_knots <= 102.2
    ):
        errors.append("impossible_speed")
    if observation.cog_degrees is not None and (
        not isfinite(observation.cog_degrees) or not 0 <= observation.cog_degrees < 360
    ):
        errors.append("invalid_course")
    if observation.heading_degrees is not None and (
        not isfinite(observation.heading_degrees) or not 0 <= observation.heading_degrees < 360
    ):
        errors.append("invalid_heading")
    if not observation.valid:
        errors.append("provider_invalid")
    return errors


def _duplicate_key(observation: AISObservation) -> tuple[str, datetime, float, float]:
    """Build a stable duplicate key without depending on mutable raw payloads."""
    return (
        observation.mmsi,
        observation.received_at,
        observation.latitude,
        observation.longitude,
    )


def build_quality_report(
    observations: list[AISObservation],
    stale_after_seconds: int = 180,
    duplicate_records: int | None = None,
    reference_time: datetime | None = None,
) -> QualityReport:
    if not observations:
        return QualityReport(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 100.0)

    invalid = duplicate = missing = gaps = invalid_mmsi = 0
    impossible_speeds = impossible_jumps = stale = 0
    seen: set[tuple[str, datetime, float, float]] = set()
    by_mmsi: dict[str, list[AISObservation]] = {}
    now = reference_time or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("reference_time must be timezone-aware")
    now = now.astimezone(timezone.utc)

    for obs in observations:
        errors = validate_observation(obs)
        invalid += int(bool(errors))
        invalid_mmsi += int("invalid_mmsi" in errors)
        impossible_speeds += int("impossible_speed" in errors)
        missing += int(obs.sog_knots is None or obs.cog_degrees is None)

        key = _duplicate_key(obs)
        duplicate += int(key in seen)
        seen.add(key)

        age_seconds = (now - obs.received_at).total_seconds()
        stale += int(age_seconds > stale_after_seconds)
        by_mmsi.setdefault(obs.mmsi, []).append(obs)

    for track in by_mmsi.values():
        ordered = sorted(track, key=lambda item: item.received_at)
        for previous, current in zip(ordered, ordered[1:]):
            delta_seconds = (current.received_at - previous.received_at).total_seconds()
            if delta_seconds > RECEIVE_GAP_SECONDS:
                gaps += 1
            if delta_seconds <= 0:
                continue
            distance_km = haversine_km(
                previous.latitude,
                previous.longitude,
                current.latitude,
                current.longitude,
            )
            if distance_km / (delta_seconds / 3600) > MAX_REALISTIC_SPEED_KMH:
                impossible_jumps += 1

    if duplicate_records is not None:
        duplicate = max(duplicate, int(duplicate_records))

    distinct_vessels = len(by_mmsi)
    tracks_with_history = sum(1 for track in by_mmsi.values() if len(track) >= 2)
    valid_records = len(observations) - invalid

    # Coverage/readiness is intentionally excluded from the data-quality score.
    # A 30-second real AIS window with one repeated vessel is not "bad data";
    # it is simply insufficient for multi-track analysis.
    issue_rate = (
        invalid + duplicate + missing + gaps + impossible_jumps
    ) / max(1, len(observations))
    quality = max(0.0, min(100.0, 100.0 * (1.0 - issue_rate)))

    return QualityReport(
        messages_processed=len(observations),
        valid_records=valid_records,
        invalid_records=invalid,
        duplicate_records=duplicate,
        missing_values=missing,
        receive_time_gaps=gaps,
        invalid_mmsi=invalid_mmsi,
        impossible_speeds=impossible_speeds,
        impossible_jumps=impossible_jumps,
        stale_records=stale,
        distinct_vessels=distinct_vessels,
        tracks_with_history=tracks_with_history,
        quality_percent=quality,
    )


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth_radius_km = 6371.0088
    lat_delta = radians(lat2 - lat1)
    lon_delta = radians(lon2 - lon1)
    a = (
        sin(lat_delta / 2) ** 2
        + cos(radians(lat1))
        * cos(radians(lat2))
        * sin(lon_delta / 2) ** 2
    )
    return earth_radius_km * 2 * asin(sqrt(max(0.0, min(1.0, a))))
