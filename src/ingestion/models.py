"""Canonical models for observations received from real AIS providers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


IngestionState = Literal["DISCONNECTED", "CONNECTING", "LIVE AIS", "REAL AIS DATA UNAVAILABLE"]
VALID_INGESTION_STATES = {"DISCONNECTED", "CONNECTING", "LIVE AIS", "REAL AIS DATA UNAVAILABLE"}


@dataclass(frozen=True)
class AISObservation:
    mmsi: str
    latitude: float
    longitude: float
    # Timestamp when the server ingested the frame; AIS Timestamp is only the UTC second within a minute.
    timestamp: datetime
    sog_knots: float | None = None
    cog_degrees: float | None = None
    heading_degrees: float | None = None
    vessel_name: str | None = None
    message_type: str = "PositionReport"
    valid: bool = True
    navigational_status: int | None = None
    ais_timestamp_second: int | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    def as_dict(self) -> dict[str, Any]:
        return {
            "mmsi": self.mmsi,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "timestamp": self.timestamp.astimezone(timezone.utc).isoformat(),
            "ais_timestamp_second": self.ais_timestamp_second,
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
    last_update: datetime
    sog_knots: float | None
    cog_degrees: float | None
    heading_degrees: float | None
    vessel_name: str | None
    message_count: int
    stale: bool = False


@dataclass(frozen=True)
class IngestionStatus:
    state: IngestionState
    reason: str
    connected_at: datetime | None
    last_message_at: datetime | None
    messages_received: int
    active_vessels: int
    latency_seconds: float | None
    websocket_status: str


@dataclass(frozen=True)
class AnomalyFinding:
    mmsi: str
    timestamp: datetime
    latitude: float
    longitude: float
    score: float
    category: str
    confidence: float
    explanation: str


@dataclass(frozen=True)
class SimilarTrack:
    mmsi: str
    date: datetime
    region: str
    cluster: int
    similarity: float
    source_label: str = "REAL AIS SESSION"
