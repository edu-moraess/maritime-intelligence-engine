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

    if diagnostics.nonempty_tracks == 0:
        metric_strip(
            {
                "TRACKS": "0",
                "MEDIAN POINTS": "—",
                "MEDIAN DURATION": "—",
                "MAX GAP": "—",
            }
        )
        notice(
            "No valid temporal track has enough real AIS observations yet. "
            "Diagnostics will populate as vessels receive repeated reports.",
            "gray",
        )
        return

    def _seconds(value: float | None) -> str:
        if value is None:
            return "—"
        if value < 60:
            return f"{value:.1f} s"
        return f"{value / 60:.1f} min"

    metric_strip(
        {
            "TRACKS": f"{diagnostics.nonempty_tracks}/{diagnostics.total_tracks}",
            "MEDIAN POINTS": diagnostics.median_points,
            "MEDIAN DURATION": _seconds(diagnostics.median_duration_seconds),
            "MAX GAP": _seconds(diagnostics.max_gap_seconds),
        }
    )

    threshold_rows = [
        {
            "Minimum points": threshold,
            "Eligible tracks": diagnostics.tracks_by_min_points.get(threshold, 0),
        }
        for threshold in sorted(diagnostics.tracks_by_min_points)
    ]
    st.dataframe(pd.DataFrame(threshold_rows), hide_index=True, width="stretch")

    window_rows = [
        {
            "Window": f"T={length}",
            "Sliding windows": diagnostics.sliding_windows.get(length, 0),
            "Non-overlapping": diagnostics.non_overlapping_windows.get(length, 0),
        }
        for length in sorted(diagnostics.sliding_windows)
    ]
    st.dataframe(pd.DataFrame(window_rows), hide_index=True, width="stretch")

    gap_count = sum(diagnostics.gaps_over_threshold.values())
    notice(
        f"Receive-time gaps above the diagnostic threshold: {gap_count}. "
        "Window counts are based only on validated real AIS observations.",
        "green",
    )
