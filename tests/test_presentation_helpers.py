"""UI presentation helper tests (no business logic)."""

from __future__ import annotations

import sys
from types import ModuleType
from contextlib import nullcontext

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
