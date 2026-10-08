"""Explicit anomaly-analysis outcomes derived from the existing detector."""

from __future__ import annotations

import numpy as np

from src.anomaly.detector import DetectorConfig, detect_anomalies
from src.evidence.runtime import ProducerEvidence
from src.ingestion.models import AISObservation
from src.ml.embeddings import EmbeddingResult
from src.trajectory.features import enrich_track, track_to_frame


def analyze_anomalies(
    tracks: dict[str, list[AISObservation]],
    embedding_result: EmbeddingResult | None = None,
    config: DetectorConfig | None = None,
) -> tuple[list, list[ProducerEvidence]]:
    """Return existing findings plus explicit positive/negative outcomes.

    Negative evidence is emitted only for detector rules with an explicit
    decision boundary. Missing model readiness remains NOT_ANALYZED.
    """
    config = config or DetectorConfig()
    findings = detect_anomalies(tracks, embedding_result, config)
    evidence: list[ProducerEvidence] = []

    for mmsi, observations in tracks.items():
        frame = enrich_track(track_to_frame(observations))
        if frame.empty:
            evidence.append(
                ProducerEvidence(
                    producer_id="ANOMALY_DETECTOR",
                    claim_type="ANOMALY_DETECTION",
                    state="NOT_ANALYZED",
                    signal_polarity="INDETERMINATE",
                    subject_id=mmsi,
                    reason_code="INSUFFICIENT_INPUT",
                )
            )
            continue

        categories = {item.category for item in findings if item.mmsi == mmsi}
        for claim_type, category in (
            ("SPEED_ANOMALY", "speed anomaly"),
            ("SIGNAL_GAP", "signal gap"),
            ("HEADING_ANOMALY", "heading anomaly"),
            ("UNUSUAL_STOP", "unusual stop"),
        ):
            detected = category in categories
            evidence.append(
                ProducerEvidence(
                    producer_id="ANOMALY_DETECTOR",
                    claim_type=claim_type,
                    state="ANALYZED_SIGNAL" if detected else "ANALYZED_NO_SIGNAL",
                    signal_polarity="POSITIVE" if detected else "NEGATIVE",
                    subject_id=mmsi,
                )
            )

        ready = (
            embedding_result is not None
            and len(embedding_result.mmsis) >= config.minimum_behavioral_tracks
            and len(embedding_result.anomaly_scores) == len(embedding_result.mmsis)
        )
        if not ready:
            evidence.append(
                ProducerEvidence(
                    producer_id="ANOMALY_DETECTOR",
                    claim_type="BEHAVIORAL_DEVIATION",
                    state="NOT_ANALYZED",
                    signal_polarity="INDETERMINATE",
                    subject_id=mmsi,
                    reason_code="INSUFFICIENT_INPUT",
                )
            )
            continue

        score = dict(
            zip(embedding_result.mmsis, embedding_result.anomaly_scores)
        ).get(mmsi)
        if score is None or not np.isfinite(score):
            evidence.append(
                ProducerEvidence(
                    producer_id="ANOMALY_DETECTOR",
                    claim_type="BEHAVIORAL_DEVIATION",
                    state="NOT_ANALYZED",
                    signal_polarity="INDETERMINATE",
                    subject_id=mmsi,
                    reason_code="UNKNOWN",
                )
            )
            continue

        detected = float(score) >= config.minimum_behavioral_score
        evidence.append(
            ProducerEvidence(
                producer_id="ANOMALY_DETECTOR",
                claim_type="BEHAVIORAL_DEVIATION",
                state="ANALYZED_SIGNAL" if detected else "ANALYZED_NO_SIGNAL",
                signal_polarity="POSITIVE" if detected else "NEGATIVE",
                subject_id=mmsi,
                score=round(float(score), 3),
            )
        )

    return findings, evidence
