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
from collections import defaultdict
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
        raise NotImplementedError

    @abstractmethod
    def fetch_tracks(self) -> dict[str, list[AISObservation]]:
        raise NotImplementedError

    @abstractmethod
    def stream(self, stop_event: threading.Event | None = None, duration_seconds: float | None = None) -> Iterator[AISObservation]:
        raise NotImplementedError


class AISStreamProvider(AISProvider):
    """Finite-window real AIS consumer with explicit receive-time semantics.

    PositionReport.Timestamp is retained as the AIS UTC second within the
    minute. It is never combined with server date/time to fabricate an
    absolute observation datetime; ``received_at`` is the MIE receive time.
    """

    def __init__(self, api_key: str, bbox: list[list[list[float]]], max_messages: int = 3000, max_vessels: int = 1000, stale_after_seconds: int = 180, config_error: str | None = None) -> None:
        self.api_key = api_key
        self.bbox = bbox
        self.max_messages = max_messages
        self.max_vessels = max_vessels
        self.stale_after_seconds = stale_after_seconds
        self.config_error = config_error
        self._observations: list[AISObservation] = []
        self._tracks: dict[str, list[AISObservation]] = defaultdict(list)
        self._connected_at: datetime | None = None
        self._last_received_at: datetime | None = None
        self._last_ais_timestamp_second: int | None = None
        self._messages_received = 0
        self._frames_received = 0
        self._position_reports_received = 0
        self._position_reports_accepted = 0
        self._parse_errors = 0
        self._non_position_frames = 0
        self._state = "DISCONNECTED"
        self._reason = "Not connected."
        self._websocket_status = "CLOSED"

    @property
    def status(self) -> IngestionStatus:
        return IngestionStatus(state=self._state, reason=self._reason, connected_at=self._connected_at, last_received_at=self._last_received_at, messages_received=self._messages_received, active_vessels=len(self._tracks), latency_seconds=None, websocket_status=self._websocket_status, ais_timestamp_second=self._last_ais_timestamp_second, frames_received=self._frames_received, position_reports_received=self._position_reports_received, position_reports_accepted=self._position_reports_accepted, parse_errors=self._parse_errors, non_position_frames=self._non_position_frames)

    def reset_session(self) -> None:
        self._observations.clear(); self._tracks.clear(); self._connected_at = None; self._last_received_at = None; self._last_ais_timestamp_second = None; self._messages_received = 0; self._frames_received = 0; self._position_reports_received = 0; self._position_reports_accepted = 0; self._parse_errors = 0; self._non_position_frames = 0; self._state = "DISCONNECTED"; self._reason = "Not connected."; self._websocket_status = "CLOSED"

    def _subscription(self) -> dict:
        return {"APIKey": self.api_key, "BoundingBoxes": self.bbox, "FilterMessageTypes": ["PositionReport"]}

    def connect(self) -> tuple[bool, str]:
        if self.config_error:
            self._set_failure(self.config_error); return False, self._reason
        if websocket is None:
            self._set_failure("websocket-client is not installed."); return False, self._reason
        if not self.api_key:
            self._set_failure("AISSTREAM_API_KEY is not configured."); return False, self._reason
        try:
            if not self.bbox:
                raise ValueError("At least one AIS bounding box is required.")
            for box in self.bbox:
                if len(box) != 2:
                    raise ValueError("Each AIS bounding box must contain two corners.")
                corners = ((float(box[0][0]), float(box[0][1])), (float(box[1][0]), float(box[1][1])))
                _validate_bbox(corners)
        except (IndexError, TypeError, ValueError) as exc:
            self._set_failure(f"Invalid AIS bounding box: {exc}"); return False, self._reason
        self._state = "CONNECTING"; self._reason = "Subscription sent; waiting for AIS messages."; self._websocket_status = "CONNECTING"; return True, self._reason

    def stream(self, stop_event: threading.Event | None = None, duration_seconds: float | None = None) -> Iterator[AISObservation]:
        ready, _ = self.connect()
        if not ready:
            return
        stop_event = stop_event or threading.Event()
        deadline = time.monotonic() + max(0.1, duration_seconds) if duration_seconds is not None else None
        backoff = 1.0
        while not stop_event.is_set() and self._messages_received < self.max_messages:
            if deadline is not None and time.monotonic() >= deadline: break
            socket = None
            try:
                socket = websocket.create_connection(STREAM_URL, timeout=8, enable_multithread=True, compression="deflate")
                self._connected_at = datetime.now(timezone.utc); self._state = "CONNECTING"; self._reason = "Subscription sent; waiting for AIS messages."; self._websocket_status = "OPEN"
                socket.send(json.dumps(self._subscription())); backoff = 1.0
                while not stop_event.is_set() and self._messages_received < self.max_messages:
                    if deadline is not None and time.monotonic() >= deadline: break
                    try:
                        socket.settimeout(1.0); frame = socket.recv()
                    except Exception as exc:
                        if _is_timeout(exc): continue
                        raise
                    if not frame: raise ConnectionError("AISStream closed the WebSocket.")
                    self._frames_received += 1
                    observation = self._parse_frame(frame)
                    if observation is None: continue
                    self._record(observation); yield observation
            except Exception as exc:
                self._websocket_status = "CLOSED"; self._state = "DISCONNECTED"; self._reason = _safe_reason(exc, self.api_key); LOGGER.warning("AISStream connection ended: %s", self._reason)
                if stop_event.is_set() or (deadline is not None and time.monotonic() >= deadline): break
                sleep_for = min(backoff + random.uniform(0, 0.4), 8.0)
                if deadline is not None: sleep_for = min(sleep_for, max(0.0, deadline - time.monotonic()))
                if sleep_for > 0: time.sleep(sleep_for)
                backoff = min(backoff * 2.0, 8.0)
            finally:
                if socket is not None:
                    try: socket.close()
                    except Exception: pass

    def _set_failure(self, reason: str) -> None:
        self._state = "DISCONNECTED"; self._reason = reason; self._websocket_status = "CLOSED"

    def _parse_frame(self, frame: str | bytes) -> AISObservation | None:
        try:
            payload = json.loads(frame)
            message = payload.get("Message", {})
            report = message.get("PositionReport")
            if not isinstance(report, dict):
                self._non_position_frames += 1; return None
            self._position_reports_received += 1
            mmsi = str(payload.get("MetaData", {}).get("MMSI") or report.get("UserID") or "").strip()
            lat = float(report.get("Latitude")); lon = float(report.get("Longitude"))
            if not mmsi or not math.isfinite(lat) or not math.isfinite(lon): raise ValueError("missing MMSI or coordinates")
            if not (-90 <= lat <= 90 and -180 <= lon <= 180): raise ValueError("coordinates outside valid range")
            received_at = datetime.now(timezone.utc)
            timestamp_second = report.get("Timestamp")
            self._last_ais_timestamp_second = int(timestamp_second) if timestamp_second is not None else None
            return AISObservation(mmsi=mmsi, latitude=lat, longitude=lon, sog=float(report.get("Sog") or 0.0), cog=float(report.get("Cog") or 0.0), received_at=received_at, ais_timestamp_second=self._last_ais_timestamp_second)
        except (TypeError, ValueError, json.JSONDecodeError, KeyError):
            self._parse_errors += 1; return None

    def _record(self, observation: AISObservation) -> None:
        self._messages_received += 1; self._position_reports_accepted += 1; self._last_received_at = observation.received_at
        self._observations.append(observation); self._tracks[observation.mmsi].append(observation)
        if len(self._observations) > self.max_messages: self._observations = self._observations[-self.max_messages:]
        if len(self._tracks) > self.max_vessels:
            oldest = next(iter(self._tracks)); self._tracks.pop(oldest, None)

    def fetch_vessels(self) -> list[VesselSnapshot]:
        return [VesselSnapshot(mmsi=mmsi, latitude=track[-1].latitude, longitude=track[-1].longitude, sog=track[-1].sog, cog=track[-1].cog, received_at=track[-1].received_at) for mmsi, track in self._tracks.items() if track]

    def fetch_tracks(self) -> dict[str, list[AISObservation]]:
        return {mmsi: list(track) for mmsi, track in self._tracks.items()}


def _is_timeout(exc: Exception) -> bool:
    return isinstance(exc, TimeoutError) or "timed out" in str(exc).lower() or "timeout" in str(exc).lower()


def _safe_reason(exc: Exception, api_key: str) -> str:
    text = str(exc).strip() or exc.__class__.__name__
    return text.replace(api_key, "***") if api_key else text
