"""Orchestration layer used by Streamlit; no business logic is embedded in app.py."""

from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone

from src.analytics.region_comparison import RegionComparison, compare_regions
from src.analytics.regional_events import RegionalEvent, detect_regional_events
from src.analytics.traffic import traffic_summary
from src.anomaly.detector import detect_anomalies
from src.config.settings import AppSettings
from src.ingestion.aisstream import AISStreamProvider
from src.environment.context import EnvironmentalContext
from src.environment.open_meteo_marine import OpenMeteoMarineProvider
from src.historical import HistoricalWriteResult, create_historical_writer
from src.historical.reader import load_recent_observations, load_recent_observations_for_bboxes
from src.historical.session_regions import persist_collection_session_regions
from src.ingestion.models import AISObservation, AnomalyFinding, IngestionStatus, VesselSnapshot
from src.ml.embeddings import EmbeddingResult, TrajectoryEmbeddingAdapter
from src.ml.temporal import TemporalAnomalyAdapter
from src.ml.temporal.types import TemporalFitResult
from src.processing.quality import QualityReport, build_quality_report
from src.processing.relevance import select_interesting_tracks
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
    last_collection_breakdown: dict[str, float]
    historical_status: str
    historical_result: HistoricalWriteResult | None
    temporal: TemporalFitResult | None = None
    region_comparison: RegionComparison | None = None
    regional_events: list[RegionalEvent] = field(default_factory=list)
    current_session_observations: list[AISObservation] = field(default_factory=list)
    current_session_findings: list[AnomalyFinding] = field(default_factory=list)
    environmental_contexts: dict[str, EnvironmentalContext] = field(default_factory=dict)


# Temporal outcomes that are deterministic functions of model inputs may be cached.
# FAILED (possibly transient) and UNAVAILABLE (environment dependent) are retried.
_CACHEABLE_TEMPORAL_STATUSES = frozenset({"READY", "NOT_READY", "WAITING"})


def _observation_signature(observation: AISObservation) -> str:
    """Canonical text of every observation field relevant to temporal processing."""
    observed_at = observation.observed_at.isoformat() if observation.observed_at is not None else "-"
    return "|".join((
        observation.received_at.isoformat(),
        repr(observation.latitude),
        repr(observation.longitude),
        repr(observation.sog_knots),
        repr(observation.cog_degrees),
        repr(observation.heading_degrees),
        repr(observation.ais_timestamp_second),
        repr(observation.navigational_status),
        "1" if observation.valid else "0",
        observed_at,
    ))


def _track_fingerprint(tracks: dict[str, list[AISObservation]]) -> str:
    """SHA-256 of the exact ordered content of the supplied model tracks."""
    digest = hashlib.sha256()
    for mmsi in sorted(tracks):
        # Stable sorting preserves the temporal pipeline's input order for ties.
        ordered = sorted(tracks[mmsi], key=lambda observation: observation.received_at)
        if not ordered:
            continue
        digest.update(f"T|{mmsi}|{len(ordered)}\n".encode("utf-8"))
        for observation in ordered:
            digest.update(_observation_signature(observation).encode("utf-8"))
            digest.update(b"\n")
    return digest.hexdigest()


