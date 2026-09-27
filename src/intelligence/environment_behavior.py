"""Deterministic correlation between vessel environment and behavior.

This layer combines two already-derived/current-session contexts:
- regional environmental observation for the vessel's live position;
- deterministic behavioral classification from the vessel's latest AIS session.

It describes co-observed conditions only. It does not infer environmental
causality, operational risk, or a predictive probability.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.config.settings import RegionBBox
from src.environment.context import EnvironmentalContext
from src.ingestion.models import AISObservation, EnvironmentalObservation, VesselSnapshot
from src.intelligence.behavior_core import BehavioralProfile
from src.intelligence.behavior_rest import build_behavioral_profile
from src.intelligence.environment_vessel import (
    VesselEnvironmentalContext,
    resolve_vessel_environment,
)


@dataclass(frozen=True)
class EnvironmentBehaviorContext:
    """Combined deterministic context for one live vessel."""

    mmsi: str
    status: str
    region: str | None
    behavior: BehavioralProfile
    environment: VesselEnvironmentalContext

    @property
    def available(self) -> bool:
        return self.status == "AVAILABLE"

    @property
    def observation(self) -> EnvironmentalObservation | None:
        return self.environment.observation

    @property
    def observed_at(self) -> datetime | None:
        return self.environment.vessel_position_observed_at


def resolve_environment_behavior(
    vessel: VesselSnapshot,
    observations: list[AISObservation],
    environmental_contexts: dict[str, EnvironmentalContext],
    bboxes: tuple[RegionBBox, ...],
) -> EnvironmentBehaviorContext:
    """Correlate current-session behavior with the vessel's environment.

    Both inputs remain independently traceable. The returned status is
    explicit whenever either side lacks sufficient real evidence.
    """
    behavior = build_behavioral_profile(vessel.mmsi, observations)
    environment = resolve_vessel_environment(vessel, environmental_contexts, bboxes)

    if behavior.classification == "INSUFFICIENT_DATA":
        status = "INSUFFICIENT_BEHAVIOR"
    elif not environment.available:
        status = "ENVIRONMENT_UNAVAILABLE"
    else:
        status = "AVAILABLE"

    return EnvironmentBehaviorContext(
        mmsi=vessel.mmsi,
        status=status,
        region=environment.region,
        behavior=behavior,
        environment=environment,
    )
