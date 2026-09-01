"""Streamlit page renderers.

All pages consume the engine snapshot and never create data.
"""

from src.ui.pages_helpers import _vessel_label  # noqa: F401

from src.ui.pages_a import (  # noqa: F401
    render_behavior,
    render_trajectory_analysis,
    render_vessel_intelligence,
    render_vessels,
)
from src.ui.pages_b import (  # noqa: F401
    render_anomalies,
    render_data_quality,
    render_similarity,
    render_system as _render_system,
    render_traffic,
)
from src.ui.pages_overview import render_overview
from src.ui.temporal_diagnostics import render_temporal_diagnostics


def render_system(engine, snapshot, settings):
    """Render the existing system page plus real-AIS temporal diagnostics."""
    _render_system(engine, snapshot, settings)
    render_temporal_diagnostics(engine)


__all__ = [
    "_vessel_label",
    "render_anomalies",
    "render_data_quality",
    "render_overview",
    "render_similarity",
    "render_system",
    "render_traffic",
    "render_trajectory_analysis",
    "render_vessel_intelligence",
    "render_vessels",
    "render_behavior",
]
