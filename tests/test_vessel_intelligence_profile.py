"""Unit tests for Vessel Intelligence Profile v1 (deterministic, no ML/LLM)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from src.ingestion.models import AISObservation, AnomalyFinding
from src.intelligence.profile import (
    STALE_SIGNAL_SECONDS,
    build_vessel_intelligence_profile,
    evaluate_confidence,
)


def _t(seconds: int = 0) -> datetime:
    return datetime(2026, 8, 31, 20, 0, 0, tzinfo=timezone.utc) + timedelta(seconds=seconds)


def _obs(
    mmsi: str,
    seconds: int,
    *,
    lat: float = 25.7,
    lon: float = -80.1,
    sog: float | None = 10.0,
    cog: float | None = 90.0,
    hdg: float | None = 95.0,
    name: str | None = "TEST SHIP",
    nav: int | None = 0,
    raw: dict | None = None,
) -> AISObservation:
    return AISObservation(
        mmsi=mmsi,
        latitude=lat,
        longitude=lon,
        received_at=_t(seconds),
        sog_knots=sog,
        cog_degrees=cog,
        heading_degrees=hdg,
        vessel_name=name,
        navigational_status=nav,
        raw=raw or {},
    )


@dataclass(frozen=True)
class _FakeHistorical:
    mmsi: str
    observation_count: int
    session_count: int
    first_seen_at: datetime | None
    last_seen_at: datetime | None
    distance_km: float | None
    average_sog_knots: float | None
    max_sog_knots: float | None
    track_points: int
    status: str


MMSI = "219234000"
REF = _t(1000)


def test_zero_observations_yields_na_blocks():
    profile = build_vessel_intelligence_profile(MMSI, [], reference_time=REF)

    assert profile.session_observation_count == 0
    assert profile.telemetry.available is False
    assert profile.movement.status == "INSUFFICIENT_DATA"
    assert profile.historical.status == "N/A"
    assert profile.historical.available is False
    assert profile.confidence.level == "N/A"
    assert profile.identity.mmsi == MMSI
    assert profile.identity.imo is None
    assert profile.identity.callsign is None


def test_single_observation_is_low_and_insufficient_movement():
    obs = _obs(MMSI, 900, sog=12.0)
    profile = build_vessel_intelligence_profile(
        MMSI, [obs], reference_time=REF, stale_after_seconds=STALE_SIGNAL_SECONDS
    )

    assert profile.session_observation_count == 1
    assert profile.telemetry.available is True
    assert profile.telemetry.sog_knots == 12.0
    assert profile.telemetry.provenance == "LIVE"
    assert profile.movement.status == "INSUFFICIENT_DATA"
    assert profile.movement.distance_km is None
    assert profile.confidence.level == "LOW"


def test_two_observations_compute_movement_without_fabricating():
    observations = [
        _obs(MMSI, 800, lon=-80.10, sog=8.0, hdg=90.0),
        _obs(MMSI, 900, lon=-80.09, sog=12.0, hdg=100.0),
    ]
    profile = build_vessel_intelligence_profile(MMSI, observations, reference_time=REF)

    assert profile.session_observation_count == 2
    assert profile.movement.status == "READY"
    assert profile.movement.distance_km is not None and profile.movement.distance_km > 0
    assert profile.movement.average_sog_knots == 10.0
    assert profile.movement.max_sog_knots == 12.0
    assert profile.movement.heading_change_degrees == 10.0
    assert profile.movement.speed_change_knots == 4.0
    assert profile.movement.provenance == "DERIVED"
    assert profile.confidence.level == "MEDIUM"


def test_multiple_observations_with_history_can_be_high():
    observations = [
        _obs(MMSI, 700, lon=-80.12, sog=7.0),
        _obs(MMSI, 800, lon=-80.11, sog=9.0),
        _obs(MMSI, 900, lon=-80.10, sog=11.0),
    ]
    historical = _FakeHistorical(
        mmsi=MMSI,
        observation_count=5,
        session_count=2,
        first_seen_at=_t(0),
        last_seen_at=_t(500),
        distance_km=12.5,
        average_sog_knots=9.5,
        max_sog_knots=14.0,
        track_points=5,
        status="READY",
    )
    profile = build_vessel_intelligence_profile(
        MMSI,
        observations,
        historical_profile=historical,
        reference_time=REF,
    )

    assert profile.historical.available is True
    assert profile.historical.provenance == "HISTORICAL"
    assert profile.historical.observation_count == 5
    assert profile.historical.session_count == 2
    assert profile.confidence.level == "HIGH"


def test_missing_sog_does_not_invent_speeds():
    observations = [
        _obs(MMSI, 800, sog=None, hdg=None, cog=None),
        _obs(MMSI, 900, sog=None, hdg=None, cog=None, lon=-80.09),
    ]
    profile = build_vessel_intelligence_profile(MMSI, observations, reference_time=REF)

    assert profile.telemetry.sog_knots is None
    assert profile.telemetry.cog_degrees is None
    assert profile.telemetry.heading_degrees is None
    assert profile.movement.status == "READY"
    assert profile.movement.average_sog_knots is None
    assert profile.movement.max_sog_knots is None
    assert profile.movement.heading_change_degrees is None
    assert profile.movement.speed_change_knots is None
    assert profile.movement.distance_km is not None


def test_stale_signal_forces_low_confidence():
    obs = [
        _obs(MMSI, 0, sog=5.0),
        _obs(MMSI, 10, sog=6.0, lon=-80.09),
    ]
    profile = build_vessel_intelligence_profile(
        MMSI,
        obs,
        reference_time=REF,
        stale_after_seconds=STALE_SIGNAL_SECONDS,
    )
    assert profile.telemetry.signal_age_seconds is not None
    assert profile.telemetry.signal_age_seconds > STALE_SIGNAL_SECONDS
    assert profile.confidence.level == "LOW"


def test_historical_unavailable_is_explicit_na():
    profile = build_vessel_intelligence_profile(
        MMSI,
        [_obs(MMSI, 900)],
        historical_profile=None,
        reference_time=REF,
    )
    assert profile.historical.status == "N/A"
    assert profile.historical.available is False
    assert profile.historical.distance_km is None


def test_historical_available_exposed_without_mixing_into_live():
    historical = _FakeHistorical(
        mmsi=MMSI,
        observation_count=3,
        session_count=1,
        first_seen_at=_t(0),
        last_seen_at=_t(100),
        distance_km=4.2,
        average_sog_knots=8.0,
        max_sog_knots=12.0,
        track_points=3,
        status="READY",
    )
    profile = build_vessel_intelligence_profile(
        MMSI,
        [_obs(MMSI, 900, sog=15.0)],
        historical_profile=historical,
        reference_time=REF,
    )
    assert profile.telemetry.sog_knots == 15.0
    assert profile.telemetry.provenance == "LIVE"
    assert profile.historical.average_sog_knots == 8.0
    assert profile.historical.provenance == "HISTORICAL"


def test_anomalies_current_vs_historical_never_mixed():
    current = AnomalyFinding(
        mmsi=MMSI,
        received_at=_t(900),
        latitude=25.7,
        longitude=-80.1,
        score=0.9,
        category="speed anomaly",
        confidence=0.9,
        explanation="session speed",
    )
    historical = AnomalyFinding(
        mmsi=MMSI,
        received_at=_t(10),
        latitude=25.6,
        longitude=-80.2,
        score=0.8,
        category="signal gap",
        confidence=0.8,
        explanation="historical gap",
    )
    other = AnomalyFinding(
        mmsi="111111111",
        received_at=_t(900),
        latitude=1.0,
        longitude=1.0,
        score=0.99,
        category="speed anomaly",
        confidence=0.99,
        explanation="other vessel",
    )
    profile = build_vessel_intelligence_profile(
        MMSI,
        [_obs(MMSI, 900)],
        session_findings=[current, other],
        historical_findings=[historical],
        reference_time=REF,
    )
    assert len(profile.anomalies.current_session) == 1
    assert profile.anomalies.current_session[0].category == "speed anomaly"
    assert len(profile.anomalies.historical) == 1
    assert profile.anomalies.historical[0].category == "signal gap"


def test_identity_does_not_infer_missing_imo_callsign():
    profile = build_vessel_intelligence_profile(
        MMSI,
        [_obs(MMSI, 900, name="ALPHA")],
        reference_time=REF,
    )
    assert profile.identity.vessel_name == "ALPHA"
    assert profile.identity.imo is None
    assert profile.identity.callsign is None


def test_identity_reads_imo_callsign_from_raw_when_present():
    profile = build_vessel_intelligence_profile(
        MMSI,
        [_obs(MMSI, 900, raw={"imo": "9123456", "callsign": "ABCD"})],
        reference_time=REF,
    )
    assert profile.identity.imo == "9123456"
    assert profile.identity.callsign == "ABCD"


def test_evaluate_confidence_matrix():
    assert evaluate_confidence(
        session_observation_count=0,
        signal_age_seconds=None,
        historical_available=False,
        historical_observation_count=0,
    ).level == "N/A"

    assert evaluate_confidence(
        session_observation_count=1,
        signal_age_seconds=10.0,
        historical_available=True,
        historical_observation_count=10,
    ).level == "LOW"

    assert evaluate_confidence(
        session_observation_count=2,
        signal_age_seconds=10.0,
        historical_available=False,
        historical_observation_count=0,
    ).level == "MEDIUM"

    assert evaluate_confidence(
        session_observation_count=3,
        signal_age_seconds=10.0,
        historical_available=True,
        historical_observation_count=2,
    ).level == "HIGH"

    assert evaluate_confidence(
        session_observation_count=5,
        signal_age_seconds=500.0,
        historical_available=True,
        historical_observation_count=10,
        stale_after_seconds=180.0,
    ).level == "LOW"


def test_invalid_observations_excluded_from_session_track():
    valid = _obs(MMSI, 900)
    invalid = AISObservation(
        mmsi=MMSI,
        latitude=25.7,
        longitude=-80.1,
        received_at=_t(910),
        valid=False,
    )
    profile = build_vessel_intelligence_profile(
        MMSI, [valid, invalid], reference_time=REF
    )
    assert profile.session_observation_count == 1
