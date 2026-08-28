"""Shared helpers for Streamlit page renderers."""

from __future__ import annotations

from datetime import timezone

import pandas as pd
import plotly.graph_objects as go
import pydeck as pdk
import streamlit as st

from src.analytics.traffic import anomaly_counts, hourly_volume, speed_distribution
from src.config.settings import AppSettings
from src.geospatial.map_data import vessel_rows
from src.ingestion.models import AnomalyFinding, VesselSnapshot
from src.intelligence.engine import EngineSnapshot, MaritimeIntelligenceEngine
from src.trajectory.features import enrich_track, track_to_frame
from src.ui.presentation import empty_state, frame_for_table, metric_strip, notice, panel_title


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
        tooltip={"html": "<b>{name}</b><br/>MMSI {mmsi}<br/>SOG {sog_knots} kn<br/>COG {cog_degrees}°<br/>Last update {last_received}", "style": {"backgroundColor": "#0d1c24", "color": "#d9e6e9"}},
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
    fig = go.Figure(go.Scattergeo(lon=frame["longitude"], lat=frame["latitude"], mode="lines+markers", line={"color": "#35c2c9", "width": 2}, marker={"size": 5, "color": "#d9e6e9"}, text=frame["received_at"].dt.strftime("%Y-%m-%d %H:%M:%S UTC"), hovertemplate="%{text}<br>Latitude %{lat:.5f}<br>Longitude %{lon:.5f}<extra></extra>"))
    fig.update_geos(showland=True, landcolor="#10242d", showocean=True, oceancolor="#08151b", showcountries=True, countrycolor="#1b3640", coastlinecolor="#31505b", projection_type="equirectangular")
    fig.update_layout(**_plot_layout(title, "Longitude", "Latitude"), height=390)
    st.plotly_chart(fig, width="stretch")


def _render_speed_chart(track: list) -> None:
    frame = enrich_track(track_to_frame(track))
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=frame["received_at"], y=frame["sog_knots"], mode="lines+markers", name="SOG", line={"color": "#51c79b"}, connectgaps=False, hovertemplate="%{x|%Y-%m-%d %H:%M:%S} UTC<br>SOG %{y:.1f} kn<extra></extra>"))
    fig.add_trace(go.Scatter(x=frame["received_at"], y=frame["cog_degrees"], mode="lines", name="COG", yaxis="y2", line={"color": "#e9b857", "dash": "dot"}, connectgaps=False, hovertemplate="%{x|%Y-%m-%d %H:%M:%S} UTC<br>COG %{y:.1f}°<extra></extra>"))
    layout = _plot_layout("Observed SOG and COG history", "UTC timestamp", "SOG (knots)")
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


def _vessel_compact(vessel: VesselSnapshot) -> None:
    st.markdown(f"<div class='data-label'>MMSI</div><div class='data-value'>{vessel.mmsi}</div>", unsafe_allow_html=True)
    st.markdown(f"<div style='margin:.45rem 0 .8rem;color:#d9e6e9;font-weight:600'>{vessel.vessel_name or 'UNKNOWN VESSEL'}</div>", unsafe_allow_html=True)
    rows = [
        ("Position", f"{vessel.latitude:.5f}, {vessel.longitude:.5f}"),
        ("SOG", f"{vessel.sog_knots:.1f} kn" if vessel.sog_knots is not None else "—"),
        ("COG", f"{vessel.cog_degrees:.1f}°" if vessel.cog_degrees is not None else "—"),
        ("Heading", f"{vessel.heading_degrees:.0f}°" if vessel.heading_degrees is not None else "—"),
        ("Last update", _utc(vessel.last_received)),
        ("State", "STALE" if vessel.stale else "ACTIVE"),
    ]
    for label, value in rows:
        st.markdown(f"<div style='display:flex;justify-content:space-between;border-bottom:1px solid #1b3640;padding:.28rem 0'><span class='data-label'>{label}</span><span class='data-value'>{value}</span></div>", unsafe_allow_html=True)


def _utc(value) -> str:
    if value is None:
        return "—"
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%H:%M:%S UTC")


def engine_tracks(snapshot: EngineSnapshot):
    # This helper exists so map rendering stays independent of the store internals.
    # The map receives no trail data when the snapshot does not carry observations.
    by_mmsi: dict[str, list] = {}
    for observation in snapshot.observations:
        by_mmsi.setdefault(observation.mmsi, []).append(observation)
    return by_mmsi.items()
