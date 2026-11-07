"""Deterministic regional intelligence events from real AIS and environmental evidence.

The detector emits only events supported by observed state transitions or
explicit external observations. It never treats session end as a geographic
exit and never fabricates environmental or behavioral evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Sequence

from src.config.settings import RegionBBox
from src.environment.context import EnvironmentalContext
from src.geospatial.region_membership import membership
from src.ingestion.models import AISObservation, AnomalyFinding
from src.intelligence.behavior_rest import build_behavioral_profile


RegionEventType = Literal[
    "VESSEL_ENTERED_REGION",
    "VESSEL_LEFT_REGION",
    "VESSEL_TRANSITION_A_TO_B",
    "VESSEL_TRANSITION_B_TO_A",
    "VESSEL_DWELL",
    "BEHAVIOR_CHANGED",
    "ANOMALY_DETECTED",
    "ENVIRONMENT_UPDATED",
    "ENVIRONMENT_CONTEXT_AVAILABLE",
]


@dataclass(frozen=True)
class RegionalEvent:
    """One deterministic regional intelligence event."""

    event_type: RegionEventType
    mmsi: str | None
    timestamp: datetime
    region_index: int | None
    region_label: str
    previous_region_index: int | None = None
    duration_seconds: float | None = None
    detail: str | None = None


def _region_state(
    observation: AISObservation,
    bboxes: Sequence[RegionBBox],
) -> int | None:
    memberships = membership(observation.latitude, observation.longitude, bboxes)
    return memberships[0] if len(memberships) == 1 else None


def _behavior_change_events(
    tracks: dict[str, list[AISObservation]],
    bboxes: Sequence[RegionBBox],
    labels: Sequence[str],
) -> list[RegionalEvent]:
    events: list[RegionalEvent] = []

    for mmsi, observations in tracks.items():
        ordered = sorted(observations, key=lambda item: item.received_at)
        prefix: list[AISObservation] = []
        previous_classification: str | None = None

        for observation in ordered:
            prefix.append(observation)
            if len(prefix) < 2:
                continue

            profile = build_behavioral_profile(mmsi, prefix)
            classification = profile.classification
            if classification == "INSUFFICIENT_DATA":
                continue

            if (
                previous_classification is not None
                and classification != previous_classification
            ):
                region_index = _region_state(observation, bboxes)
                if region_index is not None:
                    events.append(
                        RegionalEvent(
                            event_type="BEHAVIOR_CHANGED",
                            mmsi=mmsi,
                            timestamp=observation.received_at,
                            region_index=region_index,
                            region_label=labels[region_index],
                            detail=(
                                f"{previous_classification} → {classification}; "
                                f"confidence={profile.confidence}"
                            ),
                        )
                    )

            previous_classification = classification

    return events


def _anomaly_events(
    findings: Sequence[AnomalyFinding],
    bboxes: Sequence[RegionBBox],
    labels: Sequence[str],
) -> list[RegionalEvent]:
    events: list[RegionalEvent] = []
    for finding in findings:
        memberships = membership(finding.latitude, finding.longitude, bboxes)
        if len(memberships) != 1:
            continue
        region_index = memberships[0]
        events.append(
            RegionalEvent(
                event_type="ANOMALY_DETECTED",
                mmsi=finding.mmsi,
                timestamp=finding.received_at,
                region_index=region_index,
                region_label=labels[region_index],
                detail=(
                    f"{finding.category}; score={finding.score:.2f}; "
                    f"confidence={finding.confidence:.2f}"
                    if finding.confidence is not None
                    else f"{finding.category}; score={finding.score:.2f}"
                ),
            )
        )
    return events


def _environment_events(
    environmental_contexts: dict[str, EnvironmentalContext],
    labels: Sequence[str],
) -> list[RegionalEvent]:
    events: list[RegionalEvent] = []

    for region_key, context in environmental_contexts.items():
        if not region_key.startswith("region_"):
            continue
        try:
            index = int(region_key.split("_", 1)[1]) - 1
        except (ValueError, IndexError):
            continue
        if index < 0 or index >= len(labels):
            continue

        observations = sorted(context.observations, key=lambda item: item.reference_time)
        if not observations:
            continue

        latest = observations[-1]
        if len(observations) == 1:
            event_type = "ENVIRONMENT_CONTEXT_AVAILABLE"
            detail = f"source={latest.source}"
        else:
            event_type = "ENVIRONMENT_UPDATED"
            previous = observations[-2]
            detail = (
                f"source={latest.source}; "
                f"previous_reference_time={previous.reference_time.isoformat()}"
            )

        events.append(
            RegionalEvent(
                event_type=event_type,
                mmsi=None,
                timestamp=latest.reference_time,
                region_index=index,
                region_label=labels[index],
                detail=detail,
            )
        )

    return events


def detect_regional_events(
    tracks: dict[str, list[AISObservation]],
    bboxes: Sequence[RegionBBox],
    *,
    labels: Sequence[str] | None = None,
    dwell_seconds: float = 300.0,
    findings: Sequence[AnomalyFinding] = (),
    environmental_contexts: dict[str, EnvironmentalContext] | None = None,
) -> list[RegionalEvent]:
    """Detect regional, behavioral, anomaly and environmental events.

    Geographic events are emitted only from observed exclusive region
    transitions. Overlap is treated as an unknown geographic state.
    Environmental events are emitted only from real observations already
    present in the environmental context.
    """
    if len(bboxes) != 2:
        raise ValueError("Exactly two monitoring regions are required.")
    if dwell_seconds < 0:
        raise ValueError("dwell_seconds must be non-negative.")

    names = tuple(labels or ("Region A", "Region B"))
    if len(names) != 2:
        raise ValueError("Exactly two region labels are required.")

    events: list[RegionalEvent] = []

    for mmsi, observations in tracks.items():
        ordered = sorted(observations, key=lambda item: item.received_at)
        previous_state: int | None = None
        episode_started: datetime | None = None
        dwell_emitted = False

        for observation in ordered:
            current_state = _region_state(observation, bboxes)

            if current_state != previous_state:
                if previous_state is not None:
                    duration = (
                        (observation.received_at - episode_started).total_seconds()
                        if episode_started is not None
                        else None
                    )
                    events.append(
                        RegionalEvent(
                            event_type="VESSEL_LEFT_REGION",
                            mmsi=mmsi,
                            timestamp=observation.received_at,
                            region_index=previous_state,
                            region_label=names[previous_state],
                            duration_seconds=duration,
                        )
                    )

                if current_state is not None and previous_state is not None:
                    transition_type: RegionEventType | None = None
                    if previous_state == 0 and current_state == 1:
                        transition_type = "VESSEL_TRANSITION_A_TO_B"
                    elif previous_state == 1 and current_state == 0:
                        transition_type = "VESSEL_TRANSITION_B_TO_A"
                    if transition_type is not None:
                        events.append(
                            RegionalEvent(
                                event_type=transition_type,
                                mmsi=mmsi,
                                timestamp=observation.received_at,
                                region_index=current_state,
                                region_label=(
                                    f"{names[previous_state]} → "
                                    f"{names[current_state]}"
                                ),
                                previous_region_index=previous_state,
                            )
                        )

                if current_state is not None and previous_state is None:
                    events.append(
                        RegionalEvent(
                            event_type="VESSEL_ENTERED_REGION",
                            mmsi=mmsi,
                            timestamp=observation.received_at,
                            region_index=current_state,
                            region_label=names[current_state],
                        )
                    )

                previous_state = current_state
                episode_started = (
                    observation.received_at if current_state is not None else None
                )
                dwell_emitted = False

            if (
                current_state is not None
                and episode_started is not None
                and not dwell_emitted
            ):
                duration = (
                    observation.received_at - episode_started
                ).total_seconds()
                if duration >= dwell_seconds:
                    events.append(
                        RegionalEvent(
                            event_type="VESSEL_DWELL",
                            mmsi=mmsi,
                            timestamp=observation.received_at,
                            region_index=current_state,
                            region_label=names[current_state],
                            duration_seconds=duration,
                        )
                    )
                    dwell_emitted = True

    events.extend(_behavior_change_events(tracks, bboxes, names))
    events.extend(_anomaly_events(findings, bboxes, names))
    events.extend(_environment_events(environmental_contexts or {}, names))

    return sorted(
        events,
        key=lambda event: (
            event.timestamp,
            event.mmsi or "",
            event.event_type,
        ),
    )
