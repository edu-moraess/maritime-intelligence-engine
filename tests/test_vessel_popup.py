"""Focused tests for Vessel Intelligence popup helpers."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from src.ui.vessel_popup import _heading_delta, _safe_float, _signal_age, render_vessel_quick_intelligence


def test_safe_float_handles_valid_and_invalid_values():
    assert _safe_float("12.5") == 12.5
    assert _safe_float(None) is None
    assert _safe_float("not-a-number") is None


def test_heading_delta_uses_shortest_circular_distance():
    assert _heading_delta([350, 10]) == 20
    assert _heading_delta([10, 40, 100]) == 60
    assert _heading_delta([90]) is None


def test_signal_age_is_non_negative_and_timezone_aware():
    recent = datetime.now(timezone.utc) - timedelta(seconds=5)
    age = _signal_age(recent)
    assert age is not None
    assert age >= 0
    assert age < 10
    assert _signal_age(None) is None


def test_render_none_vessel_does_not_crash():
    snapshot = SimpleNamespace(observations=[], findings=[], embeddings=None)
    render_vessel_quick_intelligence(None, snapshot)


def test_render_vessel_with_insufficient_observations_does_not_require_external_enrichment():
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
    observation = SimpleNamespace(
        mmsi="235102528",
        sog_knots=0.1,
        heading_degrees=259.0,
        received_at=datetime.now(timezone.utc),
    )
    snapshot = SimpleNamespace(observations=[observation], findings=[], embeddings=None)
    render_vessel_quick_intelligence(vessel, snapshot, show_gemini_hook=False)
