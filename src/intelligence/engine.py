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
        if not self._historical_persistence_enabled or not self._historical_database_url:
            return 0
        restored = load_recent_observations(
            self._historical_database_url,
            self.settings.bbox,
            limit=self.settings.max_messages,
        )
        if not restored:
            return 0
        self.store.extend(restored)
        self._recompute()
        return len(restored)

    def collect(self, seconds: float | None = None) -> int:
        """Collect a bounded real-time window; returns only actual observations received."""
        duration = max(0.1, float(seconds if seconds is not None else self.settings.collection_seconds))
        started_at = datetime.now(timezone.utc)
        started = time.monotonic()
        stop_event = threading.Event()
        collected: list[AISObservation] = []
        for observation in self.provider.stream(stop_event, duration_seconds=duration):
            collected.append(observation)
            if time.monotonic() - started >= duration:
                stop_event.set()
                break
        stop_event.set()
        ended_at = datetime.now(timezone.utc)
        if collected:
            self.store.extend(collected)
            self.historical_result = self.historical_writer.persist_collection(
                collected,
                self.settings.bbox,
                time.monotonic() - started,
                started_at,
                ended_at,
            )
        else:
            self.historical_result = None
        self.last_collection_seconds = time.monotonic() - started
        self._recompute()
        return len(collected)

    def configure_historical_writer(self, database_url: str | None, persistence_enabled: bool) -> None:
        """Switch only the optional historical sink; preserve all live state."""
        if (
            database_url == self._historical_database_url
            and persistence_enabled == self._historical_persistence_enabled
        ):
            return
        self.historical_writer.close()
        self._historical_database_url = database_url
        self._historical_persistence_enabled = persistence_enabled
        self._historical_loaded = False
        self.historical_writer = create_historical_writer(database_url, persistence_enabled)
        self.historical_result = None
        self.settings = replace(
            self.settings,
            database_url=database_url,
            historical_persistence_enabled=persistence_enabled,
        )
        self._restore_historical_context()

    def _recompute(self) -> None:
        tracks = self.store.tracks()
        self.embeddings = self.embedding_adapter.fit(tracks)
        self.findings = detect_anomalies(tracks, self.embeddings)
        fingerprint = _track_fingerprint(tracks)
        if self.temporal is not None and self._temporal_fingerprint == fingerprint:
            return
        try:
            self.temporal = self.temporal_adapter.fit(tracks)
            self._temporal_fingerprint = fingerprint
        except Exception as exc:  # pragma: no cover — defensive isolation
            self.temporal = TemporalFitResult(
                status="FAILED",
                reason=f"Temporal path exception (classical path intact): {exc}",
            )
            self._temporal_fingerprint = fingerprint

    def _readiness(self, tracks: dict[str, list[AISObservation]]) -> ReadinessSnapshot:
        tracks_with_history = sum(1 for track in tracks.values() if len(track) >= 2)
        temporal_status = self.temporal.status if self.temporal is not None else "WAITING"
        return ReadinessSnapshot(
            distinct_vessels=len(tracks),
            tracks_with_history=tracks_with_history,
            trajectory_ready=tracks_with_history >= 1,
            embeddings_ready=self.embeddings is not None,
            embedding_status="READY" if self.embeddings is not None else ("PARTIAL" if tracks_with_history else "WAITING"),
            anomaly_count=len(self.findings),
            temporal_status=temporal_status,
        )

    def _merged_vessels(self, tracks: dict[str, list[AISObservation]]) -> list[VesselSnapshot]:
        """Expose live and restored historical targets through one vessel view."""
        live = {vessel.mmsi: vessel for vessel in self.provider.fetch_vessels()}
        now = datetime.now(timezone.utc)
        for mmsi, track in tracks.items():
            if mmsi in live or not track:
                continue
            latest = max(track, key=lambda observation: observation.received_at)
            live[mmsi] = VesselSnapshot(
                mmsi=mmsi,
                latitude=latest.latitude,
                longitude=latest.longitude,
                last_received=latest.received_at,
                sog_knots=latest.sog_knots,
                cog_degrees=latest.cog_degrees,
                heading_degrees=latest.heading_degrees,
                vessel_name=latest.vessel_name,
                message_count=len(track),
                stale=(now - latest.received_at).total_seconds() > self.settings.stale_after_seconds,
                ais_timestamp_second=latest.ais_timestamp_second,
                observed_at=latest.observed_at,
            )
        return sorted(live.values(), key=lambda vessel: vessel.last_received, reverse=True)

    def snapshot(self) -> EngineSnapshot:
        observations = self.store.all()
        tracks = self.store.tracks()
        vessels = self._merged_vessels(tracks)
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
            historical_status=self.historical_writer.status,
            historical_result=self.historical_result,
            temporal=self.temporal,
        )

    def clear_session_data(self) -> None:
        self.store.clear()
        self.provider.reset_session()
        self.embeddings = None
        self.findings = []
        self.temporal = None
        self._temporal_fingerprint = None
        self.last_collection_seconds = 0.0
        self.historical_result = None
        self._historical_loaded = True
        if self.settings.config_error or not self.settings.aisstream_api_key:
            self.provider.connect()


def create_engine(settings: AppSettings) -> MaritimeIntelligenceEngine:
    """Create an isolated engine for the current Streamlit session and region."""
    return MaritimeIntelligenceEngine(settings)
