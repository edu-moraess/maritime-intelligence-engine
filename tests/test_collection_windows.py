from __future__ import annotations

import threading

from src.ingestion import aisstream
from src.ingestion.aisstream import AISStreamProvider


class _FakeSocket:
    def __init__(self, frame: str) -> None:
        self.frame = frame
        self.sent: list[str] = []
        self.closed = False
        self._read = False

    def send(self, payload: str) -> None:
        self.sent.append(payload)

    def settimeout(self, _timeout: float) -> None:
        return None

    def recv(self) -> str:
        if not self._read:
            self._read = True
            return self.frame
        raise RuntimeError("socket closed by test")

    def close(self) -> None:
        self.closed = True


def _frame(mmsi: int, latitude: float, longitude: float, timestamp: int) -> str:
    return (
        '{"MessageType":"PositionReport",'
        '"MetaData":{"MMSI":%d,"ShipName":"TEST"},'
        '"Message":{"PositionReport":{"UserID":%d,"Latitude":%s,'
        '"Longitude":%s,"Timestamp":%d,"Valid":true,"Sog":5.0,'
        '"Cog":90.0,"TrueHeading":90}}}'
        % (mmsi, mmsi, latitude, longitude, timestamp)
    )


def test_sequential_windows_reset_only_window_message_limit(monkeypatch):
    frames = [
        _frame(367000001, 1.0, 2.0, 10),
        _frame(367000001, 1.1, 2.1, 20),
    ]
    sockets: list[_FakeSocket] = []

    def create_connection(*_args, **_kwargs):
        socket = _FakeSocket(frames[len(sockets)])
        sockets.append(socket)
        return socket

    monkeypatch.setattr(aisstream.websocket, "create_connection", create_connection)

    provider = AISStreamProvider(
        api_key="k",
        bbox=[[[1.0, 2.0], [3.0, 4.0]]],
        max_messages=1,
    )

    first = list(provider.stream(threading.Event(), duration_seconds=None))
    second = list(provider.stream(threading.Event(), duration_seconds=None))

    assert len(first) == 1
    assert len(second) == 1
    assert provider.status.messages_received == 2
    observations = first + second
    assert [observation.mmsi for observation in observations] == ["367000001", "367000001"]
    assert [observation.latitude for observation in observations] == [1.0, 1.1]
    assert [observation.longitude for observation in observations] == [2.0, 2.1]
    assert len(sockets) == 2
    assert all(socket.sent for socket in sockets)
    assert all(socket.closed for socket in sockets)


class _FakeHistoricalWriter:
    def persist_collection(self, *_args, **_kwargs):
        return type("_Result", (), {"session_id": None})()


def test_collect_starts_live_window_before_historical_restore(monkeypatch):
    from datetime import datetime, timezone

    from src.ingestion.models import AISObservation
    from src.intelligence.engine import MaritimeIntelligenceEngine
    from src.storage.memory import ObservationStore

    events: list[str] = []

    class _Provider:
        def stream(self, _stop_event, *, duration_seconds):
            events.append(f"stream-start:{duration_seconds}")
            yield AISObservation(
                "367000001",
                1.0,
                2.0,
                datetime.now(timezone.utc),
                ais_timestamp_second=10,
                sog_knots=5.0,
                cog_degrees=90.0,
                heading_degrees=90.0,
            )
            events.append("stream-end")

    engine = MaritimeIntelligenceEngine.__new__(MaritimeIntelligenceEngine)
    engine.provider = _Provider()
    engine.store = ObservationStore(max_messages=10)
    engine.settings = type(
        "_Settings",
        (),
        {
            "bbox": ((1.0, 2.0), (3.0, 4.0)),
            "monitoring_bboxes": (((1.0, 2.0), (3.0, 4.0)),),
        },
    )()
    engine.historical_writer = _FakeHistoricalWriter()
    engine._historical_persistence_enabled = False
    engine.historical_result = None
    engine.last_collection_seconds = 0.0
    engine.current_session_observations = []
    engine.current_session_findings = []
    engine._recompute = lambda: None
    engine._detect_current_session_findings = lambda: []

    def restore():
        events.append("restore")
        assert "stream-end" in events
        return 0

    engine._restore_historical_context = restore

    assert engine.collect(seconds=0.1) == 1
    assert events == ["stream-start:0.1", "stream-end", "restore"]
