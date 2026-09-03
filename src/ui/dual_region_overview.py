"""Dual-region overview rendering with strict per-region map scoping."""
from __future__ import annotations

from dataclasses import replace

import streamlit as st

from src.config.regions import format_bbox, region_name_for_bbox
from src.config.settings import AppSettings, RegionBBox
from src.geospatial.map_data import filter_rows_to_bboxes, live_vessel_rows, vessel_rows
from src.intelligence.engine import EngineSnapshot, MaritimeIntelligenceEngine
from src.ui.pages_overview import _render_workspace_controls
from src.ui.pages_helpers import _render_vessel_map, _selected_vessel
from src.ui.presentation import render_ops_bar
from src.ui.vessel_popup import render_vessel_quick_intelligence


def _in_bbox(latitude: float | None, longitude: float | None, bbox: RegionBBox) -> bool:
    if latitude is None or longitude is None:
        return False
    (min_lat, min_lon), (max_lat, max_lon) = bbox
    return min_lat <= float(latitude) <= max_lat and min_lon <= float(longitude) <= max_lon


def _regional_snapshot(snapshot: EngineSnapshot, bbox: RegionBBox) -> EngineSnapshot:
    """Create a presentation-only snapshot containing only one region."""
    observations = [o for o in snapshot.observations if _in_bbox(o.latitude, o.longitude, bbox)]
    vessels = [v for v in snapshot.vessels if _in_bbox(v.latitude, v.longitude, bbox)]
    findings = [f for f in snapshot.findings if _in_bbox(f.latitude, f.longitude, bbox)]
    speeds = [float(o.sog_knots) for o in observations if o.sog_knots is not None]
    summary = dict(snapshot.summary)
    summary.update({"active_vessels": len(vessels), "messages": len(observations), "anomalies": len(findings), "average_speed_knots": (sum(speeds) / len(speeds)) if speeds else 0.0})
    return replace(snapshot, observations=observations, vessels=vessels, findings=findings, summary=summary)


def _render_region_map(label: str, bbox: RegionBBox, snapshot: EngineSnapshot, settings: AppSettings, controls) -> None:
    min_speed, include_stale, map_style, show_vectors, show_trails, show_behavior, show_hexbin, show_anomaly_types, show_freshness, show_anomaly_hotspots = controls
    region_snapshot = _regional_snapshot(snapshot, bbox)
    region_settings = replace(settings, bbox=bbox, monitoring_bboxes=(bbox,))
    rows = vessel_rows(region_snapshot.vessels) if include_stale else live_vessel_rows(region_snapshot.vessels)
    rows = filter_rows_to_bboxes(rows, (bbox,))
    if min_speed > 0:
        rows = [row for row in rows if row.get("sog_knots") is not None and float(row["sog_knots"]) >= min_speed]
    region_name = region_name_for_bbox(bbox) or label
    st.caption(f"{label} · {region_name} · {format_bbox(bbox)}")

    # The shared map renderer historically used one fixed Streamlit key. Two
    # region maps are separate stateful PyDeck widgets, so scope that key to
    # the region while the renderer executes. This preserves its selection
    # handling without duplicating the whole tactical map implementation.
    original_pydeck_chart = st.pydeck_chart

    def _scoped_pydeck_chart(*args, **kwargs):
        kwargs["key"] = f"operational_ais_map_{label.lower()}"
        return original_pydeck_chart(*args, **kwargs)

    st.pydeck_chart = _scoped_pydeck_chart
    try:
        _render_vessel_map(rows, snapshot=region_snapshot, settings=region_settings, show_heading=show_vectors, show_trails=show_trails, show_anomalies=show_behavior, show_hexbin=show_hexbin, show_anomaly_types=show_anomaly_types, show_freshness=show_freshness, show_anomaly_hotspots=show_anomaly_hotspots, map_style=map_style)
    finally:
        st.pydeck_chart = original_pydeck_chart


def render_overview(engine: MaritimeIntelligenceEngine, snapshot: EngineSnapshot, settings: AppSettings) -> None:
    """Render A+B as separate tactical views while retaining one MIE session/subscription."""
    summary = snapshot.summary
    monitoring = tuple(settings.monitoring_bboxes)
    region = "A + B" if len(monitoring) > 1 else (region_name_for_bbox(settings.bbox) or "CUSTOM")
    duration = f"Collection {snapshot.last_collection_seconds:.1f}s" if snapshot.last_collection_seconds > 0 else "Collection —"
    render_ops_bar(live_state=snapshot.status.state, region=region, vessels=summary["active_vessels"], messages=f"{summary['messages']:,}", anomalies=summary["anomalies"], collection=duration, provenance="AIS REAL ONLY", avg_speed=f"{summary['average_speed_knots']:.1f} kn", last_message=snapshot.status.last_received_at.strftime("%H:%M:%S UTC") if snapshot.status.last_received_at else "—")
    controls = _render_workspace_controls(engine, settings)

    if len(monitoring) >= 2:
        names = [region_name_for_bbox(b) or f"Region {chr(65 + i)}" for i, b in enumerate(monitoring[:2])]
        tabs = st.tabs([f"A · {names[0]}", f"B · {names[1]}"])
        for index, (tab, bbox) in enumerate(zip(tabs, monitoring[:2])):
            with tab:
                _render_region_map(chr(65 + index), bbox, snapshot, settings, controls)
    else:
        _render_region_map("Region A", monitoring[0] if monitoring else settings.bbox, snapshot, settings, controls)

    selected = _selected_vessel(snapshot.vessels)
    if selected is not None:
        with st.container(key="tactical-vessel-panel", border=True):
            render_vessel_quick_intelligence(selected, snapshot, show_gemini_hook=True, engine=engine)
    else:
        render_vessel_quick_intelligence(selected, snapshot, show_gemini_hook=True, engine=engine)

    st.caption("Operational intelligence derived from live AIS observations. " + f"Regions: {region} · AIS REAL ONLY · Each region is geographically isolated in the tactical view.")
    if controls[2] == "Nautical Chart":
        st.caption("Nautical chart: © Open Waters: Seamap · © OpenStreetMap contributors · CC BY 4.0. Not for navigational use; consult official nautical charts.")
