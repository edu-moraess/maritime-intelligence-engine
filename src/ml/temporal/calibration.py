"""Calibração operacional de scores temporais sem fingir probabilidade."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from statistics import NormalDist
from typing import Iterable


@dataclass(frozen=True)
class CalibratedAnomaly:
    mmsi: str
    score: float
    percentile: float
    baseline_threshold: float | None
    alert: bool
    persistent_windows: int


class HistoricalScoreBaseline:
    """Baseline empírico de erro de reconstrução histórico."""

    def __init__(self, scores: Iterable[float] = ()) -> None:
        values = sorted(float(v) for v in scores if isfinite(float(v)) and float(v) >= 0)
        self._scores = values

    @property
    def size(self) -> int:
        return len(self._scores)

    @property
    def threshold(self) -> float | None:
        if not self._scores:
            return None
        index = min(len(self._scores) - 1, max(0, int(round(0.99 * (len(self._scores) - 1)))))
        return float(self._scores[index])

    def percentile(self, score: float) -> float:
        if not self._scores:
            return 50.0
        x = float(score)
        less = sum(v < x for v in self._scores)
        equal = sum(v == x for v in self._scores)
        return 100.0 * (less + 0.5 * equal) / len(self._scores)


def calibrate_anomaly(
    mmsi: str,
    score: float,
    *,
    baseline: HistoricalScoreBaseline,
    persistent_windows: int = 1,
    minimum_absolute_score: float | None = None,
    percentile_threshold: float = 99.0,
) -> CalibratedAnomaly:
    """Produz percentil empírico; 'alerta' exige os três critérios operacionais."""
    value = float(score)
    percentile = baseline.percentile(value)
    threshold = baseline.threshold
    absolute_ok = threshold is not None and value >= threshold
    if minimum_absolute_score is not None:
        absolute_ok = absolute_ok and value >= float(minimum_absolute_score)
    alert = (
        percentile >= float(percentile_threshold)
        and absolute_ok
        and int(persistent_windows) >= 3
    )
    return CalibratedAnomaly(
        mmsi=str(mmsi),
        score=value,
        percentile=percentile,
        baseline_threshold=threshold,
        alert=alert,
        persistent_windows=max(0, int(persistent_windows)),
    )
