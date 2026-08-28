"""Explainable anomaly detection for observed AIS trajectories.

All findings are derived from real AIS observations available to the current
session. Behavioral-deviation scores from the runtime IsolationForest are
session-relative ranking signals, not calibrated probabilities.
"""

from __future__ import annotations

from dataclasses import dataclass

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

    # Behavioral deviation is only evaluated when the embedding model has
    # enough real AIS tracks to make a meaningful session-level comparison.
    minimum_behavioral_score: float = 0.78
    minimum_behavioral_tracks: int = 3


def detect_anomalies(
    tracks: dict[str, list[AISObservation]],
    embedding_result: EmbeddingResult | None = None,
    config: DetectorConfig | None = None,
) -> list[AnomalyFinding]:
    config = config or DetectorConfig()

    findings: list[AnomalyFinding] = []

    embedding_by_mmsi: dict[str, float] = {}

    if embedding_result is not None:
        embedding_by_mmsi = dict(
            zip(
                embedding_result.mmsis,
                embedding_result.anomaly_scores,
            )
        )

    behavioral_detection_ready = (
        embedding_result is not None
        and len(embedding_result.mmsis) >= config.minimum_behavioral_tracks
        and len(embedding_result.anomaly_scores)
        == len(embedding_result.mmsis)
    )

    for mmsi, observations in tracks.items():
        frame = enrich_track(track_to_frame(observations))

        if frame.empty:
            continue

        # ---------------------------------------------------------------
        # Rule-based observations
        # ---------------------------------------------------------------

        for row in frame.itertuples(index=False):
            checks: list[tuple[str, float, str]] = []

            sog = getattr(row, "sog_knots", None)

            if sog is not None and np.isfinite(sog):
                if sog > config.speed_limit_knots:
                    checks.append(
                        (
                            "speed anomaly",
                            0.90,
                            (
                                f"Reported SOG {sog:.1f} kn exceeds "
                                "the configured real-data review threshold."
                            ),
                        )
                    )

            time_delta = getattr(
                row,
                "time_delta_seconds",
                0,
            )

            if (
                time_delta is not None
                and np.isfinite(time_delta)
                and time_delta > config.gap_seconds
            ):
                checks.append(
                    (
                        "signal gap",
                        0.82,
                        (
                            f"Observed timestamp gap of "
                            f"{time_delta / 60:.1f} minutes."
                        ),
                    )
                )

            heading_change = getattr(
                row,
                "heading_change",
                0,
            )

            if (
                heading_change is not None
                and np.isfinite(heading_change)
                and heading_change > config.deviation_heading_degrees
            ):
                checks.append(
                    (
                        "heading anomaly",
                        0.78,
                        (
                            f"Observed course change of "
                            f"{heading_change:.0f} degrees "
                            "between reports."
                        ),
                    )
                )

            for category, score, explanation in checks:
                findings.append(
                    AnomalyFinding(
                        mmsi=mmsi,
                        received_at=row.received_at.to_pydatetime(),
                        ais_timestamp_second=_ais_second(
                            getattr(
                                row,
                                "ais_timestamp_second",
                                None,
                            )
                        ),
                        latitude=float(row.latitude),
                        longitude=float(row.longitude),
                        score=round(min(0.99, score), 3),
                        category=category,
                        confidence=round(min(0.99, score), 3),
                        explanation=explanation,
                    )
                )

        # ---------------------------------------------------------------
        # Dwell / unusual stop
        # ---------------------------------------------------------------

        if len(frame) >= 2:
            duration = (
                frame["received_at"].iloc[-1]
                - frame["received_at"].iloc[0]
            ).total_seconds() / 60

            dwell_ratio = float(frame["is_dwell"].mean())

            if (
                duration >= config.dwell_minutes
                and dwell_ratio >= 0.8
            ):
                latest = frame.iloc[-1]

                findings.append(
                    AnomalyFinding(
                        mmsi=mmsi,
                        received_at=latest["received_at"].to_pydatetime(),
                        ais_timestamp_second=_ais_second(
                            latest.get("ais_timestamp_second")
                        ),
                        latitude=float(latest["latitude"]),
                        longitude=float(latest["longitude"]),
                        score=0.72,
                        category="unusual stop",
                        confidence=0.74,
                        explanation=(
                            f"Vessel remained below 0.5 kn for "
                            f"{duration:.0f} minutes "
                            f"({dwell_ratio:.0%} of reports)."
                        ),
                    )
                )

        # ---------------------------------------------------------------
        # Session-relative behavioral deviation
        # ---------------------------------------------------------------

        if not behavioral_detection_ready:
            continue

        score = embedding_by_mmsi.get(mmsi)

        if score is None or not np.isfinite(score):
            continue

        if score < config.minimum_behavioral_score:
            continue

        latest = frame.iloc[-1]

        findings.append(
            AnomalyFinding(
                mmsi=mmsi,
                received_at=latest["received_at"].to_pydatetime(),
                ais_timestamp_second=_ais_second(
                    latest.get("ais_timestamp_second")
                ),
                latitude=float(latest["latitude"]),
                longitude=float(latest["longitude"]),
                score=round(float(score), 3),
                category="behavioral deviation",
                # IMPORTANT:
                # This value is intentionally NOT derived from the score.
                # The runtime IsolationForest score is not calibrated as a
                # probability, therefore no fabricated confidence is emitted.
                confidence=None,
                explanation=(
                    "Trajectory representation is relatively isolated "
                    "from the other real AIS tracks fitted in this session. "
                    f"Session-relative outlier score: {score:.2f}. "
                    "This score is not a probability or calibrated confidence."
                ),
            )
        )

    return sorted(
        findings,
        key=lambda item: item.score,
        reverse=True,
    )


def _ais_second(value: object) -> int | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    return (
        int(number)
        if np.isfinite(number) and number.is_integer()
        else None
    )


def vessel_normality_score(
    findings: list[AnomalyFinding],
    mmsi: str,
) -> float:
    vessel_findings = [
        finding.score
        for finding in findings
        if finding.mmsi == mmsi
    ]

    return round(
        max(
            0.0,
            1.0 - max(vessel_findings, default=0.0),
        ),
        3,
    )


def summarize_category(
    findings: list[AnomalyFinding],
) -> dict[str, int]:
    counts: dict[str, int] = {}

    for finding in findings:
        counts[finding.category] = (
            counts.get(finding.category, 0) + 1
        )

    return counts