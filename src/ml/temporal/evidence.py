"""Producer-side evidence mapping for temporal model execution."""

from __future__ import annotations

from src.evidence.runtime import ProducerEvidence
from src.ml.temporal.types import TemporalFitResult


def temporal_evidence(result: TemporalFitResult) -> list[ProducerEvidence]:
    """Represent temporal scoring without inventing a binary anomaly threshold.

    TCN currently produces continuous reconstruction/ranking signals rather than
    a thresholded anomaly decision. Therefore READY is ANALYZED_SIGNAL for the
    scoring claim; it is not evidence of a negative anomaly state.
    """
    if result.status == "READY":
        return [
            ProducerEvidence(
                producer_id="TCN_TEMPORAL_AUTOENCODER",
                claim_type="TEMPORAL_SCORE",
                state="ANALYZED_SIGNAL",
                signal_polarity="POSITIVE",
                subject_id=score.mmsi,
                score=score.deep_anomaly_score,
            )
            for score in result.scores
        ]

    reason = (
        "INSUFFICIENT_INPUT"
        if result.status in {"WAITING", "NOT_READY"}
        else "DEPENDENCY_UNAVAILABLE"
        if result.status == "UNAVAILABLE"
        else "EXECUTION_FAILURE"
    )
    return [
        ProducerEvidence(
            producer_id="TCN_TEMPORAL_AUTOENCODER",
            claim_type="TEMPORAL_SCORE",
            state="NOT_ANALYZED",
            signal_polarity="INDETERMINATE",
            reason_code=reason,
        )
    ]
