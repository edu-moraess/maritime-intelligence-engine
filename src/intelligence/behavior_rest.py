"""Behavioral feature extraction (movement) and classification."""
from __future__ import annotations

from datetime import timezone
from math import isfinite
from typing import Any, Iterable, Sequence

from src.ingestion.models import AISObservation
from src.processing.quality import haversine_km

from src.intelligence.behavior_core import (
    BehavioralEvidence,
    BehavioralProfile,
    Classification,
    ConfidenceLevel,
    CourseFeatures,
    MovementFeatures,
    PROVENANCE,
    SpeedFeatures,
    STOPPED_SEGMENT_SOG_KNOTS,
    STOPPED_SOG_KNOTS,
    SLOW_SOG_KNOTS,
    MANEUVER_TOTAL_COURSE_CHANGE_DEG,
    MANEUVER_COURSE_RATE_DEG_PER_MIN,
    MANEUVER_SOG_STD_KNOTS,
    IRREGULAR_SOG_STD_KNOTS,
    IRREGULAR_COURSE_CONSISTENCY_MAX,
    IRREGULAR_EFFICIENCY_MAX,
    IRREGULAR_MIN_SIGNALS,
    CONF_HIGH_MIN_OBS,
    CONF_HIGH_MIN_DURATION_S,
    CONF_HIGH_MIN_SOG_RATIO,
    CONF_HIGH_MIN_COG_RATIO,
    CONF_MEDIUM_MIN_OBS,
    CONF_MEDIUM_MIN_DURATION_S,
    CONF_MEDIUM_MIN_SOG_RATIO,
    _circular_abs_delta_deg,
    _clean_observations,
    _empty_course,
    _empty_movement,
    _empty_speed,
    _insufficient,
    _is_valid_angle,
    _is_valid_sog,
    _mean,
    _safe_ratio,
    extract_course_features,
    extract_speed_features,
)


def extract_movement_features(obs: Sequence[AISObservation]) -> MovementFeatures:
    if len(obs) < 2:
        return _empty_movement()

    traveled = 0.0
    stopped_s = 0.0
    moving_s = 0.0

    for i in range(1, len(obs)):
        a, b = obs[i - 1], obs[i]
        dt = (b.received_at - a.received_at).total_seconds()
        if dt <= 0.0:
            continue
        dist = haversine_km(a.latitude, a.longitude, b.latitude, b.longitude)
        if not isfinite(dist):
            continue
        traveled += dist
        hours = dt / 3600.0
        seg_sog = (dist / hours) / 1.852 if hours > 0 else 0.0
        if seg_sog < STOPPED_SEGMENT_SOG_KNOTS:
            stopped_s += dt
        else:
            moving_s += dt

    first, last = obs[0], obs[-1]
    displacement = haversine_km(
        first.latitude, first.longitude, last.latitude, last.longitude
    )
    if not isfinite(displacement):
        displacement = None

    total_s = (last.received_at - first.received_at).total_seconds()
    if total_s < 0:
        total_s = None

    ratio = _safe_ratio(moving_s, moving_s + stopped_s) if (moving_s + stopped_s) > 0 else None
    efficiency = _safe_ratio(displacement or 0.0, traveled) if traveled > 0 else None
    if efficiency is not None:
        efficiency = max(0.0, min(1.0, efficiency))

    return MovementFeatures(
        traveled_distance_km=traveled if traveled > 0 else (0.0 if len(obs) >= 2 else None),
        displacement_km=displacement,
        movement_duration_s=moving_s if total_s is not None else None,
        stopped_duration_s=stopped_s if total_s is not None else None,
        movement_stopped_ratio=ratio,
        trajectory_efficiency=efficiency,
    )


