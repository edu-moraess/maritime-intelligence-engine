"""Streamlit entry point for the Maritime Intelligence Engine.

Real AIS only. The sidebar supports two simultaneous AISStream
BoundingBoxes collected by one live subscription and one MIE app.
"""
from __future__ import annotations

import streamlit as st
from dotenv import load_dotenv

from src.config.regions import REGION_OPTIONS, REGION_PRESETS, format_bbox, region_name_for_bbox
from src.config.settings import AppSettings, COLLECTION_DURATION_OPTIONS, _validate_bbox
from src.intelligence.engine import MaritimeIntelligenceEngine, create_engine
from src.ui.pages import (
    render_anomalies, render_behavior, render_data_quality, render_overview,
    render_similarity, render_system, render_traffic, render_trajectory_analysis,
    render_vessel_intelligence, render_vessels,
)
from src.ui.presentation import inject_css, notice, render_header
from src.ui.temporal import OPERATOR_TIMEZONE_OPTIONS

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


def _with_settings(settings: AppSettings, *, bboxes=None, bbox=None, config_error=None,
                   collection_seconds=None, historical_persistence_enabled=None) -> AppSettings:
    active = tuple(bboxes if bboxes is not None else settings.monitoring_bboxes)
    if not active:
        active = (settings.bbox,)
    primary = bbox if bbox is not None else active[0]
    return AppSettings(
        aisstream_api_key=settings.aisstream_api_key,
        bbox=primary,
        monitoring_bboxes=active,
        collection_seconds=settings.collection_seconds if collection_seconds is None else collection_seconds,
        max_messages=settings.max_messages,
        max_vessels=settings.max_vessels,
        stale_after_seconds=settings.stale_after_seconds,
        provider=settings.provider,
        config_error=settings.config_error if config_error is None else config_error,
        database_url=settings.database_url,
        historical_persistence_enabled=(settings.historical_persistence_enabled if historical_persistence_enabled is None else historical_persistence_enabled),
    )


def _normalize_bbox(bbox):
    (a, b), (c, d) = bbox
    return ((round(float(a), 5), round(float(b), 5)), (round(float(c), 5), round(float(d), 5)))


def _normalize_bboxes(bboxes):
    return tuple(_normalize_bbox(b) for b in bboxes)


def _engine_signature(settings: AppSettings) -> tuple:
    return (settings.aisstream_api_key, _normalize_bboxes(settings.monitoring_bboxes),
            settings.max_messages, settings.max_vessels, settings.stale_after_seconds,
            settings.provider, settings.config_error)


def _engine_for(settings: AppSettings) -> MaritimeIntelligenceEngine:
    signature = _engine_signature(settings)
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


def _connection_state(settings, engine) -> str:
    if not settings.aisstream_api_key:
        return "NOT CONFIGURED"
    return engine.snapshot().status.state


def _bbox_values(bbox):
    (min_lat, min_lon), (max_lat, max_lon) = bbox
    return float(min_lat), float(min_lon), float(max_lat), float(max_lon)


