from types import SimpleNamespace

import pytest

import app
from src.config.settings import AppSettings, DEFAULT_BBOX


class _FakeStore:
    def __init__(self, items=None):
        self.items = list(items or [])
        self.extended = []

    def all(self):
        return list(self.items)

    def extend(self, items):
        self.extended.extend(items)


class _FakeEngine:
    def __init__(self, settings, *, stopped=True, items=None):
        self.settings = settings
        self.stop_result = stopped
        self.stop_calls = 0
        self.store = _FakeStore(items)
        self.historical_writer = SimpleNamespace(close=lambda: None)

    def stop_live_monitoring(self, timeout=10.0):
        self.stop_calls += 1
        return self.stop_result


def test_process_registry_reuses_one_engine_for_same_configuration(monkeypatch):
    settings = AppSettings(aisstream_api_key="key", bbox=DEFAULT_BBOX)
    created = []

    def factory(candidate):
        engine = _FakeEngine(candidate)
        created.append(engine)
        return engine

    monkeypatch.setattr(app, "create_engine", factory)
    registry = app._ProcessEngineRegistry()

    first = registry.get(("config-a",), settings)
    second = registry.get(("config-a",), settings)

    assert first is second
    assert len(created) == 1


def test_process_registry_stops_old_worker_and_transfers_observations(monkeypatch):
    settings_a = AppSettings(aisstream_api_key="key", bbox=DEFAULT_BBOX)
    settings_b = AppSettings(
        aisstream_api_key="key",
        bbox=((1.0, 1.0), (2.0, 2.0)),
    )
    archived = [SimpleNamespace(mmsi="123456789")]
    created = []

    def factory(candidate):
        engine = _FakeEngine(candidate)
        created.append(engine)
        return engine

    monkeypatch.setattr(app, "create_engine", factory)
    registry = app._ProcessEngineRegistry()
    first = registry.get(("config-a",), settings_a)
    first.store.items = archived

    second = registry.get(("config-b",), settings_b)

    assert first.stop_calls == 1
    assert second is created[1]
    assert second.store.extended == archived


def test_process_registry_refuses_replacement_when_old_worker_is_alive(monkeypatch):
    settings_a = AppSettings(aisstream_api_key="key", bbox=DEFAULT_BBOX)
    settings_b = AppSettings(
        aisstream_api_key="key",
        bbox=((1.0, 1.0), (2.0, 2.0)),
    )
    created = []

    def factory(candidate):
        engine = _FakeEngine(candidate, stopped=False)
        created.append(engine)
        return engine

    monkeypatch.setattr(app, "create_engine", factory)
    registry = app._ProcessEngineRegistry()
    registry.get(("config-a",), settings_a)

    with pytest.raises(RuntimeError, match="refusing to start a second subscription"):
        registry.get(("config-b",), settings_b)

    assert len(created) == 1
