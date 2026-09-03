"""Dual-region operational picture with isolated tactical views and selection state."""
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
    """Create a presentation-only snapshot containing only one operational area."""
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


def _unified_bbox(bboxes: tuple[RegionBBox, ...]) -> RegionBBox:
    """Return one enclosing viewport without inventing a geographic midpoint."""
    return (
        (min(b[0][0] for b in bboxes), min(b[0][1] for b in bboxes)),
        (max(b[1][0] for b in bboxes), max(b[1][1] for b in bboxes)),
    )


def _capture_region_selection(event, selection_key: str) -> None:
    """Store a contact selection in region-local state without touching global selection."""
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
    if mmsi.isdigit() and len(mmsi) == 9 and st.session_state.get(selection_key) != mmsi:
        st.session_state[selection_key] = mmsi
        st.rerun()


def _selected_region_vessel(snapshot: EngineSnapshot, selection_key: str):
    """Resolve a selected contact only from the selection belonging to this region."""
    selected_mmsi = st.session_state.get(selection_key)
    if not selected_mmsi:
        return None
    return next((v for v in snapshot.vessels if str(v.mmsi) == str(selected_mmsi)), None)


def _render_map(label: str, bbox: RegionBBox, snapshot: EngineSnapshot, settings: AppSettings, controls, engine: MaritimeIntelligenceEngine, *, selection_key: str, map_key: str) -> None:
    """Render one tactical map using isolated selection and widget state."""
    (
        min_speed, include_stale, map_style, show_vectors, show_trails, show_behavior,
        show_hexbin, show_anomaly_types, show_freshness, show_anomaly_hotspots,
    ) = controls
    region_snapshot = _regional_snapshot(snapshot, bbox)
    region_settings = replace(settings, bbox=bbox, monitoring_bboxes=(bbox,))
    rows = vessel_rows(region_snapshot.vessels) if include_stale else live_vessel_rows(region_snapshot.vessels)
    rows = filter_rows_to_bboxes(rows, (bbox,))
    if min_speed > 0:
        rows = [row for row in rows if row.get("sog_knots") is not None and float(row["sog_knots"]) >= min_speed]

    region_name = region_name_for_bbox(bbox) or label
    previous_global_selection = st.session_state.get("selected_mmsi")
    region_selection = st.session_state.get(selection_key)
    st.session_state.selected_mmsi = region_selection
    original_pydeck_chart = st.__dict__["pydeck_chart"]

    def _scoped_pydeck_chart(*args, **kwargs):
        kwargs["key"] = map_key
        return original_pydeck_chart(*args, **kwargs)

    st.__dict__["pydeck_chart"] = _scoped_pydeck_chart
    original_apply_selection = map_render._apply_map_selection

    def _scoped_apply_selection(event) -> None:
        _capture_region_selection(event, selection_key)

    map_render._apply_map_selection = _scoped_apply_selection
    try:
        st.caption(f"{label} · {region_name} · {format_bbox(bbox)}")
        _render_vessel_map(rows, snapshot=region_snapshot, settings=region_settings, show_heading=show_vectors, show_trails=show_trails, show_anomalies=show_behavior, show_hexbin=show_hexbin, show_anomaly_types=show_anomaly_types, show_freshness=show_freshness, show_anomaly_hotspots=show_anomaly_hotspots, map_style=map_style)
    finally:
        map_render._apply_map_selection = original_apply_selection
        st.__dict__["pydeck_chart"] = original_pydeck_chart
        st.session_state.selected_mmsi = previous_global_selection

    selected = _selected_region_vessel(region_snapshot, selection_key)
    if selected is not None:
        with st.container(key=f"tactical-contact-panel-{label.lower()}", border=True):
            render_vessel_quick_intelligence(selected, region_snapshot, show_gemini_hook=True, engine=engine)