def _render_region_selector(settings: AppSettings):
    """Render Region A and B inside the existing MIE sidebar."""
    existing = list(settings.monitoring_bboxes) or [settings.bbox]
    first = region_name_for_bbox(existing[0]) or "Miami"
    second = region_name_for_bbox(existing[1]) if len(existing) > 1 else "English Channel"
    preset_options = list(REGION_OPTIONS)

    if second == first:
        second = next(name for name in preset_options if name not in {first, "Custom"})

    st.markdown("<div class='side-section-label'>LIVE MONITORING REGIONS</div>", unsafe_allow_html=True)
    st.caption("Duas regiões na mesma assinatura AISStream. Sem segundo app e sem segunda conexão.")

    region_a = st.selectbox(
        "Region A", preset_options,
        index=preset_options.index(first) if first in preset_options else 0,
        key="monitor_region_a",
    )
    choices_b = [name for name in preset_options if name != region_a]
    region_b = st.selectbox(
        "Region B", choices_b,
        index=choices_b.index(second) if second in choices_b else 0,
        key="monitor_region_b",
    )

    bboxes = []
    for label, name, key_prefix in (("A", region_a, "region_a"), ("B", region_b, "region_b")):
        if name == "Custom":
            fallback = existing[0 if label == "A" else min(1, len(existing) - 1)]
            st.caption(f"{label} · Custom")
            min_lat = st.number_input("Min Latitude", value=float(fallback[0][0]), min_value=-90.0, max_value=90.0, step=0.01, format="%.5f", key=f"{key_prefix}_min_lat")
            min_lon = st.number_input("Min Longitude", value=float(fallback[0][1]), min_value=-180.0, max_value=180.0, step=0.01, format="%.5f", key=f"{key_prefix}_min_lon")
            max_lat = st.number_input("Max Latitude", value=float(fallback[1][0]), min_value=-90.0, max_value=90.0, step=0.01, format="%.5f", key=f"{key_prefix}_max_lat")
            max_lon = st.number_input("Max Longitude", value=float(fallback[1][1]), min_value=-180.0, max_value=180.0, step=0.01, format="%.5f", key=f"{key_prefix}_max_lon")
            bbox = ((min_lat, min_lon), (max_lat, max_lon))
        else:
            bbox = REGION_PRESETS[name]
            st.caption(f"{label} · {name} · {format_bbox(bbox)}")
        try:
            _validate_bbox(bbox)
        except ValueError as exc:
            st.error(f"Region {label}: {exc}")
        bboxes.append(bbox)

    return tuple(bboxes), (region_a, region_b)


def _render_sidebar(settings: AppSettings):
    region_changed = False
    with st.sidebar:
        connection_placeholder = st.empty()
        st.markdown("<div class='side-section-title'>MISSION CONTEXT</div>", unsafe_allow_html=True)

        duration_options = list(COLLECTION_DURATION_OPTIONS)
        duration_index = min(range(len(duration_options)), key=lambda i: abs(duration_options[i] - settings.collection_seconds))
        selected_duration = st.selectbox("Collection duration", duration_options, index=duration_index,
            format_func=lambda s: f"Collection duration · {s} s", key="collection_duration_seconds", label_visibility="collapsed")
        if float(selected_duration) != settings.collection_seconds:
            settings = _with_settings(settings, collection_seconds=float(selected_duration))

        bboxes, region_names = _render_region_selector(settings)
        previous = st.session_state.get("active_monitoring_bboxes", tuple(settings.monitoring_bboxes))
        region_changed = _normalize_bboxes(bboxes) != _normalize_bboxes(previous)
        st.session_state.active_monitoring_bboxes = bboxes
        st.session_state.active_region_names = region_names
        if region_changed:
            settings = _with_settings(settings, bboxes=bboxes, bbox=bboxes[0])
            st.warning("Regiões alteradas. A próxima coleta abrirá uma nova assinatura AIS real para as duas regiões.")
        elif _normalize_bboxes(settings.monitoring_bboxes) != _normalize_bboxes(bboxes):
            settings = _with_settings(settings, bboxes=bboxes, bbox=bboxes[0])

        collect = st.button("Collect Real AIS · 2 Regions", width="stretch", type="primary", disabled=settings.config_error is not None)
        clear = st.button("Clear Session", width="stretch")

        st.markdown("<div class='side-section-title'>DATA</div>", unsafe_allow_html=True)
        historical_enabled = st.checkbox("Historical Persistence", value=settings.historical_persistence_enabled,
            key="historical_persistence_enabled", disabled=settings.database_url is None,
            help="Persiste somente observações AIS reais e válidas após a coleta.")
        if bool(historical_enabled) != settings.historical_persistence_enabled:
            settings = _with_settings(settings, historical_persistence_enabled=bool(historical_enabled))

        if settings.database_url is None:
            historical_state = "HISTORICAL DATABASE NOT CONFIGURED"
        elif settings.historical_persistence_enabled:
            historical_state = "HISTORICAL PERSISTENCE ENABLED"
        else:
            historical_state = "HISTORICAL PERSISTENCE OFF"
        st.markdown(f"<div class='data-value side-muted'>{historical_state}</div>", unsafe_allow_html=True)

        st.markdown("<div class='side-section-title'>ANALYSIS</div>", unsafe_allow_html=True)
        module = st.radio("Workspace module", list(NAVIGATION), label_visibility="collapsed", key="workspace_module")
        views = NAVIGATION[module]
        page = views[0] if len(views) == 1 else st.radio(f"{module} subarea", views, label_visibility="collapsed", key=f"workspace_subarea_{module}")

        engine = _engine_for(settings)
        conn = _connection_state(settings, engine)
        upper = str(conn).upper()
        pill_cls = "status-live" if upper in {"LIVE AIS", "LIVE"} else ("status-connecting" if "CONNECT" in upper else "status-disconnected")
        connection_placeholder.markdown("<div class='side-header'><div class='brand'>MIE</div><div class='side-subtitle'>MARITIME INTELLIGENCE</div>" f"<div class='side-status'><span class='status-pill {pill_cls}'>{conn}</span><span class='side-provider'>AISSTREAM</span></div></div>", unsafe_allow_html=True)
        with st.expander("SYSTEM", expanded=False):
            st.markdown(f"<div class='data-label'>Connection</div><div class='data-value'>{conn}</div>", unsafe_allow_html=True)
            st.selectbox("Operator timezone", OPERATOR_TIMEZONE_OPTIONS, index=0, key="operator_timezone", format_func=lambda v: f"Operator time · {v}", label_visibility="collapsed")

    return settings, page, collect, clear, region_changed


