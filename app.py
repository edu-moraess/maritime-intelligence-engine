"""Streamlit entry point for the Maritime Intelligence Engine.

The presentation layer delegates ingestion and analytics to ``src`` modules.
The application uses only real AIS observations and has no synthetic,
mock, fallback, or fabricated AIS mode.
"""

from __future__ import annotations

import threading

import streamlit as st
import streamlit.components.v1 as components
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
from src.ui import _install_floating_sidebar_controller
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
from src.ui.pages_overview import render_overview_workspace_controls
from src.ui.dual_region_overview import render_overview_context, render_overview_map
from src.ui.workspace_controls import NAVIGATION, render_aux_workspace_controls
from src.ui.temporal import OPERATOR_TIMEZONE_OPTIONS


load_dotenv()

st.set_page_config(
    page_title="Maritime Intelligence Engine",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# UI browser enhancements must run only after Streamlit page configuration.
_install_floating_sidebar_controller()

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
        ingestion_queue_capacity=settings.ingestion_queue_capacity,
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
        settings.ingestion_queue_capacity,
        settings.provider,
        settings.config_error,
        settings.database_url,
    )


class _ProcessEngineRegistry:
    """Process-shared owner of the active engine and its one AIS worker."""

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.signature: tuple | None = None
        self.engine: MaritimeIntelligenceEngine | None = None

    def current_engine(self) -> MaritimeIntelligenceEngine | None:
        with self.lock:
            return self.engine

    def current_settings(self) -> AppSettings | None:
        with self.lock:
            return self.engine.settings if self.engine is not None else None

    def get(self, signature: tuple, settings: AppSettings) -> MaritimeIntelligenceEngine:
        with self.lock:
            if self.engine is None or self.signature != signature:
                previous = self.engine
                archived_observations = []
                if previous is not None:
                    stopped = previous.stop_live_monitoring(timeout=10.0)
                    if not stopped:
                        raise RuntimeError(
                            "The previous AIS worker is still alive; refusing to start a second subscription."
                        )
                    if getattr(previous, "_unpersisted_observations", []):
                        raise RuntimeError(
                            "Operational configuration change blocked: unpersisted real AIS "
                            "observations remain in memory. Enable historical persistence and "
                            "finalize the session before changing monitoring configuration."
                        )
                    archived_observations = previous.store.all()
                    previous.historical_writer.close()
                self.engine = create_engine(settings)
                if archived_observations:
                    self.engine.store.extend(archived_observations)
                self.signature = signature
            return self.engine


@st.cache_resource(show_spinner=False)
def _process_engine_registry() -> _ProcessEngineRegistry:
    """One registry per Python process; not a cross-replica distributed lock."""
    return _ProcessEngineRegistry()


