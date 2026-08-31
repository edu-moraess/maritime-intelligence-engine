from datetime import datetime, timedelta, timezone

from src.historical.profile import build_vessel_profile
from src.ingestion.models import AISObservation


def _obs(
    mmsi: str,
    seconds: int,
    *,
    lat: float = 52.0,
    lon: float = 4.0,
    sog: float | None = 10.0,
    session_id: str | None = None,
) -> AISObservation:
    return AISObservation(
        mmsi=mmsi,
        latitude=lat,
        longitude=lon,
        received_at=datetime(2026, 8, 31, 20, 0, seconds, tzinfo=timezone.utc),
        sog_knots=sog,
        raw={"session_id": session_id} if session_id else {},
    )


def test_profile_empty_history_is_na():
    profile = build_vessel_profile("219234000", [])

    assert profile.status == "N/A"
    assert profile.observation_count == 0
    assert profile.session_count == 0
    assert profile.distance_km is None


def test_profile_single_point_is_partial():
    profile = build_vessel_profile(
        "219234000",
        [_obs("219234000", 1, session_id="session-a")],
    )

    assert profile.status == "PARTIAL"
    assert profile.observation_count == 1
    assert profile.session_count == 1
    assert profile.distance_km is None


def test_profile_aggregates_multi_session_history():
    observations = [
        _obs("219234000", 1, lon=4.0, sog=8.0, session_id="session-a"),
        _obs("219234000", 2, lon=4.01, sog=10.0, session_id="session-a"),
        _obs("219234000", 3, lon=4.02, sog=None, session_id="session-b"),
    ]

    profile = build_vessel_profile("219234000", observations)

    assert profile.status == "READY"
    assert profile.observation_count == 3
    assert profile.session_count == 2
    assert profile.track_points == 3
    assert profile.first_seen_at == observations[0].received_at
    assert profile.last_seen_at == observations[-1].received_at
    assert profile.distance_km is not None and profile.distance_km > 0
    assert profile.average_sog_knots == 9.0
    assert profile.max_sog_knots == 10.0


def test_profile_explicit_session_count_is_deterministic():
    observations = [
        _obs("219234000", 1, session_id="session-a"),
        _obs("219234000", 2, session_id="session-b"),
    ]

    profile = build_vessel_profile(
        "219234000",
        observations,
        session_count=5,
    )

    assert profile.session_count == 5
