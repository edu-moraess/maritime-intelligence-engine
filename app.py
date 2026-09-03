"""Streamlit entry point for the Maritime Intelligence Engine.

The presentation layer delegates ingestion and analytics to ``src`` modules.
The application uses only real AIS observations and has no synthetic,
mock, fallback, or fabricated AIS mode.
"""

from __future__ import annotations

import streamlit as st
from dotenv import load_dotenv

from src.config.regions import (
    REGION_OPTIONS,
    REGION_PRESETS,
    format_bbox,
    region_name_for_bbox,
)
from src.config.settings import (
    AppSettings,
    COLLECTION_DURATION_OPTIONS,
    RegionBBox,
    _validate_bbox,
)
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
from src.ui.workspace_controls import NAVIGATION, render_aux_workspace_controls
from src.ui.temporal import OPERATOR_TIMEZONE_OPTIONS


load_dotenv()

st.set_page_config(
    page_title="Maritime Intelligence Engine",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_css()


def _read_settings() -> AppSettings:
    """Load runtime settings from Streamlit secrets/environment."""
    try:
        secrets = st.secrets
    except Exception:
        secrets = None
    return AppSettings.from_runtime(secrets)


def _with_settings(
    settings: AppSettings,
    *,
    bboxes: tuple[RegionBBox, ...] | None = None,
    bbox: RegionBBox | None = None,
    config_error: str | None = None,
    collection_seconds: float | None = None,
    historical_persistence_enabled: bool | None = None,
) -> AppSettings:
    """Return settings with only the requested runtime values changed."""
    active = tuple(bboxes if bboxes is not None else settings.monitoring_bboxes)
    if not active:
        active = (settings.bbox,)
    primary = bbox if bbox is not None else active[0]
    return AppSettings(
        aisstream_api_key=settings.aisstream_api_key,
        bbox=primary,
        monitoring_bboxes=active,
        collection_seconds=(
            settings.collection_seconds
            if collection_seconds is None
            else collection_seconds
        ),
        max_messages=settings.max_messages,
        max_vessels=settings.max_vessels,
        stale_after_seconds=settings.stale_after_seconds,
        provider=settings.provider,
        config_error=(
            settings.config_error if config_error is None else config_error
        ),
        database_url=settings.database_url,
        historical_persistence_enabled=(
            settings.historical_persistence_enabled
            if historical_persistence_enabled is None
            else historical_persistence_enabled
        ),
    )


def _normalize_bbox(bbox: RegionBBox) -> RegionBBox:
    (min_lat, min_lon), (max_lat, max_lon) = bbox
    return (
        (round(float(min_lat), 5), round(float(min_lon), 5)),
        (round(float(max_lat), 5), round(float(max_lon), 5)),
    )


def _normalize_bboxes(bboxes: tuple[RegionBBox, ...]) -> tuple[RegionBBox, ...]:
    """Preserve operator order; A/B order is part of session identity."""
    return tuple(_normalize_bbox(bbox) for bbox in bboxes)


def _engine_signature(settings: AppSettings) -> tuple:
    """Build the state signature that defines a live engine session."""
    return (
        settings.aisstream_api_key,
        _normalize_bboxes(settings.monitoring_bboxes),
        settings.max_messages,
        settings.max_vessels,
        settings.stale_after_seconds,
        settings.provider,
        settings.config_error,
    )


def _engine_for(settings: AppSettings) -> MaritimeIntelligenceEngine:
    """Return the engine associated with the current live configuration."""
    signature = _engine_signature(settings)
    if st.session_state.get("engine_signature") != signature:
        previous_engine = st.session_state.get("engine")
        if previous_engine is not None:
            previous_engine.historical_writer.close()
        st.session_state.engine = create_engine(settings)
        st.session_state.engine_signature = signature
        st.session_state.pop("selected_mmsi", None)
        st.session_state.pop("selected_mmsi_a", None)
        st.session_state.pop("selected_mmsi_b", None)
        st.session_state.pop("selected_mmsi_unified", None)

    engine = st.session_state.engine
    engine.configure_historical_writer(
        settings.database_url,
        settings.historical_persistence_enabled,
    )
    return engine


def _connection_state(settings: AppSettings, engine: MaritimeIntelligenceEngine) -> str:
    if not settings.aisstream_api_key:
        return "NOT CONFIGURED"
    return engine.snapshot().status.state


def _bbox_values(bbox: RegionBBox) -> tuple[float, float, float, float]:
    (min_lat, min_lon), (max_lat, max_lon) = bbox
    return float(min_lat), float(min_lon), float(max_lat), float(max_lon)


def _render_region_slot(
    label: str,
    settings: AppSettings,
    existing: list[RegionBBox],
) -> tuple[RegionBBox, str, str | None]:
    """Render one region selector, including a fully functional Custom box."""
    index = 0 if label == "A" else 1
    fallback = existing[index] if len(existing) > index else existing[0]
    current = region_name_for_bbox(fallback) or "Custom"
    options = list(REGION_OPTIONS)
    if current not in options:
        current = "Custom"

    selected = st.selectbox(
        f"Region {label}",
        options,
        index=options.index(current),
        key=f"monitor_region_{label.lower()}",
    )

    if selected != "Custom":
        bbox = REGION_PRESETS[selected]
        st.caption(f"{label} · {selected} · {format_bbox(bbox)}")
    else:
        keys = {
            "min_lat": f"region_{label.lower()}_min_lat",
            "min_lon": f"region_{label.lower()}_min_lon",
            "max_lat": f"region_{label.lower()}_max_lat",
            "max_lon": f"region_{label.lower()}_max_lon",
        }
        values = _bbox_values(fallback)
        min_lat = st.number_input("Min Latitude", value=values[0], min_value=-90.0, max_value=90.0, step=0.01, format="%.5f", key=keys["min_lat"])
        min_lon = st.number_input("Min Longitude", value=values[1], min_value=-180.0, max_value=180.0, step=0.01, format="%.5f", key=keys["min_lon"])
        max_lat = st.number_input("Max Latitude", value=values[2], min_value=-90.0, max_value=90.0, step=0.01, format="%.5f", key=keys["max_lat"])
        max_lon = st.number_input("Max Longitude", value=values[3], min_value=-180.0, max_value=180.0, step=0.01, format="%.5f", key=keys["max_lon"])
        bbox = ((min_lat, min_lon), (max_lat, max_lon))
        st.caption(f"{label} · Custom · {format_bbox(bbox)}")

    try:
        _validate_bbox(bbox)
    except ValueError as exc:
        return bbox, selected, str(exc)
    return bbox, selected, None


def _render_sidebar(
    settings: AppSettings,
) -> tuple[AppSettings, str, bool, bool, bool]:
    """Render mission and map controls in the sidebar."""
    region_changed = False
    with st.sidebar:
        connection_placeholder = st.empty()
        mission_placeholder = st.empty()

        existing = list(
            st.session_state.get("monitoring_bboxes", settings.monitoring_bboxes)
        ) or [settings.bbox]

        with st.expander("MAP CONFIGURATION", expanded=False):
            st.caption(
                "Region A + Region B use one MIE app and one AISStream subscription."
            )
            bbox_a, name_a, error_a = _render_region_slot("A", settings, existing)
            bbox_b, name_b, error_b = _render_region_slot("B", settings, existing)

            if name_a == name_b and name_a != "Custom":
                error_b = "Region A and Region B must be different."

            region_error = error_a or error_b
            bboxes = (bbox_a, bbox_b)
            previous = tuple(existing)
            region_changed = _normalize_bboxes(bboxes) != _normalize_bboxes(previous)

            if region_error is None:
                settings = _with_settings(settings, bboxes=bboxes, bbox=bbox_a)
                st.session_state["monitoring_bboxes"] = bboxes
                if region_changed:
                    st.warning(
                        "Monitoring regions changed. The previous live session "
                        "will be discarded when the new subscription is collected."
                    )
            else:
                st.error(region_error)
                settings = _with_settings(
                    settings,
                    bboxes=bboxes,
                    bbox=bbox_a,
                    config_error=region_error,
                )

        engine = _engine_for(settings)
        conn = _connection_state(settings, engine)
        conn_upper = str(conn).upper()
        if conn_upper in {"LIVE AIS", "LIVE"}:
            pill_cls = "status-live"
        elif "CONNECT" in conn_upper:
            pill_cls = "status-connecting"
        else:
            pill_cls = "status-disconnected"
        connection_placeholder.markdown(
            "<div class='side-header'>"
            "<div class='brand'>MIE</div>"
            "<div class='side-subtitle'>MARITIME INTELLIGENCE</div>"
            f"<div class='side-status'><span class='status-pill {pill_cls}'>{conn}</span>"
            "<span class='side-provider'>AISSTREAM</span></div></div>",
            unsafe_allow_html=True,
        )

        can_collect = settings.config_error is None
        collect = False
        clear = False
        with mission_placeholder.container():
            with st.expander("MISSION CONTEXT", expanded=False):
                duration_options = list(COLLECTION_DURATION_OPTIONS)
                duration_index = min(
                    range(len(duration_options)),
                    key=lambda i: abs(
                        duration_options[i] - settings.collection_seconds
                    ),
                )
                st.selectbox(
                    "Collection duration",
                    duration_options,
                    index=duration_index,
                    format_func=lambda seconds: f"Collection duration · {seconds} s",
                    key="collection_duration_seconds",
                    label_visibility="collapsed",
                )
                selected_duration = st.session_state["collection_duration_seconds"]
                if float(selected_duration) != settings.collection_seconds:
                    settings = _with_settings(
                        settings,
                        collection_seconds=float(selected_duration),
                    )

                can_collect = settings.config_error is None
                collect = st.button(
                    "Collect Real AIS · 2 Regions",
                    width="stretch",
                    type="primary",
                    disabled=not can_collect,
                )
                clear = st.button("Clear Session", width="stretch")

        module = st.session_state.get("workspace_module", "Overview")
        if module not in NAVIGATION:
            module = "Overview"
        views = NAVIGATION[module]
        page = views[0]
        if len(views) > 1:
            page = st.session_state.get(f"workspace_subarea_{module}", views[0])
            if page not in views:
                page = views[0]

    return settings, page, collect, clear, region_changed


def main() -> None:
    """Run the Streamlit application."""
    settings = _read_settings()
    if "historical_persistence_enabled" in st.session_state:
        settings = _with_settings(
            settings,
            historical_persistence_enabled=bool(
                st.session_state["historical_persistence_enabled"]
            ),
        )

    settings, page, collect, clear, region_changed = _render_sidebar(settings)
    engine = _engine_for(settings)

    if region_changed:
        notice(
            "Monitoring regions changed. Run Collect Real AIS · 2 Regions "
            "to open the new single AISStream subscription."
        )

    if clear:
        engine.clear_session_data()
        for key in (
            "selected_mmsi",
            "selected_mmsi_a",
            "selected_mmsi_b",
            "selected_mmsi_unified",
        ):
            st.session_state.pop(key, None)
        st.session_state.pop("monitoring_bboxes", None)
        st.rerun()

    if collect:
        with st.spinner(
            "Opening one AISStream WebSocket for "
            f"{len(settings.monitoring_bboxes)} real AIS regions and collecting "
            f"for {int(settings.collection_seconds)} seconds…"
        ):
            received = engine.collect(seconds=settings.collection_seconds)

        if received:
            st.session_state["collection_result"] = (
                "success",
                "Collection elapsed "
                f"{engine.last_collection_seconds:.1f} s · received {received:,} "
                f"real AIS position report(s) across {len(settings.monitoring_bboxes)} regions.",
            )
        else:
            st.session_state["collection_result"] = (
                "warning",
                "Collection elapsed "
                f"{engine.last_collection_seconds:.1f} s · REAL AIS DATA "
                "UNAVAILABLE — no real observations were received in this collection window.",
            )
        st.rerun()

    collection_result = st.session_state.pop("collection_result", None)
    if collection_result:
        result_type, result_message = collection_result
        if result_type == "success":
            st.success(result_message)
        else:
            st.warning(result_message)

    snapshot = engine.snapshot()
    render_header(snapshot.status, page)

    if page != "Overview":
        render_aux_workspace_controls(engine, settings, st.columns(3))

    if snapshot.status.state != "LIVE AIS":
        status_type = (
            "red"
            if snapshot.status.state in {"DISCONNECTED", "REAL AIS DATA UNAVAILABLE"}
            else ""
        )
        notice(snapshot.status.state + ": " + snapshot.status.reason, status_type)

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
