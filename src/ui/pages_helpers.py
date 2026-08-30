"""Shared helpers for Streamlit page renderers."""

from __future__ import annotations

from datetime import timezone

import pandas as pd
import plotly.graph_objects as go
import pydeck as pdk
import streamlit as st

from src.config.settings import AppSettings
from src.ingestion.models import (
    AnomalyFinding,
    VesselSnapshot,
)
from src.intelligence.engine import (
    EngineSnapshot,
    MaritimeIntelligenceEngine,
)
from src.trajectory.features import (
    enrich_track,
    track_to_frame,
)
from src.ui.tactical_map import (
    AIS_TARGETS_LAYER_ID,
    TACTICAL_MAP_STYLE, TACTICAL_TOOLTIP_HTML, TACTICAL_TOOLTIP_STYLE,
    anomaly_mmsi_sets, build_density_layer_spec, build_track_segments,
    density_points_from_observations, enrich_tactical_rows, legend_markdown,
    operational_strip,
)
from src.ui.presentation import (
    empty_state,
    frame_for_table,
    metric_strip,
    notice,
    panel_title,
)


# ----------------------------------------------------------------------
# MAP STYLES
# ----------------------------------------------------------------------

MAP_STYLES = {
    "Dark Matter": (
        "https://basemaps.cartocdn.com/"
        "gl/dark-matter-gl-style/style.json"
    ),
    "Positron": (
        "https://basemaps.cartocdn.com/"
        "gl/positron-gl-style/style.json"
    ),
    "Voyager": (
        "https://basemaps.cartocdn.com/"
        "gl/voyager-gl-style/style.json"
    ),
    "Light": (
        "https://basemaps.cartocdn.com/"
        "gl/positron-gl-style/style.json"
    ),
}


def _render_readiness(
    snapshot: EngineSnapshot,
) -> None:
    readiness = snapshot.readiness

    duration = (
        f"{snapshot.last_collection_seconds:.1f} s"
        if snapshot.last_collection_seconds > 0
        else "—"
    )

    panel_title(
        "Session telemetry",
        "real AIS only",
    )

    metric_strip(
        {
            "COLLECTION": duration,
            "REAL MESSAGES": f"{snapshot.status.messages_received:,}",
            "DISTINCT VESSELS": readiness.distinct_vessels,
            "TRACKS WITH HISTORY": (
                f"{readiness.tracks_with_history}/"
                f"{readiness.required_tracks}"
            ),
            "EMBEDDINGS": readiness.embedding_status,
            "ANOMALIES": readiness.anomaly_count,
        }
    )

    st.write("")

    panel_title(
        "Analysis readiness",
        f"{readiness.tracks_with_history} tracks with history",
    )

    metric_strip(
        {
            "TRAJECTORY": readiness.trajectory_status,
            "BEHAVIOR": (
                f"{readiness.multitrack_status} · "
                f"{readiness.tracks_with_history}/"
                f"{readiness.required_tracks} TRACKS"
            ),
            "SIMILARITY": (
                f"{readiness.multitrack_status} · "
                f"{readiness.tracks_with_history}/"
                f"{readiness.required_tracks} TRACKS"
            ),
            "ML ANOMALY": (
                f"{readiness.multitrack_status} · "
                f"{readiness.tracks_with_history}/"
                f"{readiness.required_tracks} TRACKS"
            ),
            "DEEP TEMPORAL": getattr(readiness, "temporal_status", "WAITING"),
        }
    )


def _no_real_data_reason(
    status_reason: str,
) -> str:
    if status_reason:
        return (
            f"{status_reason} "
            "Collect real AIS data for longer or select "
            "a denser monitoring region."
        )

    return (
        "Collect real AIS data for longer or select "
        "a denser monitoring region."
    )


def _track_readiness_reason(
    module: str,
    current: int,
    required: int = 3,
) -> str:
    return (
        f"{module} analysis requires {required} distinct vessels "
        "with sufficient trajectory history. "
        f"Current: {current}/{required}. "
        "Collect real AIS data for longer or select "
        "a denser monitoring region."
    )


