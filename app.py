"""Maritime Intelligence Engine — Streamlit entry point.

The presentation layer delegates ingestion and analytics to ``src`` modules.
The application has no synthetic, mock, fallback, or fabricated AIS mode.
"""

from __future__ import annotations

import os

import streamlit as st
from dotenv import load_dotenv

from src.config.settings import AppSettings, _validate_bbox
from src.intelligence.engine import MaritimeIntelligenceEngine, create_engine
from src.ui.pages import (
    render_anomalies,
    render_behavior,
    render_data_quality,
    render_overview,
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


@st.cache_data(ttl=15, show_spinner=False)
def _runtime_clock() -> str:
    # A tiny cached function keeps reruns lightweight without caching AIS data.
    return "runtime"


def _read_settings() -> AppSettings:
    try:
        secrets = st.secrets
    except Exception:
        secrets = None
    return AppSettings.from_runtime(secrets)


def _engine_for(settings: AppSettings) -> MaritimeIntelligenceEngine:
    signature = (settings.aisstream_api_key, settings.bbox, settings.max_messages, settings.max_vessels)
    if st.session_state.get("engine_signature") != signature:
        st.session_state.engine = create_engine(settings)
        st.session_state.engine_signature = signature
        st.session_state.pop("selected_mmsi", None)
    return st.session_state.engine


def _render_sidebar(settings: AppSettings) -> tuple[AppSettings, str, bool, bool]:
    with st.sidebar:
        st.markdown("<div class='brand'>MIE <span style='color:#79939b'>/ OPERATIONS</span></div>", unsafe_allow_html=True)
        st.markdown("<div class='small-note' style='margin:.35rem 0 1rem'>Real AIS intelligence workspace</div>", unsafe_allow_html=True)
        pages = ["Overview", "Vessels", "Vessel Intelligence", "Trajectory Analysis", "Behavior", "Anomalies", "Traffic", "Data Quality", "System"]
        page = st.radio("Workspace", pages, label_visibility="collapsed")
        st.markdown("<hr>", unsafe_allow_html=True)
        st.markdown("<div class='data-label'>Ingestion</div>", unsafe_allow_html=True)
        collect = st.button("Collect real AIS", use_container_width=True, type="primary")
        clear = st.button("Clear session observations", use_container_width=True)
        st.markdown("<hr>", unsafe_allow_html=True)
        with st.expander("Monitoring region", expanded=False):
            min_lat = st.number_input("Min latitude", value=float(settings.bbox[0][0]), min_value=-90.0, max_value=90.0, step=0.01, format="%.5f")
            min_lon = st.number_input("Min longitude", value=float(settings.bbox[0][1]), min_value=-180.0, max_value=180.0, step=0.01, format="%.5f")
            max_lat = st.number_input("Max latitude", value=float(settings.bbox[1][0]), min_value=-90.0, max_value=90.0, step=0.01, format="%.5f")
            max_lon = st.number_input("Max longitude", value=float(settings.bbox[1][1]), min_value=-180.0, max_value=180.0, step=0.01, format="%.5f")
            try:
                _validate_bbox(((min_lat, min_lon), (max_lat, max_lon)))
                if (min_lat, min_lon, max_lat, max_lon) != (settings.bbox[0][0], settings.bbox[0][1], settings.bbox[1][0], settings.bbox[1][1]):
                    settings = AppSettings(
                        aisstream_api_key=settings.aisstream_api_key,
                        bbox=((min_lat, min_lon), (max_lat, max_lon)),
                        collection_seconds=settings.collection_seconds,
                        max_messages=settings.max_messages,
                        max_vessels=settings.max_vessels,
                        stale_after_seconds=settings.stale_after_seconds,
                        provider=settings.provider,
                    )
                    st.info("Region updated. Collect again to open a new subscription.")
            except ValueError as exc:
                st.error(str(exc))
        st.markdown("<hr>", unsafe_allow_html=True)
        key_state = "CONFIGURED" if settings.aisstream_api_key else "NOT CONFIGURED"
        st.markdown(f"<div class='data-label'>AISSTREAM API KEY</div><div class='data-value'>{key_state}</div>", unsafe_allow_html=True)
        st.markdown("<div class='small-note' style='margin-top:.8rem'>Keys are read server-side from .env or Streamlit Secrets. They are never sent to the browser.</div>", unsafe_allow_html=True)
    return settings, page, collect, clear


def main() -> None:
    settings = _read_settings()
    settings, page, collect, clear = _render_sidebar(settings)
    engine = _engine_for(settings)
    if clear:
        engine.clear_session_data()
        st.session_state.pop("selected_mmsi", None)
        st.rerun()
    if collect:
        with st.spinner("Opening AISStream WebSocket and collecting real AIS messages…"):
            received = engine.collect()
        if received:
            st.success(f"Received {received:,} real AIS position report(s).")
        else:
            st.warning("REAL AIS DATA UNAVAILABLE — no real observations were received in this collection window.")
    snapshot = engine.snapshot()
    render_header(snapshot.status, page)
    if snapshot.status.state != "LIVE AIS":
        notice(f"{snapshot.status.state}: {snapshot.status.reason}", "red" if snapshot.status.state == "DISCONNECTED" else "")
    if page == "Overview":
        render_overview(engine, snapshot, settings)
    elif page == "Vessels":
        render_vessels(engine, snapshot, settings)
    elif page == "Vessel Intelligence":
        render_vessel_intelligence(engine, snapshot, settings)
    elif page == "Trajectory Analysis":
        render_trajectory_analysis(engine, snapshot, settings)
    elif page == "Behavior":
        render_behavior(engine, snapshot, settings)
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
