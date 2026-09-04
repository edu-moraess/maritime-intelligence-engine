"""Streamlit entry point for the Maritime Intelligence Engine."""
from __future__ import annotations

import streamlit as st
from dotenv import load_dotenv
from src.config.regions import REGION_OPTIONS, REGION_PRESETS, format_bbox, region_name_for_bbox
from src.config.settings import AppSettings, COLLECTION_DURATION_OPTIONS, _validate_bbox
from src.intelligence.engine import MaritimeIntelligenceEngine, create_engine
from src.ui.pages import render_anomalies, render_behavior, render_data_quality, render_overview, render_system, render_trajectory_analysis, render_vessel_intelligence
from src.ui.presentation import inject_css, notice, render_header
from src.ui.temporal import OPERATOR_TIMEZONE_OPTIONS

load_dotenv()
st.set_page_config(page_title="Maritime Intelligence Engine", page_icon="◈", layout="wide", initial_sidebar_state="expanded")
inject_css()

WORKSPACES = ("Overview", "Intelligence", "System")


def _read_settings() -> AppSettings:
    try:
        secrets = st.secrets
    except Exception:
        secrets = None
    return AppSettings.from_runtime(secrets)


def _normalize_bbox(bbox):
    (a, b), (c, d) = bbox
    return ((round(float(a), 5), round(float(b), 5)), (round(float(c), 5), round(float(d), 5)))


def _runtime(settings, *, bbox=None, collection_seconds=None, historical_persistence_enabled=None, config_error=None) -> AppSettings:
    return AppSettings(
        aisstream_api_key=settings.aisstream_api_key,
        bbox=settings.bbox if bbox is None else bbox,
        collection_seconds=settings.collection_seconds if collection_seconds is None else collection_seconds,
        max_messages=settings.max_messages,
        max_vessels=settings.max_vessels,
        stale_after_seconds=settings.stale_after_seconds,
        provider=settings.provider,
        config_error=settings.config_error if config_error is None else config_error,
        database_url=settings.database_url,
        historical_persistence_enabled=(settings.historical_persistence_enabled if historical_persistence_enabled is None else historical_persistence_enabled),
    )


def _engine_for(settings: AppSettings) -> MaritimeIntelligenceEngine:
    signature = (settings.aisstream_api_key, _normalize_bbox(settings.bbox), settings.max_messages, settings.max_vessels, settings.stale_after_seconds, settings.provider, settings.config_error)
    if st.session_state.get("engine_signature") != signature:
        previous = st.session_state.get("engine")
        if previous is not None:
            previous.historical_writer.close()
        st.session_state.engine = create_engine(settings)
        st.session_state.engine_signature = signature
        st.session_state.pop("selected_mmsi", None)
    engine = st.session_state.engine
    engine.configure_historical_writer(settings.database_url, settings.historical_persistence_enabled)
    return engine


