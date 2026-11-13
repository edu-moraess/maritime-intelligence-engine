"""Regression tests for on-demand vessel history rendering."""

from contextlib import nullcontext
from types import SimpleNamespace

import src.ui.gemini_panel as gemini_panel


def test_gemini_panel_does_not_query_history_until_requested(monkeypatch):
    monkeypatch.setattr(gemini_panel.st, "expander", lambda *a, **k: nullcontext())
    monkeypatch.setattr(gemini_panel.st, "caption", lambda *a, **k: None)
    monkeypatch.setattr(gemini_panel.st, "button", lambda *a, **k: False)

    def unexpected_history_lookup(*args, **kwargs):
        raise AssertionError("historical DB lookup must be opt-in")

    monkeypatch.setattr(
        gemini_panel,
        "load_vessel_observations",
        unexpected_history_lookup,
    )

    engine = SimpleNamespace(
        settings=SimpleNamespace(
            database_url="postgresql://configured",
            historical_persistence_enabled=True,
        )
    )
    vessel = SimpleNamespace(mmsi="538010091")

    gemini_panel._render_historical_profile(engine, vessel)
