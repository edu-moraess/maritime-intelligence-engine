"""Explainable hybrid anomaly scoring built on existing real-AIS model outputs.

This module does not modify the production engine. It fuses session-relative
IsolationForest, temporal reconstruction, and rule evidence without presenting
the result as a calibrated probability or confidence.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HybridVesselScore:
    mmsi: str
    isolation_score: float | None
    temporal_score: float | None
    rule_score: float
    hybrid_score: float
    evidence: tuple[str, ...]


def fuse_scores(
    mmsi: str,
    *,
    isolation_score: float | None,
    temporal_score: float | None,
    rule_scores: list[float] | None = None,
) -> HybridVesselScore:
    """Fuse independent anomaly signals into a bounded ranking score.

    Weights are fixed and transparent: IF 45%, temporal 40%, rules 15%.
    Missing model signals are renormalized rather than replaced by synthetic data.
    The result is a session-relative ranking signal, never a probability.
    """
    rule_score = max(rule_scores or [0.0])
    components: list[tuple[float, float, str]] = []
    if isolation_score is not None:
        components.append((0.45, _bounded(isolation_score), "IsolationForest"))
    if temporal_score is not None:
        components.append((0.40, _bounded(temporal_score), "Temporal Autoencoder"))
    if rule_scores:
        components.append((0.15, _bounded(rule_score), "Rule evidence"))

    if not components:
        score = 0.0
    else:
        total_weight = sum(weight for weight, _, _ in components)
        score = sum(weight * value for weight, value, _ in components) / total_weight

    evidence = tuple(name for _, value, name in components if value >= 0.70)
    return HybridVesselScore(
        mmsi=mmsi,
        isolation_score=isolation_score,
        temporal_score=temporal_score,
        rule_score=rule_score,
        hybrid_score=round(_bounded(score), 4),
        evidence=evidence,
    )


def rank_hybrid(scores: list[HybridVesselScore]) -> list[HybridVesselScore]:
    return sorted(scores, key=lambda item: item.hybrid_score, reverse=True)


def _bounded(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
