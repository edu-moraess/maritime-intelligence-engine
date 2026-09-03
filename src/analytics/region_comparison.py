"""Comparable region-level analytics for one shared real-AIS session."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from src.ingestion.models import AISObservation, AnomalyFinding
from src.ml.temporal.types import TemporalFitResult

RegionBBox = tuple[tuple[float, float], tuple[float, float]]


@dataclass(frozen=True)
class RegionMetrics:
    """Normalized metrics for one monitored region."""

    label: str
    unique_vessels: int
    position_reports: int
    average_speed_knots: float
    eligible_temporal_tracks: int
    temporal_anomalous_tracks: int
    temporal_anomaly_rate: float
    average_temporal_score: float | None
    anomalies: int
    anomaly_rate: float


@dataclass(frozen=True)
class RegionComparison:
    """A/B comparison derived from the same session and shared model."""

    regions: tuple[RegionMetrics, RegionMetrics]
    ambiguous_observations: int = 0


def _contains(bbox: RegionBBox, latitude: float, longitude: float) -> bool:
    (min_lat, min_lon), (max_lat, max_lon) = bbox
    return min_lat <= latitude <= max_lat and min_lon <= longitude <= max_lon


def _membership(
    latitude: float,
    longitude: float,
    bboxes: Sequence[RegionBBox],
) -> tuple[int, ...]:
    return tuple(index for index, bbox in enumerate(bboxes) if _contains(bbox, latitude, longitude))


def compare_regions(
    observations: Iterable[AISObservation],
    findings: Iterable[AnomalyFinding],
    bboxes: Sequence[RegionBBox],
    temporal: TemporalFitResult | None = None,
    labels: Sequence[str] | None = None,
) -> RegionComparison | None:
    """Compare two regions without training separate regional models.

    Observations falling in overlapping boxes are excluded from both regional
    metrics instead of being double-counted. Temporal scores are assigned by
    the vessel's observed track membership and therefore remain comparable
    because the temporal model is shared across both regions.
    """
    if len(bboxes) != 2:
        return None
    names = tuple(labels or ("Region A", "Region B"))
    if len(names) != 2:
        raise ValueError("Exactly two region labels are required.")

    region_observations: list[list[AISObservation]] = [[], []]
    ambiguous = 0
    for observation in observations:
        membership = _membership(observation.latitude, observation.longitude, bboxes)
        if len(membership) == 1:
            region_observations[membership[0]].append(observation)
        elif len(membership) > 1:
            ambiguous += 1

    finding_counts = [0, 0]
    for finding in findings:
        membership = _membership(finding.latitude, finding.longitude, bboxes)
        if len(membership) == 1:
            finding_counts[membership[0]] += 1

    temporal_scores = {score.mmsi: score for score in (temporal.scores if temporal and temporal.ready else [])}
    track_regions: list[set[str]] = [set(), set()]
    for region_index, region_items in enumerate(region_observations):
        track_regions[region_index] = {item.mmsi for item in region_items}

    metrics: list[RegionMetrics] = []
    for index, region_items in enumerate(region_observations):
        vessel_ids = {item.mmsi for item in region_items}
        speeds = [item.sog_knots for item in region_items if item.sog_knots is not None]
        eligible = sorted(vessel_ids & set(temporal_scores))
        scores = [temporal_scores[mmsi] for mmsi in eligible]
        temporal_anomalous = sum(score.deep_anomaly_score >= 0.5 for score in scores)
        metrics.append(
            RegionMetrics(
                label=names[index],
                unique_vessels=len(vessel_ids),
                position_reports=len(region_items),
                average_speed_knots=round(sum(speeds) / len(speeds), 2) if speeds else 0.0,
                eligible_temporal_tracks=len(eligible),
                temporal_anomalous_tracks=temporal_anomalous,
                temporal_anomaly_rate=(temporal_anomalous / len(eligible)) if eligible else 0.0,
                average_temporal_score=(
                    round(sum(score.deep_anomaly_score for score in scores) / len(scores), 4)
                    if scores else None
                ),
                anomalies=finding_counts[index],
                anomaly_rate=(finding_counts[index] / len(vessel_ids)) if vessel_ids else 0.0,
            )
        )
    return RegionComparison(regions=(metrics[0], metrics[1]), ambiguous_observations=ambiguous)
