"""Domain models for real AIS observations and derived session state."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


IngestionState = Literal["DISCONNECTED", "CONNECTING", "LIVE AIS", "REAL AIS DATA UNAVAILABLE"]
VALID_INGESTION_STATES = {"DISCONNECTED", "CONNECTING", "LIVE AIS", "REAL AIS DATA UNAVAILABLE"}


@dataclass(frozen=True)
class AISObservation:
    """A validated real AIS PositionReport with explicit temporal semantics.

    ``received_at`` is when the MIE received/processed the frame. The AIS
    ``Timestamp`` is retained separately as ``ais_timestamp_second`` and is
    never promoted to an absolute datetime. ``observed_at`` remains ``None``
    unless a trusted absolute observation-time source is added in the future.
    """

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
            # AIS 60–63 are special states; raw keeps the provider value for audit.
            object.__setattr__(self, "ais_timestamp_second", None)

    def as_dict(self) -> dict[str, Any]:
        return {
            "mmsi": self.mmsi,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "received_at": self.received_at.astimezone(timezone.utc).isoformat(),
            "ais_timestamp_second": self.ais_timestamp_second,
            "observed_at": self.observed_at.astimezone(timezone.utc).isoformat() if self.observed_at is not None else None,
            "sog_knots": self.sog_knots,
            "cog_degrees": self.cog_degrees,
            "heading_degrees": self.heading_degrees,
            "vessel_name": self.vessel_name,
            "message_type": self.message_type,
            "valid": self.valid,
            "navigational_status": self.navigational_status,
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


@dataclass(frozen=True)
class AnomalyFinding:
    mmsi: str
    received_at: datetime
    latitude: float
    longitude: float
    score: float
    category: str
    confidence: float
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
