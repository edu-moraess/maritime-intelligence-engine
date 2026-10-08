"""Métricas operacionais derivadas do estado real do coletor AIS."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence

from src.ingestion.models import AISObservation, IngestionStatus


@dataclass(frozen=True)
class AISQualityMetrics:
    latency_seconds: float | None
    uptime_seconds: float | None
    valid_messages: int
    frames: int
    parse_errors: int
    active_contacts: int
    gaps_over_threshold: int
    max_gap_seconds: float | None
    queue_size: int
    valid_message_rate: float | None
    estimated_packet_loss: float | None


def build_quality_metrics(
    observations: Sequence[AISObservation],
    status: IngestionStatus,
    *,
    gap_threshold_seconds: float = 900.0,
) -> AISQualityMetrics:
    gaps: list[float] = []
    by_mmsi: dict[str, list[datetime]] = {}
    for obs in observations:
        by_mmsi.setdefault(obs.mmsi, []).append(obs.received_at)
    for timestamps in by_mmsi.values():
        ordered = sorted(timestamps)
        gaps.extend(
            (b - a).total_seconds()
            for a, b in zip(ordered, ordered[1:])
        )
    over = [gap for gap in gaps if gap > gap_threshold_seconds]
    latency = None
    if status.last_received_at is not None:
        latency = max(0.0, (datetime.now(timezone.utc) - status.last_received_at).total_seconds())
    return AISQualityMetrics(
        latency_seconds=latency,
        uptime_seconds=status.uptime_seconds,
        valid_messages=status.position_reports_accepted,
        frames=status.frames_received,
        parse_errors=status.parse_errors,
        active_contacts=status.active_vessels,
        gaps_over_threshold=len(over),
        max_gap_seconds=max(gaps, default=None),
        queue_size=status.queue_size,
        valid_message_rate=status.valid_message_rate,
        estimated_packet_loss=status.estimated_packet_loss,
    )
