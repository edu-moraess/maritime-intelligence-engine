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
    """Compact intelligence status presentation (UI only; states unchanged)."""
    from src.ui.presentation import render_intelligence_status

    readiness = snapshot.readiness
    hist = str(getattr(snapshot, "historical_status", "N/A") or "N/A").upper()
    if hist in {"READY", "ENABLED", "ACTIVE", "ON", "TRUE"}:
        hist_label = "ENABLED"
    elif hist in {"DISABLED", "OFF", "FALSE", "N/A", "NONE", ""}:
        hist_label = hist if hist else "N/A"
    else:
        hist_label = hist

    temporal = str(getattr(readiness, "temporal_status", "WAITING") or "WAITING")
    tracking = readiness.trajectory_status
    behavior = readiness.multitrack_status
    anomaly = readiness.multitrack_status

    render_intelligence_status(
        [
            ("TRACKING", tracking),
            ("BEHAVIOR", behavior),
            ("ANOMALY", anomaly),
            ("HISTORICAL", hist_label),
            ("TEMPORAL", temporal),
        ]
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


# Re-export map and chart helpers from the stable main implementation module.
# Kept in this file for import compatibility with pages_a / pages_b / overview.
from src.ui._pages_map_impl import (  # noqa: E402
    _apply_map_selection,
    _build_anomaly_hotspots,
    _build_density_rows,
    _build_hexbin_rows,
    _build_speed_rows,
    _plot_layout,
    _render_anomaly_map,
    _render_similarity_search,
    _render_speed_chart,
    _render_track_chart,
    _render_vessel_map,
    _select_vessel,
    _selected_vessel,
    _utc,
    _vessel_compact,
    _vessel_label,
    engine_tracks,
)