def _render_similarity_search(
    engine: MaritimeIntelligenceEngine,
    snapshot: EngineSnapshot,
    track: list,
    current_mmsi: str,
) -> None:
    panel_title(
        "Similarity search",
        "real AIS session",
    )

    if snapshot.embeddings is None:
        empty_state(
            _track_readiness_reason(
                "Similarity",
                snapshot.readiness.tracks_with_history,
            ),
            "INSUFFICIENT REAL AIS DATA",
        )

    else:
        similar = engine.embedding_adapter.similar_tracks(
            track,
            engine.store.tracks(),
            current_mmsi=current_mmsi,
        )

        if not similar:
            empty_state(
                "No comparable real AIS tracks are available in this session.",
                "NO REAL AIS MATCH",
            )

        else:
            st.dataframe(
                frame_for_table(
                    pd.DataFrame(
                        [
                            item.__dict__
                            for item in similar
                        ]
                    )
                ),
                hide_index=True,
                width="stretch",
            )

    notice(
        "Historical comparison is disabled unless a real AIS "
        "historical source is connected. Session observations "
        "are not relabeled as historical."
    )


# ----------------------------------------------------------------------
# MAP DATA HELPERS
# ----------------------------------------------------------------------


def _build_density_rows(
    snapshot: EngineSnapshot,
) -> list[dict]:
    """Return real AIS observations for spatial density rendering."""

    rows: list[dict] = []

    for observation in snapshot.observations:
        if (
            observation.latitude is None
            or observation.longitude is None
        ):
            continue

        rows.append(
            {
                "latitude": float(observation.latitude),
                "longitude": float(observation.longitude),
            }
        )

    return rows


def _build_hexbin_rows(
    snapshot: EngineSnapshot,
) -> list[dict]:
    """Build lightweight spatial bins from real AIS observations.

    Aggregation is performed entirely in-memory from the current
    real AIS session. No synthetic observations are created.
    """

    bins: dict[tuple[int, int], int] = {}

    # Approximately 0.05 degree spatial cells.
    cell_size = 0.05

    for observation in snapshot.observations:
        if (
            observation.latitude is None
            or observation.longitude is None
        ):
            continue

        latitude = float(observation.latitude)
        longitude = float(observation.longitude)

        key = (
            int(latitude / cell_size),
            int(longitude / cell_size),
        )

        bins[key] = bins.get(key, 0) + 1

    rows: list[dict] = []

    for (
        lat_index,
        lon_index,
    ), count in bins.items():
        rows.append(
            {
                "latitude": (
                    lat_index * cell_size
                    + cell_size / 2
                ),
                "longitude": (
                    lon_index * cell_size
                    + cell_size / 2
                ),
                "count": int(count),
            }
        )

    return rows


def _build_speed_rows(
    rows: list[dict],
) -> list[dict]:
    """Prepare current real vessel observations for speed rendering.

    Radius is calculated in Python so pydeck receives only concrete
    numeric values and does not need to evaluate JavaScript expressions.
    """

    result: list[dict] = []

    for row in rows:
        sog = row.get("sog_knots")

        if sog is None:
            continue

        latitude = row.get("latitude")
        longitude = row.get("longitude")

        if latitude is None or longitude is None:
            continue

        speed = max(0.0, float(sog))

        radius = max(
            250.0,
            min(1200.0, 250.0 + speed * 55.0),
        )

        result.append(
            {
                "latitude": float(latitude),
                "longitude": float(longitude),
                "sog_knots": speed,
                "cog_degrees": row.get("cog_degrees"),
                "radius": radius,
            }
        )

    return result


def _build_anomaly_hotspots(
    findings: list[AnomalyFinding],
) -> list[dict]:
    """Aggregate real anomaly findings spatially."""

    hotspots: dict[
        tuple[int, int],
        dict,
    ] = {}

    cell_size = 0.05

    for finding in findings:
        if (
            finding.latitude is None
            or finding.longitude is None
        ):
            continue

        latitude = float(finding.latitude)
        longitude = float(finding.longitude)

        key = (
            int(latitude / cell_size),
            int(longitude / cell_size),
        )

        if key not in hotspots:
            hotspots[key] = {
                "latitude": (
                    key[0] * cell_size
                    + cell_size / 2
                ),
                "longitude": (
                    key[1] * cell_size
                    + cell_size / 2
                ),
                "count": 0,
                "max_score": 0.0,
            }

        hotspots[key]["count"] += 1
        hotspots[key]["max_score"] = max(
            hotspots[key]["max_score"],
            float(finding.score),
        )

    return list(hotspots.values())


