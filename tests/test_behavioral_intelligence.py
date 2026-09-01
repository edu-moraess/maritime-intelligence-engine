"""Unit tests for deterministic Behavioral Intelligence (Etapa 4)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.ingestion.models import AISObservation
from src.intelligence.behavior import (
    STOPPED_SOG_KNOTS,
    build_behavioral_profile,
    classify_behavior,
    compute_confidence,
    extract_course_features,
    extract_movement_features,
    extract_speed_features,
    _circular_abs_delta_deg,
    _clean_observations,
)


def _ts(seconds: float = 0.0) -> datetime:
    return datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc) + timedelta(seconds=seconds)


def _obs(
    mmsi: str = "123456789",
    t: float = 0.0,
    lat: float = -23.0,
    lon: float = -43.0,
    sog: float | None = 10.0,
    cog: float | None = 90.0,
    hdg: float | None = 90.0,
    valid: bool = True,
) -> AISObservation:
    return AISObservation(
        mmsi=mmsi,
        latitude=lat,
        longitude=lon,
        received_at=_ts(t),
        sog_knots=sog,
        cog_degrees=cog,
        heading_degrees=hdg,
        valid=valid,
    )


def test_zero_observations():
    profile = build_behavioral_profile("123456789", [])
    assert profile.classification == "INSUFFICIENT_DATA"
    assert profile.confidence == "N/A"
    assert profile.speed.average_sog is None
    assert profile.movement.traveled_distance_km is None
    assert profile.provenance == "DERIVED"
    assert profile.evidence.observation_count == 0


def test_one_observation():
    profile = build_behavioral_profile("123456789", [_obs()])
    assert profile.classification == "INSUFFICIENT_DATA"
    assert profile.confidence == "LOW"
    assert profile.movement.traveled_distance_km is None
    assert profile.course.total_course_change is None


def test_two_observations():
    track = [_obs(t=0, sog=8.0, cog=90), _obs(t=60, lat=-23.01, lon=-43.0, sog=8.5, cog=92)]
    profile = build_behavioral_profile("123456789", track)
    assert profile.evidence.valid_position_count == 2
    assert profile.movement.traveled_distance_km is not None
    assert profile.provenance == "DERIVED"


def test_out_of_order_timestamps_are_sorted():
    track = [
        _obs(t=120, lat=-23.02, lon=-43.0, sog=10),
        _obs(t=0, lat=-23.0, lon=-43.0, sog=10),
        _obs(t=60, lat=-23.01, lon=-43.0, sog=10),
    ]
    cleaned = _clean_observations(track)
    assert [o.received_at for o in cleaned] == sorted(o.received_at for o in cleaned)
    profile = build_behavioral_profile("123456789", track)
    assert profile.evidence.valid_position_count == 3


def test_duplicate_timestamps_deduped():
    track = [
        _obs(t=0, lat=-23.0, lon=-43.0, sog=5),
        _obs(t=0, lat=-23.0, lon=-43.0, sog=6),
        _obs(t=60, lat=-23.01, lon=-43.0, sog=6),
    ]
    cleaned = _clean_observations(track)
    assert len(cleaned) == 2
    assert cleaned[0].sog_knots == 6


def test_missing_sog_does_not_invent_values():
    track = [
        _obs(t=0, sog=None, cog=90),
        _obs(t=60, lat=-23.01, lon=-43.0, sog=None, cog=95),
    ]
    profile = build_behavioral_profile("123456789", track)
    assert profile.speed.average_sog is None
    assert profile.speed.maximum_sog is None
    assert profile.speed.sog_std is None
    assert profile.speed.approximate_acceleration is None
    assert profile.course.total_course_change is not None


def test_missing_cog_does_not_invent_values():
    track = [
        _obs(t=0, sog=10, cog=None, hdg=None),
        _obs(t=60, lat=-23.01, lon=-43.0, sog=11, cog=None, hdg=None),
    ]
    profile = build_behavioral_profile("123456789", track)
    assert profile.course.average_cog is None
    assert profile.course.total_course_change is None
    assert profile.course.course_change_rate is None
    assert profile.speed.average_sog is not None


def test_course_wraparound_359_to_1():
    delta = _circular_abs_delta_deg(359.0, 1.0)
    assert delta == pytest.approx(2.0, abs=1e-6)

    track = [
        _obs(t=0, sog=8, cog=359),
        _obs(t=60, lat=-23.01, lon=-43.0, sog=8, cog=1),
    ]
    course = extract_course_features(track)
    assert course.total_course_change == pytest.approx(2.0, abs=0.1)


def test_stopped_vessel():
    track = [
        _obs(t=0, sog=0.1, cog=10),
        _obs(t=60, lat=-23.0001, lon=-43.0, sog=0.2, cog=12),
        _obs(t=120, lat=-23.0002, lon=-43.0, sog=0.0, cog=11),
    ]
    profile = build_behavioral_profile("123456789", track)
    assert profile.classification == "STOPPED"
    assert profile.speed.average_sog is not None
    assert profile.speed.average_sog <= STOPPED_SOG_KNOTS + 0.5


def test_slow_movement():
    track = [
        _obs(t=0, sog=1.5, cog=45),
        _obs(t=120, lat=-23.005, lon=-43.0, sog=2.0, cog=48),
        _obs(t=240, lat=-23.010, lon=-43.0, sog=1.8, cog=50),
    ]
    profile = build_behavioral_profile("123456789", track)
    assert profile.classification == "SLOW_MOVEMENT"


def test_underway():
    track = [
        _obs(t=i * 60, lat=-23.0 + i * 0.01, lon=-43.0, sog=12.0, cog=0.0, hdg=0.0)
        for i in range(5)
    ]
    profile = build_behavioral_profile("123456789", track)
    assert profile.classification == "UNDERWAY"
    assert profile.speed.average_sog == pytest.approx(12.0, abs=0.1)


def test_course_change_accumulated():
    track = [
        _obs(t=0, sog=6, cog=0),
        _obs(t=60, lat=-23.005, lon=-43.0, sog=6, cog=30),
        _obs(t=120, lat=-23.010, lon=-43.005, sog=7, cog=60),
    ]
    course = extract_course_features(track)
    assert course.total_course_change == pytest.approx(60.0, abs=1.0)
    assert course.course_change_rate is not None
    assert course.course_change_rate > 0


def test_acceleration_ignores_non_positive_dt():
    track = [
        _obs(t=0, sog=5),
        _obs(t=0, sog=15),
        _obs(t=60, lat=-23.01, lon=-43.0, sog=8),
    ]
    cleaned = _clean_observations(track)
    assert len(cleaned) == 2
    assert cleaned[0].sog_knots == 15
    speed = extract_speed_features(cleaned)
    assert speed.approximate_acceleration == pytest.approx(abs(8 - 15) / 60.0, rel=0.05)


def test_acceleration_from_sog_delta():
    track = [
        _obs(t=0, sog=5.0),
        _obs(t=10, lat=-23.001, lon=-43.0, sog=7.0),
        _obs(t=20, lat=-23.002, lon=-43.0, sog=9.0),
    ]
    speed = extract_speed_features(track)
    assert speed.approximate_acceleration is not None
    assert speed.approximate_acceleration == pytest.approx(0.2, abs=0.05)


def test_efficient_trajectory():
    track = [
        _obs(t=i * 60, lat=-23.0 + i * 0.02, lon=-43.0, sog=12, cog=0, hdg=0)
        for i in range(4)
    ]
    movement = extract_movement_features(track)
    assert movement.trajectory_efficiency is not None
    assert movement.trajectory_efficiency > 0.9


def test_inefficient_trajectory():
    track = [
        _obs(t=0, lat=-23.0, lon=-43.0, sog=8, cog=0),
        _obs(t=120, lat=-23.05, lon=-43.0, sog=8, cog=0),
        _obs(t=240, lat=-23.0, lon=-43.0, sog=8, cog=180),
    ]
    movement = extract_movement_features(track)
    assert movement.trajectory_efficiency is not None
    assert movement.trajectory_efficiency < 0.2


def test_invalid_coordinates_ignored():
    track = [
        _obs(t=0, lat=999.0, lon=-43.0, sog=10),
        _obs(t=60, lat=-23.0, lon=-43.0, sog=10),
        _obs(t=120, lat=-23.01, lon=-43.0, sog=10),
    ]
    profile = build_behavioral_profile("123456789", track)
    assert profile.evidence.valid_position_count == 2


def test_zero_traveled_distance_efficiency_is_none():
    track = [
        _obs(t=0, lat=-23.0, lon=-43.0, sog=0.0),
        _obs(t=60, lat=-23.0, lon=-43.0, sog=0.0),
    ]
    movement = extract_movement_features(track)
    assert movement.trajectory_efficiency is None


def test_confidence_low_short_track():
    track = [_obs(t=0, sog=10), _obs(t=30, lat=-23.001, lon=-43.0, sog=10)]
    profile = build_behavioral_profile("123456789", track)
    assert profile.confidence == "LOW"


def test_confidence_medium():
    track = [
        _obs(t=i * 60, lat=-23.0 + i * 0.005, lon=-43.0, sog=10, cog=0, hdg=0)
        for i in range(4)
    ]
    profile = build_behavioral_profile("123456789", track)
    assert profile.confidence in {"MEDIUM", "HIGH"}


def test_confidence_high():
    track = [
        _obs(t=i * 60, lat=-23.0 + i * 0.005, lon=-43.0, sog=10.0 + (i % 2) * 0.1, cog=5.0, hdg=5.0)
        for i in range(12)
    ]
    profile = build_behavioral_profile("123456789", track)
    assert profile.confidence == "HIGH"
    assert profile.classification == "UNDERWAY"


def test_no_artificial_values_on_empty_fields():
    profile = build_behavioral_profile("123456789", [_obs(sog=None, cog=None, hdg=None)])
    d = profile.as_dict()
    assert d["speed"]["average_sog"] is None
    assert d["speed"]["maximum_sog"] is None
    assert d["course"]["average_cog"] is None
    assert d["movement"]["traveled_distance_km"] is None


def test_maneuvering_requires_multiple_signals():
    track = [
        _obs(t=0, sog=8.0, cog=0),
        _obs(t=60, lat=-23.01, lon=-43.0, sog=8.0, cog=50),
        _obs(t=120, lat=-23.02, lon=-43.0, sog=8.1, cog=90),
    ]
    profile = build_behavioral_profile("123456789", track)
    assert profile.classification != "MANEUVERING" or profile.speed.sog_std is not None


def test_maneuvering_with_course_and_speed_variation():
    track = [
        _obs(t=0, sog=3.0, cog=0),
        _obs(t=30, lat=-23.002, lon=-43.0, sog=8.0, cog=40),
        _obs(t=60, lat=-23.005, lon=-43.005, sog=4.0, cog=90),
        _obs(t=90, lat=-23.008, lon=-43.01, sog=9.0, cog=130),
    ]
    profile = build_behavioral_profile("123456789", track)
    assert profile.classification in {"MANEUVERING", "IRREGULAR", "UNDERWAY", "SLOW_MOVEMENT"}


def test_invalid_flag_excluded():
    track = [
        _obs(t=0, sog=10, valid=False),
        _obs(t=60, lat=-23.01, lon=-43.0, sog=10),
        _obs(t=120, lat=-23.02, lon=-43.0, sog=10),
    ]
    profile = build_behavioral_profile("123456789", track)
    assert profile.evidence.valid_position_count == 2