def main() -> None:
    settings = _read_settings()
    settings, page, collect, clear, region_changed = _render_sidebar(settings)
    engine = _engine_for(settings)

    if region_changed:
        notice("Monitoring regions changed. Run Collect Real AIS · 2 Regions to open the new subscription.")
    if clear:
        engine.clear_session_data()
        st.session_state.pop("selected_mmsi", None)
        st.rerun()
    if collect:
        with st.spinner(f"Opening one AISStream WebSocket for {len(settings.monitoring_bboxes)} real AIS regions and collecting for {int(settings.collection_seconds)} seconds…"):
            received = engine.collect(seconds=settings.collection_seconds)
        if received:
            st.session_state["collection_result"] = ("success", f"Collection elapsed {engine.last_collection_seconds:.1f} s · received {received:,} real AIS position report(s) across {len(settings.monitoring_bboxes)} regions.")
        else:
            st.session_state["collection_result"] = ("warning", f"Collection elapsed {engine.last_collection_seconds:.1f} s · REAL AIS DATA UNAVAILABLE — no real observations were received across the selected regions.")
        st.rerun()

    result = st.session_state.pop("collection_result", None)
    if result:
        (st.success if result[0] == "success" else st.warning)(result[1])

    snapshot = engine.snapshot()
    render_header(snapshot.status, page)
    if snapshot.status.state != "LIVE AIS":
        notice(snapshot.status.state + ": " + snapshot.status.reason, "red" if snapshot.status.state in {"DISCONNECTED", "REAL AIS DATA UNAVAILABLE"} else "")

    renderers = {
        "Overview": render_overview, "Fleet": render_vessels, "Vessel Intelligence": render_vessel_intelligence,
        "Trajectory Analysis": render_trajectory_analysis, "Behavior": render_behavior, "Similarity": render_similarity,
        "Anomalies": render_anomalies, "Traffic": render_traffic, "Data Quality": render_data_quality, "System": render_system,
    }
    renderers[page](engine, snapshot, settings)


if __name__ == "__main__":
    main()
