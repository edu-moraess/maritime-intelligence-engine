"""Streamlit workspace renderers.

The workspace layer owns navigation between the stable UI capabilities.
Individual renderers remain isolated so this refactor does not change the
underlying AIS, behavior, anomaly, historical, or temporal implementations.
"""

import streamlit as st

from src.ui.pages_helpers import _vessel_label  # noqa: F401

from src.ui.pages_a import (
    render_behavior,
    render_trajectory_analysis,
    render_vessel_intelligence,
    render_vessels,
)
from src.ui.pages_b import (
    render_anomalies,
    render_data_quality,
    render_similarity,
    render_system as _render_system,
    render_traffic,
)
from src.ui.pages_overview import render_overview
from src.ui.temporal_diagnostics import render_temporal_diagnostics


def render_intelligence(engine, snapshot, settings):
    """Render all vessel-investigation capabilities in one workspace."""
    subview = st.radio(
        "Investigation",
        ("Vessel", "Behavior", "Trajectory", "Anomalies"),
        horizontal=True,
        label_visibility="collapsed",
    )
    if subview == "Vessel":
        render_vessel_intelligence(engine, snapshot, settings)
    elif subview == "Behavior":
        render_behavior(engine, snapshot, settings)
    elif subview == "Trajectory":
        render_trajectory_analysis(engine, snapshot, settings)
    else:
        render_anomalies(engine, snapshot, settings)


def render_system(engine, snapshot, settings):
    """Render system status, data quality, and optional temporal diagnostics."""
    _render_system(engine, snapshot, settings)
    with st.expander("Data quality", expanded=False):
        render_data_quality(engine, snapshot, settings)
    render_temporal_diagnostics(engine)


__all__ = [
    "_vessel_label",
    "render_anomalies",
    "render_behavior",
    "render_data_quality",
    "render_intelligence",
    "render_overview",
    "render_similarity",
    "render_system",
    "render_traffic",
    "render_trajectory_analysis",
    "render_vessel_intelligence",
    "render_vessels",
]
