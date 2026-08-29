"""Unsupervised comparison between Isolation Forest and Deep Temporal scores."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np

from src.ml.temporal.types import TemporalFitResult, TemporalScore


@dataclass(frozen=True)
class BenchmarkResult:
    status: str
    reason: str
    n_common: int = 0
    spearman_rho: float | None = None
    top_k: int = 0
    top_k_overlap: int = 0
    top_k_jaccard: float | None = None
    discordant_if_high_deep_low: list[str] | None = None
    discordant_deep_high_if_low: list[str] | None = None
    if_scores: dict[str, float] | None = None
    deep_scores: dict[str, float] | None = None


def if_scores_from_embeddings(embeddings: Any) -> dict[str, float]:
    """Extract MMSI → IF anomaly score from EmbeddingResult (session-relative)."""
    if embeddings is None:
        return {}
    mmsis = getattr(embeddings, "mmsis", None)
    scores = getattr(embeddings, "anomaly_scores", None)
    if mmsis is None or scores is None:
        return {}
    out: dict[str, float] = {}
    for mmsi, score in zip(list(mmsis), list(scores)):
        try:
            out[str(mmsi)] = float(score)
        except (TypeError, ValueError):
            continue
    return out


def _spearman(x: np.ndarray, y: np.ndarray) -> float | None:
    if len(x) < 2:
        return None
    rx = np.argsort(np.argsort(x)).astype(np.float64)
    ry = np.argsort(np.argsort(y)).astype(np.float64)
    rx = rx - rx.mean()
    ry = ry - ry.mean()
    denom = float(np.sqrt((rx ** 2).sum() * (ry ** 2).sum()))
    if denom < 1e-12:
        return None
    return float((rx * ry).sum() / denom)


def compare_if_vs_deep(
    if_scores: Mapping[str, float],
    deep_scores: Sequence[TemporalScore] | Mapping[str, float],
    *,
    top_k: int = 5,
) -> BenchmarkResult:
    """Compare IsolationForest and Deep Temporal rankings (unsupervised only)."""
    if isinstance(deep_scores, Mapping):
        deep_map = {str(k): float(v) for k, v in deep_scores.items()}
    else:
        deep_map = {s.mmsi: float(s.deep_anomaly_score) for s in deep_scores}

    if_map = {str(k): float(v) for k, v in if_scores.items()}
    common = sorted(set(if_map) & set(deep_map))
    if len(common) < 2:
        return BenchmarkResult(
            status="INCONCLUSIVO",
            reason=f"Need ≥2 common MMSIs; got {len(common)}.",
            n_common=len(common),
            if_scores=if_map,
            deep_scores=deep_map,
        )

    if_arr = np.asarray([if_map[m] for m in common], dtype=np.float64)
    deep_arr = np.asarray([deep_map[m] for m in common], dtype=np.float64)
    rho = _spearman(if_arr, deep_arr)

    k = max(1, min(int(top_k), len(common)))
    if_top = set(sorted(common, key=lambda m: if_map[m], reverse=True)[:k])
    deep_top = set(sorted(common, key=lambda m: deep_map[m], reverse=True)[:k])
    overlap = len(if_top & deep_top)
    jaccard = overlap / len(if_top | deep_top) if (if_top | deep_top) else None

    med_if = float(np.median(if_arr))
    med_deep = float(np.median(deep_arr))
    if_high_deep_low = [
        m for m in common if if_map[m] >= med_if and deep_map[m] <= med_deep
    ]
    deep_high_if_low = [
        m for m in common if deep_map[m] >= med_deep and if_map[m] <= med_if
    ]

    if rho is None:
        status = "INCONCLUSIVO"
        reason = "Spearman undefined (constant ranks)."
    elif rho >= 0.7 and (jaccard or 0) >= 0.5:
        status = "REDUNDANTE"
        reason = f"High agreement (ρ={rho:.3f}, Jaccard@k={jaccard:.3f})."
    elif rho <= 0.3:
        status = "COMPLEMENTAR"
        reason = f"Low rank correlation (ρ={rho:.3f}); complementary signal."
    else:
        status = "INCONCLUSIVO"
        reason = f"Moderate agreement (ρ={rho:.3f}, Jaccard@k={jaccard})."

    return BenchmarkResult(
        status=status,
        reason=reason,
        n_common=len(common),
        spearman_rho=rho,
        top_k=k,
        top_k_overlap=overlap,
        top_k_jaccard=jaccard,
        discordant_if_high_deep_low=if_high_deep_low[:10],
        discordant_deep_high_if_low=deep_high_if_low[:10],
        if_scores=if_map,
        deep_scores=deep_map,
    )


def compare_snapshot(snapshot: Any) -> BenchmarkResult:
    """Convenience: compare IF embeddings vs temporal scores on an EngineSnapshot."""
    temporal = getattr(snapshot, "temporal", None)
    embeddings = getattr(snapshot, "embeddings", None)
    if temporal is None or getattr(temporal, "status", None) != "READY":
        return BenchmarkResult(
            status="INCONCLUSIVO",
            reason="Temporal path not READY.",
            if_scores=if_scores_from_embeddings(embeddings),
        )
    scores = getattr(temporal, "scores", None) or []
    if not scores:
        return BenchmarkResult(
            status="INCONCLUSIVO",
            reason="No deep scores available.",
            if_scores=if_scores_from_embeddings(embeddings),
        )
    return compare_if_vs_deep(if_scores_from_embeddings(embeddings), scores)
