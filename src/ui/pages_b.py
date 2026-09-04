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


def render_similarity(
    engine: MaritimeIntelligenceEngine,
    snapshot: EngineSnapshot,
    settings: AppSettings,
) -> None:
    st.subheader("Similarity search")
    st.caption(
        "Compare the selected trajectory only with sufficiently represented "
        "real AIS tracks from this session."
    )

    selected = _select_vessel(snapshot, "Reference vessel")

    if selected is None:
        reason = (
            _no_real_data_reason(snapshot.status.reason)
            if not snapshot.vessels
            else "Select an observed vessel to run a similarity search."
        )
        empty_state(reason, "NO REFERENCE TRACK")
        return

    track = engine.store.tracks().get(selected.mmsi, [])

    if len(track) < 2:
        empty_state(
            "Similarity search requires at least 2 real AIS position reports "
            f"for the reference vessel. Current: {len(track)}/2. "
            "Collect real AIS data for longer or select a denser monitoring "
            "region.",
            "INSUFFICIENT REAL AIS DATA",
        )
        return

    _render_similarity_search(engine, snapshot, track, selected.mmsi)


def render_anomalies(
    engine: MaritimeIntelligenceEngine,
    snapshot: EngineSnapshot,
    settings: AppSettings,
) -> None:
    st.subheader("Behavioral anomaly explorer")

    findings = snapshot.findings

    metric_strip({
        "FINDINGS": len(findings),
        "VESSELS": len({finding.mmsi for finding in findings}),
        "CRITICAL": sum(str(finding.severity).upper() == "CRITICAL" for finding in findings),
        "ANOMALY": sum(str(finding.severity).upper() == "ANOMALY" for finding in findings),
        "SOURCE": "REAL AIS",
    })

    st.write("")

    if not findings:
        empty_state(
            _no_real_data_reason(snapshot.status.reason)
            if not snapshot.vessels
            else "No behavioral findings are currently present in this real AIS session.",
            "NO ACTIVE FINDINGS",
        )
        return

    left, right = st.columns([1.15, 1], gap="medium")

    with left:
        rows = []
        for finding in findings:
            rows.append({
                "MMSI": finding.mmsi,
                "Category": finding.category,
                "Severity": finding.severity,
                "Score": round(float(finding.score), 3),
                "Reason": finding.reason,
            })
        st.dataframe(frame_for_table(pd.DataFrame(rows)), hide_index=True, width="stretch")

    with right:
        _render_anomaly_map(snapshot, findings)

    counts = anomaly_counts(findings)
    if not counts.empty:
        fig = go.Figure(
            go.Bar(
                x=counts["category"],
                y=counts["events"],
                marker_color="#e9b857",
            )
        )
        fig.update_layout(
            **_plot_layout("Behavioral findings by category", "Category", "Events"),
            height=300,
        )
        st.plotly_chart(fig, width="stretch")


def render_traffic(
    engine: MaritimeIntelligenceEngine,
    snapshot: EngineSnapshot,
    settings: AppSettings,
) -> None:
    st.subheader("Traffic and activity")

    if not snapshot.observations:
        empty_state(
            _no_real_data_reason(snapshot.status.reason),
            "NO REAL AIS OBSERVATIONS",
        )
        return

    left, right = st.columns(2, gap="medium")

    with left:
        volume = hourly_volume(snapshot.observations)
        if volume.empty:
            empty_state("Hourly volume requires timestamped real AIS observations.", "NO TIME SERIES")
        else:
            fig = go.Figure(go.Bar(x=volume["hour"], y=volume["messages"]))
            fig.update_layout(
                **_plot_layout(
                    "Observed AIS message volume by UTC hour",
                    "UTC hour",
                    "Real AIS messages",
                ),
                height=330,
            )
            st.plotly_chart(fig, width="stretch")

    with right:
        speeds = speed_distribution(snapshot.vessels)
        if speeds.empty:
            empty_state(
                "SOG distribution requires real AIS reports with a valid "
                "speed-over-ground field.",
                "NO REAL SOG DATA",
            )
        else:
            fig = go.Figure(
                go.Histogram(
                    x=speeds["sog_knots"],
                    nbinsx=18,
                    marker_color="#51c79b",
                    hovertemplate="SOG %{x:.1f} kn<br>Vessels %{y}<extra></extra>",
                )
            )
            fig.update_layout(
                **_plot_layout(
                    "Observed speed-over-ground distribution",
                    "SOG (knots)",
                    "Vessels",
                ),
                height=330,
            )
            st.plotly_chart(fig, width="stretch")


