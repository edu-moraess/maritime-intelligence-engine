"""Streamlit presentation for real-AIS temporal track diagnostics."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src.intelligence.engine import MaritimeIntelligenceEngine
from src.ml.temporal import analyze_temporal_tracks
from src.ui.presentation import metric_strip, notice, panel_title


def render_temporal_diagnostics(engine: MaritimeIntelligenceEngine) -> None:
    """Render temporal coverage diagnostics without changing model behavior."""
    panel_title("Temporal Diagnostics", "real AIS track coverage")

    diagnostics = analyze_temporal_tracks(engine.store.tracks())
    eligible_tracks = diagnostics.tracks_by_min_points.get(4, 0)

    if eligible_tracks == 0:
        metric_strip(
            {
                "TRACKS ≥4": "0",
                "MEDIAN POINTS": diagnostics.median_points or "—",
                "MEDIAN DURATION": "—",
                "MAX GAP": _format_seconds(diagnostics.max_gap_seconds),
            }
        )
        notice(
            "No temporal track has at least 4 validated real AIS observations "
            "yet. Diagnostics will populate as vessels receive repeated reports.",
            "gray",
        )
        _render_thresholds(diagnostics)
        return

    metric_strip(
        {
            "TRACKS ≥4": f"{eligible_tracks}/{diagnostics.total_tracks}",
            "MEDIAN POINTS": diagnostics.median_points,
            "MEDIAN DURATION": _format_seconds(diagnostics.median_duration_seconds),
            "MAX GAP": _format_seconds(diagnostics.max_gap_seconds),
        }
    )

    _render_thresholds(diagnostics)

    window_rows = [
        {
            "Window": f"T={length}",
            "Sliding windows": diagnostics.sliding_windows.get(length, 0),
            "Non-overlapping": diagnostics.non_overlapping_windows.get(length, 0),
        }
        for length in sorted(diagnostics.sliding_windows)
    ]
    st.dataframe(pd.DataFrame(window_rows), hide_index=True, width="stretch")

    notice(
        f"Receive-time gaps above the diagnostic threshold: {diagnostics.gaps_over_threshold}. "
        "Window counts are based only on validated real AIS observations.",
        "green",
    )


def _render_thresholds(diagnostics) -> None:
    threshold_rows = [
        {
            "Minimum points": threshold,
            "Eligible tracks": diagnostics.tracks_by_min_points.get(threshold, 0),
        }
        for threshold in sorted(diagnostics.tracks_by_min_points)
    ]
    st.dataframe(pd.DataFrame(threshold_rows), hide_index=True, width="stretch")


def _format_seconds(value: float | None) -> str:
    if value is None:
        return "—"
    if value < 60:
        return f"{value:.1f} s"
    return f"{value / 60:.1f} min"
