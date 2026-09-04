"""Orchestration layer used by Streamlit; no business logic is embedded in app.py."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone

from src.analytics.traffic import traffic_summary
from src.anomaly.detector import detect_anomalies
from src.config.settings import AppSettings
from src.ingestion.aisstream import AISStreamProvider
from src.historical import HistoricalWriteResult, create_historical_writer
from src.historical.reader import load_recent_observations
from src.ingestion.models import AISObservation, AnomalyFinding, IngestionStatus, VesselSnapshot
from src.ml.embeddings import EmbeddingResult, TrajectoryEmbeddingAdapter
from src.ml.temporal import TemporalAnomalyAdapter
from src.ml.temporal.types import TemporalFitResult
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
    temporal_status: str = "WAITING"

    @property
    def multitrack_status(self) -> str:
        if self.tracks_with_history == 0:
            return "WAITING"
        if self.tracks_with_history < self.required_tracks:
            return "PARTIAL"
        return "READY"

    @property
    def trajectory_status(self) -> str:
        return "READY" if self.trajectory_ready else "WAITING"

    @property
    def anomaly_status(self) -> str:
        """Anomaly readiness reflects whether the detector has findings to present."""
        if self.anomaly_count > 0:
            return "READY"
        if self.tracks_with_history >= self.required_tracks:
            return "READY"
        if self.tracks_with_history > 0:
            return "PARTIAL"
        return "WAITING"


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
    historical_status: str
    historical_result: HistoricalWriteResult | None
    temporal: TemporalFitResult | None = None


def _track_fingerprint(tracks: dict[str, list[AISObservation]]) -> str:
    """Stable fingerprint of track identities and lengths for cache invalidation."""
    parts: list[str] = []
    for mmsi in sorted(tracks.keys()):
        obs = tracks[mmsi]
        if not obs:
            continue
        last = max(o.received_at for o in obs)
        parts.append(f"{mmsi}:{len(obs)}:{last.isoformat()}")
    return "|".join(parts)


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
        self.temporal_adapter = TemporalAnomalyAdapter()
        ready, reason = settings.validate_for_connection()
        if not ready:
            self.provider.config_error = reason
            self.provider.connect()
        self.embeddings: EmbeddingResult | None = None
        self.findings: list[AnomalyFinding] = []
        self.temporal: TemporalFitResult | None = None
        self._temporal_fingerprint: str | None = None
        self.last_collection_seconds: float = 0.0
        self._historical_database_url = settings.database_url
        self._historical_persistence_enabled = settings.historical_persistence_enabled
        self._historical_loaded = False
        self.historical_writer = create_historical_writer(
            settings.database_url,
            settings.historical_persistence_enabled,
        )
        self.historical_result: HistoricalWriteResult | None = None
        self._restore_historical_context()

    @property
    def region(self) -> tuple[tuple[float, float], tuple[float, float]]:
        return self.settings.bbox

    def _restore_historical_context(self) -> int:
        """Hydrate the live store from persisted real AIS history once per engine."""
        if self._historical_loaded:
            return 0
        self._historical_loaded = True
        if not self._historical_database_url or not self._historical_persistence_enabled:
            return 0
        try:
            restored = load_recent_observations(self._historical_database_url, self.region)
        except Exception:
            return 0
        if not restored:
            return 0
        self.store.extend(restored)
        self._recompute()
        return len(restored)

    def collect(self) -> None:
        started_at = datetime.now(timezone.utc)
        self.provider.start_collection()
        observations = self.provider.collect(self.settings.collection_seconds)
        ended_at = datetime.now(timezone.utc)
        self.store.extend(observations)
        self.last_collection_seconds = max(0.0, (ended_at - started_at).total_seconds())
        self.historical_result = self.historical_writer.persist_collection(
            observations,
            self.region,
            self.settings.collection_seconds,
            started_at,
            ended_at,
        )
        self._recompute()

    def clear_session(self) -> None:
        """Clear only in-memory live state; persisted history is untouched."""
        self.store.clear()
        self.embeddings = None
        self.findings = []
        self.temporal = None
        self._temporal_fingerprint = None
        self.last_collection_seconds = 0.0
        self.historical_result = None
        self._recompute()

    def _recompute(self) -> None:
        observations = self.store.observations
        tracks = self.store.tracks
        self.findings = detect_anomalies(observations, tracks)
        quality = build_quality_report(observations)
        self.embeddings = self.embedding_adapter.fit(tracks)
        fingerprint = _track_fingerprint(tracks)
        if fingerprint != self._temporal_fingerprint:
            self.temporal = self.temporal_adapter.fit(tracks)
            self._temporal_fingerprint = fingerprint
        self._snapshot = EngineSnapshot(
            observations=observations,
            vessels=self.store.vessels,
            findings=self.findings,
            quality=quality,
            status=self.provider.status,
            embeddings=self.embeddings,
            summary=traffic_summary(observations),
            readiness=ReadinessSnapshot(
                distinct_vessels=len(self.store.vessels),
                tracks_with_history=sum(1 for track in tracks.values() if len(track) >= 2),
                trajectory_ready=any(len(track) >= 2 for track in tracks.values()),
                embeddings_ready=self.embeddings is not None and bool(self.embeddings.embeddings),
                embedding_status=self.embeddings.status if self.embeddings is not None else "WAITING",
                anomaly_count=len(self.findings),
                temporal_status=self.temporal.status if self.temporal is not None else "WAITING",
            ),
            last_collection_seconds=self.last_collection_seconds,
            historical_status=self.historical_writer.status,
            historical_result=self.historical_result,
            temporal=self.temporal,
        )

    @property
    def snapshot(self) -> EngineSnapshot:
        return self._snapshot

    def close(self) -> None:
        self.provider.close()
        self.historical_writer.close()