def _engine_for(settings: AppSettings) -> MaritimeIntelligenceEngine:
    """Return the process-shared engine associated with the active configuration."""
    signature = _engine_signature(settings)
    if st.session_state.get("engine_signature") != signature:
        st.session_state.engine_signature = signature
        for key in (
            "selected_mmsi",
            "selected_mmsi_a",
            "selected_mmsi_b",
            "selected_mmsi_unified",
        ):
            st.session_state.pop(key, None)
    try:
        return _process_engine_registry().get(signature, settings)
    except RuntimeError as exc:
        st.error(f"Operational configuration change blocked: {exc}")
        st.stop()


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
) -> tuple[AppSettings, str, bool, bool, bool, bool, bool, bool]:
    """Render mission and map controls in the sidebar."""
    region_changed = False
    active_settings = _process_engine_registry().current_settings()
    if active_settings is not None:
        settings = _with_settings(
            settings,
            bboxes=active_settings.monitoring_bboxes,
            bbox=active_settings.bbox,
            config_error=active_settings.config_error,
        )
    with st.sidebar:
        connection_placeholder = st.empty()
        mission_placeholder = st.empty()

        existing = list(settings.monitoring_bboxes) or [settings.bbox]
        if len(existing) == 1:
            default_second = REGION_PRESETS["Malacca Strait"]
            if _normalize_bbox(existing[0]) == _normalize_bbox(default_second):
                default_second = REGION_PRESETS["Singapore"]
            existing.append(default_second)
        st.session_state["monitoring_bboxes"] = tuple(existing)
        for label, bbox in zip(("a", "b"), existing):
            # Initialize widget state once. Re-seeding these keys on every
            # rerun overwrites the operator's selection with the active engine
            # regions before Streamlit can process the new choice.
            region_key = f"monitor_region_{label}"
            selected_region = region_name_for_bbox(bbox) or "Custom"
            if region_key not in st.session_state:
                st.session_state[region_key] = selected_region
            if selected_region == "Custom":
                for key, value in zip(
                    (
                        f"region_{label}_min_lat",
                        f"region_{label}_min_lon",
                        f"region_{label}_max_lat",
                        f"region_{label}_max_lon",
                    ),
                    _bbox_values(bbox),
                ):
                    if key not in st.session_state:
                        st.session_state[key] = value

        with st.expander("MAP CONFIGURATION", expanded=False):
            st.caption(
                "One active AISStream subscription per Python process; independent deployment replicas may each own one."
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
                        "Monitoring regions changed. The previous session is retained as historical "
                        "in-memory observations; the new subscription will use the updated regions."
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
        elif "CONNECT" in conn_upper or conn_upper in {"DEGRADED", "RECONNECTING"}:
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

        can_collect = settings.validate_for_connection()[0]
        worker_status = engine.live_worker.status()
        worker_state = worker_status.state
        live_active = worker_status.thread_alive or worker_state not in {"STOPPED", "ERROR"}
        finite_active = engine.finite_collection_status()["state"] == "RUNNING"
        collect = False
        clear = False
        clear_view = False
        start_live = False
        stop_live = False
        st.markdown(
            "<div class='side-section-title'>MISSION CONTEXT</div>",
            unsafe_allow_html=True,
        )
        with mission_placeholder.container():
            with st.expander("MISSION CONTEXT", expanded=True):
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
    
                can_collect = settings.validate_for_connection()[0]
                live_col, stop_col = st.columns(2)
                with live_col:
                    start_live = st.button(
                        "Start Live AIS",
                        width="stretch",
                        type="primary",
                        disabled=not can_collect or live_active or finite_active,
                        help="Starts one process-local continuous AIS subscription shared by MIE sessions.",
                    )
                with stop_col:
                    stop_live = st.button(
                        "Stop Live AIS",
                        width="stretch",
                        disabled=not live_active,
                    )
                collect = st.button(
                    "Collect Finite AIS Window",
                    width="stretch",
                    disabled=not can_collect or live_active or finite_active,
                    help="Runs a bounded collection in the background; unavailable while continuous monitoring is active.",
                )
                clear_view = st.button(
                    "Clear View",
                    width="stretch",
                    help="Clears view selections only. It does not stop AIS collection or delete observations.",
                )
                clear = st.button(
                    "Clear Session",
                    width="stretch",
                    help="Stops ingestion and clears volatile session data only after persistence is confirmed.",
                )

        module = st.session_state.get("workspace_module", "Overview")
        if module not in NAVIGATION:
            module = "Overview"
        views = NAVIGATION[module]
        page = views[0]
        if len(views) > 1:
            page = st.session_state.get(f"workspace_subarea_{module}", views[0])
            if page not in views:
                page = views[0]

    return settings, page, collect, clear, clear_view, region_changed, start_live, stop_live


def _render_collection_timer(seconds: float) -> None:
    """Render a compact client-side countdown while the blocking AIS collection runs."""
    duration = max(1, int(round(float(seconds))))
    components.html(
        f"""
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                    color: #78909c; font-size: 12px; line-height: 1.2;
                    padding: 2px 0 0; width: 100%;">
          <div style="display:flex; align-items:center; gap:7px; white-space:nowrap;">
            <span id="mie-dot" style="font-size:10px;">●</span>
            <span id="mie-label">COLLECTING · {duration // 60:02d}:{duration % 60:02d} / {duration // 60:02d}:{duration % 60:02d}</span>
          </div>
          <div style="height:2px; margin-top:5px; background:rgba(120,144,156,.16); overflow:hidden;">
            <div id="mie-progress" style="height:100%; width:0%; background:rgba(120,144,156,.55);"></div>
          </div>
        </div>
        <script>
        (() => {{
          const total = {duration};
          const started = Date.now();
          const label = document.getElementById("mie-label");
          const progress = document.getElementById("mie-progress");
          const format = value => {{
            const minutes = Math.floor(value / 60);
            const seconds = value % 60;
            return String(minutes).padStart(2, "0") + ":" + String(seconds).padStart(2, "0");
          }};
          const tick = () => {{
            const elapsed = Math.min(total, Math.floor((Date.now() - started) / 1000));
            const remaining = Math.max(0, total - elapsed);
            label.textContent = "COLLECTING · " + format(remaining) + " / " + format(total);
            progress.style.width = ((elapsed / total) * 100).toFixed(1) + "%";
            if (remaining > 0) window.setTimeout(tick, 250);\n            else label.textContent = "FINALIZING · PROCESSING RESULTS";
          }};
          tick();
        }})();
        </script>
        """,
        height=34,
        scrolling=False,
    )


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

    settings, page, collect, clear, clear_view, region_changed, start_live, stop_live = _render_sidebar(settings)
    engine = _engine_for(settings)

    if clear_view:
        for key in (
            "selected_mmsi",
            "selected_mmsi_a",
            "selected_mmsi_b",
            "selected_mmsi_unified",
        ):
            st.session_state.pop(key, None)
        st.rerun()

    if region_changed:
        notice(
            "Monitoring regions changed. Start Live AIS or run a finite collection "
            "to open the new process-local AISStream subscription."
        )

    if start_live:
        started = engine.start_live_monitoring()
        if started:
            st.session_state["live_monitoring_result"] = ("success", "Continuous AIS monitoring started.")
        else:
            st.session_state["live_monitoring_result"] = ("info", "Continuous AIS monitoring is already active.")
        st.rerun()

    if stop_live:
        stopped = engine.stop_live_monitoring()
        st.session_state["live_monitoring_result"] = (
            "success" if stopped else "warning",
            "Continuous AIS monitoring stopped." if stopped else "Worker did not stop before timeout.",
        )
        st.rerun()

    live_result = st.session_state.pop("live_monitoring_result", None)
    if live_result:
        result_type, result_message = live_result
        if result_type == "success":
            st.success(result_message)
        elif result_type == "warning":
            st.warning(result_message)
        else:
            st.info(result_message)

    if clear:
        try:
            engine.clear_session_data()
        except RuntimeError as exc:
            st.error(f"Session clear blocked: {exc}")
        else:
            for key in (
                "selected_mmsi",
                "selected_mmsi_a",
                "selected_mmsi_b",
                "selected_mmsi_unified",
            ):
                st.session_state.pop(key, None)
            st.session_state.pop("monitoring_bboxes", None)
            st.rerun()

    start_error = st.session_state.pop("finite_collection_start_error", None)
    if start_error:
        st.error(start_error)
    if collect:
        try:
            started = engine.start_finite_collection(settings.collection_seconds)
        except (RuntimeError, ValueError) as exc:
            st.session_state["finite_collection_start_error"] = (
                f"Finite collection could not start: {exc}"
            )
        else:
            if not started:
                st.session_state["finite_collection_start_error"] = (
                    "A finite AIS collection is already running."
                )
        st.rerun()

    navigation_engine = _process_engine_registry().current_engine() or engine
    navigation_settings = _with_settings(
        settings,
        bboxes=navigation_engine.settings.monitoring_bboxes,
        bbox=navigation_engine.settings.bbox,
        config_error=navigation_engine.settings.config_error,
    )
    overview_map_controls = None

    if page == "Overview":
        @st.fragment(run_every="2s")
        def render_overview_context_fragment() -> None:
            """Refresh Overview context while leaving its navigation rail persistent."""
            active_engine = _process_engine_registry().current_engine() or engine
            active_settings = _with_settings(
                settings,
                bboxes=active_engine.settings.monitoring_bboxes,
                bbox=active_engine.settings.bbox,
                config_error=active_engine.settings.config_error,
            )
            snapshot = active_engine.snapshot()
            finite_status = active_engine.finite_collection_status()
            if finite_status["state"] == "RUNNING":
                st.info(
                    "FINITE AIS COLLECTION RUNNING · "
                    f"{finite_status['elapsed_seconds']:.0f}s elapsed · "
                    "waiting for real AIS reports; final count appears at completion"
                )
            elif finite_status["state"] == "COMPLETED":
                received = int(finite_status["received"])
                if received:
                    st.success(f"FINITE AIS COLLECTION COMPLETED · {received:,} real AIS reports received.")
                else:
                    st.warning("FINITE AIS COLLECTION COMPLETED · no real AIS observations were received.")
            elif finite_status["state"] == "FAILED":
                st.error(f"FINITE AIS COLLECTION FAILED · {finite_status['error']}")

            worker_is_active = snapshot.status.worker_state in {
                "STARTING", "CONNECTING", "LIVE", "RECONNECTING", "DEGRADED"
            }
            if snapshot.last_collection_breakdown and not worker_is_active:
                with st.expander("COLLECTION DIAGNOSTICS", expanded=True):
                    breakdown = snapshot.last_collection_breakdown
                    diagnostic_rows = (
                        ("AIS stream", "ais_stream"),
                        ("Historical restore", "historical_restore"),
                        ("Postgres persist", "postgres_persist"),
                        ("Region persistence", "region_persist"),
                        ("Environmental", "environmental"),
                        ("Recompute / ML", "recompute"),
                        ("Findings", "findings"),
                        ("Diagnostic overhead", "diagnostic_overhead"),
                        ("Total", "total"),
                    )
                    for label, key in diagnostic_rows:
                        st.caption(f"{label} · {breakdown.get(key, 0.0):.1f} s")
            render_header(snapshot.status, "Overview")
            if snapshot.status.state != "LIVE AIS":
                status_type = (
                    "red"
                    if snapshot.status.state in {"DISCONNECTED", "REAL AIS DATA UNAVAILABLE", "ERROR"}
                    else ""
                )
                notice(snapshot.status.state + ": " + snapshot.status.reason, status_type)
            render_overview_context(snapshot, active_settings)

        render_overview_context_fragment()

        # This rail is outside both timed fragments and now sits exactly between
        # the environmental context and the tactical map.
        overview_map_controls = render_overview_workspace_controls(
            navigation_engine, navigation_settings
        )

        @st.fragment(run_every="2s")
        def render_overview_map_fragment() -> None:
            """Refresh only the tactical map below the persistent workspace rail."""
            active_engine = _process_engine_registry().current_engine() or engine
            active_settings = _with_settings(
                settings,
                bboxes=active_engine.settings.monitoring_bboxes,
                bbox=active_engine.settings.bbox,
                config_error=active_engine.settings.config_error,
            )
            render_overview_map(
                active_engine,
                active_engine.snapshot(),
                active_settings,
                overview_map_controls,
            )

        render_overview_map_fragment()


    @st.fragment(run_every="2s")
    def render_live_workspace() -> None:
        """Refresh the active operational page while the process worker ingests AIS."""
        active_engine = _process_engine_registry().current_engine() or engine
        active_settings = _with_settings(
            settings,
            bboxes=active_engine.settings.monitoring_bboxes,
            bbox=active_engine.settings.bbox,
            config_error=active_engine.settings.config_error,
        )
        snapshot = active_engine.snapshot()
        finite_status = active_engine.finite_collection_status()
        if finite_status["state"] == "RUNNING":
            st.info(
                "FINITE AIS COLLECTION RUNNING · "
                f"{finite_status['elapsed_seconds']:.0f}s elapsed · "
                "waiting for real AIS reports; final count appears at completion"
            )
        elif finite_status["state"] == "COMPLETED":
            received = int(finite_status["received"])
            if received:
                st.success(f"FINITE AIS COLLECTION COMPLETED · {received:,} real AIS reports received.")
            else:
                st.warning("FINITE AIS COLLECTION COMPLETED · no real AIS observations were received.")
        elif finite_status["state"] == "FAILED":
            st.error(f"FINITE AIS COLLECTION FAILED · {finite_status['error']}")

        # Resolve navigation from current Session State on every fragment rerun.
        # A fragment-only rerun does not re-execute main() or refresh its closure.
        active_module = st.session_state.get("workspace_module", "Overview")
        if active_module not in NAVIGATION:
            active_module = "Overview"
        active_views = NAVIGATION[active_module]
        active_page = active_views[0]
        if len(active_views) > 1:
            candidate_page = st.session_state.get(
                f"workspace_subarea_{active_module}", active_views[0]
            )
            active_page = candidate_page if candidate_page in active_views else active_views[0]

        worker_is_active = snapshot.status.worker_state in {
            "STARTING", "CONNECTING", "LIVE", "RECONNECTING", "DEGRADED"
        }
        if snapshot.last_collection_breakdown and not worker_is_active:
            with st.expander("COLLECTION DIAGNOSTICS", expanded=True):
                breakdown = snapshot.last_collection_breakdown
                diagnostic_rows = (
                    ("AIS stream", "ais_stream"),
                    ("Historical restore", "historical_restore"),
                    ("Postgres persist", "postgres_persist"),
                    ("Region persistence", "region_persist"),
                    ("Environmental", "environmental"),
                    ("Recompute / ML", "recompute"),
                    ("Findings", "findings"),
                    ("Diagnostic overhead", "diagnostic_overhead"),
                    ("Total", "total"),
                )
                for label, key in diagnostic_rows:
                    st.caption(f"{label} · {breakdown.get(key, 0.0):.1f} s")
        render_header(snapshot.status, active_page)

        # Keep secondary-page workspace controls inside the same fragment as
        # the page they navigate. This avoids a split rerun boundary where the
        # top rail is rendered by the app script but its destination is refreshed
        # independently every two seconds.
        render_aux_workspace_controls(
            active_engine, active_settings, st.columns(3)
        )

        if snapshot.status.state != "LIVE AIS":
            status_type = (
                "red"
                if snapshot.status.state in {"DISCONNECTED", "REAL AIS DATA UNAVAILABLE", "ERROR"}
                else ""
            )
            notice(snapshot.status.state + ": " + snapshot.status.reason, status_type)

        if active_page == "Overview":
            render_overview(
                active_engine,
                snapshot,
                active_settings,
                workspace_controls=overview_map_controls,
            )
        elif active_page == "Fleet":
            render_vessels(active_engine, snapshot, active_settings)
        elif active_page == "Vessel Intelligence":
            render_vessel_intelligence(active_engine, snapshot, active_settings)
        elif active_page == "Trajectory Analysis":
            render_trajectory_analysis(active_engine, snapshot, active_settings)
        elif active_page == "Behavior":
            render_behavior(active_engine, snapshot, active_settings)
        elif active_page == "Similarity":
            render_similarity(active_engine, snapshot, active_settings)
        elif active_page == "Anomalies":
            render_anomalies(active_engine, snapshot, active_settings)
        elif active_page == "Traffic":
            render_traffic(active_engine, snapshot, active_settings)
        elif active_page == "Data Quality":
            render_data_quality(active_engine, snapshot, active_settings)
        elif active_page == "System":
            render_system(active_engine, snapshot, active_settings)

    if page != "Overview":
        render_live_workspace()



if __name__ == "__main__":
    main()
