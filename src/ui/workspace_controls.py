"""Operational workspace controls shared by the overview and secondary pages."""
from __future__ import annotations

from datetime import datetime, timezone

import streamlit as st

from src.config.settings import AppSettings
from src.intelligence.engine import MaritimeIntelligenceEngine
from src.ml.temporal.diagnostics import analyze_temporal_tracks
from src.ui.temporal import OPERATOR_TIMEZONE_OPTIONS

NAVIGATION = {
    "Overview": ("Overview",),
    "Vessels": ("Fleet", "Vessel Intelligence"),
    "Movement & Behavior": ("Trajectory Analysis", "Behavior", "Similarity"),
    "Anomaly & Traffic": ("Anomalies", "Traffic"),
    "Data & System": ("Data Quality", "System"),
}


def _sync_workspace_module() -> None:
    st.session_state["workspace_module"] = st.session_state["workspace_module_body"]


def _sync_workspace_subarea(module: str) -> None:
    st.session_state[f"workspace_subarea_{module}"] = st.session_state[
        f"workspace_subarea_body_{module}"
    ]


def _sync_historical_persistence(
    engine: MaritimeIntelligenceEngine,
    settings: AppSettings,
) -> None:
    enabled = bool(st.session_state["historical_persistence_enabled_body"])
    st.session_state["historical_persistence_enabled"] = enabled
    engine.configure_historical_writer(settings.database_url, enabled)


def _sync_operator_timezone() -> None:
    st.session_state["operator_timezone"] = st.session_state["operator_timezone_body"]


def _render_freshness_status(engine: MaritimeIntelligenceEngine) -> None:
    """Expose live/stale contact counts using the provider receive-time clock."""
    snapshot = engine.snapshot()
    vessels = snapshot.vessels
    stale_count = sum(1 for vessel in vessels if vessel.stale)
    live_count = len(vessels) - stale_count
    status = snapshot.status
    last_received = status.last_received_at
    age_seconds = (
        max(0.0, (datetime.now(timezone.utc) - last_received).total_seconds())
        if last_received is not None
        else None
    )
    age_label = f"{age_seconds:.0f}s" if age_seconds is not None else "—"
    threshold = int(getattr(engine.settings, "stale_after_seconds", 180) or 180)
    st.markdown(
        "<div class='data-label'>SIGNAL FRESHNESS</div>"
        f"<div class='data-value'>LIVE {live_count} · STALE {stale_count}</div>"
        f"<div class='side-muted'>Stale threshold {threshold}s · Last report age {age_label}</div>",
        unsafe_allow_html=True,
    )


def _render_temporal_readiness(engine: MaritimeIntelligenceEngine) -> None:
    """Expose real-track coverage required by temporal intelligence."""
    snapshot = engine.snapshot()
    session_tracks: dict[str, list] = {}
    for observation in snapshot.current_session_observations:
        session_tracks.setdefault(observation.mmsi, []).append(observation)
    diagnostics = analyze_temporal_tracks(session_tracks)
    total = diagnostics.nonempty_tracks
    counts = diagnostics.tracks_by_min_points
    eligible_4 = counts.get(4, 0)
    eligible_8 = counts.get(8, 0)
    eligible_16 = counts.get(16, 0)
    eligible_32 = counts.get(32, 0)
    if total == 0:
        state = "WAITING"
        ratio_label = "N/A"
    elif eligible_8 >= 8:
        state = "READY"
        ratio_label = f"{eligible_8 / total * 100.0:.0f}%"
    elif eligible_4 >= 8:
        state = "EARLY COVERAGE"
        ratio_label = f"{eligible_8 / total * 100.0:.0f}%"
    else:
        state = "NOT READY"
        ratio_label = f"{eligible_8 / total * 100.0:.0f}%"
    st.markdown(
        "<div class='data-label'>TEMPORAL READINESS</div>"
        f"<div class='data-value'>{state} · T8 {ratio_label}</div>"
        f"<div class='side-muted'>Tracks ≥4: {eligible_4} · ≥8: {eligible_8} · ≥16: {eligible_16} · ≥32: {eligible_32}</div>",
        unsafe_allow_html=True,
    )


