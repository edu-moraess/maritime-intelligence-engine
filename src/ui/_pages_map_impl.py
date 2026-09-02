"""Map / chart implementation helpers extracted for UI modularization.

Presentation-only split from pages_helpers; no business-logic changes.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import plotly.graph_objects as go
import pydeck as pdk
import streamlit as st

from src.config.settings import AppSettings
from src.ingestion.models import AnomalyFinding, VesselSnapshot
from src.intelligence.engine import EngineSnapshot, MaritimeIntelligenceEngine
from src.trajectory.features import enrich_track, track_to_frame
from src.ui.tactical_map import (
    AIS_TARGETS_LAYER_ID,
    TACTICAL_MAP_STYLE,
    TACTICAL_TOOLTIP_HTML,
    TACTICAL_TOOLTIP_STYLE,
    anomaly_mmsi_sets,
    build_density_layer_spec,
    build_track_segments,
    density_points_from_observations,
    enrich_tactical_rows,
    legend_markdown,
    operational_strip,
)
from src.ui.presentation import empty_state, frame_for_table, metric_strip, notice, panel_title

MAP_STYLES = {
    "Dark Matter": "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
    "Positron": "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
    "Voyager": "https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json",
    "Nautical Chart": "https://tiles.openwaters.io/seamap/style.json",
}


def _no_real_data_reason(status_reason: str) -> str:
    if status_reason:
        return (
            f"{status_reason} Collect real AIS data for longer or select "
            "a denser monitoring region."
        )
    return "Collect real AIS data for longer or select a denser monitoring region."


def _track_readiness_reason(module: str, current: int, required: int = 3) -> str:
    return (
        f"{module} analysis requires {required} distinct vessels "
        "with sufficient trajectory history. "
        f"Current: {current}/{required}. "
        "Collect real AIS data for longer or select a denser monitoring region."
    )


def _render_similarity_search(engine, snapshot, track, current_mmsi):
    panel_title("Similarity search", "real AIS session")
    if snapshot.embeddings is None:
        empty_state(
            _track_readiness_reason("Similarity", snapshot.readiness.tracks_with_history),
            "INSUFFICIENT REAL AIS DATA",
        )
    else:
        similar = engine.embedding_adapter.similar_tracks(
            track, engine.store.tracks(), current_mmsi=current_mmsi
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
        "Historical comparison is disabled unless a real AIS historical source is connected. "
        "Session observations are not relabeled as historical."
    )


def _build_density_rows(snapshot):
    rows = []
    for observation in snapshot.observations:
        if observation.latitude is None or observation.longitude is None:
            continue
        rows.append({"latitude": float(observation.latitude), "longitude": float(observation.longitude)})
    return rows


def _build_hexbin_rows(snapshot):
    bins = {}
    cell_size = 0.05
    for observation in snapshot.observations:
        if observation.latitude is None or observation.longitude is None:
            continue
        latitude = float(observation.latitude)
        longitude = float(observation.longitude)
        key = (int(latitude / cell_size), int(longitude / cell_size))
        bins[key] = bins.get(key, 0) + 1
    rows = []
    for (lat_index, lon_index), count in bins.items():
        rows.append({
            "latitude": lat_index * cell_size + cell_size / 2,
            "longitude": lon_index * cell_size + cell_size / 2,
            "count": int(count),
        })
    return rows


def _build_speed_rows(rows):
    result = []
    for row in rows:
        sog = row.get("sog_knots")
        if sog is None:
            continue
        result.append(row)
