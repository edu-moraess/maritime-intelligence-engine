"""Deployment-safe storage abstraction for the Streamlit runtime."""

from __future__ import annotations

from collections import defaultdict
from threading import Lock

from src.ingestion.models import AISObservation


class ObservationStore:
    """Bounded session storage for real AIS messages.

    The store is intentionally in-memory for Streamlit Cloud. It is an adapter
    boundary where a PostgreSQL/PostGIS repository can be added later.
    """

    def __init__(self, max_messages: int = 3000) -> None:
        self.max_messages = max_messages
        self._items: list[AISObservation] = []
        self._lock = Lock()

    def append(self, observation: AISObservation) -> None:
        with self._lock:
            self._items.append(observation)
            if len(self._items) > self.max_messages:
                del self._items[: len(self._items) - self.max_messages]

    def extend(self, observations: list[AISObservation]) -> None:
        with self._lock:
            self._items.extend(observations)
            if len(self._items) > self.max_messages:
                del self._items[: len(self._items) - self.max_messages]

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