def _build_evidence(raw_count: int, obs: Sequence[AISObservation]) -> BehavioralEvidence:
    sog_n = sum(1 for o in obs if _is_valid_sog(o.sog_knots))
    cog_n = sum(1 for o in obs if _is_valid_angle(o.cog_degrees))
    first = obs[0].received_at.astimezone(timezone.utc) if obs else None
    last = obs[-1].received_at.astimezone(timezone.utc) if obs else None
    span = (last - first).total_seconds() if first and last else None
    return BehavioralEvidence(
        observation_count=raw_count,
        valid_position_count=len(obs),
        sog_present_count=sog_n,
        cog_present_count=cog_n,
        time_span_seconds=span,
        first_received_at=first,
        last_received_at=last,
    )


def classify_behavior(
    speed: SpeedFeatures,
    course: CourseFeatures,
    movement: MovementFeatures,
    valid_positions: int,
) -> tuple[Classification, tuple[str, ...]]:
    """Explicit deterministic classification.

    Priority (first match wins after insufficiency check):
      1. INSUFFICIENT_DATA  — fewer than 2 valid positions
      2. IRREGULAR          — ≥2 inconsistent signals
      3. MANEUVERING        — significant course dynamics + speed variation
      4. STOPPED            — low average SOG and mostly stopped time
      5. SLOW_MOVEMENT      — average SOG in (STOPPED, SLOW]
      6. UNDERWAY           — average SOG > SLOW
      7. INSUFFICIENT_DATA  — no usable SOG to decide
    """
    if valid_positions < 2:
        return "INSUFFICIENT_DATA", ("fewer than 2 valid positions",)

    reasons: list[str] = []

    irregular_hits = 0
    if speed.sog_std is not None and speed.sog_std >= IRREGULAR_SOG_STD_KNOTS:
        irregular_hits += 1
        reasons.append(f"high SOG std ({speed.sog_std:.2f} kn)")
    if (
        course.heading_cog_consistency is not None
        and course.heading_cog_consistency <= IRREGULAR_COURSE_CONSISTENCY_MAX
    ):
        irregular_hits += 1
        reasons.append(f"low heading/COG consistency ({course.heading_cog_consistency:.2f})")
    if (
        course.heading_cog_consistency is None
        and course.total_course_change is not None
        and course.total_course_change >= MANEUVER_TOTAL_COURSE_CHANGE_DEG * 2
        and movement.trajectory_efficiency is not None
        and movement.trajectory_efficiency <= IRREGULAR_EFFICIENCY_MAX
    ):
        irregular_hits += 1
        reasons.append("repeated course changes with low trajectory efficiency")
    if (
        movement.trajectory_efficiency is not None
        and movement.trajectory_efficiency <= IRREGULAR_EFFICIENCY_MAX
        and speed.sog_std is not None
        and speed.sog_std >= MANEUVER_SOG_STD_KNOTS
    ):
        irregular_hits += 1
        reasons.append(f"low efficiency ({movement.trajectory_efficiency:.2f})")

    if irregular_hits >= IRREGULAR_MIN_SIGNALS:
        return "IRREGULAR", tuple(reasons)

    maneuver_course = (
        course.total_course_change is not None
        and course.total_course_change >= MANEUVER_TOTAL_COURSE_CHANGE_DEG
    ) or (
        course.course_change_rate is not None
        and course.course_change_rate >= MANEUVER_COURSE_RATE_DEG_PER_MIN
    )
    maneuver_speed = (
        speed.sog_std is not None and speed.sog_std >= MANEUVER_SOG_STD_KNOTS
    ) or (
        speed.speed_variation is not None and speed.speed_variation >= MANEUVER_SOG_STD_KNOTS
    )
    if maneuver_course and maneuver_speed:
        m_reasons = []
        if course.total_course_change is not None:
            m_reasons.append(f"total course change {course.total_course_change:.1f}°")
        if course.course_change_rate is not None:
            m_reasons.append(f"course rate {course.course_change_rate:.1f}°/min")
        if speed.sog_std is not None:
            m_reasons.append(f"SOG std {speed.sog_std:.2f} kn")
        return "MANEUVERING", tuple(m_reasons)

    avg = speed.average_sog
    if avg is None:
        ratio = movement.movement_stopped_ratio
        if ratio is not None and ratio < 0.15:
            return "STOPPED", ("derived from movement/stopped ratio; SOG absent",)
        if ratio is not None and ratio < 0.5:
            return "SLOW_MOVEMENT", ("derived from movement ratio; SOG absent",)
        if ratio is not None:
            return "UNDERWAY", ("derived from movement ratio; SOG absent",)
        return "INSUFFICIENT_DATA", ("no usable SOG and no movement ratio",)

    if avg <= STOPPED_SOG_KNOTS:
        return "STOPPED", (f"average SOG {avg:.2f} kn ≤ {STOPPED_SOG_KNOTS}",)
    if avg <= SLOW_SOG_KNOTS:
        return "SLOW_MOVEMENT", (f"average SOG {avg:.2f} kn ≤ {SLOW_SOG_KNOTS}",)
    return "UNDERWAY", (f"average SOG {avg:.2f} kn > {SLOW_SOG_KNOTS}",)


