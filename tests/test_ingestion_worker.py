from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

from src.ingestion.models import AISObservation
from src.ingestion.worker import AISIngestionWorker


class _BlockingProvider:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.stopped = threading.Event()

    def connect(self):
        return True, "ready"

    def stream(self, stop_event=None, duration_seconds=None, *, message_limit=None):
        self.started.set()
        index = 0
        while stop_event is not None and not stop_event.is_set():
            index += 1
            yield AISObservation(
                mmsi=f"{index % 9 + 100000000:09d}",
                latitude=1.0,
                longitude=2.0,
                received_at=datetime.now(timezone.utc),
            )
            time.sleep(0.005)
        self.stopped.set()


class _FiniteProvider:
    def __init__(self) -> None:
        self.calls = 0

    def connect(self):
        return True, "ready"

    def stream(self, stop_event=None, duration_seconds=None):
        self.calls += 1
        if self.calls == 1:
            yield AISObservation(
                mmsi="123456789",
                latitude=1.0,
                longitude=2.0,
                received_at=datetime.now(timezone.utc),
            )
        else:
            if stop_event is not None:
                stop_event.wait(0.05)
            return


def test_worker_start_is_idempotent_and_stop_joins():
    provider = _BlockingProvider()
    worker = AISIngestionWorker(provider, retry_delay_seconds=0.01, max_retry_delay_seconds=0.02)
    assert worker.start() is True
    assert provider.started.wait(1.0)
    assert worker.start() is False
    assert worker.stop(timeout=1.0) is True
    assert provider.stopped.wait(1.0)
    assert worker.status().state == "STOPPED"


def test_worker_delivers_validated_observations_and_reports_health():
    provider = _BlockingProvider()
    worker = AISIngestionWorker(provider, queue_capacity=100)
    worker.start()
    assert provider.started.wait(1.0)
    deadline = time.monotonic() + 1.0
    while worker.status().messages_received == 0 and time.monotonic() < deadline:
        time.sleep(0.005)
    status = worker.status()
    assert status.messages_received > 0
    assert status.last_message_at is not None
    assert worker.drain(limit=10)
    assert worker.stop(timeout=1.0)


def test_worker_queue_overflow_is_counted_and_degrades():
    provider = _BlockingProvider()
    worker = AISIngestionWorker(provider, queue_capacity=1)
    worker.start()
    assert provider.started.wait(1.0)
    deadline = time.monotonic() + 1.0
    while worker.status().dropped_messages == 0 and time.monotonic() < deadline:
        time.sleep(0.005)
    status = worker.status()
    assert status.dropped_messages > 0
    assert status.state in {"DEGRADED", "STOPPED"}
    assert worker.stop(timeout=1.0)


def test_unexpected_provider_iterator_end_is_not_reported_live():
    provider = _FiniteProvider()
    worker = AISIngestionWorker(provider, retry_delay_seconds=0.01, max_retry_delay_seconds=0.02)
    worker.start()
    deadline = time.monotonic() + 1.0
    while provider.calls < 2 and time.monotonic() < deadline:
        time.sleep(0.005)
    status = worker.status()
    assert provider.calls >= 2
    assert status.state != "LIVE"
    assert status.reconnect_attempts >= 1
    assert worker.stop(timeout=1.0)

def test_live_health_expires_when_no_new_position_reports_arrive():
    from datetime import timedelta

    now = [datetime(2026, 11, 13, 3, 0, tzinfo=timezone.utc)]

    class _OneMessageThenIdle:
        def connect(self):
            return True, "ready"

        def stream(self, stop_event=None, duration_seconds=None):
            yield AISObservation(
                mmsi="123456789",
                latitude=1.0,
                longitude=2.0,
                received_at=now[0],
            )
            if stop_event is not None:
                stop_event.wait(2.0)

    worker = AISIngestionWorker(
        _OneMessageThenIdle(),
        live_timeout_seconds=30.0,
        clock=lambda: now[0],
    )
    worker.start()
    deadline = time.monotonic() + 1.0
    while worker.status().messages_received == 0 and time.monotonic() < deadline:
        time.sleep(0.005)
    assert worker.status().state == "LIVE"

    now[0] = now[0] + timedelta(seconds=31)
    assert worker.status().state == "DEGRADED"
    assert worker.stop(timeout=1.0)
