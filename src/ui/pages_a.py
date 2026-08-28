"""Streamlit page renderers — overview, vessels, trajectory, behavior."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.config.settings import AppSettings
from src.geospatial.map_data import vessel_rows
from src.intelligence.engine import (
    EngineSnapshot,
    MaritimeIntelligenceEngine,
)

from src.ui.pages_helpers import (
    MAP_STYLES,
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

from src.ui.presentation import (
    empty_state,
    frame_for_table,
    metric_strip,
    notice,
    panel_title,
)


# ----------------------------------------------------------------------
# OVERVIEW
# ----------------------------------------------------------------------


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
            "LAST MESSAGE": _utc(
                snapshot.status.last_received_at
            ),
        }
    )

    _render_readiness(snapshot)

    st.write("")

    left, center, right = st.columns(
        [1.35, 4.8, 1.45],
        gap="small",
    )

    # ------------------------------------------------------------------
    # LEFT — MAP FILTERS
    # ------------------------------------------------------------------

    with left:
        panel_title(
            "Filters",
            "operator",
        )

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

    # ------------------------------------------------------------------
    # CENTER — OPERATIONAL MAP
    # ------------------------------------------------------------------

    with center:
        panel_title(
            "Operational map",
            f"{len(snapshot.vessels)} targets",
        )

        with st.expander(
            "MAP CONFIGURATION",
            expanded=False,
        ):
            map_style = st.selectbox(
                "Map style",
                options=list(MAP_STYLES.keys()),
                index=list(MAP_STYLES.keys()).index(
                    "Dark Matter"
                ),
                help=(
                    "Select the basemap used by "
                    "the operational map."
                ),
            )

            st.markdown(
                "<hr style='border-color:#1b3640'>",
                unsafe_allow_html=True,
            )

            st.markdown(
                "<div class='data-label' "
                "style='margin-bottom:.35rem'>"
                "VISUALIZATION LAYERS"
                "</div>",
                unsafe_allow_html=True,
            )

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
                "<hr style='border-color:#1b3640'>",
                unsafe_allow_html=True,
            )

            st.markdown(
                "<div class='data-label' "
                "style='margin-bottom:.35rem'>"
                "TRAFFIC INTELLIGENCE"
                "</div>",
                unsafe_allow_html=True,
            )

            show_density = st.checkbox(
                "Traffic density",
                value=False,
            )

            show_hexbin = st.checkbox(
                "Traffic hexbin",
                value=False,
            )

            show_speed_field = st.checkbox(
                "Speed field",
                value=False,
            )

            show_anomaly_hotspots = st.checkbox(
                "Anomaly hotspots",
                value=False,
            )

            st.markdown(
                "<p class='small-note'>"
                "Spatial intelligence layers are computed from the "
                "current AIS observation stream."
                "</p>",
                unsafe_allow_html=True,
            )

        rows = vessel_rows(
            snapshot.vessels
        )

        if min_speed > 0:
            rows = [
                row
                for row in rows
                if row["sog_knots"] is not None
                and row["sog_knots"] >= min_speed
            ]

        if only_fresh:
            rows = [
                row
                for row in rows
                if not row["stale"]
            ]

        if not rows:
            empty_state(
                _no_real_data_reason(
                    snapshot.status.reason
                )
            )
        else:
            _render_vessel_map(
                rows=rows,
                snapshot=snapshot,
                settings=settings,
                show_heading=show_heading,
                show_trails=show_trails,
                show_anomalies=show_anomalies,
                show_density=show_density,
                show_hexbin=show_hexbin,
                show_speed_field=show_speed_field,
                show_anomaly_hotspots=show_anomaly_hotspots,
                map_style=map_style,
            )

            st.caption(
                "Operational intelligence derived from live "
                "AIS observations."
            )

    # ------------------------------------------------------------------
    # RIGHT — INTELLIGENCE PANEL
    # ------------------------------------------------------------------

    with right:
        panel_title(
            "Intel panel",
            "selected",
        )

        selected = _selected_vessel(
            snapshot.vessels
        )

        if selected is None:
            empty_state(
                "Select a vessel from the Vessels page "
                "to populate this panel.",
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
                    "Behavioral anomaly detected · "
                    f"{top.category} · "
                    f"score {top.score:.2f}",
                    "red",
                )
            else:
                notice(
                    "No behavioral anomaly detected in the "
                    "available observations.",
                    "green",
                )


# ----------------------------------------------------------------------
# VESSELS
# ----------------------------------------------------------------------


def render_vessels(
    engine: MaritimeIntelligenceEngine,
    snapshot: EngineSnapshot,
    settings: AppSettings,
) -> None:
    st.subheader(
        "Observed vessels"
    )

    st.caption(
        "Current targets derived from real AIS position "
        "reports received by this session."
    )

    if not snapshot.vessels:
        empty_state(
            _no_real_data_reason(
                snapshot.status.reason
            )
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
            or term in (
                vessel.vessel_name or ""
            ).lower()
        ]

    table = pd.DataFrame(
        [
            {
                "MMSI": vessel.mmsi,
                "Name": (
                    vessel.vessel_name
                    or "UNKNOWN"
                ),
                "Latitude": (
                    f"{vessel.latitude:.5f}"
                ),
                "Longitude": (
                    f"{vessel.longitude:.5f}"
                ),
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
                "Last update": _utc(
                    vessel.last_received
                ),
                "State": (
                    "STALE"
                    if vessel.stale
                    else "ACTIVE"
                ),
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

        _vessel_compact(
            selected_vessel
        )


# ----------------------------------------------------------------------
# VESSEL INTELLIGENCE
# ----------------------------------------------------------------------


def render_vessel_intelligence(
    engine: MaritimeIntelligenceEngine,
    snapshot: EngineSnapshot,
    settings: AppSettings,
) -> None:
    st.subheader(
        "Vessel intelligence"
    )

    selected = _select_vessel(
        snapshot,
        "Target vessel",
    )

    if selected is None:
        reason = (
            _no_real_data_reason(
                snapshot.status.reason
            )
            if not snapshot.vessels
            else (
                "Select an observed vessel "
                "to inspect its profile."
            )
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

        _vessel_compact(
            selected
        )

        findings = [
            finding
            for finding in snapshot.findings
            if finding.mmsi == selected.mmsi
        ]

        max_anomaly = max(
            (
                finding.score
                for finding in findings
            ),
            default=0.0,
        )

        normality = max(
            0.0,
            1.0 - max_anomaly,
        )

        metric_strip(
            {
                "NORMALITY": f"{normality:.2f}",
                "ANOMALY": f"{max_anomaly:.2f}",
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
                        [
                            finding.__dict__
                            for finding in findings
                        ]
                    )
                ),
                hide_index=True,
                width="stretch",
            )
        else:
            notice(
                "No behavioral anomaly detected in the "
                "available real AIS observations.",
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
                "Trajectory analysis requires at least "
                "2 real AIS position reports for this "
                f"vessel. Current: {len(track)}/2. "
                "Collect real AIS data for longer or "
                "select a denser monitoring region.",
                "INSUFFICIENT REAL AIS DATA",
            )
        else:
            _render_track_chart(
                track,
                title="Current real AIS track",
            )

            _render_speed_chart(
                track
            )


# ----------------------------------------------------------------------
# TRAJECTORY ANALYSIS
# ----------------------------------------------------------------------


def render_trajectory_analysis(
    engine: MaritimeIntelligenceEngine,
    snapshot: EngineSnapshot,
    settings: AppSettings,
) -> None:
    st.subheader(
        "Trajectory analysis"
    )

    selected = _select_vessel(
        snapshot,
        "Current AIS track",
    )

    if selected is None:
        reason = (
            _no_real_data_reason(
                snapshot.status.reason
            )
            if not snapshot.vessels
            else (
                "Select an observed vessel "
                "to analyze its trajectory."
            )
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
            "Trajectory analysis requires at least "
            "2 real AIS position reports for this "
            f"vessel. Current: {len(track)}/2. "
            "Collect real AIS data for longer or "
            "select a denser monitoring region.",
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

        _render_speed_chart(
            track
        )

    with right:
        _render_similarity_search(
            engine,
            snapshot,
            track,
            selected.mmsi,
        )


# ----------------------------------------------------------------------
# BEHAVIOR
# ----------------------------------------------------------------------


def render_behavior(
    engine: MaritimeIntelligenceEngine,
    snapshot: EngineSnapshot,
    settings: AppSettings,
) -> None:
    st.subheader(
        "Behavior analysis"
    )

    result = snapshot.embeddings

    if (
        result is None
        or len(result.projection) < 3
    ):
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
        result.mmsis.index(
            selected_mmsi
        )
        if selected_mmsi in result.mmsis
        else None
    )

    behavioral_scores = {
        str(mmsi): float(score)
        for mmsi, score in zip(
            result.mmsis,
            result.anomaly_scores,
        )
        if score is not None
    }

    valid_indices = [
        i
        for i, mmsi in enumerate(
            result.mmsis
        )
        if str(mmsi).isdigit()
        and len(str(mmsi)) == 9
    ]

    if not valid_indices:
        empty_state(
            "No valid 9-digit MMSI identifiers are "
            "available for the behavior visualization.",
            "INVALID AIS IDENTIFIERS",
        )
        return

    ranked_indices = sorted(
        valid_indices,
        key=lambda i: behavioral_scores.get(
            str(result.mmsis[i]),
            0.0,
        ),
        reverse=True,
    )

    label_count = min(
        len(ranked_indices),
        max(
            3,
            len(ranked_indices) // 10,
        ),
    )

    highlighted_indices = set(
        ranked_indices[:label_count]
    )

    if (
        selected_idx is not None
        and selected_idx in valid_indices
    ):
        highlighted_indices.add(
            selected_idx
        )

    fig = go.Figure()

    valid_clusters = sorted(
        {
            int(result.clusters[i])
            for i in valid_indices
        }
    )

    for cluster in valid_clusters:
        cluster_indices = [
            i
            for i in valid_indices
            if int(result.clusters[i]) == cluster
        ]

        labels = [
            str(result.mmsis[i])
            if i in highlighted_indices
            else ""
            for i in cluster_indices
        ]

        customdata = [
            [
                str(result.mmsis[i]),
                int(result.clusters[i]),
                behavioral_scores.get(
                    str(result.mmsis[i]),
                    0.0,
                ),
            ]
            for i in cluster_indices
        ]

        fig.add_trace(
            go.Scatter(
                x=result.projection[
                    cluster_indices,
                    0,
                ],
                y=result.projection[
                    cluster_indices,
                    1,
                ],
                mode="markers+text",
                text=labels,
                textposition="top center",
                textfont={
                    "size": 10,
                },
                name=f"Cluster {cluster}",
                marker={
                    "size": 9,
                    "opacity": 0.82,
                },
                customdata=customdata,
                hovertemplate=(
                    "<b>MMSI</b>: %{customdata[0]}"
                    "<br><b>Cluster</b>: %{customdata[1]}"
                    "<br><b>Isolation Forest score</b>: "
                    "%{customdata[2]:.3f}"
                    "<br><b>PC1</b>: %{x:.3f}"
                    "<br><b>PC2</b>: %{y:.3f}"
                    "<extra></extra>"
                ),
            )
        )

    # ------------------------------------------------------------------
    # CURRENT TARGET
    # ------------------------------------------------------------------

    if (
        selected_idx is not None
        and selected_idx in valid_indices
    ):
        current_mmsi = str(
            result.mmsis[selected_idx]
        )

        current_score = behavioral_scores.get(
            current_mmsi,
            0.0,
        )

        current_cluster = int(
            result.clusters[selected_idx]
        )

        current_pc1 = result.projection[
            selected_idx,
            0,
        ]

        current_pc2 = result.projection[
            selected_idx,
            1,
        ]

        fig.add_trace(
            go.Scatter(
                x=[current_pc1],
                y=[current_pc2],
                mode="markers",
                name="CURRENT",
                marker={
                    "size": 17,
                    "symbol": "diamond",
                    "color": "#ef6b73",
                    "line": {
                        "width": 2,
                    },
                },
                hovertemplate=(
                    f"<b>MMSI</b>: {current_mmsi}"
                    f"<br><b>Cluster</b>: "
                    f"{current_cluster}"
                    f"<br><b>Isolation Forest score</b>: "
                    f"{current_score:.3f}"
                    "<br><b>Status</b>: CURRENT TARGET"
                    "<extra></extra>"
                ),
                showlegend=True,
            )
        )

    layout = _plot_layout(
        "PCA projection of real AIS trajectory representations",
        "PC1",
        "PC2",
    )

    layout.update(
        {
            "height": 500,
            "legend": {
                "orientation": "h",
                "y": 1.04,
                "x": 0,
                "xanchor": "left",
                "yanchor": "bottom",
            },
            "margin": {
                "l": 55,
                "r": 30,
                "t": 85,
                "b": 55,
            },
        }
    )

    fig.update_layout(
        **layout
    )

    st.plotly_chart(
        fig,
        width="stretch",
    )

    metric_values = {
        "METHOD": (
            "Runtime PCA + Isolation Forest"
        ),
        "CLUSTERS": len(valid_clusters),
        "TRACKS": len(result.mmsis),
        "VALID MMSI": len(valid_indices),
        "CHECKPOINT": "NONE",
    }

    current_score = None

    if (
        selected_idx is not None
        and selected_idx in valid_indices
    ):
        current_score = behavioral_scores.get(
            str(result.mmsis[selected_idx])
        )

    if current_score is not None:
        metric_values[
            "CURRENT SCORE"
        ] = f"{current_score:.3f}"

    metric_strip(
        metric_values
    )

    notice(
        f"Representation provenance: "
        f"{result.model_checkpoint}. "
        "Runtime PCA and Isolation Forest are fitted "
        "from real AIS trajectory observations available "
        "in the current session. No pretrained trajectory "
        "checkpoint is claimed or used."
    )

    st.caption(
        "Isolation Forest scores are session-relative "
        "ranking signals, not probabilities or calibrated "
        "confidence values. All valid trajectories remain "
        "available through hover; permanent labels are "
        "limited to the strongest signals and the "
        "currently selected target."
    )