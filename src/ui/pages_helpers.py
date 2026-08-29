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


def _utc(value) -> str:
    if value is None:
        return "—"

    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()

    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc).strftime("%H:%M:%S UTC")


def _vessel_label(
    mmsi: str,
    vessels: list[VesselSnapshot],
) -> str:
    vessel = next((v for v in vessels if v.mmsi == mmsi), None)
    display_name = ((vessel.vessel_name or "").strip() or "UNKNOWN") if vessel is not None else "UNKNOWN"
    return f"{mmsi} · {display_name}"


def _select_vessel(
    snapshot: EngineSnapshot,
    label: str,
) -> VesselSnapshot | None:
    if not snapshot.vessels:
        return None

    mmsis = [vessel.mmsi for vessel in snapshot.vessels]
    current = st.session_state.get("selected_mmsi")
    index = mmsis.index(current) if current in mmsis else 0

    selected = st.selectbox(
        label,
        mmsis,
        index=index,
        format_func=lambda value: _vessel_label(value, snapshot.vessels),
    )
    st.session_state.selected_mmsi = selected
    return next(vessel for vessel in snapshot.vessels if vessel.mmsi == selected)


def _selected_vessel(
    vessels: list[VesselSnapshot],
) -> VesselSnapshot | None:
    current = st.session_state.get("selected_mmsi")
    return next((vessel for vessel in vessels if vessel.mmsi == current), None)


def _plot_layout(
    title: str,
    x_title: str,
    y_title: str,
) -> dict:
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


def _render_similarity_search(
    engine: MaritimeIntelligenceEngine,
    snapshot: EngineSnapshot,
    track: list,
    current_mmsi: str,
) -> None:
    panel_title("Similarity search", "real AIS session")

    if snapshot.embeddings is None:
        empty_state(
            _track_readiness_reason("Similarity", snapshot.readiness.tracks_with_history),
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
                frame_for_table(pd.DataFrame([item.__dict__ for item in similar])),
                hide_index=True,
                width="stretch",
            )

    notice(
        "Historical comparison is disabled unless a real AIS "
        "historical source is connected. Session observations "
        "are not relabeled as historical."
    )


def _render_anomaly_map(
    findings: list[AnomalyFinding],
    settings: AppSettings,
) -> None:
    del settings
    if not findings:
        return

    rows = []
    for finding in findings:
        if finding.latitude is None or finding.longitude is None:
            continue
        rows.append(
            {
                "latitude": float(finding.latitude),
                "longitude": float(finding.longitude),
                "score": float(finding.score),
                "mmsi": finding.mmsi,
                "category": finding.category,
            }
        )

    if not rows:
        return

    center_lat = sum(row["latitude"] for row in rows) / len(rows)
    center_lon = sum(row["longitude"] for row in rows) / len(rows)

    deck = pdk.Deck(
        map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
        initial_view_state=pdk.ViewState(latitude=center_lat, longitude=center_lon, zoom=7.5),
        layers=[
            pdk.Layer(
                "ScatterplotLayer",
                data=rows,
                get_position=["longitude", "latitude"],
                get_fill_color=[239, 107, 115, 220],
                get_radius=700,
                radius_min_pixels=5,
                radius_max_pixels=14,
                pickable=True,
            )
        ],
        tooltip={
            "html": "<b>{category}</b><br/>MMSI {mmsi}<br/>Score {score}",
            "style": {"backgroundColor": "#0d1c24", "color": "#d9e6e9"},
        },
    )
    st.pydeck_chart(deck, width="stretch")


def engine_tracks(snapshot: EngineSnapshot):
    by_mmsi: dict[str, list] = {}
    for observation in snapshot.observations:
        by_mmsi.setdefault(observation.mmsi, []).append(observation)
    return by_mmsi.items()
