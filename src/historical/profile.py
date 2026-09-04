"""Historical vessel profiles built from persisted real AIS observations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from statistics import mean, pstdev

from src.ingestion.models import AISObservation
from src.processing.quality import haversine_km


@dataclass(frozen=True)
class HistoricalVesselProfile:
    mmsi: str
    observation_count: int
    session_count: int
    first_seen_at: datetime | None
    last_seen_at: datetime | None
    distance_km: float | None
    average_sog_knots: float | None
    max_sog_knots: float | None
    sog_std_knots: float | None
    track_points: int
    status: str

    def speed_baseline_deviation(self, sog_knots: float | None) -> float | None:
        """Return absolute deviation from historical mean SOG in knots.

        A baseline is only considered meaningful with at least three historical
        speed observations. This is a descriptive comparison, not a risk score.
        """
        if sog_knots is None or self.average_sog_knots is None or self.observation_count < 3:
            return None
        return round(abs(float(sog_knots) - self.average_sog_knots), 2)


def build_vessel_profile(
    mmsi: str,
    observations: list[AISObservation],
    *,
    session_count: int | None = None,
) -> HistoricalVesselProfile:
    """Build a deterministic profile from persisted real AIS observations."""
    selected = sorted(
        (obs for obs in observations if obs.mmsi == mmsi),
        key=lambda obs: obs.received_at,
    )
    if not selected:
        return HistoricalVesselProfile(
            mmsi=mmsi,
            observation_count=0,
            session_count=0,
            first_seen_at=None,
            last_seen_at=None,
            distance_km=None,
            average_sog_knots=None,
            max_sog_knots=None,
            sog_std_knots=None,
            track_points=0,
            status="N/A",
        )

    if session_count is None:
        session_ids = {
            str(obs.raw.get("session_id"))
            for obs in selected
            if obs.raw.get("session_id")
        }
        session_count = len(session_ids)

    distance_km = None
    if len(selected) >= 2:
        distance_km = sum(
            haversine_km(
                first.latitude,
                first.longitude,
                second.latitude,
                second.longitude,
            )
            for first, second in zip(selected, selected[1:])
        )

    speeds = [
        float(obs.sog_knots)
        for obs in selected
        if obs.sog_knots is not None
    ]

    return HistoricalVesselProfile(
        mmsi=mmsi,
        observation_count=len(selected),
        session_count=max(0, int(session_count)),
        first_seen_at=selected[0].received_at,
        last_seen_at=selected[-1].received_at,
        distance_km=distance_km,
        average_sog_knots=mean(speeds) if speeds else None,
        max_sog_knots=max(speeds) if speeds else None,
        sog_std_knots=pstdev(speeds) if len(speeds) >= 2 else None,
        track_points=len(selected),
        status="READY" if len(selected) >= 2 else "PARTIAL",
    )
