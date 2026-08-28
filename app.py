"""Streamlit entry point for the Maritime Intelligence Engine.

The presentation layer delegates ingestion and analytics to ``src`` modules.
The application has no synthetic, mock, fallback, or fabricated AIS mode.
"""

from __future__ import annotations

import streamlit as st
from dotenv import load_dotenv

from src.config.regions import REGION_OPTIONS, REGION_PRESETS, format_bbox, region_name_for_bbox
from src.config.settings import AppSettings, COLLECTION_DURATION_OPTIONS, _validate_bbox
from src.intelligence.engine import MaritimeIntelligenceEngine, create_engine
from src.ui.pages import (
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
from src.ui.presentation import inject_css, notice, render_header

load_dotenv()
st.set_page_config(page_title="Maritime Intelligence Engine", page_icon="◈", layout="wide", initial_sidebar_state="expanded")
inject_css()


NAVIGATION = {
    "Overview": ("Overview",),
    "Vessels": ("Fleet", "Vessel Intelligence"),
    "Movement & Behavior": ("Trajectory Analysis", "Behavior", "Similarity"),
    "Anomalies & Traffic": ("Anomalies", "Traffic"),
    "Data & System": ("Data Quality", "System"),
}


def _read_settings() -> AppSettings:
    try:
        secrets = st.secrets
    except Exception:
        secrets = None
    return AppSettings.from_runtime(secrets)


def _engine_for(settings: AppSettings) -> MaritimeIntelligenceEngine:
    signature = (
        settings.aisstream_api_key,
        settings.bbox,
        settings.max_messages,
        settings.max_vessels,
        settings.stale_after_seconds,
        settings.provider,
        settings.config_error,
    )
    if st.session_state.get("engine_signature") != signature:
        st.session_state.engine = create_engine(settings)
        st.session_state.engine_signature = signature
        st.session_state.pop("selected_mmsi", None)
    return st.session_state.engine


def _with_bbox(
    settings: AppSettings,
    bbox: tuple[tuple[float, float], tuple[float, float]],
    config_error: str | None = None,
    collection_seconds: float | None = None,
) -> AppSettings:
    return AppSettings(
        aisstream_api_key=settings.aisstream_api_key,
        bbox=bbox,
        collection_seconds=settings.collection_seconds if collection_seconds is None else collection_seconds,
        max_messages=settings.max_messages,
        max_vessels=settings.max_vessels,
        stale_after_seconds=settings.stale_after_seconds,
        provider=settings.provider,
        config_error=config_error,
    )


def _bbox_values(bbox: tuple[tuple[float, float], tuple[float, float]]) -> tuple[float, float, float, float]:
    (min_lat, min_lon), (max_lat, max_lon) = bbox
    return float(min_lat), float(min_lon), float(max_lat), float(max_lon)


def _connection_state(settings: AppSettings) -> str:
    if not settings.aisstream_api_key:
        return "NOT CONFIGURED"
    existing_engine = st.session_state.get("engine")
    if existing_engine is None or getattr(existing_engine, "settings", None).bbox != settings.bbox:
        return "DISCONNECTED"
    state = existing_engine.provider.status.state
    return state if state in {"LIVE AIS", "CONNECTING", "DISCONNECTED"} else "DISCONNECTED"


def _render_sidebar(settings: AppSettings) -> tuple[AppSettings, str, bool, bool, bool]:
    region_changed = False
    with st.sidebar:
        st.markdown("<div class='brand'>MIE <span style='color:#79939b'>/ OPERATIONS</span></div>", unsafe_allow_html=True)
        st.markdown("<div class='small-note' style='margin:.25rem 0 .9rem'>Real AIS intelligence workspace</div>", unsafe_allow_html=True)

        st.markdown("<div class='data-label'>SESSION / CONTROL</div>", unsafe_allow_html=True)
        duration_options = list(COLLECTION_DURATION_OPTIONS)
        duration_index = min(range(len(duration_options)), key=lambda index: abs(duration_options[index] - settings.collection_seconds))
        selected_duration = st.selectbox(
            "Collection duration",
            duration_options,
            index=duration_index,
            format_func=lambda seconds: f"Collection duration · {seconds} s",
            key="collection_duration_seconds",
            label_visibility="collapsed",
        )
        if float(selected_duration) != settings.collection_seconds:
            settings = _with_bbox(settings, settings.bbox, settings.config_error, collection_seconds=float(selected_duration))
        collect = st.button("Collect Real AIS", width="stretch", type="primary", disabled=settings.config_error is not None)
        clear = st.button("Clear Session", width="stretch")

        st.markdown("<div class='data-label' style='margin-top:.8rem'>REGION</div>", unsafe_allow_html=True)
        with st.expander("Bounding Box", expanded=False):
            active_bbox = st.session_state.get("active_bbox", settings.bbox)
            current_region = region_name_for_bbox(active_bbox)
            preset_index = REGION_OPTIONS.index(current_region) if current_region in REGION_OPTIONS else REGION_OPTIONS.index("Custom")
            selected_region = st.selectbox("AIS region preset", REGION_OPTIONS, index=preset_index, key="region_preset")
            if selected_region != "Custom":
                candidate_bbox = REGION_PRESETS[selected_region]
                for key, value in zip(("bbox_min_lat", "bbox_min_lon", "bbox_max_lat", "bbox_max_lon"), _bbox_values(candidate_bbox)):
                    st.session_state[key] = value
                st.caption(f"{selected_region} · {format_bbox(candidate_bbox)}")
            else:
                st.caption("Custom · applied to the next real AIS subscription")
                min_lat = st.number_input("Min Latitude", value=float(active_bbox[0][0]), min_value=-90.0, max_value=90.0, step=0.01, format="%.5f", key="bbox_min_lat")
                min_lon = st.number_input("Min Longitude", value=float(active_bbox[0][1]), min_value=-180.0, max_value=180.0, step=0.01, format="%.5f", key="bbox_min_lon")
                max_lat = st.number_input("Max Latitude", value=float(active_bbox[1][0]), min_value=-90.0, max_value=90.0, step=0.01, format="%.5f", key="bbox_max_lat")
                max_lon = st.number_input("Max Longitude", value=float(active_bbox[1][1]), min_value=-180.0, max_value=180.0, step=0.01, format="%.5f", key="bbox_max_lon")
                candidate_bbox = ((min_lat, min_lon), (max_lat, max_lon))
            region_error: str | None = None
            try:
                _validate_bbox(candidate_bbox)
            except ValueError as exc:
                region_error = str(exc)
                st.error(region_error)
            if region_error is None:
                previous_bbox = st.session_state.get("active_bbox", settings.bbox)
                region_changed = candidate_bbox != previous_bbox
                st.session_state.active_bbox = candidate_bbox
                if candidate_bbox != settings.bbox:
                    settings = _with_bbox(settings, candidate_bbox)
                if region_changed:
                    st.warning("Region changed. Previous session cleared; run a new real AIS collection.")
            else:
                settings = _with_bbox(settings, active_bbox, region_error)

        st.markdown("<div class='data-label' style='margin-top:.8rem'>CONNECTION</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='data-value'>{_connection_state(settings)}</div>", unsafe_allow_html=True)

        st.markdown("<div class='data-label' style='margin-top:.8rem'>WORKSPACE</div>", unsafe_allow_html=True)
        modules = list(NAVIGATION)
        module = st.radio("Workspace module", modules, label_visibility="collapsed", key="workspace_module")
        views = NAVIGATION[module]
        if len(views) == 1:
            page = views[0]
        else:
            page = st.radio(f"{module} subarea", views, label_visibility="collapsed", key=f"workspace_subarea_{module}")

    return settings, page, collect, clear, region_changed


def main() -> None:
    settings = _read_settings()
    settings, page, collect, clear, region_changed = _render_sidebar(settings)
    engine = _engine_for(settings)
    if region_changed:
        notice("Monitoring region changed. Previous session observations were cleared. Run Collect Real AIS to open the new subscription.")
    if clear:
        engine.clear_session_data()
        st.session_state.pop("selected_mmsi", None)
        st.rerun()
    if collect:
        with st.spinner(f"Opening AISStream WebSocket and collecting real AIS messages for {int(settings.collection_seconds)} seconds…"):
            received = engine.collect(seconds=settings.collection_seconds)
        if received:
            st.success(f"Collection elapsed {engine.last_collection_seconds:.1f} s · received {received:,} real AIS position report(s).")
        else:
            st.warning(f"Collection elapsed {engine.last_collection_seconds:.1f} s · REAL AIS DATA UNAVAILABLE — no real observations were received in this collection window.")
    snapshot = engine.snapshot()
    render_header(snapshot.status, page)
    if snapshot.status.state != "LIVE AIS":
        notice(snapshot.status.state + ": " + snapshot.status.reason, "red" if snapshot.status.state in {"DISCONNECTED", "REAL AIS DATA UNAVAILABLE"} else "")
    if page == "Overview":
        render_overview(engine, snapshot, settings)
    elif page == "Fleet":
        render_vessels(engine, snapshot, settings)
    elif page == "Vessel Intelligence":
        render_vessel_intelligence(engine, snapshot, settings)
    elif page == "Trajectory Analysis":
        render_trajectory_analysis(engine, snapshot, settings)
    elif page == "Behavior":
        render_behavior(engine, snapshot, settings)
    elif page == "Similarity":
        render_similarity(engine, snapshot, settings)
    elif page == "Anomalies":
        render_anomalies(engine, snapshot, settings)
    elif page == "Traffic":
        render_traffic(engine, snapshot, settings)
    elif page == "Data Quality":
        render_data_quality(engine, snapshot, settings)
    elif page == "System":
        render_system(engine, snapshot, settings)


if __name__ == "__main__":
    main()
