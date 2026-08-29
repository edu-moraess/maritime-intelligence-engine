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
