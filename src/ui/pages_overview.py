"""Full-width operational overview renderer — Operations Workstation layout."""
from __future__ import annotations

import streamlit as st

from src.config.regions import region_name_for_bbox
from src.config.settings import AppSettings
from src.geospatial.map_data import vessel_rows
from src.intelligence.engine import EngineSnapshot, MaritimeIntelligenceEngine
from src.ui.pages_helpers import (
    MAP_STYLES,
    _render_vessel_map,
    render_connection_banner,
    render_metric_strip,
)
from src.ui.presentation import render_section_header
from src.ui.vessel_popup import render_vessel_quick_intelligence

_WORKSTATION_CSS = """
<style>
.st-key-tactical-vessel-panel {
    position: fixed;
    top: 7.7rem;
    right: 1.25rem;
    width: min(23rem, 30vw);
    max-height: calc(100vh - 9.5rem);
    overflow-y: auto;
    z-index: 1000;
    background: rgba(12, 18, 28, 0.94);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 0.75rem;
    box-shadow: 0 12px 35px rgba(0, 0, 0, 0.35);
    backdrop-filter: blur(10px);
}
@media (max-width: 900px) {
    .st-key-tactical-vessel-panel {
        position: static;
        width: auto;
        max-height: none;
        margin-top: 0.75rem;
    }
}
</style>
"""


def _render_map_controls() -> tuple[float, bool, str, bool, bool, bool, bool, bool, bool, bool]:
    """Render compact map controls without consuming map width."""
    with st.popover("MAP CONTROLS", use_container_width=False):
        min_speed = st.slider(
            "Minimum SOG (kn)",
            0.0,
            40.0,
            0.0,
            0.5,
            key="overview_min_speed",
        )
        only_fresh = st.checkbox(
            "Fresh reports only",
            value=False,
            key="overview_only_fresh",
        )
        map_style = st.selectbox(
            "Basemap",
            options=list(MAP_STYLES.keys()),
            key="overview_map_style",
        )
        show_vectors = st.checkbox("Heading vectors", value=True, key="overview_show_vectors")
        show_trails = st.checkbox("Observed trails", value=True, key="overview_show_trails")
        show_behavior = st.checkbox("Behavioral findings", value=True, key="overview_show_behavior")
        show_density = st.checkbox("Traffic density", value=False, key="overview_show_density")
        show_hexbin = st.checkbox("Traffic hexbin", value=False, key="overview_show_hexbin")
        show_speed_field = st.checkbox("Speed field", value=False, key="overview_show_speed_field")
        show_anomaly_hotspots = st.checkbox("Anomaly hotspots", value=True, key="overview_show_anomaly_hotspots")

    return (
        min_speed,
        only_fresh,
        map_style,
        show_vectors,
        show_trails,
        show_behavior,
        show_density,
        show_hexbin,
        show_speed_field,
        show_anomaly_hotspots,
    )


def render_overview(
    engine: MaritimeIntelligenceEngine,
    snapshot: EngineSnapshot,
    settings: AppSettings,
) -> None:
    """Render the operational overview and tactical vessel workstation."""
    st.markdown(_WORKSTATION_CSS, unsafe_allow_html=True)
    render_section_header("MARITIME INTELLIGENCE / OVERVIEW")
    render_connection_banner(engine)
    render_metric_strip(snapshot)

    (
        min_speed,
        only_fresh,
        map_style,
        show_vectors,
        show_trails,
        show_behavior,
        show_density,
        show_hexbin,
        show_speed_field,
        show_anomaly_hotspots,
    ) = _render_map_controls()

    rows = vessel_rows(snapshot.vessels)
    _render_vessel_map(
        rows,
        settings=settings,
        min_speed=min_speed,
        only_fresh=only_fresh,
        map_style=map_style,
        show_vectors=show_vectors,
        show_trails=show_trails,
        show_behavior=show_behavior,
        show_density=show_density,
        show_hexbin=show_hexbin,
        show_speed_field=show_speed_field,
        show_anomaly_hotspots=show_anomaly_hotspots,
    )

    selected_mmsi = st.session_state.get("selected_mmsi")
    if selected_mmsi:
        with st.container(key="tactical-vessel-panel", border=True):
            render_vessel_quick_intelligence(snapshot, selected_mmsi)
    else:
        render_vessel_quick_intelligence(snapshot, selected_mmsi)

    st.caption(
        f"Region: {region_name_for_bbox(settings.bbox)} · AIS REAL ONLY · "
        "Map controls float above the map without reducing its width."
    )
