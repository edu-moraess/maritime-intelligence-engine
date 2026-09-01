"""Sidebar surface contract tests (presentation only; no AIS/runtime)."""

from __future__ import annotations

import ast
from pathlib import Path

from src.config.settings import COLLECTION_DURATION_OPTIONS


APP_PATH = Path("app.py")


def _app_source() -> str:
    return APP_PATH.read_text(encoding="utf-8")


def _render_sidebar_node() -> ast.FunctionDef:
    tree = ast.parse(_app_source())
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "_render_sidebar":
            return node
    raise AssertionError("_render_sidebar not found in app.py")


def test_sidebar_session_state_keys_preserved():
    source = _app_source()
    required_keys = [
        "collection_duration_seconds",
        "region_preset",
        "bbox_min_lat",
        "bbox_min_lon",
        "bbox_max_lat",
        "bbox_max_lon",
        "active_bbox",
        "historical_persistence_enabled",
        "operator_timezone",
        "workspace_module",
        "workspace_subarea_",
    ]
    missing = [key for key in required_keys if key not in source]
    assert missing == [], f"missing sidebar keys: {missing}"


def test_collection_duration_options_unchanged():
    assert COLLECTION_DURATION_OPTIONS == (30, 60, 120, 180)


def test_navigation_structure_stable():
    tree = ast.parse(_app_source())
    nav = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "NAVIGATION":
                    nav = ast.literal_eval(node.value)
    assert isinstance(nav, dict)
    assert list(nav.keys()) == [
        "Overview",
        "Vessels",
        "Movement & Behavior",
        "Anomalies & Traffic",
        "Data & System",
    ]
    assert nav["Overview"] == ("Overview",)
    assert nav["Vessels"] == ("Fleet", "Vessel Intelligence")
    assert nav["Movement & Behavior"] == (
        "Trajectory Analysis",
        "Behavior",
        "Similarity",
    )
    assert nav["Anomalies & Traffic"] == ("Anomalies", "Traffic")
    assert nav["Data & System"] == ("Data Quality", "System")


def test_render_sidebar_return_contract():
    fn = _render_sidebar_node()
    returns = [n for n in fn.body if isinstance(n, ast.Return)]
    assert returns, "expected return statement"
    last = returns[-1]
    assert isinstance(last.value, ast.Tuple)
    assert len(last.value.elts) == 5


def test_historical_disabled_when_no_database_url():
    source = _app_source()
    assert 'key="historical_persistence_enabled"' in source
    assert "disabled=settings.database_url is None" in source


def test_collect_button_primary_and_config_error_gate():
    source = _app_source()
    assert '"Collect Real AIS"' in source
    assert 'type="primary"' in source
    assert "disabled=settings.config_error is not None" in source
    assert '"Clear Session"' in source


def test_sidebar_sections_present():
    source = _app_source()
    for label in (
        "MISSION CONTEXT",
        "DATA",
        "ANALYSIS",
        "SYSTEM",
        "MARITIME INTELLIGENCE",
        "AISSTREAM",
    ):
        assert label in source, label


def test_no_map_controls_in_sidebar():
    """Sidebar UX v1 must not host map layer toggles."""
    fn = _render_sidebar_node()
    source = ast.get_source_segment(_app_source(), fn) or ""
    for forbidden in (
        "map_show_heading",
        "map_show_trails",
        "map_show_density",
        "map_show_hexbin",
        "map_show_speed_field",
        "map_show_anomaly_hotspots",
        "overview_min_speed",
    ):
        assert forbidden not in source, forbidden
