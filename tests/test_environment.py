from datetime import datetime, timezone

from src.environment.context import EnvironmentalContext
from src.ingestion.models import EnvironmentalObservation


def _obs(source: str, minute: int) -> EnvironmentalObservation:
    return EnvironmentalObservation(
        source=source,
        observed_at=datetime(2026, 10, 8, 10, minute, tzinfo=timezone.utc),
        latitude=50.0,
        longitude=0.0,
        region="region_1",
    )


def test_environment_context_keeps_latest_per_source() -> None:
    context = EnvironmentalContext(region="region_1")
    context = context.add(_obs("open-meteo-marine", 0))
    context = context.add(_obs("open-meteo-weather", 1))
    context = context.add(_obs("open-meteo-marine", 2))

    marine = context.latest_from("open-meteo-marine")
    weather = context.latest_from("open-meteo-weather")

    assert marine is not None
    assert marine.observed_at.minute == 2
    assert weather is not None
    assert weather.observed_at.minute == 1


def test_environment_observation_accepts_weather_state() -> None:
    observation = EnvironmentalObservation(
        source="open-meteo-weather",
        observed_at=datetime(2026, 10, 8, 10, 0, tzinfo=timezone.utc),
        latitude=25.7,
        longitude=-80.0,
        wind_speed_10m_kmh=22.5,
        wind_direction_10m_deg=135.0,
        wind_gusts_10m_kmh=31.0,
        precipitation_mm=0.2,
        visibility_m=12000.0,
        pressure_msl_hpa=1014.0,
    )

    payload = observation.as_dict()

    assert payload["wind_speed_10m_kmh"] == 22.5
    assert payload["wind_direction_10m_deg"] == 135.0
    assert payload["visibility_m"] == 12000.0
