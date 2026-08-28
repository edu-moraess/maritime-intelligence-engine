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

    # ------------------------------------------------------------------
    # CURRENT VESSEL COLORS + TOOLTIP-SAFE FIELDS
    # ------------------------------------------------------------------

    for row in rows:
        row["color"] = (
            [53, 194, 201, 210]
            if not row.get("stale", False)
            else [121, 147, 155, 180]
        )

        row["tooltip_name"] = (
            str(row.get("name") or "UNKNOWN VESSEL")
        )

        row["tooltip_mmsi"] = (
            str(row.get("mmsi") or "UNKNOWN")
        )

        sog = row.get("sog_knots")
        row["tooltip_sog"] = (
            f"{float(sog):.1f}"
            if sog is not None
            else "—"
        )

        cog = row.get("cog_degrees")
        row["tooltip_cog"] = (
            f"{float(cog):.1f}"
            if cog is not None
            else "—"
        )

        heading = row.get("heading_degrees")
        row["tooltip_heading"] = (
            f"{float(heading):.0f}"
            if heading is not None
            else "—"
        )

        row["tooltip_status"] = (
            "STALE"
            if row.get("stale", False)
            else "ACTIVE"
        )

        row["tooltip_last_update"] = _utc(
            row.get("last_received")
        )

    layers: list[pdk.Layer] = []

    # ------------------------------------------------------------------
    # TRAFFIC DENSITY
    #
    # Not pickable because these are aggregate observations rather than
    # individual vessel targets. This prevents the vessel tooltip from
    # being displayed over density points.
    # ------------------------------------------------------------------

    if show_density:
        density_rows = _build_density_rows(snapshot)

        if density_rows:
            layers.append(
                pdk.Layer(
                    "ScatterplotLayer",
                    data=density_rows,
                    get_position=[
                        "longitude",
                        "latitude",
                    ],
                    get_fill_color=[
                        233,
                        184,
                        87,
                        90,
                    ],
                    get_radius=900,
                    radius_min_pixels=2,
                    radius_max_pixels=18,
                    pickable=False,
                )
            )

    # ------------------------------------------------------------------
    # TRAFFIC HEXBIN
    # ------------------------------------------------------------------

    if show_hexbin:
        hexbin_rows = _build_hexbin_rows(snapshot)

        if hexbin_rows:
            max_count = max(
                row["count"]
                for row in hexbin_rows
            )

            for row in hexbin_rows:
                count = row["count"]

                row["radius"] = min(
                    4500.0,
                    700.0
                    + (
                        float(count)
                        / max(1, max_count)
                    )
                    * 3800.0,
                )

                row["alpha"] = min(
                    220,
                    70
                    + int(
                        150
                        * (
                            float(count)
                            / max(1, max_count)
                        )
                    ),
                )

            layers.append(
                pdk.Layer(
                    "ScatterplotLayer",
                    data=hexbin_rows,
                    get_position=[
                        "longitude",
                        "latitude",
                    ],
                    get_fill_color=[
                        233,
                        184,
                        87,
                        150,
                    ],
                    get_radius="radius",
                    radius_min_pixels=4,
                    radius_max_pixels=30,
                    pickable=False,
                )
            )

    # ------------------------------------------------------------------
    # CURRENT AIS TARGETS
    # ------------------------------------------------------------------

    layers.append(
        pdk.Layer(
            "ScatterplotLayer",
            data=rows,
            get_position=[
                "longitude",
                "latitude",
            ],
            get_fill_color="color",
            get_radius=340,
            radius_min_pixels=3,
            radius_max_pixels=10,
            pickable=True,
        )
    )

    # ------------------------------------------------------------------
    # BOUNDING BOX
    # ------------------------------------------------------------------

    (
        min_lat,
        min_lon,
    ), (
        max_lat,
        max_lon,
    ) = settings.bbox

    bbox_path = [
        [min_lon, min_lat],
        [max_lon, min_lat],
        [max_lon, max_lat],
        [min_lon, max_lat],
        [min_lon, min_lat],
    ]

    layers.append(
        pdk.Layer(
            "PathLayer",
            data=[
                {
                    "path": bbox_path,
                }
            ],
            get_path="path",
            get_color=[
                233,
                184,
                87,
                180,
            ],
            get_width=2,
            width_min_pixels=1,
            pickable=False,
        )
    )

    # ------------------------------------------------------------------
    # HEADING VECTORS
    # ------------------------------------------------------------------

    heading_rows = [
        row
        for row in rows
        if row.get("end_latitude") is not None
        and row.get("end_longitude") is not None
    ]

    if show_heading and heading_rows:
        layers.append(
            pdk.Layer(
                "LineLayer",
                data=heading_rows,
                get_source_position=[
                    "longitude",
                    "latitude",
                ],
                get_target_position=[
                    "end_longitude",
                    "end_latitude",
                ],
                get_color=[
                    233,
                    184,
                    87,
                    180,
                ],
                get_width=2,
                width_min_pixels=1,
                pickable=False,
            )
        )

    # ------------------------------------------------------------------
    # OBSERVED TRAILS
    # ------------------------------------------------------------------

    if show_trails:
        paths = []

        for mmsi, track in engine_tracks(snapshot):
            if len(track) < 2:
                continue

            ordered = sorted(
                track,
                key=lambda item: item.received_at,
            )

            path = []

            for observation in ordered:
                if (
                    observation.latitude is None
                    or observation.longitude is None
                ):
                    continue

                path.append(
                    [
                        float(observation.longitude),
                        float(observation.latitude),
                    ]
                )

            if len(path) >= 2:
                paths.append(
                    {
                        "path": path,
                        "mmsi": mmsi,
                    }
                )

        if paths:
            layers.append(
                pdk.Layer(
                    "PathLayer",
                    data=paths,
                    get_path="path",
                    get_color=[
                        53,
                        194,
                        201,
                        90,
                    ],
                    width_min_pixels=1,
                    get_width=1,
                    pickable=False,
                )
            )

    # ------------------------------------------------------------------
    # SPEED FIELD
    #
    # This is a derived visualization layer, not a vessel target.
    # It therefore remains non-pickable and cannot trigger the vessel
    # tooltip.
    # ------------------------------------------------------------------

    if show_speed_field:
        speed_rows = _build_speed_rows(rows)

        if speed_rows:
            layers.append(
                pdk.Layer(
                    "ScatterplotLayer",
                    data=speed_rows,
                    get_position=[
                        "longitude",
                        "latitude",
                    ],
                    get_fill_color=[
                        81,
                        199,
                        155,
                        145,
                    ],
                    get_radius="radius",
                    radius_min_pixels=3,
                    radius_max_pixels=14,
                    pickable=False,
                )
            )

    # ------------------------------------------------------------------
    # BEHAVIORAL FINDINGS
    # ------------------------------------------------------------------

    if show_anomalies and snapshot.findings:
        anomaly_rows = []

        for finding in snapshot.findings:
            if (
                finding.latitude is None
                or finding.longitude is None
            ):
                continue

            anomaly_rows.append(
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

        if anomaly_rows:
            layers.append(
                pdk.Layer(
                    "ScatterplotLayer",
                    data=anomaly_rows,
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
                    get_radius=560,
                    radius_min_pixels=4,
                    radius_max_pixels=12,
                    pickable=False,
                )
            )

    # ------------------------------------------------------------------
    # ANOMALY HOTSPOTS
    # ------------------------------------------------------------------

    if (
        show_anomaly_hotspots
        and snapshot.findings
    ):
        hotspot_rows = _build_anomaly_hotspots(
            snapshot.findings
        )

        if hotspot_rows:
            max_count = max(
                row["count"]
                for row in hotspot_rows
            )

            for row in hotspot_rows:
                count = row["count"]

                row["radius"] = min(
                    5000.0,
                    900.0
                    + (
                        float(count)
                        / max(1, max_count)
                    )
                    * 4100.0,
                )

            layers.append(
                pdk.Layer(
                    "ScatterplotLayer",
                    data=hotspot_rows,
                    get_position=[
                        "longitude",
                        "latitude",
                    ],
                    get_fill_color=[
                        239,
                        107,
                        115,
                        175,
                    ],
                    get_radius="radius",
                    radius_min_pixels=5,
                    radius_max_pixels=32,
                    pickable=False,
                )
            )

    # ------------------------------------------------------------------
    # MAP CENTER
    # ------------------------------------------------------------------

    center_lat = (
        sum(
            float(row["latitude"])
            for row in rows
        )
        / len(rows)
    )

    center_lon = (
        sum(
            float(row["longitude"])
            for row in rows
        )
        / len(rows)
    )

    # ------------------------------------------------------------------
    # MAP STYLE
    # ------------------------------------------------------------------

    selected_map_style = MAP_STYLES.get(
        map_style,
        MAP_STYLES["Dark Matter"],
    )

    # ------------------------------------------------------------------
    # DECK
    # ------------------------------------------------------------------

    deck = pdk.Deck(
        map_style=selected_map_style,
        initial_view_state=pdk.ViewState(
            latitude=center_lat,
            longitude=center_lon,
            zoom=7.5,
            pitch=0,
        ),
        layers=layers,
        tooltip={
            "html": (
                "<b>{tooltip_name}</b>"
                "<br/>MMSI {tooltip_mmsi}"
                "<br/>SOG {tooltip_sog} kn"
                "<br/>COG {tooltip_cog}°"
                "<br/>Heading {tooltip_heading}°"
                "<br/>Status {tooltip_status}"
                "<br/>Last update {tooltip_last_update}"
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