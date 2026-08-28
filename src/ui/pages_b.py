"""Streamlit page renderers — anomalies, traffic, quality, system, similarity."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.analytics.traffic import anomaly_counts, hourly_volume, speed_distribution
from src.config.settings import AppSettings
from src.ingestion.models import AnomalyFinding
from src.intelligence.engine import EngineSnapshot, MaritimeIntelligenceEngine
from src.ui.pages_helpers import (
    _no_real_data_reason,
    _plot_layout,
    _render_anomaly_map,
    _render_similarity_search,
    _select_vessel,
    _utc,
)
from src.ui.presentation import empty_state, frame_for_table, metric_strip, notice, panel_title


def render_similarity(engine: MaritimeIntelligenceEngine, snapshot: EngineSnapshot, settings: AppSettings) -> None:
    st.subheader("Similarity search")
    st.caption("Compare the selected trajectory only with sufficiently represented real AIS tracks from this session.")
    selected = _select_vessel(snapshot, "Reference vessel")
    if selected is None:
        reason = _no_real_data_reason(snapshot.status.reason) if not snapshot.vessels else "Select an observed vessel to run a similarity search."
        empty_state(reason, "NO REFERENCE TRACK")
        return
    track = engine.store.tracks().get(selected.mmsi, [])
    if len(track) < 2:
        empty_state(f"Similarity search requires at least 2 real AIS position reports for the reference vessel. Current: {len(track)}/2. Collect real AIS data for longer or select a denser monitoring region.", "INSUFFICIENT REAL AIS DATA")
        return
    _render_similarity_search(engine, snapshot, track, selected.mmsi)


def render_anomalies(engine: MaritimeIntelligenceEngine, snapshot: EngineSnapshot, settings: AppSettings) -> None:
    st.subheader("Behavioral anomaly explorer")
    findings = snapshot.findings
    metric_strip({"FINDINGS": len(findings), "VESSELS": len({f.mmsi for f in findings}), "HIGH SCORE": f"{max((f.score for f in findings), default=0):.2f}"})
    if not findings:
        empty_state("Anomalies are calculated only from currently observed real AIS reports. No finding is fabricated when data is insufficient. Collect real AIS data for longer or select a denser monitoring region if more history is required.", "NO BEHAVIORAL ANOMALIES")
        return
    categories = ["All categories"] + sorted({finding.category for finding in findings})
    selected_category = st.selectbox("Category", categories)
    filtered = findings if selected_category == "All categories" else [finding for finding in findings if finding.category == selected_category]
    left, right = st.columns([1.2, 1.8], gap="medium")
    with left:
        for finding in filtered:
            st.markdown(
                f"<div class='finding-card'><div style='display:flex;justify-content:space-between'><strong>{finding.mmsi}</strong><span>{finding.score:.2f}</span></div><div class='small-note'>{finding.category}</div><div style='margin-top:.45rem'>{finding.detail}</div><div class='small-note' style='margin-top:.35rem'>{_utc(finding.observed_at)}</div></div>",
                unsafe_allow_html=True,
            )
    with right:
        _render_anomaly_map(filtered, settings)
    notice("Anomaly scores are session-local and derived only from currently observed real AIS tracks.")


def render_traffic(engine: MaritimeIntelligenceEngine, snapshot: EngineSnapshot, settings: AppSettings) -> None:
    st.subheader("Traffic intensity")
    if not snapshot.observations:
        empty_state(_no_real_data_reason(snapshot.status.reason), "NO TRAFFIC OBSERVATIONS")
        return
    hourly = hourly_volume(snapshot.observations)
    speeds = speed_distribution(snapshot.vessels)
    categories = anomaly_counts(snapshot.findings)
    metric_strip(
        {
            "OBSERVATIONS": len(snapshot.observations),
            "PEAK HOUR": int(hourly.max()) if not hourly.empty else 0,
            "MEAN SOG": f"{speeds.mean():.1f} kn" if not speeds.empty else "—",
        }
    )
    left, right = st.columns(2, gap="medium")
    with left:
        fig = go.Figure(go.Bar(x=hourly.index.astype(str), y=hourly.values, marker_color="#35c2c9"))
        fig.update_layout(**_plot_layout("Hourly observed volume", "UTC hour", "Messages"), height=320)
        st.plotly_chart(fig, width="stretch")
    with right:
        fig = go.Figure(go.Histogram(x=speeds, nbinsx=20, marker_color="#7dd3a7"))
        fig.update_layout(**_plot_layout("Speed distribution", "SOG (knots)", "Vessels"), height=320)
        st.plotly_chart(fig, width="stretch")
    if categories:
        st.write("")
        panel_title("Finding categories", "session")
        st.dataframe(
            frame_for_table(pd.DataFrame({"category": list(categories.keys()), "count": list(categories.values())})),
            hide_index=True,
            width="stretch",
        )


def render_data_quality(engine: MaritimeIntelligenceEngine, snapshot: EngineSnapshot, settings: AppSettings) -> None:
    st.subheader("Data quality")
    report = snapshot.quality
    metric_strip(
        {
            "QUALITY": f"{report.quality_percent:.1f}%",
            "PROCESSED": report.messages_processed,
            "REJECTED": report.rejected_messages,
            "DUPLICATES": report.duplicate_messages,
        }
    )
    left, right = st.columns([1.4, 1], gap="medium")
    with left:
        rows = pd.DataFrame(
            {
                "metric": ["Invalid coordinates", "Impossible speeds", "Impossible jumps", "Stale records"],
                "count": [report.invalid_coordinates, report.impossible_speeds, report.impossible_jumps, report.stale_records],
            }
        )
        st.dataframe(rows, hide_index=True, width="stretch")
    with right:
        if report.messages_processed == 0:
            empty_state("Quality metrics will populate after real AIS messages are received.", "NO REAL AIS OBSERVATIONS")
        elif report.quality_percent >= 95:
            notice("Data quality is within the operational review threshold for this session.", "green")
        else:
            notice("Data quality requires operator review before using downstream behavioral analysis.", "red")
    notice("Quality percentages describe the current in-memory session window only. No unobserved data is estimated.")


def render_system(engine: MaritimeIntelligenceEngine, snapshot: EngineSnapshot, settings: AppSettings) -> None:
    st.subheader("System and pipeline status")
    status = snapshot.status
    metric_strip(
        {
            "PROVIDER": "AISStream.io",
            "STATE": status.state,
            "WEBSOCKET": status.websocket_status,
            "MESSAGES": f"{status.messages_received:,}",
            "LATENCY": f"{status.latency_seconds:.1f} s" if status.latency_seconds is not None else "—",
        }
    )
    st.write("")
    left, right = st.columns(2, gap="medium")
    with left:
        panel_title("Connection", "server-side")
        st.write(f"**Status:** `{status.state}`")
        st.write(f"**Reason:** {status.reason}")
        st.write(f"**Messages received:** `{status.messages_received:,}`")
        st.write(f"**Active vessels:** `{status.active_vessels:,}`")
        st.write(f"**Last ingestion:** `{_utc(status.last_message_at)}`")
        st.write(f"**Monitoring box:** `{settings.bbox[0]} → {settings.bbox[1]}`")
    with right:
        panel_title("Pipeline", "real AIS")
        st.markdown("`AISStream WebSocket`  →  `Validation`  →  `Trajectory features`  →  `Runtime PCA`  →  `IsolationForest / rules`  →  `Streamlit`")
        st.write("")
        st.write("Storage mode: bounded in-memory session store. PostgreSQL/PostGIS is an explicit future adapter, not required for the deployed disconnected state.")
        st.write("Model checkpoint: none. The current representation is fitted only on real observations received in this session.")
    if status.state == "LIVE AIS":
        notice("The application is receiving real AIS position reports from AISStream.", "green")
    else:
        notice("REAL AIS DATA UNAVAILABLE. The application intentionally renders an empty state instead of fabricated traffic.", "red")
