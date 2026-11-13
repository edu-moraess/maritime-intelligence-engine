"""Analytical summaries for observed real AIS traffic."""

from __future__ import annotations

from collections import Counter
from math import isfinite
from typing import Iterable

import pandas as pd

from src.ingestion.models import AISObservation, AnomalyFinding, VesselSnapshot


def traffic_summary(
    vessels: list[VesselSnapshot],
    observations: list[AISObservation],
    findings: list[AnomalyFinding],
    *,
    monitoring_regions: int | None = None,
) -> dict[str, float | int | None]:
    """Return canonical session metrics with explicit population definitions."""
    fresh_vessels = [vessel for vessel in vessels if not vessel.stale]
    speeds = [
        float(vessel.sog_knots)
        for vessel in fresh_vessels
        if vessel.sog_knots is not None
        and isfinite(float(vessel.sog_knots))
        and 0.0 <= float(vessel.sog_knots) <= 102.2
    ]
    anomaly_vessels = {finding.mmsi for finding in findings}
    return {
        "active_vessels": len(fresh_vessels),
        "observed_vessels": len(vessels),
        "unique_vessels": len({observation.mmsi for observation in observations}),
        "messages": len(observations),
        "speed_sample_count": len(speeds),
        "average_speed_knots": round(sum(speeds) / len(speeds), 2) if speeds else None,
        "anomalies": len(findings),
        "anomaly_vessels": len(anomaly_vessels),
        "stale_vessels": len(vessels) - len(fresh_vessels),
        "regions": max(0, int(monitoring_regions or 0)),
    }


def observations_frame(observations: Iterable[AISObservation]) -> pd.DataFrame:
    rows = [obs.as_dict() for obs in observations]
    if not rows:
        return pd.DataFrame(columns=["mmsi", "received_at", "latitude", "longitude", "sog_knots", "cog_degrees", "vessel_name"])
    frame = pd.DataFrame(rows)
    frame["received_at"] = pd.to_datetime(frame["received_at"], utc=True)
    frame["receive_hour"] = frame["received_at"].dt.hour
    return frame


def hourly_volume(observations: Iterable[AISObservation]) -> pd.DataFrame:
    frame = observations_frame(observations)
    if frame.empty:
        return pd.DataFrame({"hour": [], "messages": []})
    return frame.groupby("receive_hour", as_index=False).agg(messages=("mmsi", "size")).rename(columns={"receive_hour": "hour"})


def speed_distribution(vessels: list[VesselSnapshot]) -> pd.DataFrame:
    rows = [
        {"mmsi": vessel.mmsi, "sog_knots": vessel.sog_knots}
        for vessel in vessels
        if not vessel.stale
        and vessel.sog_knots is not None
        and isfinite(float(vessel.sog_knots))
        and 0.0 <= float(vessel.sog_knots) <= 102.2
    ]
    return pd.DataFrame(rows, columns=["mmsi", "sog_knots"])


def anomaly_counts(findings: list[AnomalyFinding]) -> pd.DataFrame:
    counts = Counter(f.category for f in findings)
    return pd.DataFrame({"category": list(counts.keys()), "events": list(counts.values())})
