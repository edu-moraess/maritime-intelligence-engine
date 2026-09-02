"""Full-width operational overview renderer — Operations Workstation layout."""

from __future__ import annotations

import streamlit as st

from src.config.regions import region_name_for_bbox
from src.config.settings import AppSettings
from src.geospatial.map_data import vessel_rows
from src.intelligence.engine import EngineSnapshot, MaritimeIntelligenceEngine
from src.ui.pages_helpers import (
    MAP_STYLES,
    _no_real_data_reason,
    _render_readiness,
    _render_vessel_map,
    _selected_vessel,
    _utc,
)
from src.ui.presentation import (
    empty_state,
    panel_title,
    render_ops_bar,
)
from src.ui.vessel_popup import render_vessel_quick_intelligence


_WORKSTATION_CSS = """
<style>
/* Keep the operational map full-width while optional intelligence floats above it. */
[data-testid="stVerticalBlock"]:has(.st-key-tactical-vessel-panel) {
    position: fixed !important;
    top: 7.7rem;
    right: 1.25rem;
    width: min(23rem, 30vw);
    max-height: calc(100vh - 9.5rem);
    overflow-y: auto;
    z-index: 1000;
    padding: 0.9rem 1rem;
    background: rgba(5, 14, 20, 0.96);
    border: 1px solid #1b3640;
    border-radius: 10px;
    box-shadow: 0 14px 40px rgba(0, 0, 0, 0.42);
    backdrop-filter: blur(10px);
}

[data-testid="stVerticalBlock"]:has(.st-key-tactical-vessel-panel) .stExpander {
    border-color: #1b3640;
}

@media (max-width: 900px) {
    [data-testid="stVerticalBlock"]:has(.st-key-tactical-vessel-panel) {
        position: static !important;
        width: auto;
        max-height: none;
        margin-top: 0.75rem;
    }
}
</style>
"""


def _render_map_controls(
    *,
    settings: AppSettings,
) -> tuple[float, bool, str, bool, bool, bool, bool, bool, bool, bool]:
    """Render compact map controls without consuming map width."""
    with st.popover("MAP CONTROLS", icon="☰", use_container_width=False):
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
            index=list(MAP_STYLES.keys()).index("Dark Matter"),
            key="map_style",
        )
        show_heading = st.checkbox(
            "Heading vectors",
            value=True,
            key="map_show_heading",
        )
        show_trails = st.checkbox(
            "Observed trails",
            value=True,
            key="map_show_trails",
        )
        show_anomalies = st.checkbox(
            "Behavioral findings",
            value=True,
            key="map_show_anomalies",
        )
        show_density = st.checkbox(
            "Traffic density",
            value=False,
            key="map_show_density",
        )
        show_hexbin = st.checkbox(
            "Traffic hexbin",
            value=False,
            key="map_show_hexbin",
        )
        show_speed_field = st.checkbox(
            "Speed field",
            value=False,
            key="map_show_speed_field",
        )
        show_anomaly_hotspots = st.checkbox(
            "Anomaly hotspots",
            value=False,
            key="map_show_anomaly_hotspots",
        )
        st.caption("Real AIS observations only. Controls float above the map and do not reduce its width.")

    del settings
    return (
        min_speed,
        only_fresh,
        map_style,
        show_heading,
        show_trails,
        show_anomalies,
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
    """Render the operational workspace with a full-width map-first hierarchy."""
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

    _render_readiness(snapshot)

    (
        min_speed,
        only_fresh,
        map_style,
        show_heading,
        show_trails,
        show_anomalies,
        show_density,
        show_hexbin,
        show_speed_field,
        show_anomaly_hotspots,
    ) = _render_map_controls(settings=settings)

    rows = vessel_rows(snapshot.vessels)

    if min_speed > 0:
        rows = [
            row
            for row in rows
            if row.get("sog_knots") is not None
            and float(row["sog_knots"]) >= min_speed
        ]

    if only_fresh:
        rows = [row for row in rows if not row.get("stale", False)]

    panel_title("Operational map", f"{len(rows)} targets")
    if not rows:
        empty_state(_no_real_data_reason(snapshot.status.reason))
    else:
        _render_vessel_map(
            rows=rows,
            snapshot=snapshot,
            settings=settings,
            show_heading=show_heading,
            show_trails=show_trails,
            show_anomalies=show_anomalies,
            show_density=show_density,
            show_hexbin=show_hexbin,
            show_speed_field=show_speed_field,
            show_anomaly_hotspots=show_anomaly_hotspots,
            map_style=map_style,
            show_operational_strip=False,
        )

    selected = _selected_vessel(snapshot.vessels)
    if selected is not None:
        with st.container(key="tactical-vessel-panel", border=True):
            st.markdown(
                "<div style='font-family:IBM Plex Mono,monospace;font-size:.65rem;"
                "letter-spacing:.08em;color:#35c2c9;margin-bottom:.35rem'>VESSEL SELECTED</div>",
                unsafe_allow_html=True,
            )
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

    st.caption("Operational intelligence derived from live AIS observations.")