def compute_confidence(
    evidence: BehavioralEvidence,
    classification: Classification,
) -> ConfidenceLevel:
    """Deterministic confidence from observation quantity, duration, and field coverage.

    N/A     — zero observations or INSUFFICIENT_DATA with <2 positions
    LOW     — sparse track or poor SOG/COG coverage
    MEDIUM  — modest track with partial coverage
    HIGH    — dense track, sustained duration, good SOG and COG coverage
    """
    n = evidence.valid_position_count
    if n == 0:
        return "N/A"
    if classification == "INSUFFICIENT_DATA" or n < 2:
        return "LOW"

    span = evidence.time_span_seconds or 0.0
    sog_ratio = evidence.sog_present_count / n if n else 0.0
    cog_ratio = evidence.cog_present_count / n if n else 0.0

    if (
        n >= CONF_HIGH_MIN_OBS
        and span >= CONF_HIGH_MIN_DURATION_S
        and sog_ratio >= CONF_HIGH_MIN_SOG_RATIO
        and cog_ratio >= CONF_HIGH_MIN_COG_RATIO
    ):
        return "HIGH"

    if (
        n >= CONF_MEDIUM_MIN_OBS
        and span >= CONF_MEDIUM_MIN_DURATION_S
        and sog_ratio >= CONF_MEDIUM_MIN_SOG_RATIO
    ):
        return "MEDIUM"

    return "LOW"


def build_behavioral_profile(
    mmsi: str,
    observations: Iterable[AISObservation],
) -> BehavioralProfile:
    """Build a full BehavioralProfile from raw AIS observations for one MMSI."""
    raw = list(observations)
    cleaned = _clean_observations(raw)
    evidence = _build_evidence(len(raw), cleaned)

    if len(cleaned) < 2:
        return _insufficient(
            mmsi,
            evidence,
            "fewer than 2 valid positions after temporal/coordinate cleaning",
        )

    speed = extract_speed_features(cleaned)
    course = extract_course_features(cleaned)
    movement = extract_movement_features(cleaned)
    classification, reasons = classify_behavior(speed, course, movement, len(cleaned))
    confidence = compute_confidence(evidence, classification)

    return BehavioralProfile(
        mmsi=mmsi,
        classification=classification,
        confidence=confidence,
        speed=speed,
        course=course,
        movement=movement,
        evidence=evidence,
        provenance=PROVENANCE,
        reasons=reasons,
    )


def profile_from_engine_track(
    mmsi: str,
    engine: Any,
) -> BehavioralProfile:
    """Adapter: load session track from engine.store.tracks() when available."""
    tracks: dict[str, list[AISObservation]] = {}
    store = getattr(engine, "store", None)
    if store is not None and hasattr(store, "tracks"):
        try:
            tracks = store.tracks() or {}
        except Exception:
            tracks = {}
    obs = tracks.get(mmsi, [])
    return build_behavioral_profile(mmsi, obs)
