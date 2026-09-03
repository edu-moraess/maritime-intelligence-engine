"""Main-workspace controls shared by the overview and secondary pages."""
from __future__ import annotations

import streamlit as st

from src.config.settings import AppSettings
from src.intelligence.engine import MaritimeIntelligenceEngine
from src.ui.temporal import OPERATOR_TIMEZONE_OPTIONS

NAVIGATION = {
    "Overview": ("Overview",),
    "Vessels": ("Fleet", "Vessel Intelligence"),
    "Movement & Behavior": ("Trajectory Analysis", "Behavior", "Similarity"),
    "Anomalies & Traffic": ("Anomalies", "Traffic"),
    "Data & System": ("Data Quality", "System"),
}


def _sync_workspace_module() -> None:
    st.session_state["workspace_module"] = st.session_state["workspace_module_body"]


def _sync_workspace_subarea(module: str) -> None:
    st.session_state[f"workspace_subarea_{module}"] = st.session_state[
        f"workspace_subarea_body_{module}"
    ]


def _sync_historical_persistence() -> None:
    st.session_state["historical_persistence_enabled"] = st.session_state[
        "historical_persistence_enabled_body"
    ]


def _sync_operator_timezone() -> None:
    st.session_state["operator_timezone"] = st.session_state["operator_timezone_body"]


def render_aux_workspace_controls(
    engine: MaritimeIntelligenceEngine,
    settings: AppSettings,
    columns,
) -> None:
    """Render DATA, ANALYSIS, and SYSTEM into supplied main-content columns."""
    with columns[0]:
        with st.popover("DATA", use_container_width=True):
            historical_enabled = st.checkbox(
                "Historical Persistence",
                value=settings.historical_persistence_enabled,
                key="historical_persistence_enabled_body",
                disabled=settings.database_url is None,
                help="Persiste somente observações AIS reais e válidas após a coleta; não altera o live.",
                on_change=_sync_historical_persistence,
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

    with columns[1]:
        with st.popover("ANALYSIS", use_container_width=True):
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
            st.caption(f"Current module · {module}")

    with columns[2]:
        conn = "NOT CONFIGURED" if not settings.aisstream_api_key else engine.snapshot().status.state
        with st.popover("SYSTEM", use_container_width=True):
            st.markdown(
                f"<div class='data-label'>Connection</div><div class='data-value'>{conn}</div>",
                unsafe_allow_html=True,
            )
            st.selectbox(
                "Operator timezone",
                OPERATOR_TIMEZONE_OPTIONS,
                index=0,
                key="operator_timezone_body",
                format_func=lambda value: f"Operator time · {value}",
                label_visibility="collapsed",
                on_change=_sync_operator_timezone,
            )
