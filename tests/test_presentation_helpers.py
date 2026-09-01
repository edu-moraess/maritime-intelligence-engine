"""UI presentation helper tests (no business logic)."""

from __future__ import annotations

import ast
import sys
from contextlib import nullcontext
from pathlib import Path
from types import ModuleType


# Streamlit may be absent in lightweight CI/dev shells — provide a stub.
if "streamlit" not in sys.modules:
    st = ModuleType("streamlit")
    st.markdown = lambda *a, **k: None
    st.columns = lambda n, **k: [nullcontext() for _ in range(n if isinstance(n, int) else len(n))]
    st.write = lambda *a, **k: None
    st.caption = lambda *a, **k: None
    st.session_state = {}
    sys.modules["streamlit"] = st

from src.ui.presentation import provenance_badge, _intel_chip_class


def test_provenance_badges_distinguishable():
    live = provenance_badge("LIVE")
    hist = provenance_badge("HISTORICAL")
    derived = provenance_badge("DERIVED")
    insuff = provenance_badge("INSUFFICIENT DATA")
    assert "prov-live" in live and "LIVE" in live
    assert "prov-historical" in hist and "HISTORICAL" in hist
    assert "prov-derived" in derived and "DERIVED" in derived
    assert "prov-insufficient" in insuff


def test_provenance_insufficient_underscore_form():
    html = provenance_badge("INSUFFICIENT_DATA")
    assert "prov-insufficient" in html
    assert "INSUFFICIENT DATA" in html


def test_intel_chip_classes():
    assert _intel_chip_class("READY") == "intel-ready"
    assert _intel_chip_class("PARTIAL") == "intel-partial"
    assert _intel_chip_class("WAITING") == "intel-waiting"
    assert _intel_chip_class("ENABLED") == "intel-enabled"
    assert _intel_chip_class("N/A") == "intel-disabled"


def test_pages_helpers_public_surface_for_pages_consumers():
    """Symbols used by pages_a / pages_b / overview must remain re-exported.

    Parsed from source so the surface contract does not require ML/runtime deps.
    """
    source = Path("src/ui/pages_helpers.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    available: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            available.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    available.add(target.id)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                available.add(alias.asname or alias.name)

    required = {
        "MAP_STYLES",
        "_no_real_data_reason",
        "_plot_layout",
        "_render_anomaly_map",
        "_render_readiness",
        "_render_similarity_search",
        "_render_speed_chart",
        "_render_track_chart",
        "_render_vessel_map",
        "_select_vessel",
        "_selected_vessel",
        "_track_readiness_reason",
        "_utc",
        "_vessel_compact",
        "_vessel_label",
    }
    missing = sorted(required - available)
    assert missing == [], f"missing pages_helpers exports: {missing}"


def test_render_vessel_map_surface_defaults_and_selection_contract():
    """Map contract used by Overview / pages_a must stay stable.

    Inspects source of the render module to avoid importing the full engine graph.
    """
    path = Path("src/ui/_pages_map_render.py")
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_render_vessel_map"
    )

    defaults = {}
    positional = [a for a in fn.args.args]
    default_vals = list(fn.args.defaults)
    for name_node, default_node in zip(positional[-len(default_vals) :], default_vals):
        defaults[name_node.arg] = ast.literal_eval(default_node)

    assert defaults.get("show_density") is False
    assert defaults.get("show_hexbin") is False
    assert defaults.get("show_speed_field") is False
    assert defaults.get("show_anomaly_hotspots") is False
    assert defaults.get("map_style") == "Dark Matter"
    assert defaults.get("show_operational_strip") is True

    assert "AIS_TARGETS_LAYER_ID" in source
    assert "id=AIS_TARGETS_LAYER_ID" in source or "id = AIS_TARGETS_LAYER_ID" in source
    assert 'selection_mode="single-object"' in source or "selection_mode='single-object'" in source
    assert 'key="operational_ais_map"' in source or "key='operational_ais_map'" in source

    assert "legend_markdown()" in source
    assert "if show_operational_strip:" in source
