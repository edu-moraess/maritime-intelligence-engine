"""Full-width operational overview renderer — Operations Workstation layout."""
from __future__ import annotations

import streamlit as st

from src.config.regions import region_name_for_bbox
from src.config.settings import AppSettings
from src.geospatial.map_data import live_vessel_rows, vessel_rows
from src.intelligence.engine import EngineSnapshot, MaritimeIntelligenceEngine
from src.ui.pages_helpers import (
    MAP_STYLES,
    _render_vessel_map,
    _selected_vessel,
    _utc,
)
from src.ui.presentation import render_ops_bar
from src.ui.vessel_popup import render_vessel_quick_intelligence
from src.ui.workspace_controls import render_aux_workspace_controls

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

/* Keep the tactical map visually clean by hiding the basemap attribution UI. */
.mapboxgl-ctrl-attrib,
.maplibregl-ctrl-attrib {
    display: none !important;
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


def _render_map_controls(container) -> tuple[float, bool, str, bool, bool, bool, bool, bool, bool, bool]:
    """Render compact map controls without consuming map width."""
    with container.popover("MAP CONTROLS", use_container_width=False):
        min_speed = st.slider(
            "Minimum SOG (kn)",
            0.0,
            40.0,
            0.0,
            0.5,
            key="overview_min_speed",
        )
        include_stale = st.checkbox(
            "Include stale session targets",
            value=False,
            key="overview_include_stale",
            help="Off keeps the operational map live-only. Session observations and temporal tracks are never deleted.",
        )
        map_style = st.selectbox(
            "Basemap",
            options=list(MAP_STYLES.keys()),
            key="overview_map_style",
        )
        show_vectors = st.checkbox("Heading vectors", value=True, key="overview_show_vectors")
        show_trails = st.checkbox("Observed trails", value=True, key="overview_show_trails")
        show_behavior = st.checkbox("Behavioral findings", value=True, key="overview_show_behavior")
        show_hexbin = st.checkbox("Traffic corridors", value=False, key="overview_show_hexbin")
        show_anomaly_types = st.checkbox("Anomaly types", value=False, key="overview_show_anomaly_types")
        show_freshness = st.checkbox("Track freshness", value=False, key="overview_show_freshness")
        show_anomaly_hotspots = st.checkbox(
            "Anomaly hotspots",
            value=True,
            key="overview_show_anomaly_hotspots",
        )

    return (
        min_speed,
        include_stale,
        map_style,
        show_vectors,
        show_trails,
        show_behavior,
        show_hexbin,
        show_anomaly_types,
        show_freshness,
        show_anomaly_hotspots,
    )


def _render_workspace_controls(engine: MaritimeIntelligenceEngine, settings: AppSettings):
    """Render Map Controls, Data, Analysis, and System in one main-workspace row."""
    columns = st.columns(4)
    map_values = _render_map_controls(columns[0])
    render_aux_workspace_controls(engine, settings, columns[1:])
    return map_values


def render_overview(
    engine: MaritimeIntelligenceEngine,
    snapshot: EngineSnapshot,
    settings: AppSettings,
) -> None:
    """Render the operational overview and tactical vessel workstation."""
    st.markdown(_WORKSTATION_CSS, unsafe_allow_html=True)

    summary = snapshot.summary
    region = region_name_for_bbox(settings.bbox) or "CUSTOM"
    duration = (
        f"Collection {snapshot.last_collection_seconds:.1f}s"
        if snapshot.last_collection_seconds > 0
        else "Collection —"
    )
    render_ops_bar(
        live_state=snapshot.status.state,
        region=region,
        vessels=summary["active_vessels"],
        messages=f"{summary['messages']:,}",
        anomalies=summary["anomalies"],
        collection=duration,
        provenance="AIS REAL ONLY",
        avg_speed=f"{summary['average_speed_knots']:.1f} kn",
        last_message=_utc(snapshot.status.last_received_at),
    )

    (
        min_speed,
        include_stale,
        map_style,
        show_vectors,
        show_trails,
        show_behavior,
        show_hexbin,
        show_anomaly_types,
        show_freshness,
        show_anomaly_hotspots,
    ) = _render_workspace_controls(engine, settings)

    rows = vessel_rows(snapshot.vessels) if include_stale else live_vessel_rows(snapshot.vessels)
    if min_speed > 0:
        rows = [
            row
            for row in rows
            if row.get("sog_knots") is not None and float(row["sog_knots"]) >= min_speed
        ]

    _render_vessel_map(
        rows,
        snapshot=snapshot,
        settings=settings,
        show_heading=show_vectors,
        show_trails=show_trails,
        show_anomalies=show_behavior,
        show_hexbin=show_hexbin,
        show_anomaly_types=show_anomaly_types,
        show_freshness=show_freshness,
        show_anomaly_hotspots=show_anomaly_hotspots,
        map_style=map_style,
    )

    selected = _selected_vessel(snapshot.vessels)
    if selected is not None:
        with st.container(key="tactical-vessel-panel", border=True):
            render_vessel_quick_intelligence(
                selected,
                snapshot,
                show_gemini_hook=True,
                engine=engine,
            )
    else:
        render_vessel_quick_intelligence(
            selected,
            snapshot,
            show_gemini_hook=True,
            engine=engine,
        )

    st.caption(
        "Operational intelligence derived from live AIS observations. "
        f"Region: {region} · AIS REAL ONLY · "
        "Map controls and workspace modules sit above the tactical map."
    )
    if map_style == "Nautical Chart":
        st.caption(
            "Nautical chart: © Open Waters: Seamap · © OpenStreetMap contributors "
            "· CC BY 4.0. Not for navigational use; consult official nautical charts."
        )
