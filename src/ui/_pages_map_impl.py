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
        latitude = row.get("latitude")
        longitude = row.get("longitude")
        if latitude is None or longitude is None:
            continue
        speed = max(0.0, float(sog))
        radius = max(250.0, min(1200.0, 250.0 + speed * 55.0))
        result.append({
            "latitude": float(latitude),
            "longitude": float(longitude),
            "sog_knots": speed,
            "cog_degrees": row.get("cog_degrees"),
            "radius": radius,
        })
    return result


def _build_anomaly_hotspots(findings):
    hotspots = {}
    cell_size = 0.05
    for finding in findings:
        if finding.latitude is None or finding.longitude is None:
            continue
        latitude = float(finding.latitude)
        longitude = float(finding.longitude)
        key = (int(latitude / cell_size), int(longitude / cell_size))
        if key not in hotspots:
            hotspots[key] = {
                "latitude": key[0] * cell_size + cell_size / 2,
                "longitude": key[1] * cell_size + cell_size / 2,
                "count": 0,
                "max_score": 0.0,
            }
        hotspots[key]["count"] += 1
        hotspots[key]["max_score"] = max(hotspots[key]["max_score"], float(finding.score))
    return list(hotspots.values())


def _build_anomaly_type_rows(findings):
    """Prepare real anomaly findings for category-aware tactical rendering."""
    colors = {
        "HEADING": [233, 184, 87, 220],
        "SPEED": [81, 199, 155, 220],
        "POSITION": [121, 147, 155, 220],
        "SPATIAL": [151, 116, 220, 220],
        "TEMPORAL": [73, 160, 220, 220],
        "SIGNAL": [239, 107, 115, 220],
    }
    rows = []
    for finding in findings:
        if finding.latitude is None or finding.longitude is None:
            continue
        category = str(finding.category or "OTHER").upper()
        rows.append({
            "latitude": float(finding.latitude),
            "longitude": float(finding.longitude),
            "mmsi": str(finding.mmsi),
            "category": category,
            "score": float(finding.score),
            "color": colors.get(category, [180, 180, 180, 210]),
            "radius": max(220.0, min(900.0, 250.0 + float(finding.score) * 650.0)),
        })
    return rows


def _build_freshness_rows(rows, reference_time: datetime | None = None):
    """Prepare vessel freshness bands from real observation timestamps only."""
    if not rows:
        return []
    if reference_time is None:
        timestamps = [row.get("last_received") for row in rows if row.get("last_received") is not None]
        reference_time = max(timestamps) if timestamps else None
    if reference_time is None:
        return []
    if reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=timezone.utc)

    result = []
    for row in rows:
        received = row.get("last_received")
        if received is None:
            continue
        if received.tzinfo is None:
            received = received.replace(tzinfo=timezone.utc)
        age_seconds = max(0.0, (reference_time - received).total_seconds())
        if age_seconds <= 30:
            band = "FRESH"
            color = [81, 199, 155, 125]
        elif age_seconds <= 120:
            band = "AGING"
            color = [233, 184, 87, 115]
        else:
            band = "STALE"
            color = [239, 107, 115, 105]
        result.append({
            "latitude": float(row["latitude"]),
            "longitude": float(row["longitude"]),
            "mmsi": str(row["mmsi"]),
            "age_seconds": age_seconds,
            "band": band,
            "color": color,
            "radius": 420.0,
        })
    return result
