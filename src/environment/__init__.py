"""Phase 1 Environmental Intelligence Layer contracts.

This package provides spatial-temporal alignment infrastructure only. It does
not fetch environmental data, perform correlation, or infer causality.
"""
from .alignment import SpatialTemporalAligner, haversine_km
from .models import (
    AlignmentPolicy,
    AlignmentResult,
    AlignmentStatus,
    EnvironmentalDataset,
    EnvironmentalNature,
    EnvironmentalPoint,
    EvidenceStatus,
    SpatialTemporalMatch,
    VesselEnvironmentTrack,
)
from .providers import EnvironmentalProvider

__all__ = [
    "AlignmentPolicy",
    "AlignmentResult",
    "AlignmentStatus",
    "EnvironmentalDataset",
    "EnvironmentalNature",
    "EnvironmentalPoint",
    "EnvironmentalProvider",
    "EvidenceStatus",
    "SpatialTemporalAligner",
    "SpatialTemporalMatch",
    "VesselEnvironmentTrack",
    "haversine_km",
]
