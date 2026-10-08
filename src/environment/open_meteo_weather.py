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

_WIND_TO_KMH = {
    "km/h": 1.0,
    "kmh": 1.0,
    "kn": 1.852,
    "knots": 1.852,
    "m/s": 3.6,
    "ms": 3.6,
    "mph": 1.609344,
}


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

        current_units = payload.get("current_units")
        if current_units is not None and not isinstance(current_units, dict):
            raise ValueError("Open-Meteo weather response current_units must be an object.")

        wind_unit = str((current_units or {}).get("wind_speed_10m", "km/h")).strip().lower()
        factor = _WIND_TO_KMH.get(wind_unit)
        if factor is None:
            raise ValueError(f"Unsupported Open-Meteo wind speed unit: {wind_unit!r}")

        observed_at = datetime.fromisoformat(
            timestamp.replace("Z", "+00:00")
        ).astimezone(timezone.utc)

        return EnvironmentalObservation(
            source="open-meteo-weather",
            observed_at=observed_at,
            latitude=float(payload["latitude"]),
            longitude=float(payload["longitude"]),
            region=region,
            wind_speed_10m_kmh=_convert_speed(current.get("wind_speed_10m"), factor),
            wind_direction_10m_deg=_number(current.get("wind_direction_10m")),
            wind_gusts_10m_kmh=_convert_speed(current.get("wind_gusts_10m"), factor),
            precipitation_mm=_number(current.get("precipitation")),
            visibility_m=_number(current.get("visibility")),
            pressure_msl_hpa=_number(current.get("pressure_msl")),
            product="Open-Meteo Weather",
            data_kind="numerical_model_forecast",
            retrieved_at=datetime.now(timezone.utc),
            forecast=True,
        )


def _number(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def _convert_speed(value: object, factor: float) -> float | None:
    number = _number(value)
    return number * factor if number is not None else None
