from datetime import timezone

from src.environment.open_meteo_marine import OpenMeteoMarineProvider


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None


def test_open_meteo_marine_provider_parses_current(monkeypatch) -> None:
    payload = {
        "latitude": 51.02,
        "longitude": 1.48,
        "current": {
            "time": "2026-09-25T02:00",
            "wave_height": 1.3,
            "wave_direction": 245.0,
            "wave_period": 6.2,
            "wind_wave_height": 0.7,
            "swell_wave_height": 0.9,
            "swell_wave_direction": 250.0,
            "ocean_current_velocity": 0.18,
            "ocean_current_direction": 80.0,
            "sea_surface_temperature": 16.5,
        },
    }

    def fake_urlopen(request, timeout):
        assert "marine-api.open-meteo.com" in request.full_url
        assert "current=" in request.full_url
        assert "cell_selection=sea" in request.full_url
        assert timeout == 10.0
        return FakeResponse(payload)

    monkeypatch.setattr(
        "src.environment.open_meteo_marine.urlopen",
        fake_urlopen,
    )

    observation = OpenMeteoMarineProvider().current(51.0, 1.5, region="B")

    assert observation.source == "open-meteo-marine"
    assert observation.region == "B"
    assert observation.observed_at.tzinfo == timezone.utc
    assert observation.latitude == 51.02
    assert observation.wave_height_m == 1.3
    assert observation.ocean_current_velocity == 0.18
    assert observation.sea_surface_temperature_c == 16.5


def test_open_meteo_marine_provider_rejects_missing_current(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        return FakeResponse({"latitude": 51.0, "longitude": 1.5})

    monkeypatch.setattr(
        "src.environment.open_meteo_marine.urlopen",
        fake_urlopen,
    )

    try:
        OpenMeteoMarineProvider().current(51.0, 1.5)
    except ValueError as exc:
        assert "current object" in str(exc)
    else:
        raise AssertionError("Expected ValueError for missing current object")