# ----------------------------------------------------------------------
# MAP RENDERING
# ----------------------------------------------------------------------


def _render_vessel_map(
    rows: list[dict],
    snapshot: EngineSnapshot,
    settings: AppSettings,
    show_heading: bool,
    show_trails: bool,
    show_anomalies: bool,
    show_density: bool = False,
    show_hexbin: bool = False,
    show_speed_field: bool = False,
    show_anomaly_hotspots: bool = False,
    map_style: str = "Dark Matter",
) -> None:
    """Render the operational AIS map and intelligence layers.

    Operational intelligence derived from live AIS observations.

    Vessel tooltips are restricted to the actual vessel layer.
    Aggregated intelligence layers do not inherit vessel metadata,
    preventing misleading null values from appearing in the UI.
    """

    if not rows:
        empty_state(
            "No real AIS position reports are available for the operational map.",
            "NO REAL AIS POSITION DATA",
        )
        return


    selected_mmsi = st.session_state.get("selected_mmsi")
    anomaly_mmsis, critical_mmsis = anomaly_mmsi_sets(snapshot.findings)
    rows = enrich_tactical_rows(rows, selected_mmsi=selected_mmsi, anomaly_mmsis=anomaly_mmsis, critical_mmsis=critical_mmsis)
    layers: list[pdk.Layer] = []

    if show_density:
        density_source = density_points_from_observations(list(snapshot.observations or []))
        density_spec = build_density_layer_spec(density_source) if density_source else None
        if density_spec is not None:
            try:
                # Optional visual only — never uses deck.gl KDE heatmap (WebGL shader failures).
                layers.append(pdk.Layer(
                    density_spec["type"],
                    data=density_spec["data"],
                    get_position=density_spec["get_position"],
                    get_fill_color=density_spec["get_fill_color"],
                    get_radius=density_spec["get_radius"],
                    radius_min_pixels=density_spec["radius_min_pixels"],
                    radius_max_pixels=density_spec["radius_max_pixels"],
                    pickable=False,
                ))
            except Exception:
                # Density failure must not break map or selection.
                pass

    if show_hexbin and snapshot.observations:
        hex_rows = [{"longitude": float(o.longitude), "latitude": float(o.latitude), "radius": 1200}
                    for o in list(snapshot.observations)[:2000]]
        if hex_rows:
            layers.append(pdk.Layer("ScatterplotLayer", data=hex_rows, get_position=["longitude","latitude"],
                get_fill_color=[233,184,87,55], get_radius="radius", radius_min_pixels=4, radius_max_pixels=28, pickable=False))

    if show_speed_field:
        speed_rows = [r for r in rows if r.get("sog_knots") is not None]
        if speed_rows:
            layers.append(pdk.Layer("ScatterplotLayer", data=speed_rows, get_position=["longitude","latitude"],
                get_fill_color=[121,147,155,40], get_radius=750, radius_min_pixels=3, radius_max_pixels=12, pickable=False))

    if show_anomaly_hotspots and snapshot.findings:
        hot = [{"latitude": float(f.latitude), "longitude": float(f.longitude),
                "radius": 900 + min(2000, float(f.score) * 1500)}
               for f in snapshot.findings if f.latitude is not None and f.longitude is not None]
        if hot:
            layers.append(pdk.Layer("ScatterplotLayer", data=hot, get_position=["longitude","latitude"],
                get_fill_color=[239,107,115,55], get_radius="radius", radius_min_pixels=5, radius_max_pixels=30, pickable=False))

    if show_trails:
        by_mmsi: dict[str, list] = {}
        for observation in list(snapshot.observations or []):
            by_mmsi.setdefault(str(observation.mmsi), []).append(observation)
        track_segments: list[dict] = []
        for mmsi, track in by_mmsi.items():
            if len(track) < 2: continue
            is_selected = bool(selected_mmsi and mmsi == selected_mmsi)
            segs = build_track_segments(track, selected=is_selected)
            if selected_mmsi and not is_selected:
                for seg in segs:
                    color = list(seg["color"]); color[3] = max(22, int(color[3]*0.4)); seg["color"] = color
            track_segments.extend(segs)
        if track_segments:
            layers.append(pdk.Layer("PathLayer", data=track_segments, get_path="path", get_color="color",
                get_width="width", width_min_pixels=1, pickable=False))

    (min_lat, min_lon), (max_lat, max_lon) = settings.bbox
    layers.append(pdk.Layer("PathLayer", data=[{"path": [[min_lon,min_lat],[max_lon,min_lat],[max_lon,max_lat],[min_lon,max_lat],[min_lon,min_lat]]}],
        get_path="path", get_color=[233,184,87,90], get_width=1, width_min_pixels=1, pickable=False))

    if show_heading:
        vector_rows = [r for r in rows if r.get("has_vector")]
        if vector_rows:
            layers.append(pdk.Layer("LineLayer", data=vector_rows, get_source_position=["longitude","latitude"],
                get_target_position=["vector_end_lon","vector_end_lat"], get_color=[233,184,87,200],
                get_width=2, width_min_pixels=1, pickable=False))

    layers.append(pdk.Layer("ScatterplotLayer", data=rows, get_position=["longitude","latitude"],
        get_fill_color="halo_color", get_radius="halo_radius", radius_min_pixels=8, radius_max_pixels=26, pickable=False))
    layers.append(pdk.Layer("PolygonLayer", data=rows, get_polygon="polygon", get_fill_color="fill_color",
        get_line_color=[7,17,22,220], line_width_min_pixels=1, stroked=True, filled=True, pickable=False))
    layers.append(pdk.Layer("ScatterplotLayer", data=rows, id=AIS_TARGETS_LAYER_ID, get_position=["longitude","latitude"],
        get_fill_color=[255,255,255,1], get_radius="core_radius", radius_min_pixels=5, radius_max_pixels=14,
        pickable=True, auto_highlight=True))

    if selected_mmsi:
        selected_rows = [r for r in rows if str(r.get("mmsi")) == str(selected_mmsi)]
        if selected_rows:
            layers.append(pdk.Layer("ScatterplotLayer", data=selected_rows, get_position=["longitude","latitude"],
                get_fill_color=[0,0,0,0], get_radius=780, radius_min_pixels=14, radius_max_pixels=24,
                stroked=True, filled=False, get_line_color=[255,255,255,235], line_width_min_pixels=2, pickable=False))

    if show_anomalies and anomaly_mmsis:
        anomaly_rows = [r for r in rows if str(r.get("mmsi")) in anomaly_mmsis
                        and (not selected_mmsi or str(r.get("mmsi")) != str(selected_mmsi))]
        if anomaly_rows:
            layers.append(pdk.Layer("ScatterplotLayer", data=anomaly_rows, get_position=["longitude","latitude"],
                get_fill_color=[0,0,0,0], get_radius=620, radius_min_pixels=11, radius_max_pixels=20,
                stroked=True, filled=False, get_line_color="ring_color", line_width_min_pixels=2, pickable=False))

    if selected_mmsi:
        focus = [r for r in rows if str(r.get("mmsi")) == str(selected_mmsi)]
        if focus:
            center_lat, center_lon = float(focus[0]["latitude"]), float(focus[0]["longitude"])
            zoom = float(st.session_state.get("tactical_map_zoom", 9.5))
        else:
            center_lat = sum(float(r["latitude"]) for r in rows) / len(rows)
            center_lon = sum(float(r["longitude"]) for r in rows) / len(rows)
            zoom = float(st.session_state.get("tactical_map_zoom", 7.5))
    else:
        center_lat = sum(float(r["latitude"]) for r in rows) / len(rows)
        center_lon = sum(float(r["longitude"]) for r in rows) / len(rows)
        zoom = float(st.session_state.get("tactical_map_zoom", 7.5))

    style = TACTICAL_MAP_STYLE if map_style in (None, "", "Dark Matter", "dark", "tactical") else MAP_STYLES.get(map_style, TACTICAL_MAP_STYLE)
    by_mmsi_obs: dict[str, int] = {}
    for observation in list(snapshot.observations or []):
        by_mmsi_obs[str(observation.mmsi)] = by_mmsi_obs.get(str(observation.mmsi), 0) + 1
    tracks_count = sum(1 for n in by_mmsi_obs.values() if n >= 2)
    live_state = str(getattr(snapshot.status, "state", "DISCONNECTED") or "DISCONNECTED")
    region = "CUSTOM"
    try:
        from src.config.regions import region_name_for_bbox
        region = region_name_for_bbox(settings.bbox) or "CUSTOM"
    except Exception:
        pass

    st.markdown(operational_strip(live_state=live_state, targets=len(rows), tracks=tracks_count,
        anomalies=len(anomaly_mmsis), region=str(region).upper()), unsafe_allow_html=True)
    st.markdown(legend_markdown(), unsafe_allow_html=True)
    deck = pdk.Deck(map_style=style, initial_view_state=pdk.ViewState(
        latitude=center_lat, longitude=center_lon, zoom=zoom, pitch=0, bearing=0),
        layers=layers, tooltip={"html": TACTICAL_TOOLTIP_HTML, "style": TACTICAL_TOOLTIP_STYLE})
    event = st.pydeck_chart(deck, width="stretch", height=580, key="operational_ais_map",
                            selection_mode="single-object", on_select="rerun")
    _apply_map_selection(event)
    st.markdown(
        f"<div style='display:flex;justify-content:space-between;font-family:IBM Plex Mono,monospace;"
        f"font-size:0.64rem;color:#79939b;letter-spacing:.06em;margin-top:.2rem'>"
        f"<span>N ▲</span><span>LAT {center_lat:.4f} · LON {center_lon:.4f}</span>"
        f"<span>TARGETS {len(rows)}</span></div>", unsafe_allow_html=True)