class MaritimeIntelligenceEngine:
    """Session-scoped coordinator for one real AIS monitoring region."""
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.provider = AISStreamProvider(api_key=settings.aisstream_api_key, bbox=settings.bbox_payload, max_messages=settings.max_messages, max_vessels=settings.max_vessels, stale_after_seconds=settings.stale_after_seconds, config_error=settings.config_error)
        self.store = ObservationStore(max_messages=settings.max_messages, max_vessels=settings.max_vessels)
        self.embedding_adapter = TrajectoryEmbeddingAdapter()
        self.temporal_adapter = TemporalAnomalyAdapter()
        ready, reason = settings.validate_for_connection()
        if not ready:
            self.provider.config_error = reason
            self.provider.connect()
        self.embeddings: EmbeddingResult | None = None
        self.findings: list[AnomalyFinding] = []
        self.current_session_findings: list[AnomalyFinding] = []
        self.current_session_observations: list[AISObservation] = []
        self.environmental_provider = OpenMeteoMarineProvider()
        self.environmental_contexts: dict[str, EnvironmentalContext] = {}
        self.temporal: TemporalFitResult | None = None
        self.region_comparison: RegionComparison | None = None
        self.regional_events: list[RegionalEvent] = []
        self._temporal_fingerprint: str | None = None
        self._session_generation: int = 0
        self.last_collection_seconds: float = 0.0
        self.last_collection_breakdown: dict[str, float] = {}
        self._historical_database_url = settings.database_url
        self._historical_persistence_enabled = settings.historical_persistence_enabled
        self._historical_loaded = False
        self.historical_writer = create_historical_writer(settings.database_url, settings.historical_persistence_enabled)
        self.historical_result: HistoricalWriteResult | None = None
        # Historical hydration is deliberately lazy. The first Streamlit render
        # must not block on Postgres or run the ML/temporal recompute path.
        # Persistence is still loaded before live collection processing.

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
        if len(self.settings.monitoring_bboxes) > 1:
            restored = load_recent_observations_for_bboxes(self._historical_database_url, self.settings.monitoring_bboxes, limit=self.settings.max_messages)
        else:
            restored = load_recent_observations(self._historical_database_url, self.settings.bbox, limit=self.settings.max_messages)
        if not restored:
            return 0
        self.store.extend(restored)
        self._recompute()
        return len(restored)

    def collect(self, seconds: float | None = None) -> int:
        """Collect a bounded real-time window starting immediately at operator action.

        Historical hydration is intentionally performed after the live window so
        database latency cannot consume any part of the operator-selected AIS
        collection duration.
        """
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
        collection_elapsed = min(duration, max(0.0, time.monotonic() - started))
        self.last_collection_seconds = collection_elapsed
        ended_at = datetime.now(timezone.utc)
        breakdown: dict[str, float] = {"ais_stream": collection_elapsed}

        # Restore persisted real AIS only after the live window has finished.
        # This keeps the selected 60/300/600 s window anchored to the operator
        # action rather than to database/network hydration latency.
        phase_started = time.monotonic()
        self._restore_historical_context()
        breakdown["historical_restore"] = time.monotonic() - phase_started

        self.current_session_observations = list(collected)
        self._session_generation += 1
        self.current_session_findings = []
        if collected:
            self.store.extend(collected)

            phase_started = time.monotonic()
            self.historical_result = self.historical_writer.persist_collection(
                collected,
                self.settings.bbox,
                collection_elapsed,
                started_at,
                ended_at,
            )
            breakdown["postgres_persist"] = time.monotonic() - phase_started

            if (
                self.historical_result.session_id is not None
                and self._historical_persistence_enabled
                and len(self.settings.monitoring_bboxes) > 1
            ):
                phase_started = time.monotonic()
                regions_persisted = persist_collection_session_regions(
                    self._historical_database_url,
                    self.historical_result.session_id,
                    self.settings.monitoring_bboxes,
                )
                breakdown["region_persist"] = time.monotonic() - phase_started
                if not regions_persisted:
                    self.historical_result = replace(
                        self.historical_result,
                        reason=(
                            f"{self.historical_result.reason} "
                            "Exact multi-region session provenance could not be persisted."
                        ),
                    )
            else:
                breakdown["region_persist"] = 0.0
        else:
            self.historical_result = None
            breakdown["postgres_persist"] = 0.0
            breakdown["region_persist"] = 0.0

        phase_started = time.monotonic()
        self._refresh_environmental_contexts()
        breakdown["environmental"] = time.monotonic() - phase_started

        phase_started = time.monotonic()
        self._recompute()
        breakdown["recompute"] = time.monotonic() - phase_started

        phase_started = time.monotonic()
        self.current_session_findings = self._detect_current_session_findings()
        breakdown["findings"] = time.monotonic() - phase_started

        breakdown["total"] = time.monotonic() - started
        self.last_collection_breakdown = breakdown
        return len(collected)

    def _refresh_environmental_contexts(self) -> None:
        """Fetch real marine context and retain only the latest two observations per region."""
        contexts: dict[str, EnvironmentalContext] = {}
        for index, bbox in enumerate(self.settings.monitoring_bboxes, start=1):
            region = f"region_{index}"
            previous = self.environmental_contexts.get(region)
            context = previous or EnvironmentalContext(region=region)
            latitude = (bbox[0][0] + bbox[1][0]) / 2.0
            longitude = (bbox[0][1] + bbox[1][1]) / 2.0
            try:
                observation = self.environmental_provider.current(
                    latitude=latitude,
                    longitude=longitude,
                    region=region,
                )
                if all(item.reference_time != observation.reference_time for item in context.observations):
                    context = context.add(observation)
                context = EnvironmentalContext(
                    region=region,
                    observations=tuple(
                        sorted(
                            context.observations,
                            key=lambda item: item.reference_time,
                        )[-2:]
                    ),
                )
            except Exception:
                pass
            contexts[region] = context
        self.environmental_contexts = contexts
    def _current_session_tracks(self) -> dict[str, list[AISObservation]]:
        """Return only observations collected in the latest live window."""
        tracks: dict[str, list[AISObservation]] = {}
        for observation in self.current_session_observations:
            tracks.setdefault(observation.mmsi, []).append(observation)
        return tracks

    def _detect_current_session_findings(self) -> list[AnomalyFinding]:
        """Detect findings only from observations collected in the latest window."""
        tracks = self._current_session_tracks()
        if not tracks:
            return []
        return detect_anomalies(tracks, self.embeddings)

    def configure_historical_writer(self, database_url: str | None, persistence_enabled: bool) -> None:
        """Switch only the optional historical sink; preserve all live state."""
        if database_url == self._historical_database_url and persistence_enabled == self._historical_persistence_enabled:
            return
        self.historical_writer.close()
        self._historical_database_url = database_url
        self._historical_persistence_enabled = persistence_enabled
        self._historical_loaded = False
        self.historical_writer = create_historical_writer(database_url, persistence_enabled)
        self.historical_result = None
        self.settings = replace(self.settings, database_url=database_url, historical_persistence_enabled=persistence_enabled)

    def _temporal_config_signature(self) -> str:
        """Configuration of the temporal adapter that influences its result."""
        adapter = self.temporal_adapter
        names = (
            "minimum_tracks", "minimum_points_per_track", "sequence_length",
            "input_dim", "max_training_seconds", "seed", "training_config",
        )
        return "|".join(f"{name}={getattr(adapter, name, None)!r}" for name in names)

    def _temporal_cache_key(self, model_tracks: dict[str, list[AISObservation]]) -> str:
        """Identity of model input, session, monitoring regions, and adapter config."""
        digest = hashlib.sha256()
        for part in (
            f"tracks={_track_fingerprint(model_tracks)}",
            f"session={self._session_generation}",
            f"bbox={self.settings.bbox!r}",
            f"regions={self.settings.monitoring_bboxes!r}",
            f"config={self._temporal_config_signature()}",
        ):
            digest.update(part.encode("utf-8"))
            digest.update(b"\n")
        return digest.hexdigest()

    def _recompute(self) -> None:
        # Keep every real AIS observation in the store for persistence and
        # cross-session context, but fit session-relative analytics only on the
        # latest operator-triggered live window.
        tracks = self._current_session_tracks()
        model_tracks = select_interesting_tracks(tracks)
        self.embeddings = self.embedding_adapter.fit(model_tracks)
        self.findings = detect_anomalies(model_tracks, self.embeddings)
        cache_key = self._temporal_cache_key(model_tracks)
        if (
            self.temporal is not None
            and self.temporal.status in _CACHEABLE_TEMPORAL_STATUSES
            and self._temporal_fingerprint == cache_key
        ):
            self.region_comparison = self._build_region_comparison()
            self.regional_events = self._build_regional_events(
                tracks,
                findings=self.findings,
                environmental_contexts=self.environmental_contexts,
            )
            return
        try:
            self.temporal = self.temporal_adapter.fit(model_tracks)
        except Exception as exc:
            self.temporal = TemporalFitResult(status="FAILED", reason=f"Temporal path exception (classical path intact): {exc}")
        self._temporal_fingerprint = (
            cache_key if self.temporal.status in _CACHEABLE_TEMPORAL_STATUSES else None
        )
        self.region_comparison = self._build_region_comparison()
        self.regional_events = self._build_regional_events(
            tracks,
            findings=self.findings,
            environmental_contexts=self.environmental_contexts,
        )

    def _build_region_comparison(self) -> RegionComparison | None:
        if len(self.settings.monitoring_bboxes) != 2:
            return None
        return compare_regions(self.current_session_observations, self.findings, self.settings.monitoring_bboxes, temporal=self.temporal)
    def _build_regional_events(
        self,
        tracks: dict[str, list[AISObservation]],
        *,
        findings: list[AnomalyFinding] | None = None,
        environmental_contexts: dict[str, EnvironmentalContext] | None = None,
    ) -> list[RegionalEvent]:
        if len(self.settings.monitoring_bboxes) != 2:
            return []
        return detect_regional_events(
            tracks,
            self.settings.monitoring_bboxes,
            findings=findings or (),
            environmental_contexts=environmental_contexts,
        )

    def _readiness(self, tracks: dict[str, list[AISObservation]]) -> ReadinessSnapshot:
        tracks_with_history = sum(1 for track in tracks.values() if len(track) >= 2)
        temporal_status = self.temporal.status if self.temporal is not None else "WAITING"
        return ReadinessSnapshot(distinct_vessels=len(tracks), tracks_with_history=tracks_with_history, trajectory_ready=tracks_with_history >= 1, embeddings_ready=self.embeddings is not None, embedding_status="READY" if self.embeddings is not None else ("PARTIAL" if tracks_with_history else "WAITING"), anomaly_count=len(self.findings), temporal_status=temporal_status)

    def _merged_vessels(self, tracks: dict[str, list[AISObservation]]) -> list[VesselSnapshot]:
        """Build the operational vessel view from the latest live session only."""
        now = datetime.now(timezone.utc)
        vessels: list[VesselSnapshot] = []
        for mmsi, track in tracks.items():
            if not track:
                continue
            latest = max(track, key=lambda observation: observation.received_at)
            vessels.append(
                VesselSnapshot(
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
            )
        return sorted(vessels, key=lambda vessel: vessel.last_received, reverse=True)[: self.settings.max_vessels]

    def snapshot(self) -> EngineSnapshot:
        observations = self.store.all()
        analysis_tracks = self._current_session_tracks()
        vessels = self._merged_vessels(analysis_tracks)
        quality = build_quality_report(observations, self.settings.stale_after_seconds, self.store.duplicate_count)
        status = replace(self.provider.status, active_vessels=len(analysis_tracks))
        return EngineSnapshot(
            observations=observations,
            vessels=vessels,
            findings=self.findings,
            quality=quality,
            status=status,
            embeddings=self.embeddings,
            summary=traffic_summary(
                vessels,
                self.current_session_observations,
                self.findings,
            ),
            readiness=self._readiness(analysis_tracks),
            last_collection_seconds=self.last_collection_seconds,
            last_collection_breakdown=dict(self.last_collection_breakdown),
            historical_status=self.historical_writer.status,
            historical_result=self.historical_result,
            temporal=self.temporal,
            region_comparison=self.region_comparison,
            regional_events=list(self.regional_events),
            current_session_observations=list(self.current_session_observations),
            current_session_findings=list(self.current_session_findings),
            environmental_contexts=dict(self.environmental_contexts),
        )

    def clear_session_data(self) -> None:
        self.store.clear()
        self.provider.reset_session()
        self.embeddings = None
        self.findings = []
        self.current_session_findings = []
        self.current_session_observations = []
        self.environmental_contexts = {}
        self.temporal = None
        self.region_comparison = None
        self.regional_events = []
        self._temporal_fingerprint = None
        self._session_generation += 1
        self.last_collection_seconds = 0.0
        self.last_collection_breakdown = {}
        self.historical_result = None
        self._historical_loaded = True
        if self.settings.config_error or not self.settings.aisstream_api_key:
            self.provider.connect()


def create_engine(settings: AppSettings) -> MaritimeIntelligenceEngine:
    return MaritimeIntelligenceEngine(settings)
