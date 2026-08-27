"""Explainable anomaly detection for observed AIS trajectories."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

import numpy as np

from src.ingestion.models import AISObservation, AnomalyFinding
from src.ml.embeddings import EmbeddingResult
from src.trajectory.features import enrich_track, track_to_frame


@dataclass(frozen=True)
class DetectorConfig:
    speed_limit_knots: float = 45.0
    gap_seconds: int = 900
    dwell_minutes: float = 60.0
    deviation_heading_degrees: float = 75.0


def detect_anomalies(
    tracks: dict[str, list[AISObservation]],
    embedding_result: EmbeddingResult | None = None,
    config: DetectorConfig | None = None,
) -> list[AnomalyFinding]:
    config = config or DetectorConfig()
    findings: list[AnomalyFinding] = []
    embedding_by_mmsi = {}
    if embedding_result is not None:
        embedding_by_mmsi = dict(zip(embedding_result.mmsis, embedding_result.anomaly_scores))
    for mmsi, observations in tracks.items():
        frame = enrich_track(track_to_frame(observations))
        if frame.empty:
            continue
        for row in frame.itertuples(index=False):
            checks: list[tuple[str, float, str]] = []
            if getattr(row, "sog_knots", None) is not None and row.sog_knots > config.speed_limit_knots:
                checks.append(("speed anomaly", 0.9, f"Reported SOG {row.sog_knots:.1f} kn exceeds the configured real-data review threshold."))
            if getattr(row, "time_delta_seconds", 0) > config.gap_seconds:
                checks.append(("signal gap", 0.82, f"Observed timestamp gap of {row.time_delta_seconds / 60:.1f} minutes."))
            if getattr(row, "heading_change", 0) > config.deviation_heading_degrees:
                checks.append(("heading anomaly", 0.78, f"Observed course change of {row.heading_change:.0f} degrees between reports."))
            for category, confidence, explanation in checks:
                findings.append(
                    AnomalyFinding(
                        mmsi=mmsi,
                        timestamp=row.timestamp.to_pydatetime(),
                        latitude=float(row.latitude),
                        longitude=float(row.longitude),
                        score=round(min(0.99, confidence), 3),
                        category=category,
                        confidence=round(confidence, 3),
                        explanation=explanation,
                    )
                )
        if len(frame) >= 2:
            duration = (frame["timestamp"].iloc[-1] - frame["timestamp"].iloc[0]).total_seconds() / 60
            dwell_ratio = float(frame["is_dwell"].mean())
            if duration >= config.dwell_minutes and dwell_ratio >= 0.8:
                latest = frame.iloc[-1]
                findings.append(
                    AnomalyFinding(
                        mmsi=mmsi,
                        timestamp=latest["timestamp"].to_pydatetime(),
                        latitude=float(latest["latitude"]),
                        longitude=float(latest["longitude"]),
                        score=0.72,
                        category="unusual stop",
                        confidence=0.74,
                        explanation=f"Vessel remained below 0.5 kn for {duration:.0f} minutes ({dwell_ratio:.0%} of reports).",
                    )
                )
        if mmsi in embedding_by_mmsi and embedding_by_mmsi[mmsi] >= 0.78:
            latest = frame.iloc[-1]
            score = float(embedding_by_mmsi[mmsi])
            findings.append(
                AnomalyFinding(
                    mmsi=mmsi,
                    timestamp=latest["timestamp"].to_pydatetime(),
                    latitude=float(latest["latitude"]),
                    longitude=float(latest["longitude"]),
                    score=round(score, 3),
                    category="behavioral deviation",
                    confidence=round(min(0.99, 0.55 + score * 0.4), 3),
                    explanation="Trajectory representation is dissimilar to the real AIS tracks fitted in this session.",
                )
            )
    return sorted(findings, key=lambda item: item.score, reverse=True)


def vessel_normality_score(findings: list[AnomalyFinding], mmsi: str) -> float:
    vessel_findings = [finding.score for finding in findings if finding.mmsi == mmsi]
    return round(max(0.0, 1.0 - max(vessel_findings, default=0.0)), 3)


def summarize_category(findings: list[AnomalyFinding]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for finding in findings:
        counts[finding.category] = counts.get(finding.category, 0) + 1
    return counts
