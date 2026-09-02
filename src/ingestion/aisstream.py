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
except ImportError:  # pragma: no cover
    websocket = None

LOGGER = logging.getLogger(__name__)
STREAM_URL = "wss://stream.aisstream.io/v0/stream"


class AISProvider(ABC):
    @abstractmethod
    def connect(self) -> tuple[bool, str]: raise NotImplementedError
    @abstractmethod
    def fetch_vessels(self) -> list[VesselSnapshot]: raise NotImplementedError
    @abstractmethod
    def fetch_tracks(self) -> dict[str, list[AISObservation]]: raise NotImplementedError
    @abstractmethod
    def stream(self, stop_event: threading.Event | None = None, duration_seconds: float | None = None) -> Iterator[AISObservation]: raise NotImplementedError


class AISStreamProvider(AISProvider):
    """Finite-window real AIS consumer with explicit receive-time semantics."""

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
                if not isinstance(box, (list, tuple)) or len(box) != 2:
                    raise ValueError("Each AIS bounding box must contain two corners.")
                corners = ((float(box[0][0]), float(box[0][1])), (float(box[1][0]), float(box[1][1])))
                _validate_bbox(corners)
        except (IndexError, TypeError, ValueError) as exc:
            self._set_failure(f"Invalid AIS bounding box: {exc}"); return False, self._reason
        self._state = "CONNECTING"; self._reason = "Subscription sent; waiting for AIS messages."; self._websocket_status = "CONNECTING"
        return True, self._reason

    def stream(self, stop_event: threading.Event | None = None, duration_seconds: float | None = None) -> Iterator[AISObservation]:
        ready, _ = self.connect()
        if not ready:
            return
        stop_event = stop_event or threading.Event()
        deadline = time.monotonic() + max(0.1, duration_seconds) if duration_seconds is not None else None
        messages_at_start = self._messages_received
        backoff = 1.0
        opened = False
        while not stop_event.is_set() and self._messages_received < self.max_messages:
            if deadline is not None and time.monotonic() >= deadline: break
            socket = None
            try:
                socket = websocket.create_connection(STREAM_URL, timeout=8, enable_multithread=True, compression="deflate")
                opened = True
                self._connected_at = datetime.now(timezone.utc)
                self._state = "CONNECTING"; self._reason = "Subscription sent; waiting for AIS messages."; self._websocket_status = "OPEN"
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
                self._websocket_status = "CLOSED"; self._state = "DISCONNECTED"; self._reason = _safe_reason(exc, self.api_key)
                LOGGER.warning("AISStream connection ended: %s", self._reason)
                if stop_event.is_set() or (deadline is not None and time.monotonic() >= deadline): break
                sleep_for = min(backoff + random.uniform(0, 0.4), 8.0)
                if deadline is not None: sleep_for = min(sleep_for, max(0.0, deadline - time.monotonic()))
                if sleep_for > 0: time.sleep(sleep_for)
                backoff = min(backoff * 2.0, 8.0)
            finally:
                if socket is not None:
                    try: socket.close()
                    except Exception: pass
                self._websocket_status = "CLOSED"
            if deadline is not None and time.monotonic() >= deadline: break
        received_this_window = self._messages_received > messages_at_start
        self._websocket_status = "CLOSED"
        if not received_this_window and opened:
            self._state = "REAL AIS DATA UNAVAILABLE"; self._reason = "No real AIS PositionReport was received during the collection window."
        elif received_this_window and self._state == "CONNECTING":
            self._state = "LIVE AIS"
            self._reason = ("Real AIS PositionReports received during the collection window. " f"Ingestion diagnostics: frames={self._frames_received}, position_reports={self._position_reports_received}, accepted={self._position_reports_accepted}, rejected={max(0, self._position_reports_received - self._position_reports_accepted)}, parse_errors={self._parse_errors}, non_position={self._non_position_frames}.")

    def _parse_frame(self, frame: str | bytes) -> AISObservation | None:
        try:
            if isinstance(frame, bytes): frame = frame.decode("utf-8")
            payload = json.loads(frame)
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
            self._parse_errors += 1; return None
        if not isinstance(payload, dict) or payload.get("MessageType") != "PositionReport":
            self._non_position_frames += 1; return None
        self._position_reports_received += 1
        meta = payload.get("MetaData") or {}; report = (payload.get("Message") or {}).get("PositionReport") or {}
        if not isinstance(meta, dict) or not isinstance(report, dict): return None
        try:
            mmsi = str(report.get("UserID") or meta.get("MMSI") or "").strip()
            if not _valid_mmsi(mmsi): return None
            latitude = float(report.get("Latitude", meta.get("Latitude"))); longitude = float(report.get("Longitude", meta.get("Longitude")))
            if not (math.isfinite(latitude) and math.isfinite(longitude) and -90 <= latitude <= 90 and -180 <= longitude <= 180): return None
            raw_timestamp = report.get("Timestamp"); ais_timestamp_second = _parse_ais_second(raw_timestamp)
            if ais_timestamp_second is None and not _is_special_ais_second(raw_timestamp): return None
            valid = report.get("Valid")
            if not isinstance(valid, bool) or not valid: return None
            received_at = datetime.now(timezone.utc)
            return AISObservation(mmsi=mmsi, latitude=latitude, longitude=longitude, received_at=received_at, sog_knots=_sog(report.get("Sog")), cog_degrees=_cog(report.get("Cog")), heading_degrees=_heading(report.get("TrueHeading")), vessel_name=(str(meta.get("ShipName")).strip() if meta.get("ShipName") else None), message_type="PositionReport", valid=True, navigational_status=_integer(report.get("NavigationalStatus")), ais_timestamp_second=ais_timestamp_second, raw=payload)
        except (TypeError, ValueError, OverflowError):
            return None

    def _record(self, observation: AISObservation) -> None:
        self._messages_received += 1; self._position_reports_accepted += 1; self._last_received_at = observation.received_at; self._last_ais_timestamp_second = observation.ais_timestamp_second; self._state = "LIVE AIS"; self._reason = "Receiving real AIS position reports from AISStream."; self._observations.append(observation); self._tracks[observation.mmsi].append(observation)
        if len(self._observations) > self.max_messages: self._observations = self._observations[-self.max_messages:]
        if len(self._tracks) > self.max_vessels:
            oldest_mmsi = min(self._tracks, key=lambda key: self._tracks[key][-1].received_at); del self._tracks[oldest_mmsi]

    def fetch_vessels(self) -> list[VesselSnapshot]:
        now = datetime.now(timezone.utc); result: list[VesselSnapshot] = []
        for mmsi, track in self._tracks.items():
            if not track: continue
            latest = track[-1]
            result.append(VesselSnapshot(mmsi=mmsi, latitude=latest.latitude, longitude=latest.longitude, last_received=latest.received_at, sog_knots=latest.sog_knots, cog_degrees=latest.cog_degrees, heading_degrees=latest.heading_degrees, vessel_name=latest.vessel_name, message_count=len(track), ais_timestamp_second=latest.ais_timestamp_second, observed_at=latest.observed_at, stale=(now - latest.received_at).total_seconds() > self.stale_after_seconds))
        return sorted(result, key=lambda vessel: vessel.last_received, reverse=True)

    def fetch_tracks(self) -> dict[str, list[AISObservation]]:
        return {mmsi: list(track) for mmsi, track in self._tracks.items()}

    def _set_failure(self, reason: str) -> None:
        self._state = "DISCONNECTED"; self._reason = reason; self._websocket_status = "CLOSED"


