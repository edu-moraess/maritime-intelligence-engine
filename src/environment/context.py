"""Environmental context aggregation without synthetic fallback data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from src.ingestion.models import EnvironmentalObservation


@dataclass(frozen=True)
class EnvironmentalContext:
    """Immutable environmental evidence for one monitoring region."""

    region: str
    observations: tuple[EnvironmentalObservation, ...] = ()
    failure_code: str | None = None
    failure_reason: str | None = None
    attempted_at: datetime | None = None

    @property
    def status(self) -> str:
        if self.observations:
            return "AVAILABLE"
        return "FAILED" if self.failure_code else "UNAVAILABLE"

    @property
    def latest(self) -> EnvironmentalObservation | None:
        if not self.observations:
            return None
        return max(self.observations, key=lambda observation: observation.observed_at)

    @property
    def observed_at(self) -> datetime | None:
        latest = self.latest
        return latest.observed_at if latest is not None else None

    def add(self, observation: EnvironmentalObservation) -> "EnvironmentalContext":
        """Return a new context containing an observation for this region."""
        if observation.region != self.region:
            raise ValueError(
                f"Observation region {observation.region!r} does not match "
                f"context region {self.region!r}."
            )
        return EnvironmentalContext(
            region=self.region,
            observations=self.observations + (observation,),
            attempted_at=observation.observed_at,
        )

    def as_dict(self) -> dict[str, object]:
        """Serialize context state without inventing unavailable values."""
        latest = self.latest
        return {
            "region": self.region,
            "status": self.status,
            "observed_at": (
                latest.observed_at.astimezone(timezone.utc).isoformat()
                if latest is not None
                else None
            ),
            "observation_count": len(self.observations),
            "failure_code": self.failure_code,
            "failure_reason": self.failure_reason,
            "attempted_at": (
                self.attempted_at.astimezone(timezone.utc).isoformat()
                if self.attempted_at is not None
                else None
            ),
            "latest": latest.as_dict() if latest is not None else None,
        }
