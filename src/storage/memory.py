"""Deployment-safe storage abstraction for the Streamlit runtime."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from threading import Lock

from src.ingestion.models import AISObservation


class ObservationStore:
    """Bounded session storage for real AIS messages.

    The store is intentionally in-memory for Streamlit Cloud. It is an adapter
    boundary where a PostgreSQL/PostGIS repository can be added later. Exact
    duplicate payloads are ignored while their count remains available for QA.
    """

    def __init__(self, max_messages: int = 3000, max_vessels: int = 1000) -> None:
        self.max_messages = max(1, max_messages)
        self.max_vessels = max(1, max_vessels)
        self._items: list[AISObservation] = []
        self._seen: set[str] = set()
        self._duplicate_count = 0
        self._lock = Lock()

    @property
    def duplicate_count(self) -> int:
        with self._lock:
            return self._duplicate_count

    @property
    def vessel_count(self) -> int:
        with self._lock:
            return len({item.mmsi for item in self._items})

    def append(self, observation: AISObservation) -> None:
        with self._lock:
            self._append_unlocked(observation)

    def extend(self, observations: list[AISObservation]) -> None:
        with self._lock:
            for observation in observations:
                self._append_unlocked(observation)

    def _append_unlocked(self, observation: AISObservation) -> None:
        key = _observation_key(observation)
        if key in self._seen:
            self._duplicate_count += 1
            return
        self._seen.add(key)
        self._items.append(observation)
        self._trim_unlocked()

    def _trim_unlocked(self) -> None:
        if len(self._items) > self.max_messages:
            del self._items[: len(self._items) - self.max_messages]
        vessels = {item.mmsi for item in self._items}
        while len(vessels) > self.max_vessels:
            latest_by_vessel = {
                mmsi: max(item.received_at for item in self._items if item.mmsi == mmsi)
                for mmsi in vessels
            }
            oldest_mmsi = min(latest_by_vessel, key=latest_by_vessel.get)
            self._items = [item for item in self._items if item.mmsi != oldest_mmsi]
            vessels.remove(oldest_mmsi)
        self._seen = {_observation_key(item) for item in self._items}

    def all(self) -> list[AISObservation]:
        with self._lock:
            return list(self._items)

    def tracks(self) -> dict[str, list[AISObservation]]:
        grouped: dict[str, list[AISObservation]] = defaultdict(list)
        for item in self.all():
            grouped[item.mmsi].append(item)
        return dict(grouped)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
            self._seen.clear()
            self._duplicate_count = 0


def _observation_key(observation: AISObservation) -> str:
    if observation.raw:
        serialized = json.dumps(observation.raw, sort_keys=True, separators=(",", ":"), default=str)
    else:
        serialized = json.dumps(
            {
                "mmsi": observation.mmsi,
                "lat": observation.latitude,
                "lon": observation.longitude,
                "sog": observation.sog_knots,
                "cog": observation.cog_degrees,
                "heading": observation.heading_degrees,
                "ais_second": observation.ais_timestamp_second,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
