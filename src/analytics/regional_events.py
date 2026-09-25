"""Deterministic temporal events for monitored real-AIS regions.

The detector operates only on observed AIS positions. It does not infer a
geographic exit when the stream provides no observation outside a region.
Direct A->B/B->A transitions are emitted when consecutive observations move
between two exclusive monitored regions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Sequence

from src.config.settings import RegionBBox
from src.geospatial.region_membership import membership
from src.ingestion.models import AISObservation

RegionEventType = Literal["ENTRY", "DWELL", "EXIT", "TRANSITION_A_TO_B", "TRANSITION_B_TO_A"]


@dataclass(frozen=True)
class RegionalEvent:
    """One deterministic temporal event derived from a real AIS track."""

    event_type: RegionEventType
    mmsi: str
    timestamp: datetime
    region_index: int | None
    region_label: str
    previous_region_index: int | None = None
    duration_seconds: float | None = None


def detect_regional_events(
    tracks: dict[str, list[AISObservation]],
    bboxes: Sequence[RegionBBox],
    *,
    labels: Sequence[str] | None = None,
    dwell_seconds: float = 300.0,
) -> list[RegionalEvent]:
    """Detect entry, dwell, exit and direct A/B transition events.

    An initial observation already inside a region is not treated as ENTRY
    because the prior geographic state is unknown. A DWELL is emitted once
    an exclusive regional episode reaches dwell_seconds. EXIT requires a
    subsequent observation outside the previous exclusive region; session
    end alone is never treated as geographic exit.

    Overlap observations are intentionally not assigned to either region.
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
        episode_started = None
        dwell_emitted = False

        for observation in ordered:
            memberships = membership(observation.latitude, observation.longitude, bboxes)
            current_state = memberships[0] if len(memberships) == 1 else None

            if current_state != previous_state:
                if previous_state is not None:
                    duration = ((observation.received_at - episode_started).total_seconds() if episode_started else None)
                    events.append(RegionalEvent("EXIT", mmsi, observation.received_at, previous_state, names[previous_state], duration_seconds=duration))

                if current_state is not None and previous_state is not None:
                    transition_type = None
                    if previous_state == 0 and current_state == 1:
                        transition_type = "TRANSITION_A_TO_B"
                    elif previous_state == 1 and current_state == 0:
                        transition_type = "TRANSITION_B_TO_A"
                    if transition_type is not None:
                        events.append(RegionalEvent(transition_type, mmsi, observation.received_at, current_state, f"{names[previous_state]} → {names[current_state]}", previous_region_index=previous_state))

                if current_state is not None and previous_state is None:
                    events.append(RegionalEvent("ENTRY", mmsi, observation.received_at, current_state, names[current_state]))

                previous_state = current_state
                episode_started = observation.received_at if current_state is not None else None
                dwell_emitted = False

            if current_state is not None and episode_started is not None and not dwell_emitted:
                duration = (observation.received_at - episode_started).total_seconds()
                if duration >= dwell_seconds:
                    events.append(RegionalEvent("DWELL", mmsi, observation.received_at, current_state, names[current_state], duration_seconds=duration))
                    dwell_emitted = True

    return sorted(events, key=lambda event: (event.timestamp, event.mmsi, event.event_type))