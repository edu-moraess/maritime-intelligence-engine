"""Regression tests for sidebar connection-state synchronization."""

from pathlib import Path
from types import SimpleNamespace

from app import _connection_state


APP_SOURCE = Path("app.py").read_text(encoding="utf-8")


class SnapshotEngine:
    def __init__(self, state: str, websocket_status: str, bbox: object = None) -> None:
        self._snapshot = SimpleNamespace(
            status=SimpleNamespace(state=state, websocket_status=websocket_status)
        )
        self.settings = SimpleNamespace(bbox=bbox)

    def snapshot(self):
        return self._snapshot


def _settings(bbox: object = None) -> SimpleNamespace:
    return SimpleNamespace(aisstream_api_key="real-key", bbox=bbox)


def test_live_provider_state_is_used_by_sidebar() -> None:
    engine = SnapshotEngine("LIVE AIS", "OPEN")

    assert _connection_state(_settings(), engine) == "LIVE AIS"
    assert "DISCONNECTED" not in _connection_state(_settings(), engine)


def test_live_state_remains_operational_after_finite_websocket_close() -> None:
    engine = SnapshotEngine("LIVE AIS", "CLOSED")

    assert _connection_state(_settings(), engine) == "LIVE AIS"


def test_real_provider_disconnect_is_shown_as_disconnected() -> None:
    engine = SnapshotEngine("DISCONNECTED", "CLOSED")

    assert _connection_state(_settings(), engine) == "DISCONNECTED"


def test_current_engine_state_is_not_replaced_by_stale_bbox_fallback() -> None:
    current_engine = SnapshotEngine("LIVE AIS", "CLOSED", bbox=((1, 2), (3, 4)))
    current_settings = _settings(bbox=((5, 6), (7, 8)))

    assert _connection_state(current_settings, current_engine) == "LIVE AIS"
    assert "existing_engine = st.session_state.get" not in APP_SOURCE
    assert "existing_settings.bbox != settings.bbox" not in APP_SOURCE


def test_sidebar_resolves_engine_after_region_controls_and_uses_snapshot() -> None:
    assert "connection_placeholder = st.empty()" in APP_SOURCE
    assert "engine = _engine_for(settings)" in APP_SOURCE
    assert "conn = _connection_state(settings, engine)" in APP_SOURCE
    assert "connection_placeholder.markdown(" in APP_SOURCE


def test_collection_refreshes_sidebar_after_collection():
    """Sidebar renders before collection, so completion must trigger a rerun."""
    assert 'st.session_state["collection_result"]' in APP_SOURCE
    assert "The sidebar is rendered before collection" in APP_SOURCE
    assert "st.rerun()" in APP_SOURCE
    assert "collection_result = st.session_state.pop(" in APP_SOURCE


def test_collection_result_is_preserved_across_refresh():
    """The rerun must not discard the existing collection result message."""
    assert '"success"' in APP_SOURCE
    assert '"warning"' in APP_SOURCE
    assert "Collection elapsed " in APP_SOURCE