def _render_unified_map(bboxes: tuple[RegionBBox, ...], snapshot: EngineSnapshot, settings: AppSettings, controls, engine: MaritimeIntelligenceEngine) -> None:
    """Render all monitored regions in one enclosing tactical viewport."""
    unified_bbox = _unified_bbox(bboxes)
    (
        min_speed, include_stale, map_style, show_vectors, show_trails, show_behavior,
        show_hexbin, show_anomaly_types, show_freshness, show_anomaly_hotspots,
    ) = controls
    unified_settings = replace(settings, bbox=unified_bbox, monitoring_bboxes=bboxes)
    rows = vessel_rows(snapshot.vessels) if include_stale else live_vessel_rows(snapshot.vessels)
    rows = filter_rows_to_bboxes(rows, bboxes)
    if min_speed > 0:
        rows = [row for row in rows if row.get("sog_knots") is not None and float(row["sog_knots"]) >= min_speed]

    # UNIFIED needs persistent selection state of its own. The shared map
    # renderer still reads the legacy global key, so that key is scoped only
    # for the render and restored afterwards; the durable selection lives in
    # selected_mmsi_unified across Streamlit reruns.
    unified_selection_key = "selected_mmsi_unified"
    previous_global_selection = st.session_state.get("selected_mmsi")
    unified_selection = st.session_state.get(unified_selection_key)
    st.session_state.selected_mmsi = unified_selection
    original_pydeck_chart = st.__dict__["pydeck_chart"]
    original_apply_selection = map_render._apply_map_selection

    def _scoped_pydeck_chart(*args, **kwargs):
        kwargs["key"] = "operational_ais_map_unified"
        return original_pydeck_chart(*args, **kwargs)

    def _capture_unified_selection(event) -> None:
        try:
            selection = event.selection if event is not None else None
            objects = selection.get("objects") if hasattr(selection, "get") else getattr(selection, "objects", None)
        except Exception:
            return
        if not isinstance(objects, dict):
            return
        layer_objects = objects.get(map_render.AIS_TARGETS_LAYER_ID) or objects.get("ais_targets")
        first = layer_objects[0] if isinstance(layer_objects, list) and layer_objects else None
        if not isinstance(first, dict):
            return
        mmsi = first.get("mmsi") or first.get("tooltip_mmsi")
        if mmsi is not None and str(mmsi).strip().isdigit() and len(str(mmsi).strip()) == 9:
            st.session_state[unified_selection_key] = str(mmsi).strip()
            st.rerun()

    st.__dict__["pydeck_chart"] = _scoped_pydeck_chart
    map_render._apply_map_selection = _capture_unified_selection
    try:
        st.caption("UNIFIED · A + B · CONSOLIDATED OPERATIONAL PICTURE")
        _render_vessel_map(rows, snapshot=snapshot, settings=unified_settings, show_heading=show_vectors, show_trails=show_trails, show_anomalies=show_behavior, show_hexbin=show_hexbin, show_anomaly_types=show_anomaly_types, show_freshness=show_freshness, show_anomaly_hotspots=show_anomaly_hotspots, map_style=map_style)
    finally:
        map_render._apply_map_selection = original_apply_selection
        st.__dict__["pydeck_chart"] = original_pydeck_chart
        st.session_state.selected_mmsi = previous_global_selection

    selected_mmsi = st.session_state.get(unified_selection_key)
    if selected_mmsi:
        selected = next((v for v in snapshot.vessels if str(v.mmsi) == str(selected_mmsi)), None)
        if selected is not None:
            with st.container(key="tactical-contact-panel-unified", border=True):
                render_vessel_quick_intelligence(selected, snapshot, show_gemini_hook=True, engine=engine)


def render_overview(engine: MaritimeIntelligenceEngine, snapshot: EngineSnapshot, settings: AppSettings) -> None:
    """Render dual-region tactical monitoring in SPLIT or UNIFIED presentation modes."""
    summary = snapshot.summary
    monitoring = tuple(settings.monitoring_bboxes)
    region = "A + B" if len(monitoring) > 1 else (region_name_for_bbox(settings.bbox) or "CUSTOM")
    duration = f"Collection {snapshot.last_collection_seconds:.1f}s" if snapshot.last_collection_seconds > 0 else "Collection —"
    render_ops_bar(live_state=snapshot.status.state, region=region, vessels=summary["active_vessels"], messages=f"{summary['messages']:,}", anomalies=summary["anomalies"], collection=duration, provenance="REAL AIS · VERIFIED SOURCE", avg_speed=f"{summary['average_speed_knots']:.1f} kn", last_message=snapshot.status.last_received_at.strftime("%H:%M:%S UTC") if snapshot.status.last_received_at else "—")
    controls = _render_workspace_controls(engine, settings)

    if len(monitoring) >= 2:
        map_mode = st.segmented_control("DISPLAY MODE", options=["SPLIT", "UNIFIED"], default="SPLIT", key="dual_region_map_mode", label_visibility="visible")
        if map_mode == "UNIFIED":
            _render_unified_map(monitoring[:2], snapshot, settings, controls, engine)
        else:
            with st.container(key="dual-region-split-view"):
                st.markdown("<style>.st-key-dual-region-split-view [data-testid='stHorizontalBlock']{gap:0.6rem !important;}</style>", unsafe_allow_html=True)
                col_a, col_b = st.columns(2, gap="small")
                with col_a:
                    _render_map("A", monitoring[0], snapshot, settings, controls, engine, selection_key="selected_mmsi_a", map_key="operational_ais_map_a")
                with col_b:
                    _render_map("B", monitoring[1], snapshot, settings, controls, engine, selection_key="selected_mmsi_b", map_key="operational_ais_map_b")
    else:
        _render_map("Region A", monitoring[0] if monitoring else settings.bbox, snapshot, settings, controls, engine, selection_key="selected_mmsi_region_a", map_key="operational_ais_map_region_a")

    st.caption("Operational picture derived from live AIS observations. " + f"Areas: {region} · REAL AIS · Regional analysis remains separated in both SPLIT and UNIFIED modes.")
    if controls[2] == "Nautical Chart":
        st.caption("Nautical chart: © Open Waters: Seamap · © OpenStreetMap contributors · CC BY 4.0. Visualization only; not for navigation. Consult official nautical charts.")
