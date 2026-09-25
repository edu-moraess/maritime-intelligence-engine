"""Open-Meteo Marine API provider for real environmental context."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .models import EnvironmentalObservation


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

        observed_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone(timezone.utc)

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
            ocean_current_velocity=_number(current.get("ocean_current_velocity")),
            ocean_current_direction_deg=_number(current.get("ocean_current_direction")),
            sea_surface_temperature_c=_number(current.get("sea_surface_temperature")),
        )


def _number(value: object) -> float | None:
    if value is None:
        return None
    return float(value)
