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


@dataclass(frozen=True)
class ReadinessSnapshot:
    """Operational readiness derived only from the current real AIS session."""

    distinct_vessels: int
    tracks_with_history: int
    trajectory_ready: bool
    embeddings_ready: bool
    embedding_status: str
    anomaly_count: int
    required_tracks: int = 3


@dataclass
class EngineSnapshot:
    observations: list[AISObservation]
    vessels: list[VesselSnapshot]
    findings: list[AnomalyFinding]
    quality: QualityReport
    status: IngestionStatus
    embeddings: EmbeddingResult | None
    summary: dict[str, float | int]
    readiness: ReadinessSnapshot
    last_collection_seconds: float


class MaritimeIntelligenceEngine:
    """Session-scoped coordinator for one real AIS monitoring region."""

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.provider = AISStreamProvider(
            api_key=settings.aisstream_api_key,
            bbox=settings.bbox_payload,
            max_messages=settings.max_messages,
            max_vessels=settings.max_vessels,
            stale_after_seconds=settings.stale_after_seconds,
            config_error=settings.config_error,
        )
        self.store = ObservationStore(max_messages=settings.max_messages, max_vessels=settings.max_vessels)
        self.embedding_adapter = TrajectoryEmbeddingAdapter()
        ready, reason = settings.validate_for_connection()
        if not ready:
            self.provider.config_error = reason
            self.provider.connect()
        self.embeddings: EmbeddingResult | None = None
        self.findings: list[AnomalyFinding] = []
        self.last_collection_seconds: float = 0.0

    @property
    def region(self) -> tuple[tuple[float, float], tuple[float, float]]:
        return self.settings.bbox

    def collect(self, seconds: float | None = None) -> int:
        """Collect a bounded real-time window; returns only actual observations received."""
        duration = max(0.1, float(seconds if seconds is not None else self.settings.collection_seconds))
        started = time.monotonic()
        stop_event = threading.Event()
        collected: list[AISObservation] = []
        for observation in self.provider.stream(stop_event, duration_seconds=duration):
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

    def _readiness(self, tracks: dict[str, list[AISObservation]]) -> ReadinessSnapshot:
        tracks_with_history = sum(1 for track in tracks.values() if len(track) >= 2)
        return ReadinessSnapshot(
            distinct_vessels=len(tracks),
            tracks_with_history=tracks_with_history,
            trajectory_ready=tracks_with_history >= 1,
            embeddings_ready=self.embeddings is not None,
            embedding_status="READY" if self.embeddings is not None else "WAITING",
            anomaly_count=len(self.findings),
        )

    def snapshot(self) -> EngineSnapshot:
        observations = self.store.all()
        vessels = self.provider.fetch_vessels()
        tracks = self.store.tracks()
        quality = build_quality_report(observations, self.settings.stale_after_seconds, self.store.duplicate_count)
        return EngineSnapshot(
            observations=observations,
            vessels=vessels,
            findings=self.findings,
            quality=quality,
            status=self.provider.status,
            embeddings=self.embeddings,
            summary=traffic_summary(vessels, observations, self.findings),
            readiness=self._readiness(tracks),
            last_collection_seconds=self.last_collection_seconds,
        )

    def clear_session_data(self) -> None:
        self.store.clear()
        self.provider.reset_session()
        self.embeddings = None
        self.findings = []
        self.last_collection_seconds = 0.0
        if self.settings.config_error or not self.settings.aisstream_api_key:
            self.provider.connect()


def create_engine(settings: AppSettings) -> MaritimeIntelligenceEngine:
    """Create an isolated engine for the current Streamlit session and region."""
    return MaritimeIntelligenceEngine(settings)
