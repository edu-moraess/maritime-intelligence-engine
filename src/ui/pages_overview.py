"""Full-width operational overview renderer."""

from __future__ import annotations

import streamlit as st

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
from src.ui.presentation import empty_state, metric_strip, panel_title
from src.ui.vessel_popup import render_vessel_quick_intelligence


def render_overview(
    engine: MaritimeIntelligenceEngine,
    snapshot: EngineSnapshot,
    settings: AppSettings,
) -> None:
    """Render the operational workspace with a full-width map."""
    summary = snapshot.summary

    metric_strip(
        {
            "ACTIVE VESSELS": summary["active_vessels"],
            "MESSAGES": f"{summary['messages']:,}",
            "ANOMALIES": summary["anomalies"],
            "AVG SPEED": f"{summary['average_speed_knots']:.1f} kn",
            "LAST MESSAGE": _utc(snapshot.status.last_received_at),
        }
    )

    _render_readiness(snapshot)
    st.write("")

    # Controls deliberately live outside the map. This prevents the control
    # panel from consuming the horizontal space reserved for the map itself.
    with st.container(border=True):
        panel_title("Map configuration", "operator")

        row_one = st.columns(4, gap="small")
        with row_one[0]:
            min_speed = st.slider(
                "Minimum SOG (kn)",
                0.0,
                40.0,
                0.0,
                0.5,
                key="overview_min_speed",
            )
        with row_one[1]:
            only_fresh = st.checkbox(
                "Fresh reports only",
                value=False,
                key="overview_only_fresh",
            )
        with row_one[2]:
            map_style = st.selectbox(
                "Basemap",
                options=list(MAP_STYLES.keys()),
                index=list(MAP_STYLES.keys()).index("Dark Matter"),
                key="map_style",
            )
        with row_one[3]:
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

        row_two = st.columns(4, gap="small")
        with row_two[0]:
            show_anomalies = st.checkbox(
                "Behavioral findings",
                value=True,
                key="map_show_anomalies",
            )
        with row_two[1]:
            show_density = st.checkbox(
                "Traffic density",
                value=False,
                key="map_show_density",
            )
        with row_two[2]:
            show_hexbin = st.checkbox(
                "Traffic hexbin",
                value=False,
                key="map_show_hexbin",
            )
        with row_two[3]:
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
        st.caption(
            "All visualization layers are derived from real AIS observations "
            "available in the current session. No synthetic traffic or "
            "fallback data is generated."
        )

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
        )
        st.caption("Operational intelligence derived from live AIS observations.")

    selected = _selected_vessel(snapshot.vessels)
    render_vessel_quick_intelligence(
        selected,
        snapshot,
        show_gemini_hook=True,
        engine=engine,
    )
