"""Shared helpers for Streamlit page renderers."""

from __future__ import annotations

from src.intelligence.engine import EngineSnapshot
from src.ui.presentation import render_intelligence_status

# Map styles and pure helpers live in the map implementation module.
from src.ui._pages_map_impl import (  # noqa: F401
    MAP_STYLES,
    _build_anomaly_hotspots,
    _build_density_rows,
    _build_hexbin_rows,
    _build_speed_rows,
    _no_real_data_reason,
    _render_similarity_search,
    _track_readiness_reason,
)
from src.ui._pages_map_render import (  # noqa: F401
    _apply_map_selection,
    _plot_layout,
    _render_anomaly_map,
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


def _render_readiness(
    snapshot: EngineSnapshot,
) -> None:
    """Compact intelligence status presentation (UI only; states unchanged)."""
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
