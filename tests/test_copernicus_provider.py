import os

import pytest

from src.environment.copernicus_marine import CopernicusMarineProvider


def test_copernicus_provider_is_fail_closed_by_default(monkeypatch) -> None:
    monkeypatch.delenv("MIE_COPERNICUS_MARINE_ENABLED", raising=False)
    assert CopernicusMarineProvider().enabled is False


def test_copernicus_provider_requires_explicit_enable(monkeypatch) -> None:
    monkeypatch.setenv("MIE_COPERNICUS_MARINE_ENABLED", "true")
    assert CopernicusMarineProvider().enabled is True


def test_disabled_provider_does_not_call_remote_service(monkeypatch) -> None:
    monkeypatch.delenv("MIE_COPERNICUS_MARINE_ENABLED", raising=False)
    with pytest.raises(RuntimeError, match="disabled"):
        CopernicusMarineProvider().current(25.7, -80.0, "miami")
