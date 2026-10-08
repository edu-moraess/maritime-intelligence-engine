from datetime import datetime, timedelta, timezone

from src.analytics.regional_events import detect_regional_events
from src.environment.context import EnvironmentalContext
from src.ingestion.models import AISObservation, AnomalyFinding, EnvironmentalObservation


BBOXES = [((0.0, 0.0), (10.0, 10.0)), ((20.0, 20.0), (30.0, 30.0))]
BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _obs(mmsi, seconds, lat, lon, sog=5.0):
    return AISObservation(
        mmsi=mmsi,
        latitude=lat,
        longitude=lon,
        received_at=BASE + timedelta(seconds=seconds),
        sog_knots=sog,
        cog_degrees=90.0,
        heading_degrees=90.0,
    )


def test_entry_and_dwell_require_observed_entry_state():
    tracks = {
        "111000001": [
            _obs("111000001", 0, 5, 5),
            _obs("111000001", 300, 5, 5),
        ]
    }
    events = detect_regional_events(tracks, BBOXES, dwell_seconds=300)
    assert [event.event_type for event in events] == [
        "VESSEL_ENTERED_REGION",
        "VESSEL_DWELL",
    ]
    assert events[1].duration_seconds == 300


def test_exit_is_emitted_only_when_next_observation_is_outside():
    tracks = {
        "111000001": [
            _obs("111000001", 0, 5, 5),
            _obs("111000001", 60, 15, 15),
        ]
    }
    events = detect_regional_events(tracks, BBOXES, dwell_seconds=300)
    assert [event.event_type for event in events] == [
        "VESSEL_ENTERED_REGION",
        "VESSEL_LEFT_REGION",
    ]
    assert events[1].region_index == 0


def test_direct_a_to_b_transition_emits_exit_and_transition():
    tracks = {
        "111000001": [
            _obs("111000001", 0, 5, 5),
            _obs("111000001", 120, 25, 25),
        ]
    }
    events = detect_regional_events(tracks, BBOXES, dwell_seconds=300)
    assert [event.event_type for event in events] == [
        "VESSEL_ENTERED_REGION",
        "VESSEL_LEFT_REGION",
        "VESSEL_TRANSITION_A_TO_B",
    ]
    assert events[2].region_index == 1
    assert events[2].previous_region_index == 0


def test_overlap_does_not_create_region_transition():
    overlapping = [
        ((0.0, 0.0), (10.0, 10.0)),
        ((5.0, 5.0), (15.0, 15.0)),
    ]
    tracks = {
        "111000001": [
            _obs("111000001", 0, 2, 2),
            _obs("111000001", 60, 7, 7),
            _obs("111000001", 120, 12, 12),
        ]
    }
    events = detect_regional_events(tracks, overlapping, dwell_seconds=300)
    assert [event.event_type for event in events] == [
        "VESSEL_ENTERED_REGION",
        "VESSEL_LEFT_REGION",
        "VESSEL_ENTERED_REGION",
    ]
    assert events[-1].region_index == 1


def test_session_end_does_not_fake_exit():
    tracks = {"111000001": [_obs("111000001", 0, 5, 5)]}
    events = detect_regional_events(tracks, BBOXES)
    assert [event.event_type for event in events] == ["VESSEL_ENTERED_REGION"]


def test_anomaly_becomes_regional_intelligence_event():
    tracks = {"111000001": [_obs("111000001", 0, 5, 5)]}
    finding = AnomalyFinding(
        mmsi="111000001",
        received_at=BASE + timedelta(seconds=30),
        latitude=5.0,
        longitude=5.0,
        score=0.91,
        category="speed anomaly",
        confidence=0.88,
        explanation="test finding",
    )
    events = detect_regional_events(tracks, BBOXES, findings=[finding])
    anomaly = [event for event in events if event.event_type == "ANOMALY_DETECTED"]
    assert len(anomaly) == 1
    assert anomaly[0].region_index == 0
    assert anomaly[0].mmsi == "111000001"


def test_environment_context_available_event_uses_real_observation():
    observation = EnvironmentalObservation(
        source="TEST_SOURCE",
        observed_at=BASE,
        latitude=5.0,
        longitude=5.0,
        region="region_1",
        wave_height_m=1.2,
    )
    contexts = {
        "region_1": EnvironmentalContext(
            region="region_1",
            observations=(observation,),
        )
    }
    events = detect_regional_events(
        {},
        BBOXES,
        environmental_contexts=contexts,
    )
    available = [
        event
        for event in events
        if event.event_type == "ENVIRONMENT_CONTEXT_AVAILABLE"
    ]
    assert len(available) == 1
    assert available[0].region_index == 0
    assert available[0].mmsi is None


def test_environment_update_requires_multiple_real_observations():
    first = EnvironmentalObservation(
        source="TEST_SOURCE",
        observed_at=BASE,
        latitude=5.0,
        longitude=5.0,
        region="region_1",
        wave_height_m=1.0,
    )
    second = EnvironmentalObservation(
        source="TEST_SOURCE",
        observed_at=BASE + timedelta(minutes=10),
        latitude=5.0,
        longitude=5.0,
        region="region_1",
        wave_height_m=1.5,
    )
    contexts = {
        "region_1": EnvironmentalContext(
            region="region_1",
            observations=(first, second),
        )
    }
    events = detect_regional_events(
        {},
        BBOXES,
        environmental_contexts=contexts,
    )
    updated = [
        event for event in events if event.event_type == "ENVIRONMENT_UPDATED"
    ]
    assert len(updated) == 1
    assert updated[0].timestamp == second.observed_at


def test_behavior_change_requires_two_non_insufficient_states():
    observations = [
        _obs("111000001", 0, 5, 5, sog=2.0),
        _obs("111000001", 60, 5.01, 5.01, sog=2.0),
        _obs("111000001", 120, 5.02, 5.02, sog=12.0),
        _obs("111000001", 180, 5.03, 5.03, sog=12.0),
    ]
    events = detect_regional_events(
        {"111000001": observations},
        BBOXES,
    )
    behavior = [
        event for event in events if event.event_type == "BEHAVIOR_CHANGED"
    ]
    assert behavior
    assert behavior[-1].mmsi == "111000001"
    assert "→" in (behavior[-1].detail or "")
