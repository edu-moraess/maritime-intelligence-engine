"""Deterministic Behavioral Intelligence derived from real AIS observations.

Provenance: DERIVED from session AIS tracks only. No synthetic data, no ML
classification, and no dependency on unmerged historical/intelligence profile
layers.

Pipeline:
    AIS observations → cleaned trajectory → behavioral features
    → classification + confidence → BehavioralProfile
"""

from __future__ import annotations

from src.intelligence.behavior_core import (
    BehavioralEvidence,
    BehavioralProfile,
    Classification,
    ConfidenceLevel,
    CourseFeatures,
    MovementFeatures,
    PROVENANCE,
    SpeedFeatures,
    STOPPED_SOG_KNOTS,
    SLOW_SOG_KNOTS,
    MANEUVER_TOTAL_COURSE_CHANGE_DEG,
    MANEUVER_COURSE_RATE_DEG_PER_MIN,
    MANEUVER_SOG_STD_KNOTS,
    IRREGULAR_SOG_STD_KNOTS,
    IRREGULAR_COURSE_CONSISTENCY_MAX,
    IRREGULAR_EFFICIENCY_MAX,
    IRREGULAR_MIN_SIGNALS,
    _circular_abs_delta_deg,
    _circular_delta_deg,
    _clean_observations,
    extract_course_features,
    extract_speed_features,
)
from src.intelligence.behavior_rest import (
    build_behavioral_profile,
    classify_behavior,
    compute_confidence,
    extract_movement_features,
    profile_from_engine_track,
)

__all__ = [
    "BehavioralEvidence",
    "BehavioralProfile",
    "Classification",
    "ConfidenceLevel",
    "CourseFeatures",
    "MovementFeatures",
    "PROVENANCE",
    "SpeedFeatures",
    "STOPPED_SOG_KNOTS",
    "SLOW_SOG_KNOTS",
    "build_behavioral_profile",
    "classify_behavior",
    "compute_confidence",
    "extract_course_features",
    "extract_movement_features",
    "extract_speed_features",
    "profile_from_engine_track",
    "_circular_abs_delta_deg",
    "_circular_delta_deg",
    "_clean_observations",
]
