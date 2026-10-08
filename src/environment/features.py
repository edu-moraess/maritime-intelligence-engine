"""Deterministic environmental features derived from aligned evidence."""

from __future__ import annotations

from dataclasses import dataclass
from math import cos, radians, sin


@dataclass(frozen=True)
class EnvironmentalFeatures:
    """Contextual features; values are descriptive, not causal or anomaly scores."""

    source: str
    relative_current_speed_knots: float | None = None
    current_alignment_deg: float | None = None
    wind_alignment_deg: float | None = None
    wave_height_m: float | None = None
    wave_period_s: float | None = None
    wind_speed_10m_kmh: float | None = None
    wind_gusts_10m_kmh: float | None = None
    visibility_m: float | None = None
    precipitation_mm: float | None = None
    temporal_age_seconds: float | None = None
    spatial_distance_km: float | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "relative_current_speed_knots": self.relative_current_speed_knots,
            "current_alignment_deg": self.current_alignment_deg,
            "wind_alignment_deg": self.wind_alignment_deg,
            "wave_height_m": self.wave_height_m,
            "wave_period_s": self.wave_period_s,
            "wind_speed_10m_kmh": self.wind_speed_10m_kmh,
            "wind_gusts_10m_kmh": self.wind_gusts_10m_kmh,
            "visibility_m": self.visibility_m,
            "precipitation_mm": self.precipitation_mm,
            "temporal_age_seconds": self.temporal_age_seconds,
            "spatial_distance_km": self.spatial_distance_km,
        }


def derive_environmental_features(
    alignment: object,
    *,
    vessel_sog_knots: float | None,
    vessel_cog_degrees: float | None,
) -> EnvironmentalFeatures | None:
    """Derive contextual features only from a usable EnvironmentalAlignment.

    No value is created when the alignment is stale, unavailable, or spatially
    invalid. Current-relative speed is the magnitude of the vector difference
    between vessel velocity and environmental current velocity.
    """
    if not getattr(alignment, "usable", False):
        return None

    observation = getattr(alignment, "observation", None)
    if observation is None:
        return None

    current_speed = observation.ocean_current_velocity
    current_direction = observation.ocean_current_direction_deg
    relative_current = None
    if (
        vessel_sog_knots is not None
        and current_speed is not None
        and vessel_cog_degrees is not None
        and current_direction is not None
    ):
        vessel_x, vessel_y = _vector(vessel_sog_knots, vessel_cog_degrees)
        current_x, current_y = _vector(current_speed, current_direction)
        relative_current = (
            (vessel_x - current_x) ** 2 + (vessel_y - current_y) ** 2
        ) ** 0.5

    return EnvironmentalFeatures(
        source=getattr(alignment, "source"),
        relative_current_speed_knots=relative_current,
        current_alignment_deg=(
            _angular_difference(vessel_cog_degrees, current_direction)
            if vessel_cog_degrees is not None and current_direction is not None
            else None
        ),
        wind_alignment_deg=(
            _angular_difference(vessel_cog_degrees, observation.wind_direction_10m_deg)
            if vessel_cog_degrees is not None and observation.wind_direction_10m_deg is not None
            else None
        ),
        wave_height_m=observation.wave_height_m,
        wave_period_s=observation.wave_period_s,
        wind_speed_10m_kmh=observation.wind_speed_10m_kmh,
        wind_gusts_10m_kmh=observation.wind_gusts_10m_kmh,
        visibility_m=observation.visibility_m,
        precipitation_mm=observation.precipitation_mm,
        temporal_age_seconds=getattr(alignment, "temporal_age_seconds"),
        spatial_distance_km=getattr(alignment, "spatial_distance_km"),
    )


def _vector(speed: float, bearing_deg: float) -> tuple[float, float]:
    angle = radians(bearing_deg)
    return speed * sin(angle), speed * cos(angle)


def _angular_difference(first: float, second: float) -> float:
    return abs((first - second + 180.0) % 360.0 - 180.0)
