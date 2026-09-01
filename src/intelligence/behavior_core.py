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

# ---------------------------------------------------------------------------
# Thresholds (centralized — do not scatter magic numbers)
# ---------------------------------------------------------------------------

STOPPED_SOG_KNOTS = 0.5
SLOW_SOG_KNOTS = 3.0

# Maneuvering requires multiple signals, not a single course jump.
MANEUVER_TOTAL_COURSE_CHANGE_DEG = 40.0
MANEUVER_COURSE_RATE_DEG_PER_MIN = 8.0
MANEUVER_SOG_STD_KNOTS = 1.5

# IRREGULAR requires a combination of inconsistent signals.
IRREGULAR_SOG_STD_KNOTS = 4.0
IRREGULAR_COURSE_CONSISTENCY_MAX = 0.45
IRREGULAR_EFFICIENCY_MAX = 0.35
IRREGULAR_MIN_SIGNALS = 2

# Confidence gates
CONF_HIGH_MIN_OBS = 10
CONF_HIGH_MIN_DURATION_S = 600.0
CONF_HIGH_MIN_SOG_RATIO = 0.6
CONF_HIGH_MIN_COG_RATIO = 0.6

CONF_MEDIUM_MIN_OBS = 3
CONF_MEDIUM_MIN_DURATION_S = 120.0
CONF_MEDIUM_MIN_SOG_RATIO = 0.4

# Acceleration: ignore absurd spikes (AIS jumps)
MAX_ABS_ACCEL_KN_PER_S = 2.0

# Temporal: ignore non-positive deltas for rates/acceleration
MIN_DT_SECONDS = 1e-6

# Stopped segment: segment speed below this counts as stopped time
STOPPED_SEGMENT_SOG_KNOTS = 0.5

PROVENANCE = "DERIVED"

Classification = str  # UNDERWAY | SLOW_MOVEMENT | STOPPED | MANEUVERING | IRREGULAR | INSUFFICIENT_DATA
ConfidenceLevel = str  # N/A | LOW | MEDIUM | HIGH


@dataclass(frozen=True)
class SpeedFeatures:
    average_sog: float | None
    maximum_sog: float | None
    sog_std: float | None
    speed_variation: float | None  # max - min among valid SOG
    approximate_acceleration: float | None  # mean |Δv/Δt| in kn/s (valid pairs)


@dataclass(frozen=True)
class CourseFeatures:
    average_cog: float | None
    total_course_change: float | None  # sum of absolute circular deltas (deg)
    course_change_rate: float | None  # deg per minute over track span
    heading_cog_consistency: float | None  # 0..1 (1 = aligned)


@dataclass(frozen=True)
class MovementFeatures:
    traveled_distance_km: float | None
    displacement_km: float | None  # origin → last
    movement_duration_s: float | None
    stopped_duration_s: float | None
    movement_stopped_ratio: float | None  # moving_time / total_time
    trajectory_efficiency: float | None  # displacement / traveled (0..1)


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
    """Deterministic behavioral profile for a single MMSI session track."""

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


def _circular_delta_deg(a: float, b: float) -> float:
    """Smallest signed angle from a → b in (-180, 180]."""
    return (b - a + 180.0) % 360.0 - 180.0


def _circular_abs_delta_deg(a: float, b: float) -> float:
    return abs(_circular_delta_deg(a, b))


def _is_valid_coord(lat: float | None, lon: float | None) -> bool:
    if lat is None or lon is None:
        return False
    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except (TypeError, ValueError):
        return False
    if not (isfinite(lat_f) and isfinite(lon_f)):
        return False
    return -90.0 <= lat_f <= 90.0 and -180.0 <= lon_f <= 180.0


def _is_valid_sog(value: float | None) -> bool:
    if value is None:
        return False
    try:
        v = float(value)
    except (TypeError, ValueError):
        return False
    return isfinite(v) and 0.0 <= v <= 100.0


def _is_valid_angle(value: float | None) -> bool:
    if value is None:
        return False
    try:
        v = float(value)
    except (TypeError, ValueError):
        return False
    return isfinite(v) and 0.0 <= v <= 360.0


