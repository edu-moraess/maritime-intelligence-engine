"""Deterministic environmental state attached to a live vessel position.

The UI consumes the same spatial/temporal alignment contract used by the
engine. It never falls back to the latest regional state when that state is
future, stale, or spatially out of bounds.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from src.config.settings import RegionBBox
from src.environment.alignment import EnvironmentalStateAlignment, EnvironmentalStateAlignmentEngine
from src.environment.context import EnvironmentalContext
from src.geospatial.region_membership import membership
from src.ingestion.models import AISObservation, EnvironmentalObservation, VesselSnapshot


_SOURCE_PRIORITY = {
    "open-meteo-marine": 0,
    "open-meteo-weather": 1,
    "copernicus-marine": 2,
}


@dataclass(frozen=True)
class VesselEnvironmentalContext:
    """Environmental state associated with one vessel after explicit alignment."""

    mmsi: str
    status: str
    region: str | None
    observation: EnvironmentalObservation | None
    vessel_position_observed_at: datetime | None
    environment_age_seconds: float | None
    temporal_offset_seconds: float | None = None
    spatial_distance_km: float | None = None
    alignments: tuple[EnvironmentalStateAlignment, ...] = ()

    @property
    def available(self) -> bool:
        return self.status == "AVAILABLE" and self.observation is not None

    def observation_from(self, source: str) -> EnvironmentalObservation | None:
        for alignment in self.alignments:
            if alignment.source == source and alignment.usable:
                return alignment.observation
        return None


def resolve_vessel_environment(
    vessel: VesselSnapshot,
    environmental_contexts: dict[str, EnvironmentalContext],
    bboxes: tuple[RegionBBox, ...],
    *,
    alignment_engine: EnvironmentalStateAlignmentEngine | None = None,
) -> VesselEnvironmentalContext:
    """Resolve environmental state using the same alignment rules as the engine."""
    vessel_time = vessel.last_received
    memberships = membership(vessel.latitude, vessel.longitude, bboxes)
    if len(memberships) != 1:
        status = "AMBIGUOUS_REGION" if len(memberships) > 1 else "OUTSIDE_MONITORED_REGIONS"
        return VesselEnvironmentalContext(
            mmsi=vessel.mmsi,
            status=status,
            region=None,
            observation=None,
            vessel_position_observed_at=vessel.observed_at or vessel_time,
            environment_age_seconds=None,
        )

    index = memberships[0]
    region_key = f"region_{index + 1}"
    context = environmental_contexts.get(region_key)
    if context is None or not context.observations:
        return VesselEnvironmentalContext(
            mmsi=vessel.mmsi,
            status="UNAVAILABLE",
            region=region_key,
            observation=None,
            vessel_position_observed_at=vessel.observed_at or vessel_time,
            environment_age_seconds=None,
        )

    ais = AISObservation(
        mmsi=str(vessel.mmsi),
        latitude=float(vessel.latitude),
        longitude=float(vessel.longitude),
        received_at=vessel_time,
        sog_knots=vessel.sog_knots,
        cog_degrees=vessel.cog_degrees,
        heading_degrees=vessel.heading_degrees,
        vessel_name=vessel.vessel_name,
        observed_at=vessel.observed_at,
    )
    engine = alignment_engine or EnvironmentalStateAlignmentEngine()
    alignments = engine.align(ais, context)
    usable = [alignment for alignment in alignments if alignment.usable]

    if not usable:
        primary = _primary_alignment(alignments)
        return VesselEnvironmentalContext(
            mmsi=vessel.mmsi,
            status=primary.status if primary is not None else "UNAVAILABLE",
            region=region_key,
            observation=primary.observation if primary is not None else None,
            vessel_position_observed_at=vessel.observed_at or vessel_time,
            environment_age_seconds=primary.temporal_age_seconds if primary is not None else None,
            temporal_offset_seconds=primary.temporal_offset_seconds if primary is not None else None,
            spatial_distance_km=primary.spatial_distance_km if primary is not None else None,
            alignments=alignments,
        )

    primary = min(
        usable,
        key=lambda item: (
            _SOURCE_PRIORITY.get(item.source, 99),
            item.temporal_age_seconds if item.temporal_age_seconds is not None else float("inf"),
            item.spatial_distance_km if item.spatial_distance_km is not None else float("inf"),
        ),
    )
    return VesselEnvironmentalContext(
        mmsi=vessel.mmsi,
        status="AVAILABLE",
        region=region_key,
        observation=primary.observation,
        vessel_position_observed_at=vessel.observed_at or vessel_time,
        environment_age_seconds=primary.temporal_age_seconds,
        temporal_offset_seconds=primary.temporal_offset_seconds,
        spatial_distance_km=primary.spatial_distance_km,
        alignments=alignments,
    )


def _primary_alignment(
    alignments: tuple[EnvironmentalStateAlignment, ...],
) -> EnvironmentalStateAlignment | None:
    if not alignments:
        return None
    return min(
        alignments,
        key=lambda item: (
            _SOURCE_PRIORITY.get(item.source, 99),
            item.temporal_age_seconds if item.temporal_age_seconds is not None else float("inf"),
            item.spatial_distance_km if item.spatial_distance_km is not None else float("inf"),
        ),
    )
