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
    assert len(provider.fetch_tracks()["367000001"]) == 2
    assert len(sockets) == 2
    assert all(socket.sent for socket in sockets)
    assert all(socket.closed for socket in sockets)
