from datetime import datetime, timezone

from src.ingestion.models import AISObservation
from src.processing.relevance import select_interesting_tracks, track_is_interesting


def _obs(mmsi: str, lat: float, lon: float, *, seconds: int, speed: float | None) -> AISObservation:
    return AISObservation(
        mmsi=mmsi,
        latitude=lat,
        longitude=lon,
        received_at=datetime(2026, 9, 25, 0, 0, seconds, tzinfo=timezone.utc),
        sog_knots=speed,
    )


def test_single_observation_is_not_model_relevant():
    track = [_obs("111111111", -23.0, -46.0, seconds=0, speed=10.0)]
    assert not track_is_interesting(track)


def test_one_speed_observation_is_not_enough_by_itself():
    track = [
        _obs("111111111", -23.0, -46.0, seconds=0, speed=0.0),
        _obs("111111111", -23.0, -46.0, seconds=10, speed=4.0),
    ]
    assert not track_is_interesting(track)


def test_stationary_repeated_track_is_not_model_relevant():
    track = [
        _obs("111111111", -23.0, -46.0, seconds=0, speed=0.0),
        _obs("111111111", -23.0, -46.0, seconds=10, speed=0.0),
    ]
    assert not track_is_interesting(track)


def test_sustained_speed_makes_track_model_relevant():
    track = [
        _obs("111111111", -23.0, -46.0, seconds=0, speed=3.0),
        _obs("111111111", -23.0, -46.0, seconds=10, speed=4.0),
    ]
    assert track_is_interesting(track)


def test_displacement_can_make_track_relevant_without_speed():
    track = [
        _obs("111111111", -23.0, -46.0, seconds=0, speed=None),
        _obs("111111111", -23.0025, -46.0, seconds=10, speed=None),
    ]
    assert track_is_interesting(track)


def test_selector_keeps_only_relevant_tracks():
    moving = [
        _obs("111111111", -23.0, -46.0, seconds=0, speed=3.0),
        _obs("111111111", -23.0, -46.0, seconds=10, speed=4.0),
    ]
    stationary = [
        _obs("222222222", -23.0, -46.0, seconds=0, speed=0.0),
        _obs("222222222", -23.0, -46.0, seconds=10, speed=0.0),
    ]
    selected = select_interesting_tracks({"111111111": moving, "222222222": stationary})
    assert set(selected) == {"111111111"}