def _render_reconnect_telemetry(engine: MaritimeIntelligenceEngine) -> None:
    """Expose bounded WebSocket recovery telemetry without exposing secrets."""
    status = engine.snapshot().status
    attempts = status.reconnect_attempts
    last_reconnect = status.last_reconnect_at
    last_disconnect = status.last_disconnect_at
    reconnect_label = (
        last_reconnect.astimezone(timezone.utc).strftime("%H:%M:%S UTC")
        if last_reconnect is not None
        else "—"
    )
    disconnect_label = (
        last_disconnect.astimezone(timezone.utc).strftime("%H:%M:%S UTC")
        if last_disconnect is not None
        else "—"
    )
    if attempts:
        state = f"{attempts} RETRY" if attempts == 1 else f"{attempts} RETRIES"
    else:
        state = "STABLE"
    st.markdown(
        "<div class='data-label'>WEBSOCKET RECOVERY</div>"
        f"<div class='data-value'>{state} · {status.worker_state or status.state}</div>"
        f"<div class='side-muted'>Last disconnect {disconnect_label} · Last reconnect {reconnect_label}</div>"
        f"<div class='side-muted'>Queue {status.queue_depth} · Dropped {status.dropped_messages}</div>",
        unsafe_allow_html=True,
    )
    if status.last_error:
        st.caption(f"Last network error · {status.last_error}")


def _render_historical_persistence(engine: MaritimeIntelligenceEngine, settings: AppSettings) -> None:
    """Expose historical persistence configuration and latest write status in System."""
    global_enabled = bool(engine._historical_persistence_enabled)
    st.session_state["historical_persistence_enabled_body"] = global_enabled
    historical_enabled = st.checkbox(
        "Historical Persistence",
        value=global_enabled,
        key="historical_persistence_enabled_body",
        disabled=settings.database_url is None,
        help="System-wide setting for this process. Persists real AIS observations when a session is finalized.",
        on_change=lambda: _sync_historical_persistence(engine, settings),
    )
    if settings.database_url is None:
        historical_state = "HISTORICAL DATABASE NOT CONFIGURED"
    elif historical_enabled:
        historical_state = "HISTORICAL PERSISTENCE ENABLED"
    else:
        historical_state = "HISTORICAL PERSISTENCE OFF"
    st.markdown(
        f"<div class='data-value side-muted'>{historical_state}</div>",
        unsafe_allow_html=True,
    )
    result = engine.snapshot().historical_result
    if result is not None:
        st.caption(f"Persisted observations · {result.persisted_observations}")
        if result.duplicate_observations:
            st.caption(f"Duplicate observations skipped · {result.duplicate_observations}")
        if result.reason:
            st.caption(f"Persist detail · {result.reason}")


def render_aux_workspace_controls(
    engine: MaritimeIntelligenceEngine,
    settings: AppSettings,
    columns,
) -> None:
    """Render DATA, ANALYSIS and SYSTEM into the workspace rail."""
    with columns[0]:
        with st.expander("DATA", expanded=False):
            quality = engine.snapshot().quality
            st.metric("Messages", quality.messages_processed)
            st.metric("Quality", f"{quality.quality_percent:.1f}%")
            st.caption(f"Valid records · {quality.valid_records}")
    with columns[1]:
        with st.expander("ANALYSIS", expanded=False):
            module = st.radio(
                "Workspace module",
                list(NAVIGATION),
                label_visibility="collapsed",
                key="workspace_module_body",
                on_change=_sync_workspace_module,
            )
            views = NAVIGATION[module]
            if len(views) > 1:
                st.radio(
                    f"{module} subarea",
                    views,
                    label_visibility="collapsed",
                    key=f"workspace_subarea_body_{module}",
                    on_change=lambda: _sync_workspace_subarea(module),
                )
            st.caption(f"Current operational module · {module}")

    with columns[2]:
        conn = "NOT CONFIGURED" if not settings.aisstream_api_key else engine.snapshot().status.state
        with st.expander("SYSTEM", expanded=False):
            st.markdown(
                f"<div class='data-label'>CONNECTION STATE</div><div class='data-value'>{conn}</div>",
                unsafe_allow_html=True,
            )
            _render_freshness_status(engine)
            _render_reconnect_telemetry(engine)
            _render_temporal_readiness(engine)
            st.caption("Historical Persistence")
            st.markdown("<div class='data-label'>HISTORICAL PERSISTENCE</div>", unsafe_allow_html=True)
            _render_historical_persistence(engine, settings)
            st.selectbox(
                "Operator timezone",
                OPERATOR_TIMEZONE_OPTIONS,
                index=0,
                key="operator_timezone_body",
                format_func=lambda value: f"Operator time · {value}",
                label_visibility="collapsed",
                on_change=_sync_operator_timezone,
            )
