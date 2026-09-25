"""AISStream WebSocket ingestion.

The module deliberately has no synthetic or fallback provider. If AISStream is not
available, it yields no observations and reports the reason to the UI.
"""

from __future__ import annotations

import json
import logging
import math
import random
import threading
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Iterator

from src.config.settings import _validate_bbox

from .models import AISObservation, IngestionStatus, VesselSnapshot

try:
    import websocket
except ImportError:  # pragma: no cover - exercised only before dependencies install
    websocket = None

LOGGER = logging.getLogger(__name__)
STREAM_URL = "wss://stream.aisstream.io/v0/stream"


class AISProvider(ABC):
    """Interface allowing additional real AIS providers without UI coupling."""

    @abstractmethod
    def connect(self) -> tuple[bool, str]:
        raise NotImplementedError

    @abstractmethod
    def fetch_vessels(self) -> list[VesselSnapshot]:
        now = datetime.now(timezone.utc)
        tracks = self.fetch_tracks()
        result: list[VesselSnapshot] = []
        for mmsi, track in tracks.items():
            if not track:
                continue
            latest = track[-1]
            result.append(
                VesselSnapshot(
                    mmsi=mmsi,
                    latitude=latest.latitude,
                    longitude=latest.longitude,
                    last_received=latest.received_at,
                    sog_knots=latest.sog_knots,
                    cog_degrees=latest.cog_degrees,
                    heading_degrees=latest.heading_degrees,
                    vessel_name=latest.vessel_name,
                    message_count=len(track),
                    ais_timestamp_second=latest.ais_timestamp_second,
                    observed_at=latest.observed_at,
                    stale=(now - latest.received_at).total_seconds() > self.stale_after_seconds,
                )
            )
        return sorted(result, key=lambda vessel: vessel.last_received, reverse=True)[: self.max_vessels]

    def fetch_tracks(self) -> dict[str, list[AISObservation]]:
        tracks: dict[str, list[AISObservation]] = {}
        for observation in self._observations:
            tracks.setdefault(observation.mmsi, []).append(observation)
        return tracks
    def _set_failure(self, reason: str) -> None:
        self._state = "DISCONNECTED"
        self._reason = reason
        self._websocket_status = "CLOSED"
        self._last_error = reason


def _valid_mmsi(value: str) -> bool:
    return value.isdigit() and len(value) == 9


def _ais_timestamp_integer(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        second = int(value)
    except (TypeError, ValueError):
        return None
    if isinstance(value, float) and value != second:
        return None
    return second


def _parse_ais_second(value: object) -> int | None:
    """Return only ordinary AIS seconds; special states are not normal seconds.

    AIS values 60–63 are special protocol states. This parser deliberately
    returns ``None`` for them, so they are not persisted as ordinary seconds,
    converted to ``received_at``, or used to fabricate ``observed_at``.
    """
    second = _ais_timestamp_integer(value)
    return second if second is not None and 0 <= second <= 59 else None


def _is_special_ais_second(value: object) -> bool:
    second = _ais_timestamp_integer(value)
    return second is not None and 60 <= second <= 63


def _sog(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and 0 <= number <= 102.2 else None


def _cog(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and 0 <= number < 360 else None


def _heading(value: object) -> float | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return float(number) if 0 <= number <= 359 else None


def _integer(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _is_timeout(exc: Exception) -> bool:
    return "timed out" in str(exc).lower() or "timeout" in str(exc).lower()


def _safe_reason(exc: Exception, secret: str = "") -> str:
    text = str(exc).strip().replace("\n", " ")
    if secret:
        text = text.replace(secret, "[redacted]")
    return text[:240] or exc.__class__.__name__
