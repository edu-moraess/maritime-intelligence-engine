"""Optional, fail-safe historical persistence for real AIS observations.

The live ObservationStore remains the source of truth for the running
intelligence session. This module is only a sink for validated observations
that were actually received from AISStream.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID, uuid4

from src.config.regions import region_name_for_bbox
from src.ingestion.models import AISObservation
from src.processing.quality import validate_observation

LOGGER = logging.getLogger(__name__)
DEFAULT_PIPELINE_VERSION = "mie-v2-e2"
DEFAULT_MIGRATION_DIR = Path(__file__).resolve().parents[2] / "migrations"


@dataclass(frozen=True)
class HistoricalWriteResult:
    status: str
    session_id: str | None
    persisted_observations: int
    duplicate_observations: int
    skipped_invalid: int
    reason: str


class HistoricalWriter(ABC):
    """Sink interface that never owns or replaces live session state."""

    @property
    @abstractmethod
    def status(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def enabled(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def persist_collection(
        self,
        observations: Iterable[AISObservation],
        bbox: tuple[tuple[float, float], tuple[float, float]],
        collection_seconds: float,
        started_at: datetime,
        ended_at: datetime,
    ) -> HistoricalWriteResult:
        raise NotImplementedError

    def close(self) -> None:
        """Release an optional connection; live state is unaffected."""


class NullHistoricalWriter(HistoricalWriter):
    """No-op sink used when historical persistence is unavailable or disabled."""

    def __init__(
        self,
        status: str = "HISTORICAL DATABASE NOT CONFIGURED",
        reason: str = "DATABASE_URL is not configured; live session remains LIVE-ONLY.",
    ) -> None:
        self._status = status
        self._reason = reason

    @property
    def status(self) -> str:
        return self._status

    @property
    def enabled(self) -> bool:
        return False

    def persist_collection(
        self,
        observations: Iterable[AISObservation],
        bbox: tuple[tuple[float, float], tuple[float, float]],
        collection_seconds: float,
        started_at: datetime,
        ended_at: datetime,
    ) -> HistoricalWriteResult:
        return HistoricalWriteResult(
            status=self.status,
            session_id=None,
            persisted_observations=0,
            duplicate_observations=0,
            skipped_invalid=0,
            reason=self._reason,
        )


class PostgresHistoricalWriter(HistoricalWriter):
    """Lazy PostgreSQL/PostGIS writer with idempotent observation inserts."""

    def __init__(
        self,
        database_url: str,
        *,
        connect_fn: Callable[[str], Any] | None = None,
        migration_dir: Path | None = None,
        pipeline_version: str = DEFAULT_PIPELINE_VERSION,
    ) -> None:
        self.database_url = database_url
        self._connect_fn = connect_fn or _default_connect
        self._migration_dir = migration_dir or DEFAULT_MIGRATION_DIR
        self.pipeline_version = pipeline_version
        self._connection: Any | None = None
        self._status = "HISTORICAL PERSISTENCE ENABLED"
        self.last_result: HistoricalWriteResult | None = None

    @property
    def status(self) -> str:
        return self._status

    @property
    def enabled(self) -> bool:
        return True

    def persist_collection(
        self,
        observations: Iterable[AISObservation],
        bbox: tuple[tuple[float, float], tuple[float, float]],
        collection_seconds: float,
        started_at: datetime,
        ended_at: datetime,
    ) -> HistoricalWriteResult:
        all_observations = list(observations)
        valid_observations = [obs for obs in all_observations if not validate_observation(obs)]
        skipped_invalid = len(all_observations) - len(valid_observations)
        if not valid_observations:
            result = HistoricalWriteResult(
                status=self.status,
                session_id=None,
                persisted_observations=0,
                duplicate_observations=0,
                skipped_invalid=skipped_invalid,
                reason="No valid real AIS observations were available for historical persistence.",
            )
            self.last_result = result
            return result

        session_id = uuid4()
        try:
            connection = self._get_connection()
            self._ensure_schema(connection)
            persisted = 0
            duplicates = 0
            with connection.cursor() as cursor:
                region_id = self._region_id(cursor, region_name_for_bbox(bbox))
                cursor.execute(
                    """
                    INSERT INTO collection_sessions
                        (session_id, region_id, bbox, started_at, ended_at, collection_seconds,
                         messages_received, pipeline_version, source)
                    VALUES (%s, %s, ST_MakeEnvelope(%s, %s, %s, %s, 4326), %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        session_id,
                        region_id,
                        float(bbox[0][1]),
                        float(bbox[0][0]),
                        float(bbox[1][1]),
                        float(bbox[1][0]),
                        _utc(started_at),
                        _utc(ended_at),
                        max(0.0, float(collection_seconds)),
                        len(valid_observations),
                        self.pipeline_version,
                        "AISSTREAM",
                    ),
                )
                for observation in valid_observations:
                    cursor.execute(
                        """
                        INSERT INTO vessels (mmsi, last_known_name, first_seen_at, last_seen_at)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (mmsi) DO UPDATE SET
                            last_known_name = CASE
                                WHEN EXCLUDED.last_known_name IS NOT NULL
                                     AND EXCLUDED.last_known_name <> ''
                                THEN EXCLUDED.last_known_name
                                ELSE vessels.last_known_name
                            END,
                            first_seen_at = LEAST(vessels.first_seen_at, EXCLUDED.first_seen_at),
                            last_seen_at = GREATEST(vessels.last_seen_at, EXCLUDED.last_seen_at)
                        """,
                        (
                            observation.mmsi,
                            observation.vessel_name.strip() if observation.vessel_name and observation.vessel_name.strip() else None,
                            _utc(observation.received_at),
                            _utc(observation.received_at),
                        ),
                    )
                    payload_hash = observation_payload_hash(observation)
                    cursor.execute(
                        """
                        INSERT INTO ais_observations
                            (session_id, mmsi, geom, received_at, ais_timestamp_second, observed_at,
                             sog_knots, cog_degrees, heading_degrees, vessel_name,
                             navigational_status, valid, payload_hash)
                        VALUES (%s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s, %s, %s,
                                %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (session_id, payload_hash) DO NOTHING
                        RETURNING observation_id
                        """,
                        (
                            session_id,
                            observation.mmsi,
                            float(observation.longitude),
                            float(observation.latitude),
                            _utc(observation.received_at),
                            observation.ais_timestamp_second,
                            _utc(observation.observed_at),
                            observation.sog_knots,
                            observation.cog_degrees,
                            observation.heading_degrees,
                            observation.vessel_name.strip() if observation.vessel_name and observation.vessel_name.strip() else None,
                            observation.navigational_status,
                            bool(observation.valid),
                            payload_hash,
                        ),
                    )
                    if cursor.fetchone() is None:
                        duplicates += 1
                    else:
                        persisted += 1
            connection.commit()
            self._status = "HISTORICAL DATABASE AVAILABLE"
            result = HistoricalWriteResult(
                status=self.status,
                session_id=str(session_id),
                persisted_observations=persisted,
                duplicate_observations=duplicates,
                skipped_invalid=skipped_invalid,
                reason="Validated real AIS observations persisted idempotently.",
            )
            self.last_result = result
            return result
        except Exception as exc:
            self._rollback_and_close()
            self._status = "HISTORICAL DATABASE UNAVAILABLE"
            LOGGER.exception("Historical persistence failed")
            result = HistoricalWriteResult(
                status=self.status,
                session_id=None,
                persisted_observations=0,
                duplicate_observations=0,
                skipped_invalid=skipped_invalid,
                reason=f"Historical persistence failed ({type(exc).__name__}): {exc}",
            )
            self.last_result = result
            return result

    def _get_connection(self) -> Any:
        if self._connection is None or getattr(self._connection, "closed", False):
            self._connection = self._connect_fn(self.database_url)
        return self._connection

    def _ensure_schema(self, connection: Any) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS mie_schema_migrations (
                    version TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            for migration in sorted(self._migration_dir.glob("*.sql")):
                cursor.execute("SELECT 1 FROM mie_schema_migrations WHERE version = %s", (migration.name,))
                if cursor.fetchone() is not None:
                    continue
                _execute_sql_script(cursor, migration.read_text(encoding="utf-8"))
                cursor.execute(
                    "INSERT INTO mie_schema_migrations (version) VALUES (%s)",
                    (migration.name,),
                )
        connection.commit()

    @staticmethod
    def _region_id(cursor: Any, region_name: str | None) -> int | None:
        if not region_name:
            return None
        cursor.execute("SELECT region_id FROM regions WHERE name = %s", (region_name,))
        row = cursor.fetchone()
        return int(row[0]) if row else None

    def _rollback_and_close(self) -> None:
        if self._connection is None:
            return
        try:
            self._connection.rollback()
        except Exception:
            pass
        try:
            self._connection.close()
        except Exception:
            pass
        self._connection = None

    def close(self) -> None:
        if self._connection is not None:
            try:
                self._connection.close()
            except Exception:
                pass
            self._connection = None


@dataclass(frozen=True)
class DatabaseDiagnostics:
    """Sanitized connectivity probe for PostgreSQL/PostGIS. Never includes secrets."""

    database_url_status: str
    postgresql_status: str
    postgis_status: str
    historical_write_status: str
    postgresql_version: str | None = None
    postgis_version: str | None = None
    detail: str = ""


def diagnose_database(
    database_url: str | None,
    *,
    historical_persistence_enabled: bool = False,
    connect_fn: Callable[[str], Any] | None = None,
) -> DatabaseDiagnostics:
    """Read-only connectivity check. Runs only SELECT version() / PostGIS_Version().

    Does not apply migrations, create tables, or write any rows.
    """
    write_status = "ON" if historical_persistence_enabled else "OFF"
    if not database_url:
        return DatabaseDiagnostics(
            database_url_status="ABSENT",
            postgresql_status="UNAVAILABLE",
            postgis_status="UNAVAILABLE",
            historical_write_status=write_status,
            detail="DATABASE_URL is not configured in the application runtime.",
        )

    connection = None
    try:
        connector = connect_fn or _default_connect
        connection = connector(database_url)
        with connection.cursor() as cursor:
            cursor.execute("SELECT version()")
            pg_row = cursor.fetchone()
            pg_version = str(pg_row[0]).split(",")[0].strip() if pg_row and pg_row[0] else "unknown"
            try:
                cursor.execute("SELECT PostGIS_Version()")
                postgis_row = cursor.fetchone()
                postgis_version = str(postgis_row[0]).strip() if postgis_row and postgis_row[0] else None
                postgis_status = "AVAILABLE" if postgis_version else "UNAVAILABLE"
            except Exception:
                postgis_version = None
                postgis_status = "UNAVAILABLE"
        return DatabaseDiagnostics(
            database_url_status="PRESENT",
            postgresql_status="CONNECTED",
            postgis_status=postgis_status,
            historical_write_status=write_status,
            postgresql_version=pg_version,
            postgis_version=postgis_version,
            detail="Read-only connectivity probe succeeded. No migrations or writes were executed.",
        )
    except Exception as exc:
        LOGGER.warning("Database diagnostics failed without exposing connection details.")
        return DatabaseDiagnostics(
            database_url_status="PRESENT",
            postgresql_status="UNAVAILABLE",
            postgis_status="UNAVAILABLE",
            historical_write_status=write_status,
            detail="Connection error: authentication/connection failure",
        )
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass


def create_historical_writer(database_url: str | None, persistence_enabled: bool = False) -> HistoricalWriter:
    if not database_url:
        return NullHistoricalWriter(
            "HISTORICAL DATABASE NOT CONFIGURED",
            "DATABASE_URL is not configured; live session remains LIVE-ONLY.",
        )
    if not persistence_enabled:
        return NullHistoricalWriter(
            "HISTORICAL PERSISTENCE OFF",
            "Historical persistence is disabled by configuration; live session remains LIVE-ONLY.",
        )
    return PostgresHistoricalWriter(database_url)


def observation_payload_hash(observation: AISObservation) -> str:
    """Stable deduplication key derived from the real provider payload."""
    payload = observation.raw if observation.raw else observation.as_dict()
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return sha256(canonical.encode("utf-8")).hexdigest()


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("historical timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def _database_url_for_connection(database_url: str) -> str:
    """Require SSL for remote PostgreSQL without changing local development URLs."""
    parsed = urlsplit(database_url)
    if parsed.hostname in {None, "localhost", "127.0.0.1", "::1"}:
        return database_url
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if query.get("sslmode", "").lower() in {"", "disable"}:
        query["sslmode"] = "require"
    return urlunsplit(parsed._replace(query=urlencode(query)))


def _execute_sql_script(cursor: Any, script: str) -> None:
    """Execute a semicolon-delimited SQL script safely with a DB cursor.

    psycopg supports a single statement reliably across versions; migrations
    are therefore split here rather than relying on multi-statement execution.
    The splitter ignores semicolons inside quoted SQL literals/identifiers.
    """
    statement: list[str] = []
    in_single_quote = False
    in_double_quote = False
    index = 0
    while index < len(script):
        character = script[index]
        if character == "'" and not in_double_quote:
            statement.append(character)
            if in_single_quote and index + 1 < len(script) and script[index + 1] == "'":
                statement.append(script[index + 1])
                index += 2
                continue
            in_single_quote = not in_single_quote
        elif character == '"' and not in_single_quote:
            statement.append(character)
            if in_double_quote and index + 1 < len(script) and script[index + 1] == '"':
                statement.append(script[index + 1])
                index += 2
                continue
            in_double_quote = not in_double_quote
        elif character == ";" and not in_single_quote and not in_double_quote:
            sql = "".join(statement).strip()
            if sql:
                cursor.execute(sql)
            statement = []
        else:
            statement.append(character)
        index += 1
    sql = "".join(statement).strip()
    if sql:
        cursor.execute(sql)


def _default_connect(database_url: str) -> Any:
    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover - depends on deployment package set
        raise RuntimeError("PostgreSQL driver is not installed") from exc
    return psycopg.connect(_database_url_for_connection(database_url), connect_timeout=10)