def _sidebar(settings):
    with st.sidebar:
        st.markdown("### MIE")
        st.caption("MARITIME INTELLIGENCE")
        options = list(COLLECTION_DURATION_OPTIONS)
        index = min(range(len(options)), key=lambda i: abs(options[i] - settings.collection_seconds))
        duration = st.selectbox("Collection duration", options, index=index, format_func=lambda x: f"{x} s")
        if float(duration) != settings.collection_seconds:
            settings = _runtime(settings, collection_seconds=float(duration))
        collect = st.button("Collect Real AIS", width="stretch", type="primary", disabled=settings.config_error is not None)
        clear = st.button("Clear Session", width="stretch")
        st.divider()
        st.markdown("**Monitoring region**")
        active = st.session_state.get("active_bbox", settings.bbox)
        current = region_name_for_bbox(active)
        pidx = REGION_OPTIONS.index(current) if current in REGION_OPTIONS else REGION_OPTIONS.index("Custom")
        region = st.selectbox("AIS region", REGION_OPTIONS, index=pidx)
        if region != "Custom":
            candidate = REGION_PRESETS[region]
            st.caption(f"{region} · {format_bbox(candidate)}")
        else:
            (min_lat, min_lon), (max_lat, max_lon) = active
            min_lat = st.number_input("Min latitude", value=float(min_lat), min_value=-90.0, max_value=90.0, step=0.01, format="%.5f")
            min_lon = st.number_input("Min longitude", value=float(min_lon), min_value=-180.0, max_value=180.0, step=0.01, format="%.5f")
            max_lat = st.number_input("Max latitude", value=float(max_lat), min_value=-90.0, max_value=90.0, step=0.01, format="%.5f")
            max_lon = st.number_input("Max longitude", value=float(max_lon), min_value=-180.0, max_value=180.0, step=0.01, format="%.5f")
            candidate = ((min_lat, min_lon), (max_lat, max_lon))
        error = None
        try:
            _validate_bbox(candidate)
        except ValueError as exc:
            error = str(exc)
            st.error(error)
        changed = False
        if error is None:
            previous = st.session_state.get("active_bbox", settings.bbox)
            changed = _normalize_bbox(candidate) != _normalize_bbox(previous)
            st.session_state.active_bbox = candidate
            if _normalize_bbox(candidate) != _normalize_bbox(settings.bbox):
                settings = _runtime(settings, bbox=candidate)
        else:
            settings = _runtime(settings, config_error=error)
        st.divider()
        historical = st.checkbox("Historical persistence", value=settings.historical_persistence_enabled, disabled=settings.database_url is None, help="Persist only real, valid AIS observations after collection.")
        if bool(historical) != settings.historical_persistence_enabled:
            settings = _runtime(settings, historical_persistence_enabled=bool(historical))
        with st.expander("System controls", expanded=False):
            st.selectbox("Operator timezone", OPERATOR_TIMEZONE_OPTIONS, index=0)
    return settings, collect, clear, changed


def _intelligence(engine, snapshot, settings):
    subview = st.radio("Investigation", ("Vessel", "Behavior", "Trajectory", "Anomalies"), horizontal=True, label_visibility="collapsed")
    if subview == "Vessel":
        render_vessel_intelligence(engine, snapshot, settings)
    elif subview == "Behavior":
        render_behavior(engine, snapshot, settings)
    elif subview == "Trajectory":
        render_trajectory_analysis(engine, snapshot, settings)
    else:
        render_anomalies(engine, snapshot, settings)


def main():
    settings = _read_settings()
    settings, collect, clear, region_changed = _sidebar(settings)
    engine = _engine_for(settings)
    if region_changed:
        notice("Monitoring region changed. The previous live AIS session was discarded. Run Collect Real AIS to open the new subscription.")
    if clear:
        engine.clear_session_data()
        st.session_state.pop("selected_mmsi", None)
        st.rerun()
    if collect:
        with st.spinner(f"Opening AISStream WebSocket and collecting real AIS messages for {int(settings.collection_seconds)} seconds…"):
            received = engine.collect(seconds=settings.collection_seconds)
        if received:
            st.session_state["collection_result"] = ("success", f"Collection elapsed {engine.last_collection_seconds:.1f} s · received {received:,} real AIS position report(s).")
        else:
            st.session_state["collection_result"] = ("warning", f"Collection elapsed {engine.last_collection_seconds:.1f} s · REAL AIS DATA UNAVAILABLE — no real observations were received in this collection window.")
        st.rerun()
    result = st.session_state.pop("collection_result", None)
    if result:
        (st.success if result[0] == "success" else st.warning)(result[1])
    snapshot = engine.snapshot()
    workspace = st.radio("Workspace", WORKSPACES, horizontal=True, label_visibility="collapsed", key="workspace")
    render_header(snapshot.status, workspace)
    if snapshot.status.state != "LIVE AIS":
        status_type = "red" if snapshot.status.state in {"DISCONNECTED", "REAL AIS DATA UNAVAILABLE"} else ""
        notice(f"{snapshot.status.state}: {snapshot.status.reason}", status_type)
    if workspace == "Overview":
        render_overview(engine, snapshot, settings)
    elif workspace == "Intelligence":
        _intelligence(engine, snapshot, settings)
    else:
        render_system(engine, snapshot, settings)
        with st.expander("Data quality", expanded=False):
            render_data_quality(engine, snapshot, settings)


if __name__ == "__main__":
    main()
