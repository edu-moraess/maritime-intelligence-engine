"""Deterministic environmental context attached to a live vessel position.

This layer correlates a vessel's current-session position with the already
retrieved regional environmental observation. It does not infer causality or
score operational risk from environmental conditions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from src.config.settings import RegionBBox
from src.environment.context import EnvironmentalContext
from src.geospatial.region_membership import membership
from src.ingestion.models import EnvironmentalObservation, VesselSnapshot


@dataclass(frozen=True)
class VesselEnvironmentalContext:
    """Environmental evidence associated with one vessel's current position."""

    mmsi: str
    status: str
    region: str | None
    observation: EnvironmentalObservation | None
    vessel_position_observed_at: datetime | None
    environment_age_seconds: float | None

    @property
    def available(self) -> bool:
        return self.status == "AVAILABLE" and self.observation is not None


def resolve_vessel_environment(
    vessel: VesselSnapshot,
    environmental_contexts: dict[str, EnvironmentalContext],
    bboxes: tuple[RegionBBox, ...],
) -> VesselEnvironmentalContext:
    """Resolve the regional environmental evidence for a live vessel.

    Only an exclusive region membership is accepted. Overlap or out-of-region
    positions remain explicit instead of being assigned to an arbitrary region.
    """
    memberships = membership(vessel.latitude, vessel.longitude, bboxes)
    if len(memberships) != 1:
        status = "AMBIGUOUS_REGION" if len(memberships) > 1 else "OUTSIDE_MONITORED_REGIONS"
        return VesselEnvironmentalContext(
            mmsi=vessel.mmsi,
            status=status,
            region=None,
            observation=None,
            vessel_position_observed_at=vessel.observed_at or vessel.last_received,
            environment_age_seconds=None,
        )

    index = memberships[0]
    region_key = f"region_{index + 1}"
    context = environmental_contexts.get(region_key)
    observation = context.latest if context is not None else None
    if observation is None:
        return VesselEnvironmentalContext(
            mmsi=vessel.mmsi,
            status="UNAVAILABLE",
            region=region_key,
            observation=None,
            vessel_position_observed_at=vessel.observed_at or vessel.last_received,
            environment_age_seconds=None,
        )

    vessel_time = vessel.observed_at or vessel.last_received
    age = max(0.0, (vessel_time - observation.observed_at).total_seconds())
    return VesselEnvironmentalContext(
        mmsi=vessel.mmsi,
        status="AVAILABLE",
        region=region_key,
        observation=observation,
        vessel_position_observed_at=vessel_time,
        environment_age_seconds=age,
    )
