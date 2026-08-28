"""Analytical summaries for observed real AIS traffic."""

from __future__ import annotations

from collections import Counter
from typing import Iterable

import pandas as pd

from src.ingestion.models import AISObservation, AnomalyFinding, VesselSnapshot


def traffic_summary(vessels: list[VesselSnapshot], observations: list[AISObservation], findings: list[AnomalyFinding]) -> dict[str, float | int]:
    speeds = [v.sog_knots for v in vessels if v.sog_knots is not None]
    return {
        "active_vessels": len(vessels),
        "messages": len(observations),
        "average_speed_knots": round(sum(speeds) / len(speeds), 2) if speeds else 0.0,
        "anomalies": len(findings),
        "stale_vessels": sum(v.stale for v in vessels),
        "regions": len({(round(v.latitude, 1), round(v.longitude, 1)) for v in vessels}),
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
    rows = [{"mmsi": v.mmsi, "sog_knots": v.sog_knots} for v in vessels if v.sog_knots is not None]
    return pd.DataFrame(rows, columns=["mmsi", "sog_knots"])


def anomaly_counts(findings: list[AnomalyFinding]) -> pd.DataFrame:
    counts = Counter(f.category for f in findings)
    return pd.DataFrame({"category": list(counts.keys()), "events": list(counts.values())})
