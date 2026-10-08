"""Open-Meteo Marine API provider for real environmental context."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from src.ingestion.models import EnvironmentalObservation


MARINE_API_URL = "https://marine-api.open-meteo.com/v1/marine"

MARINE_VARIABLES = (
    "wave_height",
    "wave_direction",
    "wave_period",
    "wind_wave_height",
    "swell_wave_height",
    "swell_wave_direction",
    "ocean_current_velocity",
    "ocean_current_direction",
    "sea_surface_temperature",
)

_CURRENT_TO_KNOTS = {
    "kn": 1.0,
    "knots": 1.0,
    "km/h": 1.0 / 1.852,
    "kmh": 1.0 / 1.852,
    "m/s": 1.9438444924406048,
    "ms": 1.9438444924406048,
    "mph": 0.8689762419,
}


class EnvironmentalProvider(ABC):
    """Interface for real environmental data providers."""

    @abstractmethod
    def current(
        self,
        latitude: float,
        longitude: float,
        region: str | None = None,
    ) -> EnvironmentalObservation:
        raise NotImplementedError


class OpenMeteoMarineProvider(EnvironmentalProvider):
    """Fetch current marine model conditions from Open-Meteo."""

    def __init__(self, timeout_seconds: float = 10.0) -> None:
        self.timeout_seconds = timeout_seconds

    def current(
        self,
        latitude: float,
        longitude: float,
        region: str | None = None,
    ) -> EnvironmentalObservation:
        params = urlencode(
            {
                "latitude": latitude,
                "longitude": longitude,
                "current": ",".join(MARINE_VARIABLES),
                "timezone": "GMT",
                "cell_selection": "sea",
                "wind_speed_unit": "kn",
            }
        )
        request = Request(
            f"{MARINE_API_URL}?{params}",
            headers={"User-Agent": "maritime-intelligence-engine/1.0"},
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            payload = json.load(response)

        current = payload.get("current")
        if not isinstance(current, dict):
            raise ValueError("Open-Meteo response does not contain a current object.")

        timestamp = current.get("time")
        if not isinstance(timestamp, str):
            raise ValueError("Open-Meteo response does not contain a valid current timestamp.")

        current_units = payload.get("current_units")
        if current_units is not None and not isinstance(current_units, dict):
            raise ValueError("Open-Meteo response current_units must be an object.")

        current_unit = str((current_units or {}).get("ocean_current_velocity", "kn")).strip().lower()
        factor = _CURRENT_TO_KNOTS.get(current_unit)
        if factor is None:
            raise ValueError(
                f"Unsupported Open-Meteo ocean_current_velocity unit: {current_unit!r}"
            )

        observed_at = datetime.fromisoformat(
            timestamp.replace("Z", "+00:00")
        ).astimezone(timezone.utc)

        return EnvironmentalObservation(
            source="open-meteo-marine",
            observed_at=observed_at,
            latitude=float(payload["latitude"]),
            longitude=float(payload["longitude"]),
            region=region,
            wave_height_m=_number(current.get("wave_height")),
            wave_direction_deg=_number(current.get("wave_direction")),
            wave_period_s=_number(current.get("wave_period")),
            wind_wave_height_m=_number(current.get("wind_wave_height")),
            swell_height_m=_number(current.get("swell_wave_height")),
            swell_direction_deg=_number(current.get("swell_wave_direction")),
            ocean_current_velocity=_convert_current(
                current.get("ocean_current_velocity"), factor
            ),
            product="Open-Meteo Marine",
            data_kind="numerical_model_forecast",
            retrieved_at=datetime.now(timezone.utc),
            forecast=True,
            ocean_current_direction_deg=_number(current.get("ocean_current_direction")),
            sea_surface_temperature_c=_number(current.get("sea_surface_temperature")),
        )


def _number(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def _convert_current(value: object, factor: float) -> float | None:
    number = _number(value)
    return number * factor if number is not None else None
