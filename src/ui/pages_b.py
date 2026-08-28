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
    selected_category = st.selectbox("Category", categories, label_visibility="collapsed")
    filtered = findings if selected_category == "All categories" else [f for f in findings if f.category == selected_category]
    table = pd.DataFrame(
        [
            {
                "Timestamp": _utc(f.received_at),
                "MMSI": f.mmsi,
                "Location": f"{f.latitude:.4f}, {f.longitude:.4f}",
                "Score": f"{f.score:.2f}",
                "Category": f.category,
                "Confidence": f"{f.confidence:.2f}",
                "Explanation": f.explanation,
            }
            for f in filtered
        ]
    )
    st.dataframe(table, hide_index=True, width="stretch")
    _render_anomaly_map(filtered, settings)
    notice("Interpretation guardrail: these are behavioral anomalies in observed movement data, not determinations of hostile intent.")


def render_traffic(engine: MaritimeIntelligenceEngine, snapshot: EngineSnapshot, settings: AppSettings) -> None:
    st.subheader("Traffic analytics")
    summary = snapshot.summary
    metric_strip({"ACTIVE VESSELS": summary["active_vessels"], "MESSAGES": f"{summary['messages']:,}", "AVG SPEED": f"{summary['average_speed_knots']:.1f} kn", "REGIONS": summary["regions"], "ANOMALIES": summary["anomalies"]})
    if not snapshot.observations:
        empty_state(_no_real_data_reason(snapshot.status.reason))
        return
    left, right = st.columns(2, gap="medium")
    with left:
        volume = hourly_volume(snapshot.observations)
        fig = go.Figure(go.Bar(x=volume["hour"], y=volume["messages"], marker_color="#35c2c9", hovertemplate="UTC hour %{x}: %{y} real messages<extra></extra>"))
        fig.update_layout(**_plot_layout("Observed AIS message volume by UTC hour", "UTC hour", "Real AIS messages"), height=330)
        st.plotly_chart(fig, width="stretch")
    with right:
        speeds = speed_distribution(snapshot.vessels)
        if speeds.empty:
            empty_state("SOG distribution requires real AIS reports with a valid speed-over-ground field.", "NO REAL SOG DATA")
        else:
            fig = go.Figure(go.Histogram(x=speeds["sog_knots"], nbinsx=18, marker_color="#51c79b", hovertemplate="SOG %{x:.1f} kn<br>Vessels %{y}<extra></extra>"))
            fig.update_layout(**_plot_layout("Observed speed-over-ground distribution", "SOG (knots)", "Vessels"), height=330)
            st.plotly_chart(fig, width="stretch")
    counts = anomaly_counts(snapshot.findings)
    if not counts.empty:
        fig = go.Figure(go.Bar(x=counts["category"], y=counts["events"], marker_color="#e9b857"))
        fig.update_layout(**_plot_layout("Behavioral findings by category", "Category", "Events"), height=300)
        st.plotly_chart(fig, width="stretch")


def render_data_quality(engine: MaritimeIntelligenceEngine, snapshot: EngineSnapshot, settings: AppSettings) -> None:
    st.subheader("Data quality")
    report = snapshot.quality
    metric_strip({"QUALITY": f"{report.quality_percent:.1f}%", "MESSAGES": f"{report.messages_processed:,}", "INVALID": f"{report.invalid_records:,}", "DUPLICATES": f"{report.duplicate_records:,}", "LAST UPDATE": _utc(snapshot.status.last_message_at)})
    st.write("")
    left, right = st.columns([1.2, 1], gap="medium")
    with left:
        rows = pd.DataFrame(
            {
                "Check": ["Invalid coordinates / records", "Duplicate messages", "Missing values", "Timestamp gaps", "Invalid MMSI", "Impossible speeds", "Impossible geographic jumps", "Stale reports"],
                "Count": [report.invalid_records, report.duplicate_records, report.missing_values, report.receive_time_gaps, report.invalid_mmsi, report.impossible_speeds, report.impossible_jumps, report.stale_records],
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
    metric_strip({"PROVIDER": "AISStream.io", "STATE": status.state, "WEBSOCKET": status.websocket_status, "MESSAGES": f"{status.messages_received:,}", "LATENCY": f"{status.latency_seconds:.1f} s" if status.latency_seconds is not None else "—"})
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
