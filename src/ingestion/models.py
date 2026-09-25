"""Domain models for real AIS observations and derived session state."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


IngestionState = Literal[
    "DISCONNECTED",
    "CONNECTING",
    "LIVE AIS",
    "REAL AIS DATA UNAVAILABLE",
]

VALID_INGESTION_STATES = {
    "DISCONNECTED",
    "CONNECTING",
    "LIVE AIS",
    "REAL AIS DATA UNAVAILABLE",
}

_MMSI_PATTERN = re.compile(r"^\d{9}$")


def is_valid_mmsi(value: object) -> bool:
    """Return True only for a standard 9-digit numeric AIS MMSI."""
    return isinstance(value, str) and _MMSI_PATTERN.fullmatch(value) is not None


@dataclass(frozen=True)
class AISObservation:
    """A validated real AIS PositionReport with explicit temporal semantics."""

    mmsi: str
    latitude: float
    longitude: float
    received_at: datetime
    sog_knots: float | None = None
    cog_degrees: float | None = None
    heading_degrees: float | None = None
    vessel_name: str | None = None
    message_type: str = "PositionReport"
    valid: bool = True
    navigational_status: int | None = None
    ais_timestamp_second: int | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)
    observed_at: datetime | None = None

    def __post_init__(self) -> None:
        if not is_valid_mmsi(self.mmsi):
            raise ValueError(f"Invalid AIS MMSI: {self.mmsi!r}. Expected exactly 9 numeric digits.")
        if self.received_at.tzinfo is None or self.received_at.utcoffset() is None:
            raise ValueError("received_at must be timezone-aware")
        object.__setattr__(self, "received_at", self.received_at.astimezone(timezone.utc))
        if self.observed_at is not None:
            if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
                raise ValueError("observed_at must be timezone-aware when provided")
            object.__setattr__(self, "observed_at", self.observed_at.astimezone(timezone.utc))
        if self.ais_timestamp_second is not None and (
            isinstance(self.ais_timestamp_second, bool)
            or not isinstance(self.ais_timestamp_second, int)
            or not 0 <= self.ais_timestamp_second <= 59
        ):
            object.__setattr__(self, "ais_timestamp_second", None)

    def as_dict(self) -> dict[str, Any]:
        return {
            "mmsi": self.mmsi,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "received_at": self.received_at.astimezone(timezone.utc).isoformat(),
            "ais_timestamp_second": self.ais_timestamp_second,
            "observed_at": self.observed_at.astimezone(timezone.utc).isoformat() if self.observed_at else None,
            "sog_knots": self.sog_knots,
            "cog_degrees": self.cog_degrees,
            "heading_degrees": self.heading_degrees,
            "vessel_name": self.vessel_name,
            "message_type": self.message_type,
            "valid": self.valid,
            "navigational_status": self.navigational_status,
        }


@dataclass(frozen=True)
class EnvironmentalObservation:
    """A real external environmental observation for maritime context."""

    source: str
    observed_at: datetime
    latitude: float
    longitude: float
    region: str | None = None
    wave_height_m: float | None = None
    wave_direction_deg: float | None = None
    wave_period_s: float | None = None
    wind_wave_height_m: float | None = None
    swell_height_m: float | None = None
    swell_direction_deg: float | None = None
    ocean_current_velocity: float | None = None
    ocean_current_direction_deg: float | None = None
    sea_surface_temperature_c: float | None = None

    def __post_init__(self) -> None:
        if not self.source.strip():
            raise ValueError("source must not be empty")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        object.__setattr__(self, "observed_at", self.observed_at.astimezone(timezone.utc))
        if not -90.0 <= self.latitude <= 90.0:
            raise ValueError("latitude must be between -90 and 90 degrees")
        if not -180.0 <= self.longitude <= 180.0:
            raise ValueError("longitude must be between -180 and 180 degrees")
        for name in (
            "wave_height_m",
            "wave_period_s",
            "wind_wave_height_m",
            "swell_height_m",
            "ocean_current_velocity",
        ):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"{name} must be non-negative")
        for name in (
            "wave_direction_deg",
            "swell_direction_deg",
            "ocean_current_direction_deg",
        ):
            value = getattr(self, name)
            if value is not None and not 0.0 <= value <= 360.0:
                raise ValueError(f"{name} must be between 0 and 360 degrees")

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "observed_at": self.observed_at.astimezone(timezone.utc).isoformat(),
            "latitude": self.latitude,
            "longitude": self.longitude,
            "region": self.region,
            "wave_height_m": self.wave_height_m,
            "wave_direction_deg": self.wave_direction_deg,
            "wave_period_s": self.wave_period_s,
            "wind_wave_height_m": self.wind_wave_height_m,
            "swell_height_m": self.swell_height_m,
            "swell_direction_deg": self.swell_direction_deg,
            "ocean_current_velocity": self.ocean_current_velocity,
            "ocean_current_direction_deg": self.ocean_current_direction_deg,
            "sea_surface_temperature_c": self.sea_surface_temperature_c,
        }


@dataclass
class VesselSnapshot:
    mmsi: str
    latitude: float
    longitude: float
    last_received: datetime
    sog_knots: float | None
    cog_degrees: float | None
    heading_degrees: float | None
    vessel_name: str | None
    message_count: int
    stale: bool = False
    ais_timestamp_second: int | None = None
    observed_at: datetime | None = None
    ship_type: int | None = None


@dataclass(frozen=True)
class IngestionStatus:
    state: IngestionState
    reason: str
    connected_at: datetime | None
    last_received_at: datetime | None
    messages_received: int
    active_vessels: int
    latency_seconds: float | None
    websocket_status: str
    ais_timestamp_second: int | None = None
    frames_received: int = 0
    position_reports_received: int = 0
    position_reports_accepted: int = 0
    parse_errors: int = 0
    non_position_frames: int = 0
    reconnect_attempts: int = 0
    last_disconnect_at: datetime | None = None
    last_reconnect_at: datetime | None = None
    last_error: str | None = None


@dataclass(frozen=True)
class AnomalyFinding:
    mmsi: str
    received_at: datetime
    latitude: float
    longitude: float
    score: float
    category: str
    confidence: float | None
    explanation: str
    ais_timestamp_second: int | None = None


@dataclass(frozen=True)
class SimilarTrack:
    mmsi: str
    first_received_at: datetime | None
    region: str
    cluster: int
    similarity: float
    source_label: str = "REAL AIS SESSION"
