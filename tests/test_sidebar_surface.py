"""Sidebar and workspace surface contract tests (presentation only)."""

from __future__ import annotations

import ast
from pathlib import Path

from src.config.settings import COLLECTION_DURATION_OPTIONS


APP_PATH = Path("app.py")
WORKSPACE_PATH = Path("src/ui/workspace_controls.py")
OVERVIEW_PATH = Path("src/ui/pages_overview.py")


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _render_sidebar_node() -> ast.FunctionDef:
    tree = ast.parse(_source(APP_PATH))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "_render_sidebar":
            return node
    raise AssertionError("_render_sidebar not found in app.py")


def test_sidebar_keeps_mission_and_map_controls():
    source = _source(APP_PATH)
    assert 'st.expander("MAP CONFIGURATION", expanded=False)' in source
    assert 'st.expander("MISSION CONTEXT", expanded=False)' in source
    assert '"Collect Real AIS · 2 Regions"' in source
    assert '"Clear Session"' in source


def test_sidebar_no_longer_renders_workspace_modules():
    fn_source = ast.get_source_segment(_source(APP_PATH), _render_sidebar_node()) or ""
    assert 'st.expander("DATA"' not in fn_source
    assert 'st.expander("ANALYSIS"' not in fn_source
    assert 'st.expander("SYSTEM"' not in fn_source


def test_workspace_modules_live_in_main_content():
    source = _source(WORKSPACE_PATH)
    assert 'st.popover("DATA"' in source
    assert 'st.popover("ANALYSIS"' in source
    assert 'st.popover("SYSTEM"' in source
    assert "render_aux_workspace_controls" in source


def test_historical_persistence_lives_under_system_controls():
    source = _source(WORKSPACE_PATH)
    data_block = source[source.index('with st.popover("DATA"'):source.index('with st.popover("ANALYSIS"')]
    system_block = source[source.index('with st.popover("SYSTEM"'):]
    assert '"Historical Persistence"' not in data_block
    assert '"Historical Persistence"' in system_block
    assert "_render_historical_persistence(engine, settings)" in system_block


def test_overview_places_map_controls_before_workspace_modules():
    source = _source(OVERVIEW_PATH)
    assert "columns = st.columns(4)" in source
    assert "map_values = _render_map_controls(columns[0])" in source
    assert "render_aux_workspace_controls(engine, settings, columns[1:])" in source


def test_collection_duration_options_include_temporal_windows():
    assert COLLECTION_DURATION_OPTIONS == (30, 60, 120, 180, 300, 600, 900)


def test_navigation_structure_stable():
    source = _source(WORKSPACE_PATH)
    tree = ast.parse(source)
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
        "Anomaly & Traffic",
        "Data & System",
    ]
    assert nav["Overview"] == ("Overview",)
    assert nav["Vessels"] == ("Fleet", "Vessel Intelligence")
    assert nav["Movement & Behavior"] == (
        "Trajectory Analysis",
        "Behavior",
        "Similarity",
    )
    assert nav["Anomaly & Traffic"] == ("Anomalies", "Traffic")
    assert nav["Data & System"] == ("Data Quality", "System")


def test_render_sidebar_return_contract():
    fn = _render_sidebar_node()
    returns = [n for n in fn.body if isinstance(n, ast.Return)]
    assert returns, "expected return statement"
    last = returns[-1]
    assert isinstance(last.value, ast.Tuple)
    assert len(last.value.elts) == 5


def test_no_map_controls_in_sidebar():
    """Sidebar must not host the tactical map layer toggles."""
    fn_source = ast.get_source_segment(_source(APP_PATH), _render_sidebar_node()) or ""
    for forbidden in (
        "overview_min_speed",
        "overview_only_fresh",
        "overview_map_style",
        "overview_show_vectors",
        "overview_show_trails",
        "overview_show_behavior",
        "overview_show_hexbin",
        "overview_show_anomaly_types",
        "overview_show_freshness",
        "overview_show_anomaly_hotspots",
    ):
        assert forbidden not in fn_source, forbidden


def test_clear_session_resets_all_contact_selection_state():
    """Clearing a live session must remove every region selection namespace."""
    source = _source(APP_PATH)
    clear_block = source[source.index('if clear:'):source.index('if collect:')]
    for key in (
        '"selected_mmsi"',
        '"selected_mmsi_a"',
        '"selected_mmsi_b"',
        '"selected_mmsi_unified"',
    ):
        assert key in clear_block
