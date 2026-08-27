"""AISStream WebSocket ingestion.

The module deliberately has no synthetic or fallback provider. If AISStream is not
available, it yields no observations and reports the reason to the UI.
"""

from __future__ import annotations

import json
import logging
import random
import threading
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import datetime, timezone
from typing import Iterator

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
        raise NotImplementedError

    @abstractmethod
    def fetch_tracks(self) -> dict[str, list[AISObservation]]:
        raise NotImplementedError

    @abstractmethod
    def stream(self, stop_event: threading.Event | None = None) -> Iterator[AISObservation]:
        raise NotImplementedError


class AISStreamProvider(AISProvider):
    """Finite-window consumer for the AISStream real-time WebSocket."""

    def __init__(
        self,
        api_key: str,
        bbox: list[list[list[float]]],
        max_messages: int = 3000,
        max_vessels: int = 1000,
        stale_after_seconds: int = 180,
    ) -> None:
        self.api_key = api_key
        self.bbox = bbox
        self.max_messages = max_messages
        self.max_vessels = max_vessels
        self.stale_after_seconds = stale_after_seconds
        self._observations: list[AISObservation] = []
        self._tracks: dict[str, list[AISObservation]] = defaultdict(list)
        self._connected_at: datetime | None = None
        self._last_message_at: datetime | None = None
        self._messages_received = 0
        self._state = "DISCONNECTED"
        self._reason = "Not connected."
        self._websocket_status = "CLOSED"
        self._latency_seconds: float | None = None

    @property
    def status(self) -> IngestionStatus:
        return IngestionStatus(
            state=self._state,
            reason=self._reason,
            connected_at=self._connected_at,
            last_message_at=self._last_message_at,
            messages_received=self._messages_received,
            active_vessels=len(self._tracks),
            latency_seconds=self._latency_seconds,
            websocket_status=self._websocket_status,
        )

    def _subscription(self) -> dict:
        return {
            "APIKey": self.api_key,
            "BoundingBoxes": self.bbox,
            "FilterMessageTypes": ["PositionReport"],
        }

    def connect(self) -> tuple[bool, str]:
        if websocket is None:
            self._set_failure("websocket-client is not installed.")
            return False, self._reason
        if not self.api_key:
            self._set_failure("AISSTREAM_API_KEY is not configured.")
            return False, self._reason
        self._state = "CONNECTING"
        self._reason = "Opening AISStream WebSocket."
        self._websocket_status = "CONNECTING"
        return True, self._reason

    def stream(self, stop_event: threading.Event | None = None) -> Iterator[AISObservation]:
        """Read continuously for the caller's finite collection window.

        The generator reconnects with exponential backoff and jitter after a
        transient disconnect. It never manufactures an observation on failure.
        """
        ready, _ = self.connect()
        if not ready:
            return
        stop_event = stop_event or threading.Event()
        backoff = 1.0
        while not stop_event.is_set() and self._messages_received < self.max_messages:
            socket = None
            try:
                socket = websocket.create_connection(
                    STREAM_URL,
                    timeout=8,
                    enable_multithread=True,
                    compression="deflate",
                )
                self._connected_at = datetime.now(timezone.utc)
                self._state = "CONNECTING"
                self._reason = "Subscription sent; waiting for AIS messages."
                self._websocket_status = "OPEN"
                socket.send(json.dumps(self._subscription()))
                backoff = 1.0
                while not stop_event.is_set() and self._messages_received < self.max_messages:
                    try:
                        socket.settimeout(1.0)
                        frame = socket.recv()
                    except Exception as exc:
                        if _is_timeout(exc):
                            continue
                        raise
                    if not frame:
                        raise ConnectionError("AISStream closed the WebSocket.")
                    observation = self._parse_frame(frame)
                    if observation is None:
                        continue
                    self._record(observation)
                    yield observation
            except Exception as exc:
                self._websocket_status = "CLOSED"
                self._state = "DISCONNECTED"
                self._reason = _safe_reason(exc)
                LOGGER.warning("AISStream connection ended: %s", self._reason)
                if stop_event.is_set():
                    break
                time.sleep(min(backoff + random.uniform(0, 0.4), 8.0))
                backoff = min(backoff * 2.0, 8.0)
            finally:
                if socket is not None:
                    try:
                        socket.close()
                    except Exception:
                        pass
        if self._state == "CONNECTING" and not self._last_message_at:
            self._state = "DISCONNECTED"
            self._reason = "No real AIS messages received during the collection window."
            self._websocket_status = "CLOSED"

    def _parse_frame(self, frame: str | bytes) -> AISObservation | None:
        try:
            if isinstance(frame, bytes):
                frame = frame.decode("utf-8")
            payload = json.loads(frame)
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
            return None
        if payload.get("MessageType") != "PositionReport":
            return None
        meta = payload.get("MetaData") or {}
        report = (payload.get("Message") or {}).get("PositionReport") or {}
        try:
            mmsi = str(report.get("UserID") or meta.get("MMSI") or "").strip()
            latitude = float(report.get("Latitude", meta.get("Latitude")))
            longitude = float(report.get("Longitude", meta.get("Longitude")))
            if not mmsi or not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                return None
            timestamp_value = report.get("Timestamp")
            timestamp = _parse_timestamp(timestamp_value)
            if timestamp is None:
                timestamp = datetime.now(timezone.utc)
            return AISObservation(
                mmsi=mmsi,
                latitude=latitude,
                longitude=longitude,
                timestamp=timestamp,
                sog_knots=_number(report.get("Sog")),
                cog_degrees=_number(report.get("Cog")),
                heading_degrees=_number(report.get("TrueHeading")),
                vessel_name=(str(meta.get("ShipName")).strip() if meta.get("ShipName") else None),
                message_type="PositionReport",
                valid=bool(report.get("Valid", True)),
                navigational_status=_integer(report.get("NavigationalStatus")),
                raw=payload,
            )
        except (TypeError, ValueError):
            return None

    def _record(self, observation: AISObservation) -> None:
        now = datetime.now(timezone.utc)
        self._messages_received += 1
        self._last_message_at = now
        self._latency_seconds = max(0.0, (now - observation.timestamp).total_seconds())
        self._state = "LIVE AIS"
        self._reason = "Receiving real AIS position reports from AISStream."
        self._observations.append(observation)
        self._tracks[observation.mmsi].append(observation)
        if len(self._observations) > self.max_messages:
            self._observations = self._observations[-self.max_messages :]
        if len(self._tracks) > self.max_vessels:
            oldest_mmsi = min(self._tracks, key=lambda key: self._tracks[key][-1].timestamp)
            del self._tracks[oldest_mmsi]

    def fetch_vessels(self) -> list[VesselSnapshot]:
        now = datetime.now(timezone.utc)
        result: list[VesselSnapshot] = []
        for mmsi, track in self._tracks.items():
            if not track:
                continue
            latest = track[-1]
            result.append(
                VesselSnapshot(
                    mmsi=mmsi,
                    latitude=latest.latitude,
                    longitude=latest.longitude,
                    last_update=latest.timestamp,
                    sog_knots=latest.sog_knots,
                    cog_degrees=latest.cog_degrees,
                    heading_degrees=latest.heading_degrees,
                    vessel_name=latest.vessel_name,
                    message_count=len(track),
                    stale=(now - latest.timestamp).total_seconds() > self.stale_after_seconds,
                )
            )
        return sorted(result, key=lambda vessel: vessel.last_update, reverse=True)

    def fetch_tracks(self) -> dict[str, list[AISObservation]]:
        return {mmsi: list(track) for mmsi, track in self._tracks.items()}

    def _set_failure(self, reason: str) -> None:
        self._state = "DISCONNECTED"
        self._reason = reason
        self._websocket_status = "CLOSED"


def _parse_timestamp(value: object) -> datetime | None:
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def _number(value: object) -> float | None:
    try:
        number = float(value)
        return number if number >= 0 else None
    except (TypeError, ValueError):
        return None


def _integer(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _is_timeout(exc: Exception) -> bool:
    return "timed out" in str(exc).lower() or "timeout" in str(exc).lower()


def _safe_reason(exc: Exception) -> str:
    text = str(exc).strip().replace("\n", " ")
    return text[:240] or exc.__class__.__name__