def render_data_quality(
    engine: MaritimeIntelligenceEngine,
    snapshot: EngineSnapshot,
    settings: AppSettings,
) -> None:
    st.subheader("Data quality")

    report = snapshot.quality

    metric_strip(
        {
            "QUALITY": f"{report.quality_percent:.1f}%",
            "MESSAGES": f"{report.messages_processed:,}",
            "INVALID": f"{report.invalid_records:,}",
            "DUPLICATES": f"{report.duplicate_records:,}",
            "LAST UPDATE": _utc(snapshot.status.last_received_at),
        }
    )

    st.write("")

    left, right = st.columns([1.2, 1], gap="medium")

    with left:
        rows = pd.DataFrame(
            {
                "Check": [
                    "Invalid coordinates / records",
                    "Duplicate messages",
                    "Missing values",
                    "Timestamp gaps",
                    "Invalid MMSI",
                    "Impossible speeds",
                    "Impossible geographic jumps",
                    "Stale reports",
                ],
                "Count": [
                    report.invalid_records,
                    report.duplicate_records,
                    report.missing_values,
                    report.receive_time_gaps,
                    report.invalid_mmsi,
                    report.impossible_speeds,
                    report.impossible_jumps,
                    report.stale_records,
                ],
            }
        )
        st.dataframe(rows, hide_index=True, width="stretch")

    with right:
        if report.messages_processed == 0:
            empty_state(
                "Quality metrics will populate after real AIS messages are received.",
                "NO REAL AIS OBSERVATIONS",
            )
        elif report.quality_percent >= 95:
            notice(
                "Data quality is within the operational review threshold for this session.",
                "green",
            )
        else:
            notice(
                "Data quality requires operator review before using downstream behavioral analysis.",
                "red",
            )

    notice(
        "Quality percentages describe the current in-memory session window only. "
        "No unobserved data is estimated."
    )


def render_system(
    engine: MaritimeIntelligenceEngine,
    snapshot: EngineSnapshot,
    settings: AppSettings,
) -> None:
    st.subheader("System health")

    status = snapshot.status

    metric_strip(
        {
            "PROVIDER": "AISStream.io",
            "STATE": status.state,
            "WEBSOCKET": status.websocket_status,
            "MESSAGES": f"{status.messages_received:,}",
            "LATENCY": (
                f"{status.latency_seconds:.1f} s"
                if status.latency_seconds is not None
                else "—"
            ),
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
        st.write(f"**Last ingestion:** `{_utc(status.last_received_at)}`")
        st.write(
            f"**Monitoring box:** `{settings.bbox[0]} → {settings.bbox[1]}`"
        )

    with right:
        panel_title("Advanced Intelligence", "optional temporal layer")
        temporal = snapshot.temporal
        if temporal is None:
            metric_strip({
                "STATUS": "WAITING",
                "MODEL": "TCN Temporal AE",
                "TRACKS": "—",
                "TRAINING": "—",
                "LOSS": "—",
                "INFERENCE": "no",
            })
            notice(
                "Advanced temporal modeling has not run yet. It is optional and requires "
                "enough real AIS trajectory history.",
                "gray",
            )
        else:
            loss = f"{temporal.best_loss:.6f}" if temporal.best_loss is not None else "—"
            train_s = f"{temporal.training_seconds:.2f} s" if temporal.training_seconds else "—"
            epochs = str(temporal.epochs_completed) if temporal.epochs_completed else "—"
            metric_strip({
                "STATUS": temporal.status,
                "MODEL": temporal.method,
                "TRACKS": f"{temporal.n_tracks_usable}/{temporal.n_tracks_seen}",
                "TRAINING": f"{epochs} ep · {train_s}",
                "LOSS": loss,
                "INFERENCE": "yes" if temporal.inference_available else "no",
            })
            st.write(f"**Reason:** {temporal.reason}")
            if temporal.scores:
                top = sorted(temporal.scores, key=lambda s: s.deep_anomaly_score, reverse=True)[:5]
                lines = [
                    f"`{s.mmsi}`  recon={s.reconstruction_error:.6f}  deep={s.deep_anomaly_score:.3f}"
                    for s in top
                ]
                st.markdown(
                    "**Top deep scores (session-relative ranking):**\n\n"
                    + "\n\n".join(lines)
                )
            if temporal.status == "READY":
                notice(
                    "Advanced temporal modeling trained on real AIS only. "
                    "deep_anomaly_score is session-relative ranking, not probability.",
                    "green",
                )
            elif temporal.status == "NOT_READY":
                notice(temporal.reason, "gray")
            elif temporal.status in {"FAILED", "UNAVAILABLE"}:
                notice(temporal.reason, "red")

    with st.expander("Pipeline and persistence", expanded=False):
        panel_title("Pipeline", "real AIS")

        st.markdown(
            "`AISStream WebSocket`  →  `Validation`  →  "
            "`Trajectory features`  →  `Runtime PCA / IsolationForest`  →  "
            "`Streamlit`"
        )
        st.caption(
            "Advanced temporal modeling is optional and session-gated; it does not "
            "replace the core rule-based / IsolationForest anomaly path."
        )

        st.write(f"**Historical persistence:** `{snapshot.historical_status}`")

        if snapshot.historical_result is not None:
            result = snapshot.historical_result
            st.write(f"**Persisted observations:** `{result.persisted_observations}`")

            if result.duplicate_observations:
                st.write(
                    f"**Duplicate observations skipped:** `{result.duplicate_observations}`"
                )

            if result.reason:
                st.write(f"**Persist detail:** {result.reason}")

        st.write(
            "Model checkpoint: none. The current representation is fitted "
            "only on real observations received in this session."
        )

    if status.state == "LIVE AIS":
        notice(
            "The application is receiving real AIS position reports from AISStream.",
            "green",
        )
    else:
        notice(
            "REAL AIS DATA UNAVAILABLE. The application intentionally renders an "
            "empty state instead of fabricated traffic.",
            "red",
        )
