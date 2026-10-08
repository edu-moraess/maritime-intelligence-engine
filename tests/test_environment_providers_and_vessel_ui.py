from datetime import datetime, timedelta, timezone
from io import BytesIO

from src.environment.alignment import EnvironmentalStateAlignmentEngine
from src.environment.context import EnvironmentalContext
from src.environment.open_meteo_marine import OpenMeteoMarineProvider
from src.environment.open_meteo_weather import OpenMeteoWeatherProvider
from src.ingestion.models import EnvironmentalObservation, VesselSnapshot
from src.intelligence.environment_vessel import resolve_vessel_environment


UTC = timezone.utc


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        import json
        return json.dumps(self.payload).encode()


def test_open_meteo_marine_normalizes_current_unit(monkeypatch):
    import src.environment.open_meteo_marine as module

    payload = {
        "latitude": 25.76,
        "longitude": -80.19,
        "current": {
            "time": "2026-10-08T20:15",
            "wave_height": 0.5,
            "wave_direction": 32.0,
            "wave_period": 6.8,
            "ocean_current_velocity": 3.704,
            "ocean_current_direction": 90.0,
        },
        "current_units": {"ocean_current_velocity": "km/h"},
    }
    monkeypatch.setattr(module, "urlopen", lambda *args, **kwargs: _Response(payload))

    observation = OpenMeteoMarineProvider().current(25.76, -80.19, "region_1")

    assert round(observation.ocean_current_velocity or 0.0, 3) == 2.0
    assert observation.observed_at == datetime(2026, 10, 8, 20, 15, tzinfo=UTC)
    assert observation.forecast is True
    assert observation.product == "Open-Meteo Marine"


def test_open_meteo_weather_normalizes_wind_unit(monkeypatch):
    import src.environment.open_meteo_weather as module

    payload = {
        "latitude": 25.76,
        "longitude": -80.19,
        "current": {
            "time": "2026-10-08T20:15",
            "wind_speed_10m": 10.0,
            "wind_direction_10m": 135.0,
            "wind_gusts_10m": 15.0,
        },
        "current_units": {"wind_speed_10m": "kn"},
    }
    monkeypatch.setattr(module, "urlopen", lambda *args, **kwargs: _Response(payload))

    observation = OpenMeteoWeatherProvider().current(25.76, -80.19, "region_1")

    assert round(observation.wind_speed_10m_kmh or 0.0, 3) == 18.52
    assert round(observation.wind_gusts_10m_kmh or 0.0, 3) == 27.78
    assert observation.forecast is True
    assert observation.data_kind == "numerical_model_forecast"


def _vessel(received_at: datetime) -> VesselSnapshot:
    return VesselSnapshot(
        mmsi="367020910",
        latitude=25.76,
        longitude=-80.19,
        last_received=received_at,
        sog_knots=8.0,
        cog_degrees=90.0,
        heading_degrees=90.0,
        vessel_name="TEST VESSEL",
        message_count=1,
        observed_at=received_at,
    )


def test_vessel_ui_does_not_attach_future_model_state():
    t = datetime(2026, 10, 8, 20, 15, tzinfo=UTC)
    context = EnvironmentalContext(
        region="region_1",
        observations=(
            EnvironmentalObservation(
                source="open-meteo-marine",
                observed_at=t + timedelta(minutes=10),
                latitude=25.76,
                longitude=-80.19,
                region="region_1",
                wave_height_m=0.5,
                forecast=True,
            ),
        ),
    )

    result = resolve_vessel_environment(
        _vessel(t),
        {"region_1": context},
        (((25.0, -81.0), (26.0, -79.0)),),
        alignment_engine=EnvironmentalStateAlignmentEngine(allow_forecast=False),
    )

    assert result.status == "FUTURE"
    assert result.observation is not None
    assert result.environment_age_seconds == 600.0
    assert result.available is False


def test_vessel_ui_rejects_environmental_state_outside_spatial_limit():
    t = datetime(2026, 10, 8, 20, 15, tzinfo=UTC)
    context = EnvironmentalContext(
        region="region_1",
        observations=(
            EnvironmentalObservation(
                source="open-meteo-marine",
                observed_at=t,
                latitude=25.76,
                longitude=-78.0,
                region="region_1",
                wave_height_m=0.5,
            ),
        ),
    )

    result = resolve_vessel_environment(
        _vessel(t),
        {"region_1": context},
        (((25.0, -81.0), (26.0, -77.0)),),
        alignment_engine=EnvironmentalStateAlignmentEngine(max_spatial_distance_km=50.0),
    )

    assert result.status == "OUT_OF_BOUNDS"
    assert result.available is False
