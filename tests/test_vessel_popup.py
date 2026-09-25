"""Focused tests for Vessel Intelligence UI helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from src.ingestion.models import AISObservation
from src.intelligence.profile import (
    _angular_delta,
    _signal_age_seconds,
    build_vessel_intelligence_profile,
)
from src.ui.vessel_popup import build_profile_for_ui, render_vessel_quick_intelligence


def test_angular_delta_uses_shortest_circular_distance():
    assert _angular_delta(350, 10) == 20
    assert _angular_delta(10, 40) == 30


def test_signal_age_is_non_negative_and_timezone_aware():
    now = datetime(2026, 8, 31, 20, 0, 0, tzinfo=timezone.utc)
    received = datetime(2026, 8, 31, 19, 59, 50, tzinfo=timezone.utc)
    age = _signal_age_seconds(received, reference_time=now)
    assert age == 10.0
    assert _signal_age_seconds(None) is None


def test_render_none_vessel_does_not_crash():
    snapshot = SimpleNamespace(observations=[], findings=[], embeddings=None)
    render_vessel_quick_intelligence(None, snapshot)


def test_build_profile_for_ui_does_not_fabricate_when_history_disabled():
    vessel = SimpleNamespace(
        mmsi="235102528",
        vessel_name="BF VOLUNTEER",
        sog_knots=0.1,
        cog_degrees=272.6,
        heading_degrees=259.0,
        latitude=51.32,
        longitude=1.42,
        navigational_status=None,
        last_received=datetime.now(timezone.utc),
    )
    observation = AISObservation(
        mmsi="235102528",
        latitude=51.32,
        longitude=1.42,
        received_at=datetime.now(timezone.utc),
        sog_knots=0.1,
        heading_degrees=259.0,
    )
    snapshot = SimpleNamespace(
        observations=[observation],
        findings=[],
        embeddings=None,
    )
    profile = build_profile_for_ui(vessel, snapshot, engine=None)
    assert profile.identity.mmsi == "235102528"
    assert profile.historical.status == "N/A"
    assert profile.movement.status == "INSUFFICIENT_DATA"
    assert profile.confidence.level == "LOW"


def test_render_vessel_with_insufficient_observations():
    vessel = SimpleNamespace(
        mmsi="235102528",
        vessel_name="BF VOLUNTEER",
        sog_knots=0.1,
        cog_degrees=272.6,
        heading_degrees=259.0,
        latitude=51.32,
        longitude=1.42,
        navigational_status=None,
        last_received=datetime.now(timezone.utc),
    )
    observation = AISObservation(
        mmsi="235102528",
        latitude=51.32,
        longitude=1.42,
        received_at=datetime.now(timezone.utc),
        sog_knots=0.1,
        heading_degrees=259.0,
    )
    snapshot = SimpleNamespace(
        observations=[observation],
        findings=[],
        embeddings=None,
    )
    render_vessel_quick_intelligence(vessel, snapshot, show_gemini_hook=False)


def test_build_profile_for_ui_keeps_restored_history_out_of_current_telemetry():
    mmsi = "235102528"
    vessel = SimpleNamespace(
        mmsi=mmsi,
        vessel_name="BF VOLUNTEER",
        sog_knots=0.1,
        cog_degrees=272.6,
        heading_degrees=259.0,
        latitude=51.32,
        longitude=1.42,
        navigational_status=None,
        last_received=datetime.now(timezone.utc),
    )
    restored_observation = AISObservation(
        mmsi=mmsi,
        latitude=51.30,
        longitude=1.40,
        received_at=datetime(2026, 8, 30, tzinfo=timezone.utc),
        sog_knots=9.0,
    )
    snapshot = SimpleNamespace(
        observations=[restored_observation],
        current_session_observations=[],
        findings=[],
        embeddings=None,
    )

    profile = build_profile_for_ui(vessel, snapshot, engine=None)

    assert profile.telemetry.available is False
    assert profile.telemetry.observation_count == 0
    assert profile.historical.status == "N/A"
