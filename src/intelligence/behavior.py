"""Deterministic Behavioral Intelligence derived from real AIS observations.

Provenance: DERIVED from session AIS tracks only. No synthetic data, no ML
classification, and no dependency on unmerged historical/intelligence profile
layers.

Pipeline:
    AIS observations → cleaned trajectory → behavioral features
    → classification + confidence → BehavioralProfile
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from math import isfinite
from typing import Any, Iterable, Sequence

from src.ingestion.models import AISObservation
from src.processing.quality import haversine_km

STOPPED_SOG_KNOTS = 0.5
SLOW_SOG_KNOTS = 3.0
MANEUVER_TOTAL_COURSE_CHANGE_DEG = 40.0
MANEUVER_COURSE_RATE_DEG_PER_MIN = 8.0
MANEUVER_SOG_STD_KNOTS = 1.5
IRREGULAR_SOG_STD_KNOTS = 4.0
IRREGULAR_COURSE_CONSISTENCY_MAX = 0.45
IRREGULAR_EFFICIENCY_MAX = 0.35
IRREGULAR_MIN_SIGNALS = 2
CONF_HIGH_MIN_OBS = 10
CONF_HIGH_MIN_DURATION_S = 600.0
CONF_HIGH_MIN_SOG_RATIO = 0.6
CONF_HIGH_MIN_COG_RATIO = 0.6
CONF_MEDIUM_MIN_OBS = 3
CONF_MEDIUM_MIN_DURATION_S = 120.0
CONF_MEDIUM_MIN_SOG_RATIO = 0.4
MAX_ABS_ACCEL_KN_PER_S = 2.0
MIN_DT_SECONDS = 1e-6
STOPPED_SEGMENT_SOG_KNOTS = 0.5
PROVENANCE = "DERIVED"

Classification = str
ConfidenceLevel = str


@dataclass(frozen=True)
class SpeedFeatures:
    average_sog: float | None
    maximum_sog: float | None
    sog_std: float | None
    speed_variation: float | None
    approximate_acceleration: float | None


@dataclass(frozen=True)
class CourseFeatures:
    average_cog: float | None
    total_course_change: float | None
    course_change_rate: float | None
    heading_cog_consistency: float | None


@dataclass(frozen=True)
class MovementFeatures:
    traveled_distance_km: float | None
    displacement_km: float | None
    movement_duration_s: float | None
    stopped_duration_s: float | None
    movement_stopped_ratio: float | None
    trajectory_efficiency: float | None


@dataclass(frozen=True)
class BehavioralEvidence:
    observation_count: int
    valid_position_count: int
    sog_present_count: int
    cog_present_count: int
    time_span_seconds: float | None
    first_received_at: datetime | None
    last_received_at: datetime | None


@dataclass(frozen=True)
class BehavioralProfile:
    mmsi: str
    classification: Classification
    confidence: ConfidenceLevel
    speed: SpeedFeatures
    course: CourseFeatures
    movement: MovementFeatures
    evidence: BehavioralEvidence
    provenance: str = PROVENANCE
    reasons: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
