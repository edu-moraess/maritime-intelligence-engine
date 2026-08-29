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