def _render_anomaly_map(
    findings: list[AnomalyFinding],
    settings: AppSettings,
) -> None:
    """Render anomaly findings using a simple WebGL-safe layer."""

    del settings

    if not findings:
        return

    rows = []

    for finding in findings:
        if (
            finding.latitude is None
            or finding.longitude is None
        ):
            continue

        rows.append(
            {
                "latitude": float(
                    finding.latitude
                ),
                "longitude": float(
                    finding.longitude
                ),
                "score": float(
                    finding.score
                ),
                "mmsi": finding.mmsi,
                "category": finding.category,
            }
        )

    if not rows:
        return

    center_lat = (
        sum(
            row["latitude"]
            for row in rows
        )
        / len(rows)
    )

    center_lon = (
        sum(
            row["longitude"]
            for row in rows
        )
        / len(rows)
    )

    deck = pdk.Deck(
        map_style=(
            "https://basemaps.cartocdn.com/"
            "gl/dark-matter-gl-style/style.json"
        ),
        initial_view_state=pdk.ViewState(
            latitude=center_lat,
            longitude=center_lon,
            zoom=7.5,
        ),
        layers=[
            pdk.Layer(
                "ScatterplotLayer",
                data=rows,
                get_position=[
                    "longitude",
                    "latitude",
                ],
                get_fill_color=[
                    239,
                    107,
                    115,
                    220,
                ],
                get_radius=700,
                radius_min_pixels=5,
                radius_max_pixels=14,
                pickable=True,
            )
        ],
        tooltip={
            "html": (
                "<b>{category}</b>"
                "<br/>MMSI {mmsi}"
                "<br/>Score {score}"
            ),
            "style": {
                "backgroundColor": "#0d1c24",
                "color": "#d9e6e9",
            },
        },
    )

    st.pydeck_chart(
        deck,
        width="stretch",
    )


