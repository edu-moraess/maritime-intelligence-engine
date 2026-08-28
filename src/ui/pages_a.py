"""Streamlit page renderers — overview, vessels, trajectory, behavior."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.config.settings import AppSettings
from src.geospatial.map_data import vessel_rows
from src.intelligence.engine import EngineSnapshot, MaritimeIntelligenceEngine
from src.ui.pages_helpers import (
    _no_real_data_reason,
    _plot_layout,
    _render_readiness,
    _render_similarity_search,
    _render_speed_chart,
    _render_track_chart,
    _render_vessel_map,
    _select_vessel,
    _selected_vessel,
    _track_readiness_reason,
    _utc,
    _vessel_compact,
    _vessel_label,
)
from src.ui.presentation import empty_state, frame_for_table, metric_strip, notice, panel_title


def render_overview(
    engine: MaritimeIntelligenceEngine,
    snapshot: EngineSnapshot,
    settings: AppSettings,
) -> None:
    summary = snapshot.summary

    metric_strip(
        {
            "ACTIVE VESSELS": summary["active_vessels"],
            "MESSAGES": f"{summary['messages']:,}",
            "ANOMALIES": summary["anomalies"],
            "AVG SPEED": f"{summary['average_speed_knots']:.1f} kn",
            "LAST MESSAGE": _utc(snapshot.status.last_received_at),
        }
    )

    _render_readiness(snapshot)

    st.write("")

    left, center, right = st.columns([1.35, 4.8, 1.45], gap="small")

    with left:
        panel_title("Filters", "operator")

        min_speed = st.slider(
            "Minimum SOG (kn)",
            0.0,
            40.0,
            0.0,
            0.5,
        )

        only_fresh = st.checkbox(
            "Fresh reports only",
            value=False,
        )

        st.markdown(
            "<hr style='border-color:#1b3640'>",
            unsafe_allow_html=True,
        )

        panel_title("Layers", "map")

        show_heading = st.checkbox(
            "Heading vectors",
            value=True,
        )

        show_trails = st.checkbox(
            "Observed trails",
            value=True,
        )

        show_anomalies = st.checkbox(
            "Behavioral findings",
            value=True,
        )

        st.markdown(
            "<p class='small-note'>"
            "All layers originate from current real AIS observations. "
            "No synthetic vessel or fallback layer is rendered."
            "</p>",
            unsafe_allow_html=True,
        )

    with center:
        panel_title(
            "Operational map",
            f"{len(snapshot.vessels)} targets",
        )

        rows = vessel_rows(snapshot.vessels)

        if min_speed > 0:
            rows = [
                row
                for row in rows
                if row["sog_knots"] >= min_speed
            ]

        if only_fresh:
            rows = [
                row
                for row in rows
                if not row["stale"]
            ]

        if not rows:
            empty_state(
                _no_real_data_reason(snapshot.status.reason)
            )
        else:
            _render_vessel_map(
                rows,
                snapshot,
                settings,
                show_heading,
                show_trails,
                show_anomalies,
            )

            st.caption(
                "WebGL map · AISStream position reports · "
                "click a vessel row in Vessels or Vessel Intelligence "
                "to inspect it"
            )

    with right:
        panel_title(
            "Intel panel",
            "selected",
        )

        selected = _selected_vessel(snapshot.vessels)

        if selected is None:
            empty_state(
                "Select a vessel from the Vessels page to populate this panel.",
                "NO TARGET SELECTED",
            )
        else:
            _vessel_compact(selected)

            findings = [
                finding
                for finding in snapshot.findings
                if finding.mmsi == selected.mmsi
            ]

            if findings:
                top = findings[0]

                notice(
                    f"Behavioral anomaly detected · "
                    f"{top.category} · score {top.score:.2f}",
                    "red",
                )
            else:
                notice(
                    "No behavioral anomaly detected in the available observations.",
                    "green",
                )


def render_vessels(
    engine: MaritimeIntelligenceEngine,
    snapshot: EngineSnapshot,
    settings: AppSettings,
) -> None:
    st.subheader("Observed vessels")

    st.caption(
        "Current targets derived from real AIS position reports received by this session."
    )

    if not snapshot.vessels:
        empty_state(
            _no_real_data_reason(snapshot.status.reason)
        )
        return

    search = st.text_input(
        "Search MMSI or vessel name",
        placeholder="e.g. 368207620",
        label_visibility="collapsed",
    )

    filtered = snapshot.vessels

    if search:
        term = search.lower().strip()

        filtered = [
            vessel
            for vessel in filtered
            if term in vessel.mmsi.lower()
            or term in (vessel.vessel_name or "").lower()
        ]

    table = pd.DataFrame(
        [
            {
                "MMSI": vessel.mmsi,
                "Name": vessel.vessel_name or "UNKNOWN",
                "Latitude": f"{vessel.latitude:.5f}",
                "Longitude": f"{vessel.longitude:.5f}",
                "SOG kn": (
                    f"{vessel.sog_knots:.1f}"
                    if vessel.sog_knots is not None
                    else "—"
                ),
                "COG °": (
                    f"{vessel.cog_degrees:.1f}"
                    if vessel.cog_degrees is not None
                    else "—"
                ),
                "Reports": vessel.message_count,
                "Last update": _utc(vessel.last_received),
                "State": "STALE" if vessel.stale else "ACTIVE",
            }
            for vessel in filtered
        ]
    )

    st.dataframe(
        table,
        hide_index=True,
        width="stretch",
    )

    options = [
        vessel.mmsi
        for vessel in filtered
    ]

    if options:
        selected = st.selectbox(
            "Inspect vessel",
            options,
            format_func=lambda value: _vessel_label(
                value,
                snapshot.vessels,
            ),
        )

        st.session_state.selected_mmsi = selected

        selected_vessel = next(
            vessel
            for vessel in snapshot.vessels
            if vessel.mmsi == selected
        )

        _vessel_compact(selected_vessel)


def render_vessel_intelligence(
    engine: MaritimeIntelligenceEngine,
    snapshot: EngineSnapshot,
    settings: AppSettings,
) -> None:
    st.subheader("Vessel intelligence")

    selected = _select_vessel(
        snapshot,
        "Target vessel",
    )

    if selected is None:
        reason = (
            _no_real_data_reason(snapshot.status.reason)
            if not snapshot.vessels
            else "Select an observed vessel to inspect its profile."
        )

        empty_state(
            reason,
            "NO TARGET SELECTED",
        )

        return

    left, right = st.columns(
        [1.1, 2.5],
        gap="medium",
    )

    with left:
        panel_title(
            "Identity and telemetry",
            "AIS",
        )

        _vessel_compact(selected)

        findings = [
            finding
            for finding in snapshot.findings
            if finding.mmsi == selected.mmsi
        ]

        normality = max(
            0.0,
            1.0
            - max(
                (finding.score for finding in findings),
                default=0.0,
            ),
        )

        metric_strip(
            {
                "NORMALITY": f"{normality:.2f}",
                "ANOMALY": f"{max((finding.score for finding in findings), default=0.0):.2f}",
                "REPORTS": selected.message_count,
            }
        )

        st.write("")

        panel_title(
            "Event timeline",
            "observed",
        )

        if findings:
            st.dataframe(
                frame_for_table(
                    pd.DataFrame(
                        [finding.__dict__ for finding in findings]
                    )
                ),
                hide_index=True,
                width="stretch",
            )
        else:
            notice(
                "No behavioral anomaly detected in the available real AIS observations.",
                "green",
            )

    with right:
        panel_title(
            "Observed trajectory",
            "current session",
        )

        track = engine.store.tracks().get(
            selected.mmsi,
            [],
        )

        if len(track) < 2:
            empty_state(
                f"Trajectory analysis requires at least 2 real AIS "
                f"position reports for this vessel. Current: "
                f"{len(track)}/2. Collect real AIS data for longer "
                f"or select a denser monitoring region.",
                "INSUFFICIENT REAL AIS DATA",
            )
        else:
            _render_track_chart(
                track,
                title="Current real AIS track",
            )

            _render_speed_chart(track)


def render_trajectory_analysis(
    engine: MaritimeIntelligenceEngine,
    snapshot: EngineSnapshot,
    settings: AppSettings,
) -> None:
    st.subheader("Trajectory analysis")

    selected = _select_vessel(
        snapshot,
        "Current AIS track",
    )

    if selected is None:
        reason = (
            _no_real_data_reason(snapshot.status.reason)
            if not snapshot.vessels
            else "Select an observed vessel to analyze its trajectory."
        )

        empty_state(
            reason,
            "NO TRAJECTORY SELECTED",
        )

        return

    track = engine.store.tracks().get(
        selected.mmsi,
        [],
    )

    if len(track) < 2:
        empty_state(
            f"Trajectory analysis requires at least 2 real AIS "
            f"position reports for this vessel. Current: "
            f"{len(track)}/2. Collect real AIS data for longer "
            f"or select a denser monitoring region.",
            "INSUFFICIENT REAL AIS DATA",
        )

        return

    left, right = st.columns(
        [1.65, 1],
        gap="medium",
    )

    with left:
        _render_track_chart(
            track,
            title="Current real AIS trajectory",
        )

        _render_speed_chart(track)

    with right:
        _render_similarity_search(
            engine,
            snapshot,
            track,
            selected.mmsi,
        )


def render_behavior(
    engine: MaritimeIntelligenceEngine,
    snapshot: EngineSnapshot,
    settings: AppSettings,
) -> None:
    st.subheader("Behavior analysis")

    result = snapshot.embeddings

    if result is None or len(result.projection) < 3:
        empty_state(
            _track_readiness_reason(
                "Behavior",
                snapshot.readiness.tracks_with_history,
            ),
            "INSUFFICIENT REAL AIS DATA",
        )

        return

    selected_mmsi = st.session_state.get(
        "selected_mmsi"
    )

    selected_idx = (
        result.mmsis.index(selected_mmsi)
        if selected_mmsi in result.mmsis
        else None
    )

    fig = go.Figure()

    for cluster in sorted(
        set(result.clusters.tolist())
    ):
        indices = [
            i
            for i, value in enumerate(result.clusters)
            if value == cluster
        ]

        fig.add_trace(
            go.Scatter(
                x=result.projection[indices, 0],
                y=result.projection[indices, 1],
                mode="markers+text",
                text=[
                    result.mmsis[i]
                    for i in indices
                ],
                textposition="top center",
                name=f"Cluster {cluster}",
                marker={
                    "size": 9,
                    "opacity": 0.8,
                },
                hovertemplate="MMSI %{text}<extra></extra>",
            )
        )

    if selected_idx is not None:
        fig.add_trace(
            go.Scatter(
                x=[
                    result.projection[
                        selected_idx,
                        0,
                    ]
                ],
                y=[
                    result.projection[
                        selected_idx,
                        1,
                    ]
                ],
                mode="markers",
                name="CURRENT",
                marker={
                    "size": 16,
                    "symbol": "diamond",
                    "color": "#ef6b73",
                },
            )
        )

    # FIX:
    # Build the layout dictionary first so that a possible
    # "legend" key returned by _plot_layout() is overwritten
    # intentionally instead of being passed twice as a keyword.
    layout = _plot_layout(
        "PCA projection of real AIS trajectory representations",
        "PC1",
        "PC2",
    )

    layout["height"] = 460
    layout["legend"] = {
        "orientation": "h",
        "y": 1.08,
    }

    fig.update_layout(**layout)

    st.plotly_chart(
        fig,
        width="stretch",
    )

    metric_strip(
        {
            "METHOD": "Runtime PCA",
            "CLUSTERS": len(
                set(result.clusters.tolist())
            ),
            "TRACKS": len(result.mmsis),
            "CHECKPOINT": "NONE",
        }
    )

    notice(
        f"Representation provenance: {result.model_checkpoint}. "
        "No pretrained trajectory checkpoint is claimed or used."
    )