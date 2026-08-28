"""Streamlit page renderers. All pages consume the engine snapshot and never create data."""

from src.ui.pages_impl import (  # noqa: F401
    render_anomalies,
    render_behavior,
    render_data_quality,
    render_overview,
    render_similarity,
    render_system,
    render_traffic,
    render_trajectory_analysis,
    render_vessel_intelligence,
    render_vessels,
)

__all__ = [
    "render_anomalies",
    "render_behavior",
    "render_data_quality",
    "render_overview",
    "render_similarity",
    "render_system",
    "render_traffic",
    "render_trajectory_analysis",
    "render_vessel_intelligence",
    "render_vessels",
]
