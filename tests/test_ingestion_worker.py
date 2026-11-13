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

    def stream(self, stop_event=None, duration_seconds=None, *, message_limit=None):
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

        def stream(self, stop_event=None, duration_seconds=None, *, message_limit=None):
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

def test_engine_drains_live_worker_and_transitions_to_disconnected_on_stop(monkeypatch):
    from src.config.settings import AppSettings, DEFAULT_BBOX
    from src.intelligence.engine import MaritimeIntelligenceEngine

    from src.ingestion.models import IngestionStatus

    class _EngineProvider:
        def __init__(self):
            self._state = "DISCONNECTED"
            self._websocket_status = "CLOSED"
            self._last_received = None
            self._messages = 0

        @property
        def status(self):
            return IngestionStatus(
                state=self._state,
                reason="test provider",
                connected_at=None,
                last_received_at=self._last_received,
                messages_received=self._messages,
                active_vessels=0,
                latency_seconds=None,
                websocket_status=self._websocket_status,
            )

        def stream(self, stop_event=None, duration_seconds=None, *, message_limit=None):
            self._state = "CONNECTING"
            self._websocket_status = "OPEN"
            for mmsi in ("123456789", "123456788"):
                if stop_event is not None and stop_event.is_set():
                    break
                self._last_received = datetime.now(timezone.utc)
                self._messages += 1
                self._state = "LIVE AIS"
                yield AISObservation(
                    mmsi=mmsi,
                    latitude=1.0,
                    longitude=2.0,
                    received_at=self._last_received,
                )
            while stop_event is not None and not stop_event.is_set():
                time.sleep(0.005)
            self._state = "DISCONNECTED"
            self._websocket_status = "CLOSED"

    engine = MaritimeIntelligenceEngine(
        AppSettings(aisstream_api_key="test-key", bbox=DEFAULT_BBOX)
    )
    provider = _EngineProvider()
    engine.provider = provider
    engine.live_worker = AISIngestionWorker(provider, queue_capacity=10)
    engine._recompute = lambda: None
    engine._detect_current_session_findings = lambda: []
    engine._refresh_environmental_contexts = lambda: None

    assert engine.start_live_monitoring() is True
    deadline = time.monotonic() + 1.0
    while engine.live_worker.status().messages_received < 2 and time.monotonic() < deadline:
        time.sleep(0.005)

    live_snapshot = engine.snapshot()
    assert live_snapshot.status.state == "LIVE AIS"
    assert len(live_snapshot.current_session_observations) == 2
    assert len(live_snapshot.vessels) == 2

    assert engine.stop_live_monitoring(timeout=1.0) is True
    stopped_snapshot = engine.snapshot()
    assert stopped_snapshot.status.state == "DISCONNECTED"
    assert stopped_snapshot.status.websocket_status == "CLOSED"

    engine.clear_session_data()
    cleared_snapshot = engine.snapshot()
    assert cleared_snapshot.current_session_observations == []
    assert engine.store.all() == []
    assert engine.live_worker.status().queue_depth == 0

def test_connecting_worker_degrades_when_no_first_position_report_arrives():
    from datetime import timedelta

    now = [datetime(2026, 11, 13, 3, 0, tzinfo=timezone.utc)]

    class _SilentProvider:
        def connect(self):
            return True, "ready"

        def stream(self, stop_event=None, duration_seconds=None, *, message_limit=None):
            if stop_event is not None:
                stop_event.wait(2.0)
            return
            yield  # pragma: no cover

    worker = AISIngestionWorker(
        _SilentProvider(),
        live_timeout_seconds=30.0,
        clock=lambda: now[0],
    )
    worker.start()
    now[0] = now[0] + timedelta(seconds=31)
    assert worker.status().state == "DEGRADED"
    assert worker.stop(timeout=1.0)

def test_worker_reset_discards_pending_queue_and_clears_telemetry():
    provider = _BlockingProvider()
    worker = AISIngestionWorker(provider, queue_capacity=100)
    worker.start()
    assert provider.started.wait(1.0)
    deadline = time.monotonic() + 1.0
    while worker.status().messages_received == 0 and time.monotonic() < deadline:
        time.sleep(0.005)
    assert worker.stop(timeout=1.0)
    worker.reset()

    status = worker.status()
    assert status.state == "STOPPED"
    assert status.started_at is None
    assert status.queue_depth == 0
    assert status.messages_received == 0
    assert status.thread_alive is False

