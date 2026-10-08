"""Spatial/temporal alignment of real AIS and environmental evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import asin, cos, radians, sin, sqrt
from typing import Literal

from src.environment.context import EnvironmentalContext
from src.ingestion.models import AISObservation, EnvironmentalObservation


AlignmentStatus = Literal["ALIGNED", "STALE", "OUT_OF_BOUNDS", "UNAVAILABLE"]


@dataclass(frozen=True)
class EnvironmentalAlignment:
    """Traceable relationship between one AIS observation and one environment state."""

    status: AlignmentStatus
    ais_received_at: datetime
    ais_latitude: float
    ais_longitude: float
    source: str
    observation: EnvironmentalObservation | None
    temporal_age_seconds: float | None
    spatial_distance_km: float | None
    max_temporal_age_seconds: float
    max_spatial_distance_km: float

    @property
    def usable(self) -> bool:
        return self.status == "ALIGNED" and self.observation is not None

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "ais_received_at": self.ais_received_at.astimezone(timezone.utc).isoformat(),
            "ais_latitude": self.ais_latitude,
            "ais_longitude": self.ais_longitude,
            "source": self.source,
            "temporal_age_seconds": self.temporal_age_seconds,
            "spatial_distance_km": self.spatial_distance_km,
            "max_temporal_age_seconds": self.max_temporal_age_seconds,
            "max_spatial_distance_km": self.max_spatial_distance_km,
            "observation": self.observation.as_dict() if self.observation else None,
        }


class EnvironmentalAlignmentEngine:
    """Align AIS events to external model/observation states without causal inference."""

    def __init__(
        self,
        *,
        max_temporal_age_seconds: float = 3600.0,
        max_spatial_distance_km: float = 50.0,
    ) -> None:
        if max_temporal_age_seconds <= 0:
            raise ValueError("max_temporal_age_seconds must be positive")
        if max_spatial_distance_km <= 0:
            raise ValueError("max_spatial_distance_km must be positive")
        self.max_temporal_age_seconds = float(max_temporal_age_seconds)
        self.max_spatial_distance_km = float(max_spatial_distance_km)

    def align(
        self,
        observation: AISObservation,
        context: EnvironmentalContext,
        *,
        source: str | None = None,
    ) -> tuple[EnvironmentalAlignment, ...]:
        """Return one nearest-state alignment per requested environmental source.

        Selection is deterministic: minimize temporal age first, then spatial
        distance. No environmental value is synthesized or interpolated.
        """
        sources = (
            (source,)
            if source is not None
            else tuple(sorted({item.source for item in context.observations}))
        )
        results: list[EnvironmentalAlignment] = []
        for source_name in sources:
            candidates = [
                item for item in context.observations if item.source == source_name
            ]
            results.append(self._align_source(observation, source_name, candidates))
        return tuple(results)

    def _align_source(
        self,
        ais: AISObservation,
        source: str,
        candidates: list[EnvironmentalObservation],
    ) -> EnvironmentalAlignment:
        if not candidates:
            return EnvironmentalAlignment(
                status="UNAVAILABLE",
                ais_received_at=ais.received_at,
                ais_latitude=ais.latitude,
                ais_longitude=ais.longitude,
                source=source,
                observation=None,
                temporal_age_seconds=None,
                spatial_distance_km=None,
                max_temporal_age_seconds=self.max_temporal_age_seconds,
                max_spatial_distance_km=self.max_spatial_distance_km,
            )

        ranked = sorted(
            (
                (
                    abs((item.observed_at - ais.received_at).total_seconds()),
                    _haversine_km(
                        ais.latitude,
                        ais.longitude,
                        item.latitude,
                        item.longitude,
                    ),
                    item,
                )
                for item in candidates
            ),
            key=lambda value: (value[0], value[1], value[2].observed_at),
        )
        temporal_age, spatial_distance, selected = ranked[0]

        if spatial_distance > self.max_spatial_distance_km:
            status: AlignmentStatus = "OUT_OF_BOUNDS"
        elif temporal_age > self.max_temporal_age_seconds:
            status = "STALE"
        else:
            status = "ALIGNED"

        return EnvironmentalAlignment(
            status=status,
            ais_received_at=ais.received_at,
            ais_latitude=ais.latitude,
            ais_longitude=ais.longitude,
            source=source,
            observation=selected,
            temporal_age_seconds=temporal_age,
            spatial_distance_km=spatial_distance,
            max_temporal_age_seconds=self.max_temporal_age_seconds,
            max_spatial_distance_km=self.max_spatial_distance_km,
        )


def _haversine_km(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> float:
    """Great-circle distance between two WGS84 coordinates, in kilometers."""
    earth_radius_km = 6371.0088
    lat1, lat2 = radians(latitude_a), radians(latitude_b)
    delta_lat = radians(latitude_b - latitude_a)
    delta_lon = radians(longitude_b - longitude_a)
    haversine = (
        sin(delta_lat / 2.0) ** 2
        + cos(lat1) * cos(lat2) * sin(delta_lon / 2.0) ** 2
    )
    return earth_radius_km * 2.0 * asin(sqrt(min(1.0, haversine)))
