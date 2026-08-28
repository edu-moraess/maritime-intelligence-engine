"""Streamlit page renderers. All pages consume the engine snapshot and never create data."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import pydeck as pdk
import streamlit as st

from src.analytics.traffic import anomaly_counts, hourly_volume, speed_distribution
from src.config.regions import region_timezone_for_bbox
from src.config.settings import AppSettings
from src.geospatial.map_data import vessel_rows
from src.ingestion.models import AnomalyFinding, VesselSnapshot
from src.intelligence.engine import EngineSnapshot, MaritimeIntelligenceEngine
from src.trajectory.features import enrich_track, track_to_frame
from src.ui.presentation import empty_state, frame_for_table, metric_strip, notice, panel_title
from src.ui.temporal import format_ais_second, format_observation_time, format_received, format_region_or_operator


def render_overview(engine: MaritimeIntelligenceEngine, snapshot: EngineSnapshot, settings: AppSettings) -> None:
    summary = snapshot.summary
    metric_strip(
        {
            "ACTIVE VESSELS": summary["active_vessels"],
            "MESSAGES": f"{summary['messages']:,}",
            "ANOMALIES": summary["anomalies"],
            "AVG SPEED": f"{summary['average_speed_knots']:.1f} kn",
            "LAST RECEIVED": format_received(snapshot.status.last_received_at),
        }
    )
    _render_readiness(snapshot)
    st.write("")
    left, center, right = st.columns([1.35, 4.8, 1.45], gap="small")
    with left:
        panel_title("Filters", "operator")
        min_speed = st.slider("Minimum SOG (kn)", 0.0, 40.0, 0.0, 0.5)
        only_fresh = st.checkbox("Fresh reports only", value=False)
        st.markdown("<hr style='border-color:#1b3640'>", unsafe_allow_html=True)
        panel_title("Layers", "map")
        show_heading = st.checkbox("Heading vectors", value=True)
        show_trails = st.checkbox("Observed trails", value=True)
        show_anomalies = st.checkbox("Behavioral findings", value=True)
        st.markdown("<p class='small-note'>All layers originate from current real AIS observations. No synthetic vessel or fallback layer is rendered.</p>", unsafe_allow_html=True)
    with center:
        panel_title("Operational map", f"{len(snapshot.vessels)} targets")
        rows = vessel_rows(snapshot.vessels)
        if min_speed > 0:
            rows = [row for row in rows if row["sog_knots"] >= min_speed]
        if only_fresh:
            rows = [row for row in rows if not row["stale"]]
        if not rows:
            empty_state(_no_real_data_reason(snapshot.status.reason))
        else:
            _render_vessel_map(rows, snapshot, settings, show_heading, show_trails, show_anomalies)
            st.caption("WebGL map · AISStream position reports · click a vessel row in Vessels or Vessel Intelligence to inspect it")
    with right:
        panel_title("Intel panel", "selected")
        selected = _selected_vessel(snapshot.vessels)
        if selected is None:
            empty_state("Select a vessel from the Vessels page to populate this panel.", "NO TARGET SELECTED")
        else:
            _vessel_compact(selected, settings)
            findings = [finding for finding in snapshot.findings if finding.mmsi == selected.mmsi]
            if findings:
                top = findings[0]
                notice(f"Behavioral anomaly detected · {top.category} · score {top.score:.2f}", "red")
            else:
                notice("No behavioral anomaly detected in the available observations.", "green")


def _render_readiness(snapshot: EngineSnapshot) -> None:
    readiness = snapshot.readiness
    duration = f"{snapshot.last_collection_seconds:.1f} s" if snapshot.last_collection_seconds > 0 else "—"
    panel_title("Session telemetry", "real AIS only")
    metric_strip(
        {
            "COLLECTION": duration,
            "REAL MESSAGES": f"{snapshot.status.messages_received:,}",
            "DISTINCT VESSELS": readiness.distinct_vessels,
            "TRACKS WITH HISTORY": f"{readiness.tracks_with_history}/{readiness.required_tracks}",
            "EMBEDDINGS": readiness.embedding_status,
            "ANOMALIES": readiness.anomaly_count,
        }
    )
    st.write("")
    panel_title("Analysis readiness", f"{readiness.tracks_with_history} tracks with history")
    metric_strip(
        {
            "TRAJECTORY": readiness.trajectory_status,
            "BEHAVIOR": f"{readiness.multitrack_status} · {readiness.tracks_with_history}/{readiness.required_tracks} TRACKS",
            "SIMILARITY": f"{readiness.multitrack_status} · {readiness.tracks_with_history}/{readiness.required_tracks} TRACKS",
            "ML ANOMALY": f"{readiness.multitrack_status} · {readiness.tracks_with_history}/{readiness.required_tracks} TRACKS",
        }
    )


def _no_real_data_reason(status_reason: str) -> str:
    if status_reason:
        return f"{status_reason} Collect real AIS data for longer or select a denser monitoring region."
    return "Collect real AIS data for longer or select a denser monitoring region."


def _track_readiness_reason(module: str, current: int, required: int = 3) -> str:
    return f"{module} analysis requires {required} distinct vessels with sufficient trajectory history. Current: {current}/{required}. Collect real AIS data for longer or select a denser monitoring region."


def render_vessels(engine: MaritimeIntelligenceEngine, snapshot: EngineSnapshot, settings: AppSettings) -> None:
    st.subheader("Observed vessels")
    st.caption("Current targets derived from real AIS position reports received by this session.")
    if not snapshot.vessels:
        empty_state(_no_real_data_reason(snapshot.status.reason))
        return
    search = st.text_input("Search MMSI or vessel name", placeholder="e.g. 368207620", label_visibility="collapsed")
    filtered = snapshot.vessels
    if search:
        term = search.lower().strip()
        filtered = [v for v in filtered if term in v.mmsi.lower() or term in (v.vessel_name or "").lower()]
    table = pd.DataFrame(
        [
            {
                "MMSI": vessel.mmsi,
                "Name": vessel.vessel_name or "UNKNOWN",
                "Latitude": f"{vessel.latitude:.5f}",
                "Longitude": f"{vessel.longitude:.5f}",
                "SOG kn": f"{vessel.sog_knots:.1f}" if vessel.sog_knots is not None else "—",
                "COG °": f"{vessel.cog_degrees:.1f}" if vessel.cog_degrees is not None else "—",
                "Reports": vessel.message_count,
                "Last received": format_received(vessel.last_received),
                "State": "STALE" if vessel.stale else "ACTIVE",
            }
            for vessel in filtered
        ]
    )
    st.dataframe(table, hide_index=True, width="stretch")
    options = [v.mmsi for v in filtered]
    if options:
        selected = st.selectbox("Inspect vessel", options, format_func=lambda value: _vessel_label(value, snapshot.vessels))
        st.session_state.selected_mmsi = selected
        selected_vessel = next(v for v in snapshot.vessels if v.mmsi == selected)
        _vessel_compact(selected_vessel, settings)


def render_vessel_intelligence(engine: MaritimeIntelligenceEngine, snapshot: EngineSnapshot, settings: AppSettings) -> None:
    st.subheader("Vessel intelligence")
    selected = _select_vessel(snapshot, "Target vessel")
    if selected is None:
        reason = _no_real_data_reason(snapshot.status.reason) if not snapshot.vessels else "Select an observed vessel to inspect its profile."
        empty_state(reason, "NO TARGET SELECTED")
        return
    left, right = st.columns([1.1, 2.5], gap="medium")
    with left:
        panel_title("Identity and telemetry", "AIS")
        _vessel_compact(selected, settings)
        findings = [finding for finding in snapshot.findings if finding.mmsi == selected.mmsi]
        normality = max(0.0, 1.0 - max((f.score for f in findings), default=0.0))
        metric_strip({"NORMALITY": f"{normality:.2f}", "ANOMALY": f"{max((f.score for f in findings), default=0.0):.2f}", "REPORTS": selected.message_count})
        st.write("")
        panel_title("Event timeline", "observed")
        if findings:
            st.dataframe(frame_for_table(pd.DataFrame([f.__dict__ for f in findings])), hide_index=True, width="stretch")
        else:
            notice("No behavioral anomaly detected in the available real AIS observations.", "green")
    with right:
        panel_title("Observed trajectory", "current session")
        track = engine.store.tracks().get(selected.mmsi, [])
        if len(track) < 2:
            empty_state(f"Trajectory analysis requires at least 2 real AIS position reports for this vessel. Current: {len(track)}/2. Collect real AIS data for longer or select a denser monitoring region.", "INSUFFICIENT REAL AIS DATA")
        else:
            _render_track_chart(track, title="Current real AIS track")
            _render_speed_chart(track)


def render_trajectory_analysis(engine: MaritimeIntelligenceEngine, snapshot: EngineSnapshot, settings: AppSettings) -> None:
    st.subheader("Trajectory analysis")
    selected = _select_vessel(snapshot, "Current AIS track")
    if selected is None:
        reason = _no_real_data_reason(snapshot.status.reason) if not snapshot.vessels else "Select an observed vessel to analyze its trajectory."
        empty_state(reason, "NO TRAJECTORY SELECTED")
        return
    track = engine.store.tracks().get(selected.mmsi, [])
    if len(track) < 2:
        empty_state(f"Trajectory analysis requires at least 2 real AIS position reports for this vessel. Current: {len(track)}/2. Collect real AIS data for longer or select a denser monitoring region.", "INSUFFICIENT REAL AIS DATA")
        return
    left, right = st.columns([1.65, 1], gap="medium")
    with left:
        _render_track_chart(track, title="Current real AIS trajectory")
        _render_speed_chart(track)
    with right:
        _render_similarity_search(engine, snapshot, track, selected.mmsi)


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


def _render_similarity_search(engine: MaritimeIntelligenceEngine, snapshot: EngineSnapshot, track: list, current_mmsi: str) -> None:
    panel_title("Similarity search", "real AIS session")
    if snapshot.embeddings is None:
        empty_state(_track_readiness_reason("Similarity", snapshot.readiness.tracks_with_history), "INSUFFICIENT REAL AIS DATA")
    else:
        similar = engine.embedding_adapter.similar_tracks(track, engine.store.tracks(), current_mmsi=current_mmsi)
        if not similar:
            empty_state("No comparable real AIS tracks are available in this session.", "NO REAL AIS MATCH")
        else:
            st.dataframe(
                frame_for_table(pd.DataFrame([item.__dict__ for item in similar])),
                hide_index=True,
                width="stretch",
            )
    notice("Historical comparison is disabled unless a real AIS historical source is connected. Session observations are not relabeled as historical.")


def render_behavior(engine: MaritimeIntelligenceEngine, snapshot: EngineSnapshot, settings: AppSettings) -> None:
    st.subheader("Behavior analysis")
    result = snapshot.embeddings
    if result is None or len(result.projection) < 3:
        empty_state(_track_readiness_reason("Behavior", snapshot.readiness.tracks_with_history), "INSUFFICIENT REAL AIS DATA")
        return
    selected_mmsi = st.session_state.get("selected_mmsi")
    selected_idx = result.mmsis.index(selected_mmsi) if selected_mmsi in result.mmsis else None
    fig = go.Figure()
    for cluster in sorted(set(result.clusters.tolist())):
        indices = [i for i, value in enumerate(result.clusters) if value == cluster]
        fig.add_trace(
            go.Scatter(
                x=result.projection[indices, 0],
                y=result.projection[indices, 1],
                mode="markers+text",
                text=[result.mmsis[i] for i in indices],
                textposition="top center",
                name=f"Cluster {cluster}",
                marker={"size": 9, "opacity": 0.8},
                hovertemplate="MMSI %{text}<extra></extra>",
            )
        )
    if selected_idx is not None:
        fig.add_trace(go.Scatter(x=[result.projection[selected_idx, 0]], y=[result.projection[selected_idx, 1]], mode="markers", name="CURRENT", marker={"size": 16, "symbol": "diamond", "color": "#ef6b73"}))
    fig.update_layout(**_plot_layout("PCA projection of real AIS trajectory representations", "PC1", "PC2"), height=460, legend={"orientation": "h", "y": 1.08})
    st.plotly_chart(fig, width="stretch")
    metric_strip({"METHOD": "Runtime PCA", "CLUSTERS": len(set(result.clusters.tolist())), "TRACKS": len(result.mmsis), "CHECKPOINT": "NONE"})
    notice(f"Representation provenance: {result.model_checkpoint}. No pretrained trajectory checkpoint is claimed or used.")


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
                "Received": format_received(f.received_at),
                "AIS UTC second": format_ais_second(f.ais_timestamp_second),
                "Observation time": format_observation_time(None),
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
        fig = go.Figure(go.Bar(x=volume["hour"], y=volume["messages"], marker_color="#35c2c9", hovertemplate="UTC receive hour %{x}: %{y} real messages<extra></extra>"))
        fig.update_layout(**_plot_layout("AIS messages received by UTC hour", "UTC receive hour", "Real AIS messages"), height=330)
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
    metric_strip({"QUALITY": f"{report.quality_percent:.1f}%", "MESSAGES": f"{report.messages_processed:,}", "INVALID": f"{report.invalid_records:,}", "DUPLICATES": f"{report.duplicate_records:,}", "LAST RECEIVED": format_received(snapshot.status.last_received_at), "OBSERVATION TIME": "UNAVAILABLE"})
    st.write("")
    left, right = st.columns([1.2, 1], gap="medium")
    with left:
        rows = pd.DataFrame(
            {
                "Check": ["Invalid coordinates / records", "Duplicate messages", "Missing values", "Receive-time gaps", "Invalid MMSI", "Impossible speeds", "Impossible geographic jumps", "Stale reports"],
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
    metric_strip({"PROVIDER": "AISStream.io", "STATE": status.state, "WEBSOCKET": status.websocket_status, "MESSAGES RECEIVED": f"{status.messages_received:,}", "LAST RECEIVED": format_received(status.last_received_at), "AIS UTC SECOND": format_ais_second(status.ais_timestamp_second), "LATENCY": "UNAVAILABLE", "HISTORICAL": snapshot.historical_status})
    st.write("")
    left, right = st.columns(2, gap="medium")
    with left:
        panel_title("Connection", "server-side")
        st.write(f"**Status:** `{status.state}`")
        st.write(f"**Reason:** {status.reason}")
        st.write(f"**Messages received:** `{status.messages_received:,}`")
        st.write(f"**Active vessels:** `{status.active_vessels:,}`")
        st.write(f"**Last received:** `{format_received(status.last_received_at)}`")
        st.write(f"**AIS UTC second:** `{format_ais_second(status.ais_timestamp_second)}`")
        st.write("**Observation time:** `UNAVAILABLE`")
        st.write("**Latency:** `UNAVAILABLE`")
        st.write(f"**Historical database:** `{snapshot.historical_status}`")
        if snapshot.historical_result is not None:
            result = snapshot.historical_result
            st.write(f"**Historical write:** `{result.persisted_observations}` persisted · `{result.duplicate_observations}` duplicate · `{result.skipped_invalid}` invalid skipped")
        st.write(f"**Monitoring box:** `{settings.bbox[0]} → {settings.bbox[1]}`")
    with right:
        panel_title("Pipeline", "real AIS")
        st.markdown("`AISStream WebSocket`  →  `Validation`  →  `Trajectory features`  →  `Runtime PCA`  →  `IsolationForest / rules`  →  `Streamlit`")
        st.write("")
        st.write("Storage mode: bounded in-memory session store is the live source of truth. Optional PostgreSQL/PostGIS persistence runs only after valid observations are received and never blocks live AIS.")
        st.write("Model checkpoint: none. The current representation is fitted only on real observations received in this session.")
    if status.state == "LIVE AIS":
        notice("The application is receiving real AIS position reports from AISStream.", "green")
    else:
        notice("REAL AIS DATA UNAVAILABLE. The application intentionally renders an empty state instead of fabricated traffic.", "red")


def _render_vessel_map(rows: list[dict], snapshot: EngineSnapshot, settings: AppSettings, show_heading: bool, show_trails: bool, show_anomalies: bool) -> None:
    colors = [[53, 194, 201, 210] if not row["stale"] else [121, 147, 155, 180] for row in rows]
    for row, color in zip(rows, colors):
        row["color"] = color
    layers = [
        pdk.Layer("ScatterplotLayer", data=rows, get_position="[longitude, latitude]", get_fill_color="color", get_radius=340, radius_min_pixels=3, radius_max_pixels=10, pickable=True),
    ]
    (min_lat, min_lon), (max_lat, max_lon) = settings.bbox
    bbox_path = [[min_lon, min_lat], [max_lon, min_lat], [max_lon, max_lat], [min_lon, max_lat], [min_lon, min_lat]]
    layers.append(pdk.Layer("PathLayer", data=[{"path": bbox_path}], get_path="path", get_color=[233, 184, 87, 180], get_width=2, width_min_pixels=1))
    heading_rows = [row for row in rows if row["end_latitude"] is not None and row["end_longitude"] is not None]
    if show_heading and heading_rows:
        layers.append(
            pdk.Layer(
                "LineLayer",
                data=heading_rows,
                get_source_position="[longitude, latitude]",
                get_target_position="[end_longitude, end_latitude]",
                get_color=[233, 184, 87, 180],
                get_width=2,
                width_min_pixels=1,
            )
        )
    if show_trails:
        paths = []
        for mmsi, track in engine_tracks(snapshot):
            if len(track) >= 2:
                paths.append({"path": [[o.longitude, o.latitude] for o in sorted(track, key=lambda item: item.received_at)], "mmsi": mmsi})
        if paths:
            layers.append(pdk.Layer("PathLayer", data=paths, get_path="path", get_color=[53, 194, 201, 90], width_min_pixels=1, get_width=1))
    if show_anomalies and snapshot.findings:
        anomaly_rows = [{"latitude": f.latitude, "longitude": f.longitude, "score": f.score, "mmsi": f.mmsi} for f in snapshot.findings]
        layers.append(pdk.Layer("ScatterplotLayer", data=anomaly_rows, get_position="[longitude, latitude]", get_fill_color=[239, 107, 115, 220], get_radius=560, radius_min_pixels=4, radius_max_pixels=12, pickable=True))
    center_lat = sum(row["latitude"] for row in rows) / len(rows)
    center_lon = sum(row["longitude"] for row in rows) / len(rows)
    deck = pdk.Deck(
        map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
        initial_view_state=pdk.ViewState(latitude=center_lat, longitude=center_lon, zoom=7.5, pitch=0),
        layers=layers,
        tooltip={"html": "<b>{name}</b><br/>MMSI {mmsi}<br/>SOG {sog_knots} kn<br/>COG {cog_degrees}°<br/>Last received {last_received}<br/>AIS UTC second {ais_timestamp_second}<br/>Observation time UNAVAILABLE", "style": {"backgroundColor": "#0d1c24", "color": "#d9e6e9"}},
    )
    st.pydeck_chart(deck, width="stretch")


def _render_anomaly_map(findings: list[AnomalyFinding], settings: AppSettings) -> None:
    if not findings:
        return
    rows = [{"latitude": f.latitude, "longitude": f.longitude, "score": f.score, "mmsi": f.mmsi, "category": f.category} for f in findings]
    center_lat = sum(row["latitude"] for row in rows) / len(rows)
    center_lon = sum(row["longitude"] for row in rows) / len(rows)
    deck = pdk.Deck(
        map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
        initial_view_state=pdk.ViewState(latitude=center_lat, longitude=center_lon, zoom=7.5),
        layers=[pdk.Layer("ScatterplotLayer", data=rows, get_position="[longitude, latitude]", get_fill_color=[239, 107, 115, 220], get_radius=700, radius_min_pixels=5, radius_max_pixels=14, pickable=True)],
        tooltip={"html": "<b>{category}</b><br/>MMSI {mmsi}<br/>Score {score}", "style": {"backgroundColor": "#0d1c24", "color": "#d9e6e9"}},
    )
    st.pydeck_chart(deck, width="stretch")


def _render_track_chart(track: list, title: str) -> None:
    frame = track_to_frame(track)
    fig = go.Figure(go.Scattergeo(lon=frame["longitude"], lat=frame["latitude"], mode="lines+markers", line={"color": "#35c2c9", "width": 2}, marker={"size": 5, "color": "#d9e6e9"}, text=frame["received_at"].dt.strftime("%Y-%m-%d %H:%M:%S UTC"), hovertemplate="Received %{text}<br>Latitude %{lat:.5f}<br>Longitude %{lon:.5f}<extra></extra>"))
    fig.update_geos(showland=True, landcolor="#10242d", showocean=True, oceancolor="#08151b", showcountries=True, countrycolor="#1b3640", coastlinecolor="#31505b", projection_type="equirectangular")
    fig.update_layout(**_plot_layout(title, "Longitude", "Latitude"), height=390)
    st.plotly_chart(fig, width="stretch")
    st.caption("Trajectory timeline: message receive time. Observation time: UNAVAILABLE.")


def _render_speed_chart(track: list) -> None:
    frame = enrich_track(track_to_frame(track))
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=frame["received_at"], y=frame["sog_knots"], mode="lines+markers", name="SOG", line={"color": "#51c79b"}, connectgaps=False, hovertemplate="Received %{x|%Y-%m-%d %H:%M:%S} UTC<br>SOG %{y:.1f} kn<extra></extra>"))
    fig.add_trace(go.Scatter(x=frame["received_at"], y=frame["cog_degrees"], mode="lines", name="COG", yaxis="y2", line={"color": "#e9b857", "dash": "dot"}, connectgaps=False, hovertemplate="Received %{x|%Y-%m-%d %H:%M:%S} UTC<br>COG %{y:.1f}°<extra></extra>"))
    layout = _plot_layout("SOG and COG by message receive time", "Message receive time (UTC)", "SOG (knots)")
    layout.update({"height": 300, "yaxis2": {"title": "COG (°)", "overlaying": "y", "side": "right", "range": [0, 360], "gridcolor": "rgba(0,0,0,0)"}, "legend": {"orientation": "h", "y": 1.12}})
    fig.update_layout(**layout)
    st.plotly_chart(fig, width="stretch")


def _plot_layout(title: str, x_title: str, y_title: str) -> dict:
    return {
        "title": {"text": title, "font": {"size": 13, "color": "#d9e6e9"}, "x": 0},
        "paper_bgcolor": "#0d1c24",
        "plot_bgcolor": "#0d1c24",
        "font": {"family": "Inter, sans-serif", "color": "#b2c7cc", "size": 11},
        "margin": {"l": 48, "r": 22, "t": 50, "b": 42},
        "xaxis": {"title": x_title, "gridcolor": "#1b3640", "zerolinecolor": "#1b3640"},
        "yaxis": {"title": y_title, "gridcolor": "#1b3640", "zerolinecolor": "#1b3640", "automargin": True},
        "hovermode": "x unified",
        "hoverlabel": {"bgcolor": "#10242d", "font": {"color": "#d9e6e9"}},
        "legend": {"orientation": "h", "y": 1.08, "x": 0},
    }


def _select_vessel(snapshot: EngineSnapshot, label: str) -> VesselSnapshot | None:
    if not snapshot.vessels:
        return None
    mmsis = [v.mmsi for v in snapshot.vessels]
    current = st.session_state.get("selected_mmsi")
    index = mmsis.index(current) if current in mmsis else 0
    selected = st.selectbox(label, mmsis, index=index, format_func=lambda value: _vessel_label(value, snapshot.vessels))
    st.session_state.selected_mmsi = selected
    return next(v for v in snapshot.vessels if v.mmsi == selected)


def _selected_vessel(vessels: list[VesselSnapshot]) -> VesselSnapshot | None:
    current = st.session_state.get("selected_mmsi")
    return next((v for v in vessels if v.mmsi == current), None)


def _vessel_label(mmsi: str, vessels: list[VesselSnapshot]) -> str:
    vessel = next((v for v in vessels if v.mmsi == mmsi), None)
    display_name = ((vessel.vessel_name or "").strip() or "UNKNOWN") if vessel is not None else "UNKNOWN"
    return f"{mmsi} · {display_name}"


def _vessel_compact(vessel: VesselSnapshot, settings: AppSettings) -> None:
    region_timezone = region_timezone_for_bbox(settings.bbox)
    operator_timezone = st.session_state.get("operator_timezone", "UTC")
    st.markdown(f"<div class='data-label'>MMSI</div><div class='data-value'>{vessel.mmsi}</div>", unsafe_allow_html=True)
    st.markdown(f"<div style='margin:.45rem 0 .8rem;color:#d9e6e9;font-weight:600'>{vessel.vessel_name or 'UNKNOWN VESSEL'}</div>", unsafe_allow_html=True)
    rows = [
        ("Position", f"{vessel.latitude:.5f}, {vessel.longitude:.5f}"),
        ("SOG", f"{vessel.sog_knots:.1f} kn" if vessel.sog_knots is not None else "—"),
        ("COG", f"{vessel.cog_degrees:.1f}°" if vessel.cog_degrees is not None else "—"),
        ("Heading", f"{vessel.heading_degrees:.0f}°" if vessel.heading_degrees is not None else "—"),
        ("Last received", format_received(vessel.last_received)),
        ("AIS UTC second", format_ais_second(vessel.ais_timestamp_second)),
        ("Observation time", format_observation_time(vessel.observed_at)),
        ("Region local", format_region_or_operator(vessel.last_received, region_timezone)),
        ("Operator local", format_region_or_operator(vessel.last_received, operator_timezone)),
        ("State", "STALE" if vessel.stale else "ACTIVE"),
    ]
    for label, value in rows:
        st.markdown(f"<div style='display:flex;justify-content:space-between;border-bottom:1px solid #1b3640;padding:.28rem 0'><span class='data-label'>{label}</span><span class='data-value'>{value}</span></div>", unsafe_allow_html=True)


def engine_tracks(snapshot: EngineSnapshot):
    # This helper exists so map rendering stays independent of the store internals.
    # The map receives no trail data when the snapshot does not carry observations.
    by_mmsi: dict[str, list] = {}
    for observation in snapshot.observations:
        by_mmsi.setdefault(observation.mmsi, []).append(observation)
    return by_mmsi.items()
