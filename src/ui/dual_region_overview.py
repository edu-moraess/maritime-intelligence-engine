"""Dual-region overview rendering with isolated tactical views and selection state."""
from __future__ import annotations

from dataclasses import replace

import streamlit as st

from src.config.regions import format_bbox, region_name_for_bbox
from src.config.settings import AppSettings, RegionBBox
from src.geospatial.map_data import filter_rows_to_bboxes, live_vessel_rows, vessel_rows
from src.intelligence.engine import EngineSnapshot, MaritimeIntelligenceEngine
from src.ui import _pages_map_render as map_render
from src.ui.pages_overview import _render_workspace_controls
from src.ui.pages_helpers import _render_vessel_map
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
    summary.update(
        {
            "active_vessels": len(vessels),
            "messages": len(observations),
            "anomalies": len(findings),
            "average_speed_knots": (sum(speeds) / len(speeds)) if speeds else 0.0,
        }
    )
    return replace(snapshot, observations=observations, vessels=vessels, findings=findings, summary=summary)


def _capture_region_selection(event, selection_key: str) -> None:
    """Store a click in region-local state and rerun without touching global selection."""
    try:
        selection = event.selection if event is not None else None
        objects = selection.get("objects") if hasattr(selection, "get") else getattr(selection, "objects", None)
    except Exception:
        return
    if not isinstance(objects, dict):
        return
    layer_objects = objects.get(map_render.AIS_TARGETS_LAYER_ID) or objects.get("ais_targets")
    if not layer_objects:
        return
    first = layer_objects[0] if isinstance(layer_objects, list) and layer_objects else None
    if not isinstance(first, dict):
        return
    mmsi = first.get("mmsi") or first.get("tooltip_mmsi")
    if mmsi is None:
        return
    mmsi = str(mmsi).strip()
    if mmsi.isdigit() and len(mmsi) == 9:
        if st.session_state.get(selection_key) != mmsi:
            st.session_state[selection_key] = mmsi
            st.rerun()


def _selected_region_vessel(snapshot: EngineSnapshot, selection_key: str):
    """Resolve a vessel only from the selection belonging to this region."""
    selected_mmsi = st.session_state.get(selection_key)
    if not selected_mmsi:
        return None
    return next((v for v in snapshot.vessels if str(v.mmsi) == str(selected_mmsi)), None)


def _render_region_map(
    label: str,
    bbox: RegionBBox,
    snapshot: EngineSnapshot,
    settings: AppSettings,
    controls,
    engine: MaritimeIntelligenceEngine,
) -> None:
    """Render one independent tactical map and its region-local vessel panel."""
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
    ) = controls
    region_snapshot = _regional_snapshot(snapshot, bbox)
    region_settings = replace(settings, bbox=bbox, monitoring_bboxes=(bbox,))
    rows = vessel_rows(region_snapshot.vessels) if include_stale else live_vessel_rows(region_snapshot.vessels)
    rows = filter_rows_to_bboxes(rows, (bbox,))
    if min_speed > 0:
        rows = [
            row
            for row in rows
            if row.get("sog_knots") is not None and float(row["sog_knots"]) >= min_speed
        ]

    region_name = region_name_for_bbox(bbox) or label
    selection_key = f"selected_mmsi_{label.lower()}"
    previous_global_selection = st.session_state.get("selected_mmsi")
    region_selection = st.session_state.get(selection_key)

    # The shared map renderer reads the legacy global key. Scope it only for
    # this invocation, then restore it so Region A cannot leak into Region B.
    st.session_state.selected_mmsi = region_selection
    original_pydeck_chart = st.__dict__["pydeck_chart"]

    def _scoped_pydeck_chart(*args, **kwargs):
        kwargs["key"] = f"operational_ais_map_{label.lower()}"
        return original_pydeck_chart(*args, **kwargs)

    st.__dict__["pydeck_chart"] = _scoped_pydeck_chart
    original_apply_selection = map_render._apply_map_selection

    def _scoped_apply_selection(event) -> None:
        _capture_region_selection(event, selection_key)

    map_render._apply_map_selection = _scoped_apply_selection
    try:
        st.caption(f"{label} · {region_name} · {format_bbox(bbox)}")
        _render_vessel_map(
            rows,
            snapshot=region_snapshot,
            settings=region_settings,
            show_heading=show_vectors,
            show_trails=show_trails,
            show_anomalies=show_behavior,
            show_hexbin=show_hexbin,
            show_anomaly_types=show_anomaly_types,
            show_freshness=show_freshness,
            show_anomaly_hotspots=show_anomaly_hotspots,
            map_style=map_style,
        )
    finally:
        map_render._apply_map_selection = original_apply_selection
        st.__dict__["pydeck_chart"] = original_pydeck_chart
        st.session_state.selected_mmsi = previous_global_selection

    selected = _selected_region_vessel(region_snapshot, selection_key)
    if selected is not None:
        with st.container(key=f"tactical-vessel-panel-{label.lower()}", border=True):
            render_vessel_quick_intelligence(
                selected,
                region_snapshot,
                show_gemini_hook=True,
                engine=engine,
            )


def render_overview(engine: MaritimeIntelligenceEngine, snapshot: EngineSnapshot, settings: AppSettings) -> None:
    """Render A+B as simultaneous, geographically isolated tactical views."""
    summary = snapshot.summary
    monitoring = tuple(settings.monitoring_bboxes)
    region = "A + B" if len(monitoring) > 1 else (region_name_for_bbox(settings.bbox) or "CUSTOM")
    duration = f"Collection {snapshot.last_collection_seconds:.1f}s" if snapshot.last_collection_seconds > 0 else "Collection —"
    render_ops_bar(
        live_state=snapshot.status.state,
        region=region,
        vessels=summary["active_vessels"],
        messages=f"{summary['messages']:,}",
        anomalies=summary["anomalies"],
        collection=duration,
        provenance="AIS REAL ONLY",
        avg_speed=f"{summary['average_speed_knots']:.1f} kn",
        last_message=snapshot.status.last_received_at.strftime("%H:%M:%S UTC") if snapshot.status.last_received_at else "—",
    )
    controls = _render_workspace_controls(engine, settings)

    if len(monitoring) >= 2:
        col_a, col_b = st.columns(2, gap="medium")
        with col_a:
            _render_region_map("A", monitoring[0], snapshot, settings, controls, engine)
        with col_b:
            _render_region_map("B", monitoring[1], snapshot, settings, controls, engine)
    else:
        _render_region_map("Region A", monitoring[0] if monitoring else settings.bbox, snapshot, settings, controls, engine)

    st.caption(
        "Operational intelligence derived from live AIS observations. "
        + f"Regions: {region} · AIS REAL ONLY · Region A and Region B maintain independent map viewports and vessel selections."
    )
    if controls[2] == "Nautical Chart":
        st.caption("Nautical chart: © Open Waters: Seamap · © OpenStreetMap contributors · CC BY 4.0. Not for navigational use; consult official nautical charts.")