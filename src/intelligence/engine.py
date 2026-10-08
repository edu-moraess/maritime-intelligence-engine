"""Orchestration layer used by Streamlit; no business logic is embedded in app.py."""

from __future__ import annotations

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
from src.ingestion.background import AISBackgroundService
from src.environment.alignment import EnvironmentalStateAlignmentEngine
from src.environment.context import EnvironmentalContext
from src.environment.features import EnvironmentalFeatures, derive_environmental_features
from src.environment.open_meteo_marine import OpenMeteoMarineProvider
from src.environment.copernicus_marine import CopernicusMarineProvider
from src.environment.open_meteo_weather import OpenMeteoWeatherProvider
from src.historical import HistoricalWriteResult, create_historical_writer
from src.historical.reader import load_recent_observations, load_recent_observations_for_bboxes
from src.historical.session_regions import persist_collection_session_regions
from src.ingestion.models import AISObservation, AnomalyFinding, IngestionStatus, VesselSnapshot
from src.geospatial.region_membership import membership
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
    environmental_features: dict[str, tuple[EnvironmentalFeatures, ...]] = field(default_factory=dict)


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
        self.provider = AISStreamProvider(api_key=settings.aisstream_api_key, bbox=settings.bbox_payload, max_messages=settings.max_messages, max_vessels=settings.max_vessels, stale_after_seconds=settings.stale_after_seconds, config_error=settings.config_error)
        self.background = AISBackgroundService(self.provider, queue_maxsize=settings.max_messages)
        self._background_last_flush = 0.0
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
        self.weather_provider = OpenMeteoWeatherProvider()
        self.copernicus_provider = CopernicusMarineProvider()
        self.environmental_contexts: dict[str, EnvironmentalContext] = {}
        self.environmental_features: dict[str, tuple[EnvironmentalFeatures, ...]] = {}
        self.environmental_alignment = EnvironmentalStateAlignmentEngine()
        self.temporal: TemporalFitResult | None = None
        self.region_comparison: RegionComparison | None = None
        self.regional_events: list[RegionalEvent] = []
        self._temporal_fingerprint: str | None = None
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
            restored = load_recent_observations_for_bboxes(self._historical_database_url, self.settings.monitoring_bboxes, limit=self.settings.max_messages, retention_days=self.settings.historical_retention_days)
        else:
            restored = load_recent_observations(self._historical_database_url, self.settings.bbox, limit=self.settings.max_messages, retention_days=self.settings.historical_retention_days)
        if not restored:
            return 0
        self.store.extend(restored)
        return len(restored)

    def start_background(self) -> bool:
        """Inicia ingestão contínua sem bloquear o thread do Streamlit."""
        self._restore_historical_context()
        return self.background.start()

    def stop_background(self) -> None:
        """Encerra o worker de ingestão e fecha o ciclo de rede."""
        self.background.stop()

    def refresh_background(self, *, force: bool = False, batch_interval_seconds: float = 45.0) -> int:
        """Drena um lote do worker e atualiza o estado analítico no thread da UI."""
        if not self.background.running and not force:
            return 0
        now = time.monotonic()
        if not force and now - self._background_last_flush < max(5.0, float(batch_interval_seconds)):
            return 0
        batch = self.background.drain(self.settings.max_messages)
        self._background_last_flush = now
        if not batch:
            return 0
        self.current_session_observations.extend(batch)
        self.store.extend(batch)
        started_at = min(o.received_at for o in batch)
        ended_at = max(o.received_at for o in batch)
        self.historical_result = self.historical_writer.persist_collection(
            batch,
            self.settings.bbox,
            max(0.0, (ended_at - started_at).total_seconds()),
            started_at,
            ended_at,
        )
        self._refresh_environmental_contexts()
        self._refresh_environmental_features()
        self._recompute()
        self.current_session_findings = self._detect_current_session_findings()
        return len(batch)

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
            timing = getattr(self.historical_writer, "last_timing", None)
            if timing is not None:
                breakdown["postgres_schema"] = timing.schema_seconds
                breakdown["postgres_session"] = timing.session_seconds
                breakdown["postgres_vessels"] = timing.vessel_seconds
                breakdown["postgres_staging"] = timing.staging_seconds
                breakdown["postgres_insert"] = timing.insert_seconds
                breakdown["postgres_commit"] = timing.commit_seconds

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
        self._refresh_environmental_features()
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
            previous = getattr(self, "environmental_contexts", {}).get(region)
            context = previous or EnvironmentalContext(region=region)
            latitude = (bbox[0][0] + bbox[1][0]) / 2.0
            longitude = (bbox[0][1] + bbox[1][1]) / 2.0
            providers = [
                provider
                for provider in (
                    getattr(self, "environmental_provider", None),
                    getattr(self, "weather_provider", None),
                )
                if provider is not None
            ]
            copernicus = getattr(self, "copernicus_provider", None)
            if copernicus is not None and copernicus.enabled:
                providers.append(copernicus)
            for provider in providers:
                try:
                    observation = provider.current(
                        latitude=latitude,
                        longitude=longitude,
                        region=region,
                    )
                    if all(
                        item.source != observation.source
                        or item.observed_at != observation.observed_at
                        for item in context.observations
                    ):
                        context = context.add(observation)
                except Exception:
                    # Environmental APIs are optional context; AIS remains authoritative.
                    continue
            context = EnvironmentalContext(
                region=region,
                observations=tuple(
                    sorted(
                        context.observations,
                        key=lambda item: (item.observed_at, item.source),
                    )[-4:]
                ),
            )
            contexts[region] = context
        self.environmental_contexts = contexts



    def _refresh_environmental_features(self) -> None:
        """Derive deterministic environmental features without changing anomaly scoring."""
        if not self.current_session_observations or not self.environmental_contexts:
            self.environmental_features = {}
            return

        features_by_mmsi: dict[str, list[EnvironmentalFeatures]] = {}
        for ais in self.current_session_observations:
            memberships = membership(
                ais.latitude, ais.longitude, self.settings.monitoring_bboxes
            )
            if len(memberships) != 1:
                continue
            region = f"region_{memberships[0] + 1}"
            context = self.environmental_contexts.get(region)
            if context is None:
                continue
            for alignment in self.environmental_alignment.align(ais, context):
                features = derive_environmental_features(
                    alignment, vessel_sog_knots=ais.sog_knots, vessel_cog_degrees=ais.cog_degrees
                )
                if features is not None:
                    features_by_mmsi.setdefault(ais.mmsi, []).append(features)

        self.environmental_features = {mmsi: tuple(items) for mmsi, items in features_by_mmsi.items()}
    def configure_historical_writer(self, database_url: str | None, persistence_enabled: bool) -> None:
        """Switch only the optional historical sink; preserve live state."""
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

    def _current_tracks(self) -> dict[str, list[AISObservation]]:
        return {
            mmsi: track
            for mmsi, track in self.store.tracks().items()
            if any(observation in self.current_session_observations for observation in track)
        }

    def _recompute(self) -> None:
        current_tracks = self._current_tracks()
        self.embeddings = self.embedding_adapter.fit(current_tracks)
        self.findings = detect_anomalies(current_tracks, self.embeddings)

        all_tracks = select_interesting_tracks(self.store.tracks())
        fingerprint = _track_fingerprint(all_tracks)
        if self.temporal is None or self._temporal_fingerprint != fingerprint:
            try:
                self.temporal = self.temporal_adapter.fit(all_tracks)
                self._temporal_fingerprint = fingerprint
            except Exception as exc:  # pragma: no cover - defensive isolation
                self.temporal = TemporalFitResult(
                    status="FAILED",
                    reason=f"Temporal path exception (classical path intact): {exc}",
                )
                self._temporal_fingerprint = fingerprint

        current_observations = list(self.current_session_observations)
        self.region_comparison = compare_regions(
            current_observations,
            self.findings,
            self.settings.monitoring_bboxes,
            self.temporal,
        ) if len(self.settings.monitoring_bboxes) == 2 else None

        current_tracks = self._current_tracks()
        self.regional_events = detect_regional_events(
            current_tracks,
            self.settings.monitoring_bboxes,
            findings=self.findings,
            environmental_contexts=self.environmental_contexts,
        ) if len(self.settings.monitoring_bboxes) == 2 else []

    def _detect_current_session_findings(self) -> list[AnomalyFinding]:
        current_tracks = self._current_tracks()
        if not current_tracks:
            return []
        embeddings = self.embedding_adapter.fit(current_tracks)
        return detect_anomalies(current_tracks, embeddings)

    def _readiness(self, tracks: dict[str, list[AISObservation]]) -> ReadinessSnapshot:
        tracks_with_history = sum(1 for track in tracks.values() if len(track) >= 2)
        temporal_status = self.temporal.status if self.temporal is not None else "WAITING"
        return ReadinessSnapshot(
            distinct_vessels=len(tracks),
            tracks_with_history=tracks_with_history,
            trajectory_ready=tracks_with_history >= 1,
            embeddings_ready=self.embeddings is not None,
            embedding_status="READY" if self.embeddings is not None else (
                "PARTIAL" if tracks_with_history else "WAITING"
            ),
            anomaly_count=len(self.findings),
            temporal_status=temporal_status,
        )

    def _merged_vessels(self, tracks: dict[str, list[AISObservation]]) -> list[VesselSnapshot]:
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
        current_observations = list(self.current_session_observations)
        tracks = self._current_tracks()
        vessels = self._merged_vessels(tracks)
        quality = build_quality_report(
            current_observations,
            self.settings.stale_after_seconds,
            self.store.duplicate_count,
        )
        return EngineSnapshot(
            observations=observations,
            vessels=vessels,
            findings=self.findings,
            quality=quality,
            status=replace(self.provider.status, active_vessels=len(vessels)),
            embeddings=self.embeddings,
            summary=traffic_summary(vessels, current_observations, self.findings),
            readiness=self._readiness(tracks),
            last_collection_seconds=self.last_collection_seconds,
            last_collection_breakdown=dict(self.last_collection_breakdown),
            historical_status=self.historical_writer.status,
            historical_result=self.historical_result,
            temporal=self.temporal,
            region_comparison=self.region_comparison,
            regional_events=list(self.regional_events),
            current_session_observations=current_observations,
            current_session_findings=list(self.current_session_findings),
            environmental_contexts=dict(self.environmental_contexts),
            environmental_features=dict(self.environmental_features),
        )

    def clear_session_data(self) -> None:
        self.background.stop()
        self.store.clear()
        self.current_session_observations.clear()
        self.current_session_findings.clear()
        self.provider.reset_session()
        self.embeddings = None
        self.findings = []
        self.temporal = None
        self.region_comparison = None
        self.regional_events = []
        self.environmental_contexts = {}
        self.environmental_features = {}
        self._temporal_fingerprint = None
        self._background_last_flush = 0.0
        self.last_collection_seconds = 0.0
        self.last_collection_breakdown = {}
        self.historical_result = None
        self._historical_loaded = True
        if self.settings.config_error or not self.settings.aisstream_api_key:
            self.provider.connect()


def create_engine(settings: AppSettings) -> MaritimeIntelligenceEngine:
    """Create an isolated engine for the current Streamlit session and region."""
    return MaritimeIntelligenceEngine(settings)