# ----------------------------------------------------------------------
# TRAJECTORY CHARTS
# ----------------------------------------------------------------------


def _render_track_chart(
    track: list,
    title: str,
) -> None:
    frame = track_to_frame(track)

    fig = go.Figure(
        go.Scattergeo(
            lon=frame["longitude"],
            lat=frame["latitude"],
            mode="lines+markers",
            line={
                "color": "#35c2c9",
                "width": 2,
            },
            marker={
                "size": 5,
                "color": "#d9e6e9",
            },
            text=frame[
                "received_at"
            ].dt.strftime(
                "%Y-%m-%d %H:%M:%S UTC"
            ),
            hovertemplate=(
                "%{text}"
                "<br>Latitude %{lat:.5f}"
                "<br>Longitude %{lon:.5f}"
                "<extra></extra>"
            ),
        )
    )

    fig.update_geos(
        showland=True,
        landcolor="#10242d",
        showocean=True,
        oceancolor="#08151b",
        showcountries=True,
        countrycolor="#1b3640",
        coastlinecolor="#31505b",
        projection_type="equirectangular",
    )

    fig.update_layout(
        **_plot_layout(
            title,
            "Longitude",
            "Latitude",
        ),
        height=390,
    )

    st.plotly_chart(
        fig,
        width="stretch",
    )


