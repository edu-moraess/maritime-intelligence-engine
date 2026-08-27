"""Orchestration layer used by Streamlit; no business logic is embedded in app.py."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from src.analytics.traffic import traffic_summary
from src.anomaly.detector import detect_anomalies
from src.config.settings import AppSettings
from src.ingestion.aisstream import AISStreamProvider
from src.ingestion.models import AISObservation, AnomalyFinding, IngestionStatus, VesselSnapshot
from src.ml.embeddings import EmbeddingResult, TrajectoryEmbeddingAdapter
from src.processing.quality import QualityReport, build_quality_report
from src.storage.memory import ObservationStore


@dataclass
class EngineSnapshot:
    observations: list[AISObservation]
    vessels: list[VesselSnapshot]
    findings: list[AnomalyFinding]
    quality: QualityReport
    status: IngestionStatus
    embeddings: EmbeddingResult | None
    summary: dict[str, float | int]


class MaritimeIntelligenceEngine:
    """Session-scoped coordinator for a real AIS monitoring region."""

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.provider = AISStreamProvider(
            api_key=settings.aisstream_api_key,
            bbox=settings.bbox_payload,
            max_messages=settings.max_messages,
            max_vessels=settings.max_vessels,
            stale_after_seconds=settings.stale_after_seconds,
        )
        self.store = ObservationStore(max_messages=settings.max_messages)
        self.embedding_adapter = TrajectoryEmbeddingAdapter()
        self.embeddings: EmbeddingResult | None = None
        self.findings: list[AnomalyFinding] = []
        self.last_collection_seconds: float = 0.0

    def collect(self, seconds: float | None = None) -> int:
        """Collect a bounded real-time window; returns only actual observations received."""
        duration = seconds if seconds is not None else self.settings.collection_seconds
        started = time.monotonic()
        stop_event = threading.Event()
        collected: list[AISObservation] = []
        for observation in self.provider.stream(stop_event):
            collected.append(observation)
            if time.monotonic() - started >= duration:
                stop_event.set()
                break
        stop_event.set()
        if collected:
            self.store.extend(collected)
        self.last_collection_seconds = time.monotonic() - started
        self._recompute()
        return len(collected)

    def _recompute(self) -> None:
        tracks = self.store.tracks()
        self.embeddings = self.embedding_adapter.fit(tracks)
        self.findings = detect_anomalies(tracks, self.embeddings)

    def snapshot(self) -> EngineSnapshot:
        observations = self.store.all()
        vessels = self.provider.fetch_vessels()
        quality = build_quality_report(observations, self.settings.stale_after_seconds)
        return EngineSnapshot(
            observations=observations,
            vessels=vessels,
            findings=self.findings,
            quality=quality,
            status=self.provider.status,
            embeddings=self.embeddings,
            summary=traffic_summary(vessels, observations, self.findings),
        )

    def clear_session_data(self) -> None:
        self.store.clear()
        self.embeddings = None
        self.findings = []


def create_engine(settings: AppSettings) -> MaritimeIntelligenceEngine:
    return MaritimeIntelligenceEngine(settings)
