from datetime import datetime, timedelta, timezone

from src.analytics.regional_events import detect_regional_events
from src.ingestion.models import AISObservation


BBOXES = [((0.0, 0.0), (10.0, 10.0)), ((20.0, 20.0), (30.0, 30.0))]
BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _obs(mmsi, seconds, lat, lon):
    return AISObservation(mmsi=mmsi, latitude=lat, longitude=lon, received_at=BASE + timedelta(seconds=seconds), sog_knots=5.0)


def test_entry_and_dwell_require_observed_entry_state():
    tracks = {"111000001": [_obs("111000001", 0, 5, 5), _obs("111000001", 300, 5, 5)]}
    events = detect_regional_events(tracks, BBOXES, dwell_seconds=300)
    assert [event.event_type for event in events] == ["ENTRY", "DWELL"]
    assert events[1].duration_seconds == 300


def test_exit_is_emitted_only_when_next_observation_is_outside():
    tracks = {"111000001": [_obs("111000001", 0, 5, 5), _obs("111000001", 60, 15, 15)]}
    events = detect_regional_events(tracks, BBOXES, dwell_seconds=300)
    assert [event.event_type for event in events] == ["ENTRY", "EXIT"]
    assert events[1].region_index == 0


def test_direct_a_to_b_transition_emits_exit_and_transition():
    tracks = {"111000001": [_obs("111000001", 0, 5, 5), _obs("111000001", 120, 25, 25)]}
    events = detect_regional_events(tracks, BBOXES, dwell_seconds=300)
    assert [event.event_type for event in events] == ["ENTRY", "EXIT", "TRANSITION_A_TO_B"]
    assert events[2].region_index == 1
    assert events[2].previous_region_index == 0


def test_overlap_does_not_create_region_transition():
    overlapping = [((0.0, 0.0), (10.0, 10.0)), ((5.0, 5.0), (15.0, 15.0))]
    tracks = {"111000001": [_obs("111000001", 0, 2, 2), _obs("111000001", 60, 7, 7), _obs("111000001", 120, 12, 12)]}
    events = detect_regional_events(tracks, overlapping, dwell_seconds=300)
    assert [event.event_type for event in events] == ["ENTRY", "EXIT", "ENTRY"]
    assert events[-1].region_index == 1


def test_session_end_does_not_fake_exit():
    tracks = {"111000001": [_obs("111000001", 0, 5, 5)]}
    events = detect_regional_events(tracks, BBOXES)
    assert [event.event_type for event in events] == ["ENTRY"]