def _valid_mmsi(value: str) -> bool: return value.isdigit() and len(value) == 9

def _ais_timestamp_integer(value: object) -> int | None:
    if isinstance(value, bool): return None
    try: second = int(value)
    except (TypeError, ValueError): return None
    if isinstance(value, float) and value != second: return None
    return second

def _parse_ais_second(value: object) -> int | None:
    second = _ais_timestamp_integer(value); return second if second is not None and 0 <= second <= 59 else None

def _is_special_ais_second(value: object) -> bool:
    second = _ais_timestamp_integer(value); return second is not None and 60 <= second <= 63

def _sog(value: object) -> float | None:
    try: number = float(value)
    except (TypeError, ValueError): return None
    return number if math.isfinite(number) and 0 <= number <= 102.2 else None

def _cog(value: object) -> float | None:
    try: number = float(value)
    except (TypeError, ValueError): return None
    return number if math.isfinite(number) and 0 <= number < 360 else None

def _heading(value: object) -> float | None:
    try: number = int(value)
    except (TypeError, ValueError): return None
    return float(number) if 0 <= number <= 359 else None

def _integer(value: object) -> int | None:
    try: return int(value)
    except (TypeError, ValueError): return None

def _is_timeout(exc: Exception) -> bool: return "timed out" in str(exc).lower() or "timeout" in str(exc).lower()

def _safe_reason(exc: Exception, secret: str = "") -> str:
    text = str(exc).strip().replace("\n", " ")
    if secret: text = text.replace(secret, "[redacted]")
    return text[:240] or exc.__class__.__name__
