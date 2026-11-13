"""Process-local background AIS producer with bounded, observable handoff.

The worker deliberately knows nothing about Streamlit or engine analytics. It owns
only the blocking provider iterator and publishes validated observations to a
bounded queue. A runtime/engine must drain the queue on its own controlled path.
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from src.ingestion.aisstream import AISProvider
from src.ingestion.models import AISObservation


@dataclass(frozen=True)
class WorkerStatus:
    state: str
    started_at: datetime | None
    last_message_at: datetime | None
    messages_received: int
    reconnect_attempts: int
    queue_depth: int
    dropped_messages: int
    last_error: str | None


class AISIngestionWorker:
    """Own one provider stream in a daemon thread and expose a bounded queue.

    This class is process-local. It does not coordinate separate Python
    processes or deployment replicas. Callers are responsible for ensuring one
    worker per normalized configuration within their process.
    """

    def __init__(
        self,
        provider: AISProvider,
        *,
        queue_capacity: int = 5000,
        retry_delay_seconds: float = 1.0,
        max_retry_delay_seconds: float = 8.0,
        live_timeout_seconds: float = 30.0,
        clock: Callable[[], datetime] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if queue_capacity < 1:
            raise ValueError("queue_capacity must be >= 1")
        if retry_delay_seconds <= 0 or max_retry_delay_seconds < retry_delay_seconds:
            raise ValueError("retry delays must be positive and max >= initial")
        if live_timeout_seconds <= 0:
            raise ValueError("live_timeout_seconds must be positive")
        self.provider = provider
        self.observations: queue.Queue[AISObservation] = queue.Queue(maxsize=queue_capacity)
        self._retry_delay = retry_delay_seconds
        self._max_retry_delay = max_retry_delay_seconds
        self._live_timeout = live_timeout_seconds
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._sleep = sleep
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._started_at: datetime | None = None
        self._last_message_at: datetime | None = None
        self._messages_received = 0
        self._reconnect_attempts = 0
        self._dropped_messages = 0
        self._last_error: str | None = None
        self._state = "STOPPED"

    def start(self) -> bool:
        """Start once; repeated calls while running are harmless."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False
            self._stop.clear()
            self._started_at = self._clock()
            self._last_message_at = None
            self._messages_received = 0
            self._reconnect_attempts = 0
            self._dropped_messages = 0
            self._last_error = None
            self._state = "STARTING"
            self._thread = threading.Thread(
                target=self._run,
                name="mie-ais-ingestion",
                daemon=True,
            )
            self._thread.start()
            return True

    def stop(self, timeout: float = 10.0) -> bool:
        """Request shutdown and wait at most timeout seconds."""
        self._stop.set()
        with self._lock:
            thread = self._thread
            if thread is None:
                self._state = "STOPPED"
                return True
        thread.join(max(0.0, timeout))
        stopped = not thread.is_alive()
        with self._lock:
            self._state = "STOPPED" if stopped else "ERROR"
            if not stopped:
                self._last_error = "Worker did not stop before the shutdown timeout."
        return stopped

    def drain(self, limit: int = 1000) -> list[AISObservation]:
        """Return up to limit queued observations without blocking."""
        if limit < 1:
            return []
        items: list[AISObservation] = []
        for _ in range(limit):
            try:
                items.append(self.observations.get_nowait())
            except queue.Empty:
                break
        return items

    def status(self) -> WorkerStatus:
        with self._lock:
            state = self._state
            if (
                state == "LIVE"
                and self._last_message_at is not None
                and (self._clock() - self._last_message_at).total_seconds() > self._live_timeout
            ):
                state = "DEGRADED"
            return WorkerStatus(
                state=state,
                started_at=self._started_at,
                last_message_at=self._last_message_at,
                messages_received=self._messages_received,
                reconnect_attempts=self._reconnect_attempts,
                queue_depth=self.observations.qsize(),
                dropped_messages=self._dropped_messages,
                last_error=self._last_error,
            )

    def _run(self) -> None:
        delay = self._retry_delay
        first_attempt = True
        while not self._stop.is_set():
            if not first_attempt:
                with self._lock:
                    self._reconnect_attempts += 1
                    self._state = "RECONNECTING"
                if self._stop.wait(delay):
                    break
                delay = min(delay * 2.0, self._max_retry_delay)
            first_attempt = False
            with self._lock:
                self._state = "CONNECTING"
            try:
                received_any = False
                for observation in self.provider.stream(self._stop, duration_seconds=None, message_limit=0):
                    if self._stop.is_set():
                        break
                    received_any = True
                    try:
                        self.observations.put_nowait(observation)
                    except queue.Full:
                        with self._lock:
                            self._dropped_messages += 1
                            self._state = "DEGRADED"
                    with self._lock:
                        self._messages_received += 1
                        self._last_message_at = observation.received_at
                        if self._state != "DEGRADED":
                            self._state = "LIVE"
                if self._stop.is_set():
                    break
                with self._lock:
                    self._state = "DEGRADED"
                    if not received_any:
                        self._last_error = "Provider stream ended without observations."
                # A finite/unexpected provider iterator ending is treated as a
                # reconnect condition; it is never reported as LIVE.
            except Exception as exc:  # defensive boundary around provider implementations
                with self._lock:
                    self._state = "DEGRADED"
                    self._last_error = f"{exc.__class__.__name__}: {str(exc)[:200]}"
            delay = self._retry_delay
        with self._lock:
            self._state = "STOPPED"


__all__ = ["AISIngestionWorker", "WorkerStatus"]