def _render_speed_chart(
    track: list,
) -> None:
    frame = enrich_track(
        track_to_frame(track)
    )

    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=frame["received_at"],
            y=frame["sog_knots"],
            mode="lines+markers",
            name="SOG",
            line={
                "color": "#51c79b",
            },
            connectgaps=False,
            hovertemplate=(
                "%{x|%Y-%m-%d %H:%M:%S} UTC"
                "<br>SOG %{y:.1f} kn"
                "<extra></extra>"
            ),
        )
    )

    fig.add_trace(
        go.Scatter(
            x=frame["received_at"],
            y=frame["cog_degrees"],
            mode="lines",
            name="COG",
            yaxis="y2",
            line={
                "color": "#e9b857",
                "dash": "dot",
            },
            connectgaps=False,
            hovertemplate=(
                "%{x|%Y-%m-%d %H:%M:%S} UTC"
                "<br>COG %{y:.1f}°"
                "<extra></extra>"
            ),
        )
    )

    layout = _plot_layout(
        "Observed SOG and COG history",
        "UTC timestamp",
        "SOG (knots)",
    )

    layout.update(
        {
            "height": 300,
            "yaxis2": {
                "title": "COG (°)",
                "overlaying": "y",
                "side": "right",
                "range": [
                    0,
                    360,
                ],
                "gridcolor": (
                    "rgba(0,0,0,0)"
                ),
            },
            "legend": {
                "orientation": "h",
                "y": 1.12,
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


# ----------------------------------------------------------------------
# PLOTLY LAYOUT
# ----------------------------------------------------------------------


def _plot_layout(
    title: str,
    x_title: str,
    y_title: str,
) -> dict:
    return {
        "title": {
            "text": title,
            "font": {
                "size": 13,
                "color": "#d9e6e9",
            },
            "x": 0,
        },
        "paper_bgcolor": "#0d1c24",
        "plot_bgcolor": "#0d1c24",
        "font": {
            "family": "Inter, sans-serif",
            "color": "#b2c7cc",
            "size": 11,
        },
        "margin": {
            "l": 48,
            "r": 22,
            "t": 50,
            "b": 42,
        },
        "xaxis": {
            "title": x_title,
            "gridcolor": "#1b3640",
            "zerolinecolor": "#1b3640",
        },
        "yaxis": {
            "title": y_title,
            "gridcolor": "#1b3640",
            "zerolinecolor": "#1b3640",
            "automargin": True,
        },
        "hovermode": "x unified",
        "hoverlabel": {
            "bgcolor": "#10242d",
            "font": {
                "color": "#d9e6e9",
            },
        },
        "legend": {
            "orientation": "h",
            "y": 1.08,
            "x": 0,
        },
    }


# ----------------------------------------------------------------------
# VESSEL SELECTION
# ----------------------------------------------------------------------



def _apply_map_selection(event) -> None:
    try:
        selection = event.selection if event is not None else None
    except Exception:
        return
    if selection is None:
        return
    try:
        objects = selection.get("objects") if hasattr(selection, "get") else getattr(selection, "objects", None)
    except Exception:
        objects = getattr(selection, "objects", None)
    if not objects or not isinstance(objects, dict):
        return
    layer_objects = objects.get(AIS_TARGETS_LAYER_ID) or objects.get("ais_targets")
    if not layer_objects:
        return
    first = layer_objects[0] if isinstance(layer_objects, list) and layer_objects else None
    if not isinstance(first, dict):
        return
    mmsi = first.get("mmsi") or first.get("tooltip_mmsi")
    if mmsi is None:
        return
    mmsi = str(mmsi).strip()
    if mmsi.isdigit() and len(mmsi) == 9:
        st.session_state.selected_mmsi = mmsi


def _select_vessel(
    snapshot: EngineSnapshot,
    label: str,
) -> VesselSnapshot | None:
    if not snapshot.vessels:
        return None

    mmsis = [
        vessel.mmsi
        for vessel in snapshot.vessels
    ]

    current = st.session_state.get(
        "selected_mmsi"
    )

    index = (
        mmsis.index(current)
        if current in mmsis
        else 0
    )

    selected = st.selectbox(
        label,
        mmsis,
        index=index,
        format_func=lambda value: _vessel_label(
            value,
            snapshot.vessels,
        ),
    )

    st.session_state.selected_mmsi = selected

    return next(
        vessel
        for vessel in snapshot.vessels
        if vessel.mmsi == selected
    )


def _selected_vessel(
    vessels: list[VesselSnapshot],
) -> VesselSnapshot | None:
    current = st.session_state.get(
        "selected_mmsi"
    )

    return next(
        (
            vessel
            for vessel in vessels
            if vessel.mmsi == current
        ),
        None,
    )


def _vessel_label(
    mmsi: str,
    vessels: list[VesselSnapshot],
) -> str:
    vessel = next(
        (
            vessel
            for vessel in vessels
            if vessel.mmsi == mmsi
        ),
        None,
    )

    display_name = (
        (
            vessel.vessel_name
            or ""
        ).strip()
        or "UNKNOWN"
    ) if vessel is not None else "UNKNOWN"

    return f"{mmsi} · {display_name}"


def _vessel_compact(
    vessel: VesselSnapshot,
) -> None:
    st.markdown(
        f"<div class='data-label'>MMSI</div>"
        f"<div class='data-value'>{vessel.mmsi}</div>",
        unsafe_allow_html=True,
    )

    st.markdown(
        f"<div style='margin:.45rem 0 .8rem;"
        f"color:#d9e6e9;font-weight:600'>"
        f"{vessel.vessel_name or 'UNKNOWN VESSEL'}"
        f"</div>",
        unsafe_allow_html=True,
    )

    rows = [
        (
            "Position",
            (
                f"{vessel.latitude:.5f}, "
                f"{vessel.longitude:.5f}"
            ),
        ),
        (
            "SOG",
            (
                f"{vessel.sog_knots:.1f} kn"
                if vessel.sog_knots is not None
                else "—"
            ),
        ),
        (
            "COG",
            (
                f"{vessel.cog_degrees:.1f}°"
                if vessel.cog_degrees is not None
                else "—"
            ),
        ),
        (
            "Heading",
            (
                f"{vessel.heading_degrees:.0f}°"
                if vessel.heading_degrees is not None
                else "—"
            ),
        ),
        (
            "Last update",
            _utc(
                vessel.last_received
            ),
        ),
        (
            "State",
            (
                "STALE"
                if vessel.stale
                else "ACTIVE"
            ),
        ),
    ]

    for label, value in rows:
        st.markdown(
            f"<div style='display:flex;"
            f"justify-content:space-between;"
            f"border-bottom:1px solid #1b3640;"
            f"padding:.28rem 0'>"
            f"<span class='data-label'>{label}</span>"
            f"<span class='data-value'>{value}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )


def _utc(value) -> str:
    if value is None:
        return "—"

    if hasattr(
        value,
        "to_pydatetime",
    ):
        value = value.to_pydatetime()

    if value.tzinfo is None:
        value = value.replace(
            tzinfo=timezone.utc
        )

    return value.astimezone(
        timezone.utc
    ).strftime(
        "%H:%M:%S UTC"
    )


# ----------------------------------------------------------------------
# SNAPSHOT TRACK ACCESS
# ----------------------------------------------------------------------


def engine_tracks(
    snapshot: EngineSnapshot,
):
    """Expose snapshot observations grouped by MMSI.

    The map remains independent from ObservationStore internals.
    """

    by_mmsi: dict[
        str,
        list,
    ] = {}

    for observation in snapshot.observations:
        by_mmsi.setdefault(
            observation.mmsi,
            [],
        ).append(
            observation
        )

    return by_mmsi.items()
