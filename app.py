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
    _validate_bbox,
)
from src.intelligence.engine import (
    MaritimeIntelligenceEngine,
    create_engine,
)
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
from src.ui.presentation import (
    inject_css,
    notice,
    render_header,
)
from src.ui.temporal import OPERATOR_TIMEZONE_OPTIONS


load_dotenv()

st.set_page_config(
    page_title="Maritime Intelligence Engine",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_css()


# ----------------------------------------------------------------------
# WORKSPACE NAVIGATION
# ----------------------------------------------------------------------

NAVIGATION = {
    "Overview": ("Overview",),
    "Vessels": (
        "Fleet",
        "Vessel Intelligence",
    ),
    "Movement & Behavior": (
        "Trajectory Analysis",
        "Behavior",
        "Similarity",
    ),
    "Anomalies & Traffic": (
        "Anomalies",
        "Traffic",
    ),
    "Data & System": (
        "Data Quality",
        "System",
    ),
}


# ----------------------------------------------------------------------
# SETTINGS
# ----------------------------------------------------------------------


def _read_settings() -> AppSettings:
    """Load runtime settings from Streamlit secrets/environment."""

    try:
        secrets = st.secrets
    except Exception:
        secrets = None

    return AppSettings.from_runtime(secrets)


def _with_bbox(
    settings: AppSettings,
    bbox: tuple[tuple[float, float], tuple[float, float]],
    config_error: str | None = None,
    collection_seconds: float | None = None,
    historical_persistence_enabled: bool | None = None,
) -> AppSettings:
    """Return settings with only the requested runtime values changed."""

    return AppSettings(
        aisstream_api_key=settings.aisstream_api_key,
        bbox=bbox,
        collection_seconds=(
            settings.collection_seconds
            if collection_seconds is None
            else collection_seconds
        ),
        max_messages=settings.max_messages,
        max_vessels=settings.max_vessels,
        stale_after_seconds=settings.stale_after_seconds,
        provider=settings.provider,
        config_error=config_error,
        database_url=settings.database_url,
        historical_persistence_enabled=(
            settings.historical_persistence_enabled
            if historical_persistence_enabled is None
            else historical_persistence_enabled
        ),
    )


def _bbox_values(
    bbox: tuple[tuple[float, float], tuple[float, float]],
) -> tuple[float, float, float, float]:
    """Flatten a bounding box for Streamlit numeric inputs."""

    (min_lat, min_lon), (max_lat, max_lon) = bbox

    return (
        float(min_lat),
        float(min_lon),
        float(max_lat),
        float(max_lon),
    )


# ----------------------------------------------------------------------
# ENGINE LIFECYCLE
# ----------------------------------------------------------------------


def _normalize_bbox(
    bbox: tuple[tuple[float, float], tuple[float, float]],
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Stable bbox for session identity (avoids float-noise engine resets)."""

    (min_lat, min_lon), (max_lat, max_lon) = bbox
    return (
        (round(float(min_lat), 5), round(float(min_lon), 5)),
        (round(float(max_lat), 5), round(float(max_lon), 5)),
    )


def _engine_signature(
    settings: AppSettings,
) -> tuple:
    """Build the state signature that defines a live engine session.

    Only AIS identity parameters belong here. Collection duration and
    historical-persistence toggles must not recreate the in-memory session.
    Bbox coordinates are rounded so widget float noise does not discard
    ObservationStore / tracks on ordinary Streamlit reruns.
    """

    return (
        settings.aisstream_api_key,
        _normalize_bbox(settings.bbox),
        settings.max_messages,
        settings.max_vessels,
        settings.stale_after_seconds,
        settings.provider,
        settings.config_error,
    )


def _engine_for(
    settings: AppSettings,
) -> MaritimeIntelligenceEngine:
    """Return the engine associated with the current runtime configuration.

    A change in the live AIS configuration, especially the monitoring
    bounding box, creates a new isolated engine session.
    """

    signature = _engine_signature(settings)
    current_signature = st.session_state.get(
        "engine_signature"
    )

    if current_signature != signature:
        previous_engine = st.session_state.get(
            "engine"
        )

        if previous_engine is not None:
            previous_engine.historical_writer.close()

        st.session_state.engine = create_engine(
            settings
        )
        st.session_state.engine_signature = signature

        # Vessel selection belongs to the previous region/session.
        st.session_state.pop(
            "selected_mmsi",
            None,
        )

    engine = st.session_state.engine

    engine.configure_historical_writer(
        settings.database_url,
        settings.historical_persistence_enabled,
    )

    return engine


# ----------------------------------------------------------------------
# CONNECTION STATE
# ----------------------------------------------------------------------


def _connection_state(
    settings: AppSettings,
    engine: MaritimeIntelligenceEngine,
) -> str:
    """Return the user-facing state from the current engine snapshot."""

    if not settings.aisstream_api_key:
        return "NOT CONFIGURED"

    return engine.snapshot().status.state


# ----------------------------------------------------------------------
# SIDEBAR
# ----------------------------------------------------------------------


def _render_sidebar(
    settings: AppSettings,
) -> tuple[
    AppSettings,
    str,
    bool,
    bool,
    bool,
]:
    """Render the operational control console sidebar and return user selections.

    Presentation-only grouping (MISSION / DATA / ANALYSIS / SYSTEM). Widget
    keys, defaults, and control flow are unchanged from the previous sidebar.
    """

    region_changed = False

    with st.sidebar:
        connection_placeholder = st.empty()

        st.markdown(
            "<div class='side-section-title'>MISSION CONTEXT</div>",
            unsafe_allow_html=True,
        )

        duration_options = list(COLLECTION_DURATION_OPTIONS)

        duration_index = min(
            range(len(duration_options)),
            key=lambda index: abs(
                duration_options[index] - settings.collection_seconds
            ),
        )

        selected_duration = st.selectbox(
            "Collection duration",
            duration_options,
            index=duration_index,
            format_func=lambda seconds: (
                f"Collection duration · {seconds} s"
            ),
            key="collection_duration_seconds",
            label_visibility="collapsed",
        )

        if float(selected_duration) != settings.collection_seconds:
            settings = _with_bbox(
                settings,
                settings.bbox,
                settings.config_error,
                collection_seconds=float(selected_duration),
            )

        collect = st.button(
            "Collect Real AIS",
            width="stretch",
            type="primary",
            disabled=settings.config_error is not None,
        )

        clear = st.button(
            "Clear Session",
            width="stretch",
        )

        st.markdown(
            "<div class='side-section-label'>Region</div>",
            unsafe_allow_html=True,
        )

        with st.expander(
            "Bounding Box",
            expanded=False,
        ):
            active_bbox = st.session_state.get(
                "active_bbox",
                settings.bbox,
            )

            current_region = region_name_for_bbox(active_bbox)

            if current_region in REGION_OPTIONS:
                preset_index = REGION_OPTIONS.index(current_region)
            else:
                preset_index = REGION_OPTIONS.index("Custom")

            selected_region = st.selectbox(
                "AIS region preset",
                REGION_OPTIONS,
                index=preset_index,
                key="region_preset",
            )

            if selected_region != "Custom":
                candidate_bbox = REGION_PRESETS[selected_region]

                for key, value in zip(
                    (
                        "bbox_min_lat",
                        "bbox_min_lon",
                        "bbox_max_lat",
                        "bbox_max_lon",
                    ),
                    _bbox_values(candidate_bbox),
                ):
                    st.session_state[key] = value

                st.caption(
                    f"{selected_region} · {format_bbox(candidate_bbox)}"
                )

            else:
                st.caption(
                    "Custom · applied to the next "
                    "real AIS subscription"
                )

                min_lat = st.number_input(
                    "Min Latitude",
                    value=float(active_bbox[0][0]),
                    min_value=-90.0,
                    max_value=90.0,
                    step=0.01,
                    format="%.5f",
                    key="bbox_min_lat",
                )

                min_lon = st.number_input(
                    "Min Longitude",
                    value=float(active_bbox[0][1]),
                    min_value=-180.0,
                    max_value=180.0,
                    step=0.01,
                    format="%.5f",
                    key="bbox_min_lon",
                )

                max_lat = st.number_input(
                    "Max Latitude",
                    value=float(active_bbox[1][0]),
                    min_value=-90.0,
                    max_value=90.0,
                    step=0.01,
                    format="%.5f",
                    key="bbox_max_lat",
                )

                max_lon = st.number_input(
                    "Max Longitude",
                    value=float(active_bbox[1][1]),
                    min_value=-180.0,
                    max_value=180.0,
                    step=0.01,
                    format="%.5f",
                    key="bbox_max_lon",
                )

                candidate_bbox = (
                    (min_lat, min_lon),
                    (max_lat, max_lon),
                )

            region_error: str | None = None

            try:
                _validate_bbox(candidate_bbox)
            except ValueError as exc:
                region_error = str(exc)
                st.error(region_error)

            if region_error is None:
                previous_bbox = st.session_state.get(
                    "active_bbox",
                    settings.bbox,
                )

                region_changed = (
                    _normalize_bbox(candidate_bbox)
                    != _normalize_bbox(previous_bbox)
                )

                st.session_state.active_bbox = candidate_bbox

                if candidate_bbox != settings.bbox:
                    settings = _with_bbox(
                        settings,
                        candidate_bbox,
                    )

                if region_changed:
                    st.warning(
                        "Region changed. "
                        "The previous live AIS session "
                        "will be discarded when the new "
                        "region is applied."
                    )

            else:
                settings = _with_bbox(
                    settings,
                    active_bbox,
                    region_error,
                )

        st.markdown(
            "<div class='side-section-title'>DATA</div>",
            unsafe_allow_html=True,
        )

        historical_enabled = st.checkbox(
            "Historical Persistence",
            value=settings.historical_persistence_enabled,
            key="historical_persistence_enabled",
            disabled=settings.database_url is None,
            help=(
                "Persiste somente observações AIS reais "
                "e válidas após a coleta; não altera o live."
            ),
        )

        if (
            bool(historical_enabled)
            != settings.historical_persistence_enabled
        ):
            settings = _with_bbox(
                settings,
                settings.bbox,
                historical_persistence_enabled=bool(
                    historical_enabled
                ),
            )

        if settings.database_url is None:
            historical_state = "HISTORICAL DATABASE NOT CONFIGURED"
        elif settings.historical_persistence_enabled:
            historical_state = "HISTORICAL PERSISTENCE ENABLED"
        else:
            historical_state = "HISTORICAL PERSISTENCE OFF"

        st.markdown(
            f"<div class='data-value side-muted'>{historical_state}</div>",
            unsafe_allow_html=True,
        )

        st.markdown(
            "<div class='side-section-title'>ANALYSIS</div>",
            unsafe_allow_html=True,
        )

        modules = list(NAVIGATION)

        module = st.radio(
            "Workspace module",
            modules,
            label_visibility="collapsed",
            key="workspace_module",
        )

        views = NAVIGATION[module]

        if len(views) == 1:
            page = views[0]
        else:
            page = st.radio(
                f"{module} subarea",
                views,
                label_visibility="collapsed",
                key=f"workspace_subarea_{module}",
            )

        # Resolve the final engine after region controls have been applied,
        # then render the indicator from the same snapshot used by SYSTEM.
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
            f"<div class='side-status'>"
            f"<span class='status-pill {pill_cls}'>{conn}</span>"
            f"<span class='side-provider'>AISSTREAM</span>"
            f"</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        with st.expander("SYSTEM", expanded=False):
            st.markdown(
                f"<div class='data-label'>Connection</div>"
                f"<div class='data-value'>{conn}</div>",
                unsafe_allow_html=True,
            )

            st.selectbox(
                "Operator timezone",
                OPERATOR_TIMEZONE_OPTIONS,
                index=0,
                key="operator_timezone",
                format_func=lambda value: (
                    f"Operator time · {value}"
                ),
                label_visibility="collapsed",
            )

    return (
        settings,
        page,
        collect,
        clear,
        region_changed,
    )


# ----------------------------------------------------------------------
# MAIN APPLICATION
# ----------------------------------------------------------------------


def main() -> None:
    """Run the Streamlit application."""

    settings = _read_settings()

    (
        settings,
        page,
        collect,
        clear,
        region_changed,
    ) = _render_sidebar(settings)

    engine = _engine_for(
        settings
    )

    if region_changed:
        notice(
            "Monitoring region changed. "
            "The previous live AIS session has been "
            "discarded. Run Collect Real AIS to open "
            "the new subscription."
        )

    if clear:
        engine.clear_session_data()

        st.session_state.pop(
            "selected_mmsi",
            None,
        )

        st.rerun()

    if collect:
        with st.spinner(
            "Opening AISStream WebSocket and "
            f"collecting real AIS messages for "
            f"{int(settings.collection_seconds)} seconds…"
        ):
            received = engine.collect(
                seconds=settings.collection_seconds
            )

        if received:
            st.session_state["collection_result"] = (
                "success",
                "Collection elapsed "
                f"{engine.last_collection_seconds:.1f} s · "
                f"received {received:,} real AIS "
                "position report(s).",
            )
        else:
            st.session_state["collection_result"] = (
                "warning",
                "Collection elapsed "
                f"{engine.last_collection_seconds:.1f} s · "
                "REAL AIS DATA UNAVAILABLE — "
                "no real observations were received "
                "in this collection window.",
            )

        # The sidebar is rendered before collection. Rerun once so its
        # connection indicator observes the provider state produced by the
        # completed collection instead of the pre-collection state.
        st.rerun()

    collection_result = st.session_state.pop(
        "collection_result",
        None,
    )
    if collection_result:
        result_type, result_message = collection_result
        if result_type == "success":
            st.success(result_message)
        else:
            st.warning(result_message)

    snapshot = engine.snapshot()

    render_header(
        snapshot.status,
        page,
    )

    if snapshot.status.state != "LIVE AIS":
        status_type = (
            "red"
            if snapshot.status.state
            in {
                "DISCONNECTED",
                "REAL AIS DATA UNAVAILABLE",
            }
            else ""
        )

        notice(
            (
                snapshot.status.state
                + ": "
                + snapshot.status.reason
            ),
            status_type,
        )

    if page == "Overview":
        render_overview(
            engine,
            snapshot,
            settings,
        )

    elif page == "Fleet":
        render_vessels(
            engine,
            snapshot,
            settings,
        )

    elif page == "Vessel Intelligence":
        render_vessel_intelligence(
            engine,
            snapshot,
            settings,
        )

    elif page == "Trajectory Analysis":
        render_trajectory_analysis(
            engine,
            snapshot,
            settings,
        )

    elif page == "Behavior":
        render_behavior(
            engine,
            snapshot,
            settings,
        )

    elif page == "Similarity":
        render_similarity(
            engine,
            snapshot,
            settings,
        )

    elif page == "Anomalies":
        render_anomalies(
            engine,
            snapshot,
            settings,
        )

    elif page == "Traffic":
        render_traffic(
            engine,
            snapshot,
            settings,
        )

    elif page == "Data Quality":
        render_data_quality(
            engine,
            snapshot,
            settings,
        )

    elif page == "System":
        render_system(
            engine,
            snapshot,
            settings,
        )


if __name__ == "__main__":
    main()
