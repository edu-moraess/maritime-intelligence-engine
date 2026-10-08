"""Open-Meteo weather model provider for contextual maritime state."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from src.ingestion.models import EnvironmentalObservation

WEATHER_API_URL = "https://api.open-meteo.com/v1/forecast"

WEATHER_VARIABLES = (
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
    "precipitation",
    "visibility",
    "pressure_msl",
)


class OpenMeteoWeatherProvider:
    """Fetch current atmospheric model state without synthetic fallback."""

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
                "current": ",".join(WEATHER_VARIABLES),
                "timezone": "GMT",
                "wind_speed_unit": "kmh",
                "forecast_days": 1,
            }
        )
        request = Request(
            f"{WEATHER_API_URL}?{params}",
            headers={"User-Agent": "maritime-intelligence-engine/1.0"},
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            payload = json.load(response)

        current = payload.get("current")
        if not isinstance(current, dict):
            raise ValueError("Open-Meteo weather response does not contain current.")

        timestamp = current.get("time")
        if not isinstance(timestamp, str):
            raise ValueError("Open-Meteo weather response has no valid timestamp.")

        observed_at = datetime.fromisoformat(
            timestamp.replace("Z", "+00:00")
        ).astimezone(timezone.utc)

        return EnvironmentalObservation(
            source="open-meteo-weather",
            observed_at=observed_at,
            latitude=float(payload["latitude"]),
            longitude=float(payload["longitude"]),
            region=region,
            wind_speed_10m_kmh=_number(current.get("wind_speed_10m")),
            wind_direction_10m_deg=_number(current.get("wind_direction_10m")),
            wind_gusts_10m_kmh=_number(current.get("wind_gusts_10m")),
            precipitation_mm=_number(current.get("precipitation")),
            visibility_m=_number(current.get("visibility")),
            pressure_msl_hpa=_number(current.get("pressure_msl")),
        )


def _number(value: object) -> float | None:
    if value is None:
        return None
    return float(value)