def _mean(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _std(values: Sequence[float]) -> float | None:
    if len(values) < 2:
        return None
    m = sum(values) / len(values)
    var = sum((x - m) ** 2 for x in values) / (len(values) - 1)
    return var ** 0.5


def _safe_ratio(num: float, den: float) -> float | None:
    if den <= 0.0 or not isfinite(den) or not isfinite(num):
        return None
    return num / den


def _circular_mean_deg(angles: Sequence[float]) -> float | None:
    if not angles:
        return None
    import math

    sx = sum(math.cos(math.radians(a)) for a in angles)
    sy = sum(math.sin(math.radians(a)) for a in angles)
    if abs(sx) < 1e-12 and abs(sy) < 1e-12:
        return None
    deg = math.degrees(math.atan2(sy, sx)) % 360.0
    return deg


def _clean_observations(
    observations: Iterable[AISObservation],
) -> list[AISObservation]:
    """Sort by time, drop invalid coords/timestamps; on duplicate timestamps keep the last record."""
    cleaned: list[AISObservation] = []
    for obs in observations:
        if not getattr(obs, "valid", True):
            continue
        ts = getattr(obs, "received_at", None)
        if ts is None:
            continue
        if ts.tzinfo is None:
            continue
        if not _is_valid_coord(obs.latitude, obs.longitude):
            continue
        cleaned.append(obs)

    cleaned.sort(key=lambda o: o.received_at.astimezone(timezone.utc))

    deduped: list[AISObservation] = []
    last_ts: datetime | None = None
    for obs in cleaned:
        ts = obs.received_at.astimezone(timezone.utc)
        if last_ts is not None and ts == last_ts:
            deduped[-1] = obs
            continue
        deduped.append(obs)
        last_ts = ts
    return deduped


def _empty_speed() -> SpeedFeatures:
    return SpeedFeatures(None, None, None, None, None)


def _empty_course() -> CourseFeatures:
    return CourseFeatures(None, None, None, None)


def _empty_movement() -> MovementFeatures:
    return MovementFeatures(None, None, None, None, None, None)


def _insufficient(mmsi: str, evidence: BehavioralEvidence, reason: str) -> BehavioralProfile:
    return BehavioralProfile(
        mmsi=mmsi,
        classification="INSUFFICIENT_DATA",
        confidence="N/A" if evidence.observation_count == 0 else "LOW",
        speed=_empty_speed(),
        course=_empty_course(),
        movement=_empty_movement(),
        evidence=evidence,
        provenance=PROVENANCE,
        reasons=(reason,),
    )


def extract_speed_features(obs: Sequence[AISObservation]) -> SpeedFeatures:
    sogs = [float(o.sog_knots) for o in obs if _is_valid_sog(o.sog_knots)]
    average = _mean(sogs)
    maximum = max(sogs) if sogs else None
    std = _std(sogs)
    variation = (max(sogs) - min(sogs)) if len(sogs) >= 2 else None

    accel_samples: list[float] = []
    for i in range(1, len(obs)):
        a, b = obs[i - 1], obs[i]
        if not (_is_valid_sog(a.sog_knots) and _is_valid_sog(b.sog_knots)):
            continue
        dt = (b.received_at - a.received_at).total_seconds()
        if dt <= 0.0 or dt < MIN_DT_SECONDS:
            continue
        dv = float(b.sog_knots) - float(a.sog_knots)
        acc = dv / dt
        if not isfinite(acc) or abs(acc) > MAX_ABS_ACCEL_KN_PER_S:
            continue
        accel_samples.append(abs(acc))

    approx_accel = _mean(accel_samples)
    return SpeedFeatures(
        average_sog=average,
        maximum_sog=maximum,
        sog_std=std,
        speed_variation=variation,
        approximate_acceleration=approx_accel,
    )


def extract_course_features(obs: Sequence[AISObservation]) -> CourseFeatures:
    cogs = [float(o.cog_degrees) for o in obs if _is_valid_angle(o.cog_degrees)]
    average = _circular_mean_deg(cogs)

    total_change = 0.0
    change_pairs = 0
    for i in range(1, len(obs)):
        a, b = obs[i - 1], obs[i]
        if not (_is_valid_angle(a.cog_degrees) and _is_valid_angle(b.cog_degrees)):
            continue
        total_change += _circular_abs_delta_deg(float(a.cog_degrees), float(b.cog_degrees))
        change_pairs += 1

    total_course_change = total_change if change_pairs > 0 else None

    span_s = None
    if len(obs) >= 2:
        span_s = (obs[-1].received_at - obs[0].received_at).total_seconds()
    course_rate = None
    if total_course_change is not None and span_s is not None and span_s > 0:
        course_rate = total_course_change / (span_s / 60.0)

    alignments: list[float] = []
    for o in obs:
        if _is_valid_angle(o.cog_degrees) and _is_valid_angle(o.heading_degrees):
            delta = _circular_abs_delta_deg(float(o.cog_degrees), float(o.heading_degrees))
            alignments.append(max(0.0, 1.0 - delta / 180.0))
    consistency = _mean(alignments)

    return CourseFeatures(
        average_cog=average,
        total_course_change=total_course_change,
        course_change_rate=course_rate,
        heading_cog_consistency=consistency,
    )
