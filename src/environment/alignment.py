"""Explicit, non-interpolating AIS/environment alignment."""
from __future__ import annotations

from datetime import datetime, timezone
from math import asin, cos, radians, sin, sqrt

from src.ingestion.models import AISObservation

from .models import (
    AlignmentPolicy,
    AlignmentResult,
    AlignmentStatus,
    EnvironmentalDataset,
    EnvironmentalNature,
    EvidenceStatus,
    SpatialTemporalMatch,
    _REASON_INTERPOLATION_POLICY,
    _REASON_MISSING_METADATA,
    _REASON_MISSING_SPATIAL_REFERENCE,
    _REASON_MISSING_TEMPORAL_REFERENCE,
    _REASON_NO_DATASET,
    _REASON_NO_POINT,
    _REASON_SPATIAL_MISMATCH,
    _REASON_SPATIAL_POLICY,
    _REASON_TEMPORAL_MISMATCH,
    _REASON_TEMPORAL_POLICY,
)


class SpatialTemporalAligner:
    """Pair an AIS observation with one explicit environmental point.

    Phase 1 supports only direct point-to-point distance and absolute timestamp
    comparison when the caller provides both methods and thresholds. It does
    not select a nearest cell, interpolate, or infer thresholds.
    """

    def __init__(self, policy: AlignmentPolicy | None = None) -> None:
        self.policy = policy

    def align(self, observation: AISObservation, dataset: EnvironmentalDataset | None) -> AlignmentResult:
        if dataset is None:
            return AlignmentResult(EvidenceStatus.NOT_ANALYZED, _REASON_NO_DATASET)
        if not dataset.points:
            return AlignmentResult(EvidenceStatus.NOT_ANALYZED, _REASON_NO_POINT)
        point = dataset.points[0]
        if len(dataset.points) > 1:
            # Choosing a point would be a nearest-cell/selection policy. Phase 1
            # intentionally refuses to make that decision implicitly.
            return AlignmentResult(EvidenceStatus.NOT_ANALYZED, _REASON_MISSING_METADATA)
        if observation is None:
            return AlignmentResult(EvidenceStatus.NOT_ANALYZED, _REASON_MISSING_METADATA)
        if point.latitude is None or point.longitude is None:
            return AlignmentResult(EvidenceStatus.NOT_ANALYZED, _REASON_MISSING_SPATIAL_REFERENCE)
        if point.temporal_reference is None:
            return AlignmentResult(EvidenceStatus.NOT_ANALYZED, _REASON_MISSING_TEMPORAL_REFERENCE)
        if not point.provenance:
            return AlignmentResult(EvidenceStatus.NOT_ANALYZED, _REASON_MISSING_METADATA)
        if self.policy is None or not self.policy.spatially_defined:
            return AlignmentResult(EvidenceStatus.NOT_ANALYZED, _REASON_SPATIAL_POLICY)
        if self.policy.spatial_method != "DIRECT_POINT":
            return AlignmentResult(EvidenceStatus.NOT_ANALYZED, _REASON_INTERPOLATION_POLICY)
        if not self.policy.temporally_defined:
            return AlignmentResult(EvidenceStatus.NOT_ANALYZED, _REASON_TEMPORAL_POLICY)
        if self.policy.temporal_method != "ABSOLUTE_REFERENCE_TIME":
            return AlignmentResult(EvidenceStatus.NOT_ANALYZED, _REASON_INTERPOLATION_POLICY)

        spatial_distance = haversine_km(observation.latitude, observation.longitude, point.latitude, point.longitude)
        temporal_delta = abs((observation.received_at.astimezone(timezone.utc) - point.temporal_reference).total_seconds())
        spatial_status = (
            AlignmentStatus.VALID
            if spatial_distance <= float(self.policy.max_spatial_distance_km)
            else AlignmentStatus.MISMATCH
        )
        temporal_status = (
            AlignmentStatus.LIMITED if point.nature is EnvironmentalNature.ENVIRONMENTAL_MODEL_STATE else AlignmentStatus.VALID
        )
        if temporal_delta > float(self.policy.max_temporal_delta_seconds):
            temporal_status = AlignmentStatus.MISMATCH

        provenance = dict(point.provenance)
        provenance.update(
            {
                "alignment_reference_kind": "model_validity_time" if point.nature is EnvironmentalNature.ENVIRONMENTAL_MODEL_STATE else "reference_time",
                "spatial_method": self.policy.spatial_method,
                "temporal_method": self.policy.temporal_method,
            }
        )
        match = SpatialTemporalMatch(
            ais_observation=observation,
            environmental_point=point,
            spatial_distance_km=spatial_distance,
            temporal_delta_seconds=temporal_delta,
            spatial_match_status=spatial_status,
            temporal_match_status=temporal_status,
            source=point.source,
            nature=point.nature,
            provenance=provenance,
            spatial_method=self.policy.spatial_method,
            temporal_method=self.policy.temporal_method,
        )
        if spatial_status is AlignmentStatus.MISMATCH:
            return AlignmentResult(EvidenceStatus.NOT_ANALYZED, _REASON_SPATIAL_MISMATCH, match)
        if temporal_status is AlignmentStatus.MISMATCH:
            return AlignmentResult(EvidenceStatus.NOT_ANALYZED, _REASON_TEMPORAL_MISMATCH, match)
        return AlignmentResult(EvidenceStatus.NOT_ANALYZED, "ALIGNMENT_ONLY_NO_ANALYSIS", match)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate point distance in kilometres; no threshold is implied."""
    earth_radius_km = 6371.0088
    lat_delta = radians(lat2 - lat1)
    lon_delta = radians(lon2 - lon1)
    a = sin(lat_delta / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(lon_delta / 2) ** 2
    return earth_radius_km * 2 * asin(sqrt(max(0.0, min(1.0, a))))
