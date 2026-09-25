from datetime import datetime, timezone

import pytest

from src.ingestion.models import EnvironmentalObservation


def test_environmental_observation_normalizes_timestamp_and_serializes() -> None:
    observation = EnvironmentalObservation(
        source="open-meteo-marine",
        observed_at=datetime(2026, 9, 25, 2, 0, tzinfo=timezone.utc),
        latitude=51.0,
        longitude=1.5,
        region="B",
        wave_height_m=1.2,
        wave_direction_deg=270.0,
        wave_period_s=6.0,
        sea_surface_temperature_c=16.4,
    )

    payload = observation.as_dict()

    assert observation.observed_at.tzinfo == timezone.utc
    assert payload["source"] == "open-meteo-marine"
    assert payload["observed_at"] == "2026-09-25T02:00:00+00:00"
    assert payload["region"] == "B"
    assert payload["wave_height_m"] == 1.2


def test_environmental_observation_requires_timezone_aware_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        EnvironmentalObservation(
            source="open-meteo-marine",
            observed_at=datetime(2026, 9, 25, 2, 0),
            latitude=51.0,
            longitude=1.5,
        )


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [
        (91.0, 1.0),
        (-91.0, 1.0),
        (51.0, 181.0),
        (51.0, -181.0),
    ],
)
def test_environmental_observation_rejects_invalid_coordinates(
    latitude: float, longitude: float
) -> None:
    with pytest.raises(ValueError):
        EnvironmentalObservation(
            source="open-meteo-marine",
            observed_at=datetime(2026, 9, 25, 2, 0, tzinfo=timezone.utc),
            latitude=latitude,
            longitude=longitude,
        )


@pytest.mark.parametrize(
    "field_name",
    [
        "wave_height_m",
        "wave_period_s",
        "wind_wave_height_m",
        "swell_height_m",
        "ocean_current_velocity",
    ],
)
def test_environmental_observation_rejects_negative_magnitudes(field_name: str) -> None:
    kwargs = {
        "source": "open-meteo-marine",
        "observed_at": datetime(2026, 9, 25, 2, 0, tzinfo=timezone.utc),
        "latitude": 51.0,
        "longitude": 1.5,
        field_name: -0.1,
    }

    with pytest.raises(ValueError, match="non-negative"):
        EnvironmentalObservation(**kwargs)


@pytest.mark.parametrize(
    "field_name",
    [
        "wave_direction_deg",
        "swell_direction_deg",
        "ocean_current_direction_deg",
    ],
)
def test_environmental_observation_rejects_invalid_directions(field_name: str) -> None:
    kwargs = {
        "source": "open-meteo-marine",
        "observed_at": datetime(2026, 9, 25, 2, 0, tzinfo=timezone.utc),
        "latitude": 51.0,
        "longitude": 1.5,
        field_name: 361.0,
    }

    with pytest.raises(ValueError, match="between 0 and 360"):
        EnvironmentalObservation(**kwargs)


def test_environmental_observation_requires_source() -> None:
    with pytest.raises(ValueError, match="source"):
        EnvironmentalObservation(
            source=" ",
            observed_at=datetime(2026, 9, 25, 2, 0, tzinfo=timezone.utc),
            latitude=51.0,
            longitude=1.5,
        )
