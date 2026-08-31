"""Deterministic Vessel Intelligence Profile v1.

Combines current-session AIS with optional persisted historical context.
No ML and no LLM participate in profile construction or confidence scoring.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import fabs
from statistics import mean
from typing import Any, Sequence

from src.ingestion.models import AISObservation, AnomalyFinding
from src.processing.quality import haversine_km

# Explicit operational thresholds (documented, non-ML).
STALE_SIGNAL_SECONDS = 180.0
HIGH_CONFIDENCE_MIN_SESSION_OBS = 3
HIGH_CONFIDENCE_MIN_HISTORICAL_OBS = 2


@dataclass(frozen=True)
class IdentityBlock:
    """Static identity fields. Missing values stay None — never inferred."""

    mmsi: str
    vessel_name: str | None
    imo: str | None
    callsign: str | None
    navigational_status: int | None
    provenance: str = "LIVE"


@dataclass(frozen=True)
class TelemetryBlock:
    """Most recent valid AIS observation from the current session."""

    latitude: float | None
    longitude: float | None
    sog_knots: float | None
    cog_degrees: float | None
    heading_degrees: float | None
    navigational_status: int | None
    signal_age_seconds: float | None
    observation_count: int
    received_at: datetime | None
    provenance: str = "LIVE"
    available: bool = False


@dataclass(frozen=True)
class HistoricalBlock:
    """Persisted real-AIS history when available; otherwise status N/A."""

    observation_count: int
    session_count: int
    first_seen_at: datetime | None
    last_seen_at: datetime | None
    distance_km: float | None
    average_sog_knots: float | None
    max_sog_knots: float | None
    status: str  # N/A | PARTIAL | READY
    provenance: str = "HISTORICAL"
    available: bool = False


@dataclass(frozen=True)
class MovementBlock:
    """Session-derived kinematics. Requires ≥2 valid positions."""

    distance_km: float | None
    average_sog_knots: float | None
    max_sog_knots: float | None
    heading_change_degrees: float | None
    speed_change_knots: float | None
    status: str  # READY | INSUFFICIENT_DATA
    provenance: str = "DERIVED"


@dataclass(frozen=True)
class AnomalyBlock:
    """Session findings and historical findings kept strictly separate."""

    current_session: tuple[AnomalyFinding, ...]
    historical: tuple[AnomalyFinding, ...]
    provenance: str = "DERIVED"


@dataclass(frozen=True)
class ConfidenceBlock:
    """Deterministic confidence — rules documented in evaluate_confidence()."""

    level: str  # N/A | LOW | MEDIUM | HIGH
    reasons: tuple[str, ...]
    provenance: str = "DERIVED"


@dataclass(frozen=True)
class VesselIntelligenceProfile:
    """Operational profile for one selected MMSI."""

    mmsi: str
    identity: IdentityBlock
    telemetry: TelemetryBlock
    historical: HistoricalBlock
    movement: MovementBlock
    anomalies: AnomalyBlock
    confidence: ConfidenceBlock
    session_observation_count: int
    built_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def _angular_delta(a: float, b: float) -> float:
    diff = fabs(b - a) % 360.0
    return min(diff, 360.0 - diff)


def _signal_age_seconds(
    received_at: datetime | None,
    reference_time: datetime | None = None,
) -> float | None:
    if received_at is None:
        return None
    now = reference_time or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("reference_time must be timezone-aware")
    stamp = received_at if received_at.tzinfo else received_at.replace(tzinfo=timezone.utc)
    return max(0.0, (now.astimezone(timezone.utc) - stamp.astimezone(timezone.utc)).total_seconds())


def _session_track(mmsi: str, observations: Sequence[AISObservation]) -> list[AISObservation]:
    return sorted(
        (obs for obs in observations if obs.mmsi == mmsi and obs.valid),
        key=lambda obs: obs.received_at,
    )


def _identity_from_track(
    mmsi: str,
    track: list[AISObservation],
    vessel: Any | None,
) -> IdentityBlock:
    latest = track[-1] if track else None
    name = None
    nav = None
    if latest is not None:
        name = latest.vessel_name
        nav = latest.navigational_status
    if vessel is not None:
        vessel_name = getattr(vessel, "vessel_name", None) or getattr(vessel, "name", None)
        if vessel_name:
            name = str(vessel_name).strip() or name
        vessel_nav = getattr(vessel, "navigational_status", None)
        if vessel_nav is not None and nav is None:
            nav = vessel_nav
    imo = None
    callsign = None
    if latest is not None and isinstance(latest.raw, dict):
        raw_imo = latest.raw.get("imo") or latest.raw.get("IMO")
        raw_cs = latest.raw.get("callsign") or latest.raw.get("CallSign")
        if raw_imo is not None and str(raw_imo).strip() and str(raw_imo).strip() not in {"0", "None"}:
            imo = str(raw_imo).strip()
        if raw_cs is not None and str(raw_cs).strip():
            callsign = str(raw_cs).strip()
    return IdentityBlock(
        mmsi=mmsi,
        vessel_name=name,
        imo=imo,
        callsign=callsign,
        navigational_status=nav,
        provenance="LIVE",
    )


def _telemetry_from_track(
    track: list[AISObservation],
    reference_time: datetime | None,
) -> TelemetryBlock:
    if not track:
        return TelemetryBlock(
            latitude=None,
            longitude=None,
            sog_knots=None,
            cog_degrees=None,
            heading_degrees=None,
            navigational_status=None,
            signal_age_seconds=None,
            observation_count=0,
            received_at=None,
            available=False,
        )
    latest = track[-1]
    return TelemetryBlock(
        latitude=float(latest.latitude),
        longitude=float(latest.longitude),
        sog_knots=float(latest.sog_knots) if latest.sog_knots is not None else None,
        cog_degrees=float(latest.cog_degrees) if latest.cog_degrees is not None else None,
        heading_degrees=(
            float(latest.heading_degrees) if latest.heading_degrees is not None else None
        ),
        navigational_status=latest.navigational_status,
        signal_age_seconds=_signal_age_seconds(latest.received_at, reference_time),
        observation_count=len(track),
        received_at=latest.received_at,
        available=True,
    )


def _movement_from_track(track: list[AISObservation]) -> MovementBlock:
    if len(track) < 2:
        return MovementBlock(
            distance_km=None,
            average_sog_knots=None,
            max_sog_knots=None,
            heading_change_degrees=None,
            speed_change_knots=None,
            status="INSUFFICIENT_DATA",
        )

    distance_km = sum(
        haversine_km(a.latitude, a.longitude, b.latitude, b.longitude)
        for a, b in zip(track, track[1:])
    )
    speeds = [float(o.sog_knots) for o in track if o.sog_knots is not None]
    headings = [float(o.heading_degrees) for o in track if o.heading_degrees is not None]

    heading_change = None
    if len(headings) >= 2:
        heading_change = max(
            _angular_delta(a, b) for a, b in zip(headings, headings[1:])
        )

    speed_change = None
    if len(speeds) >= 2:
        speed_change = max(fabs(b - a) for a, b in zip(speeds, speeds[1:]))

    return MovementBlock(
        distance_km=distance_km,
        average_sog_knots=mean(speeds) if speeds else None,
        max_sog_knots=max(speeds) if speeds else None,
        heading_change_degrees=heading_change,
        speed_change_knots=speed_change,
        status="READY",
    )


def _historical_block(historical: Any | None) -> HistoricalBlock:
    """Accept optional HistoricalVesselProfile-compatible object (Etapa 2)."""
    if historical is None:
        return HistoricalBlock(
            observation_count=0,
            session_count=0,
            first_seen_at=None,
            last_seen_at=None,
            distance_km=None,
            average_sog_knots=None,
            max_sog_knots=None,
            status="N/A",
            available=False,
        )
    status = str(getattr(historical, "status", "N/A") or "N/A")
    obs_count = int(getattr(historical, "observation_count", 0) or 0)
    return HistoricalBlock(
        observation_count=obs_count,
        session_count=int(getattr(historical, "session_count", 0) or 0),
        first_seen_at=getattr(historical, "first_seen_at", None),
        last_seen_at=getattr(historical, "last_seen_at", None),
        distance_km=getattr(historical, "distance_km", None),
        average_sog_knots=getattr(historical, "average_sog_knots", None),
        max_sog_knots=getattr(historical, "max_sog_knots", None),
        status=status,
        available=status != "N/A" and obs_count > 0,
    )


def evaluate_confidence(
    *,
    session_observation_count: int,
    signal_age_seconds: float | None,
    historical_available: bool,
    historical_observation_count: int,
    stale_after_seconds: float = STALE_SIGNAL_SECONDS,
) -> ConfidenceBlock:
    """Deterministic confidence rules (no ML).

    N/A     — zero session observations
    LOW     — exactly one session observation, OR signal older than stale threshold
    MEDIUM  — ≥2 session observations, but history limited/absent or not enough for HIGH
    HIGH    — ≥3 session observations AND historical available with ≥2 obs AND signal recent
    """
    reasons: list[str] = []

    if session_observation_count <= 0:
        return ConfidenceBlock(level="N/A", reasons=("No valid session observations for this MMSI.",))

    signal_stale = (
        signal_age_seconds is not None and signal_age_seconds > stale_after_seconds
    )
    if session_observation_count == 1:
        reasons.append("Only one valid session observation.")
        if signal_stale:
            reasons.append(
                f"Signal age {signal_age_seconds:.0f}s exceeds {stale_after_seconds:.0f}s threshold."
            )
        return ConfidenceBlock(level="LOW", reasons=tuple(reasons))

    if signal_stale:
        reasons.append(
            f"Signal age {signal_age_seconds:.0f}s exceeds {stale_after_seconds:.0f}s threshold."
        )
        return ConfidenceBlock(level="LOW", reasons=tuple(reasons))

    history_consistent = (
        historical_available
        and historical_observation_count >= HIGH_CONFIDENCE_MIN_HISTORICAL_OBS
    )
    multi_obs = session_observation_count >= HIGH_CONFIDENCE_MIN_SESSION_OBS

    if multi_obs and history_consistent and not signal_stale:
        reasons.append(
            f"{session_observation_count} session observations with recent signal."
        )
        reasons.append(
            f"Historical profile available ({historical_observation_count} persisted observations)."
        )
        return ConfidenceBlock(level="HIGH", reasons=tuple(reasons))

    reasons.append(f"{session_observation_count} session observations.")
    if not historical_available:
        reasons.append("Persisted historical profile unavailable or empty.")
    elif historical_observation_count < HIGH_CONFIDENCE_MIN_HISTORICAL_OBS:
        reasons.append("Historical profile present but limited (fewer than 2 observations).")
    if not multi_obs:
        reasons.append("Fewer than 3 session observations.")
    return ConfidenceBlock(level="MEDIUM", reasons=tuple(reasons))


def build_vessel_intelligence_profile(
    mmsi: str,
    session_observations: Sequence[AISObservation],
    *,
    vessel: Any | None = None,
    session_findings: Sequence[AnomalyFinding] | None = None,
    historical_profile: Any | None = None,
    historical_findings: Sequence[AnomalyFinding] | None = None,
    reference_time: datetime | None = None,
    stale_after_seconds: float = STALE_SIGNAL_SECONDS,
) -> VesselIntelligenceProfile:
    """Build a fully deterministic Vessel Intelligence Profile for one MMSI.

    historical_profile accepts an optional HistoricalVesselProfile-compatible
    object (Etapa 2). When absent, the historical block is N/A and the profile
    still functions fully without LLM or ML.
    """
    track = _session_track(mmsi, session_observations)
    identity = _identity_from_track(mmsi, track, vessel)
    telemetry = _telemetry_from_track(track, reference_time)
    movement = _movement_from_track(track)
    historical = _historical_block(historical_profile)

    current_findings = tuple(
        f for f in (session_findings or ()) if str(getattr(f, "mmsi", "")) == mmsi
    )
    hist_findings = tuple(
        f for f in (historical_findings or ()) if str(getattr(f, "mmsi", "")) == mmsi
    )
    anomalies = AnomalyBlock(
        current_session=current_findings,
        historical=hist_findings,
    )

    confidence = evaluate_confidence(
        session_observation_count=len(track),
        signal_age_seconds=telemetry.signal_age_seconds,
        historical_available=historical.available,
        historical_observation_count=historical.observation_count,
        stale_after_seconds=stale_after_seconds,
    )

    return VesselIntelligenceProfile(
        mmsi=mmsi,
        identity=identity,
        telemetry=telemetry,
        historical=historical,
        movement=movement,
        anomalies=anomalies,
        confidence=confidence,
        session_observation_count=len(track),
        built_at=reference_time or datetime.now(timezone.utc),
    )
