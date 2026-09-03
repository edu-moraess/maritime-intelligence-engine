"""Read-only hydration of persisted real AIS observations into a live session."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Sequence

from src.ingestion.models import AISObservation

from .writer import _database_url_for_connection

RegionBBox = tuple[tuple[float, float], tuple[float, float]]


def load_recent_observations(
    database_url: str | None,
    bbox: RegionBBox,
    *,
    limit: int = 3000,
    connect_fn: Callable[[str], Any] | None = None,
) -> list[AISObservation]:
    """Load recent persisted AIS observations for one monitoring bbox.

    This is intentionally read-only. Persisted observations are historical
    context only; they are never treated as live data and are merged into the
    bounded in-memory store through its normal deduplication path.
    """
    if not database_url or limit <= 0:
        return []

    (min_lat, min_lon), (max_lat, max_lon) = bbox
    connection = None
    try:
        connector = connect_fn or _default_connect
        connection = connector(database_url)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    o.session_id,
                    o.mmsi,
                    ST_Y(o.geom) AS latitude,
                    ST_X(o.geom) AS longitude,
                    o.received_at,
                    o.ais_timestamp_second,
                    o.observed_at,
                    o.sog_knots,
                    o.cog_degrees,
                    o.heading_degrees,
                    o.vessel_name,
                    o.navigational_status
                FROM ais_observations AS o
                WHERE o.valid = TRUE
                  AND o.geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326)
                  AND ST_Intersects(
                        o.geom,
                        ST_SetSRID(ST_MakeEnvelope(%s, %s, %s, %s, 4326), 4326)
                  )
                ORDER BY o.received_at DESC
                LIMIT %s
                """,
                (
                    float(min_lon),
                    float(min_lat),
                    float(max_lon),
                    float(max_lat),
                    float(min_lon),
                    float(min_lat),
                    float(max_lon),
                    float(max_lat),
                    int(limit),
                ),
            )
            rows = cursor.fetchall()

        return [
            _observation_from_row(row)
            for row in reversed(rows)
            if isinstance(row[4], datetime)
        ]
    except Exception:
        return []
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass


def load_recent_observations_for_bboxes(
    database_url: str | None,
    bboxes: Sequence[RegionBBox],
    *,
    limit: int = 3000,
    connect_fn: Callable[[str], Any] | None = None,
) -> list[AISObservation]:
    """Load recent persisted AIS history across multiple monitoring bboxes.

    Each region receives an equal hydration budget so a high-volume region
    cannot consume the entire temporal history. Overlapping bboxes are
    deduplicated before the final global limit is applied. With one bbox this
    delegates to the legacy loader, preserving the single-region path.
    """
    normalized = tuple(bboxes)
    if not database_url or limit <= 0 or not normalized:
        return []
    if len(normalized) == 1:
        return load_recent_observations(
            database_url,
            normalized[0],
            limit=limit,
            connect_fn=connect_fn,
        )

    per_region_limit = max(1, (int(limit) + len(normalized) - 1) // len(normalized))
    candidates: list[AISObservation] = []
    for bbox in normalized:
        candidates.extend(
            load_recent_observations(
                database_url,
                bbox,
                limit=per_region_limit,
                connect_fn=connect_fn,
            )
        )

    deduplicated: dict[tuple[Any, ...], AISObservation] = {}
    for observation in candidates:
        key = (
            observation.raw.get("session_id"),
            observation.mmsi,
            observation.received_at,
            observation.ais_timestamp_second,
            observation.latitude,
            observation.longitude,
        )
        deduplicated[key] = observation

    ordered = sorted(deduplicated.values(), key=lambda observation: observation.received_at)
    return ordered[-int(limit):]


def load_vessel_observations(
    database_url: str | None,
    mmsi: str,
    *,
    limit: int = 5000,
    connect_fn: Callable[[str], Any] | None = None,
) -> tuple[list[AISObservation], int]:
    """Load one vessel's persisted history and its distinct session count.

    The query is read-only and scoped to a single MMSI. Session identity is
    carried in ``raw['session_id']`` solely as provenance for the profile
    layer; it is never treated as provider payload or live telemetry.
    """
    if not database_url or not mmsi or limit <= 0:
        return [], 0

    connection = None
    try:
        connector = connect_fn or _default_connect
        connection = connector(database_url)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    o.session_id,
                    o.mmsi,
                    ST_Y(o.geom) AS latitude,
                    ST_X(o.geom) AS longitude,
                    o.received_at,
                    o.ais_timestamp_second,
                    o.observed_at,
                    o.sog_knots,
                    o.cog_degrees,
                    o.heading_degrees,
                    o.vessel_name,
                    o.navigational_status
                FROM ais_observations AS o
                WHERE o.valid = TRUE
                  AND o.mmsi = %s
                ORDER BY o.received_at ASC
                LIMIT %s
                """,
                (str(mmsi), int(limit)),
            )
            rows = cursor.fetchall()

        observations = [
            _observation_from_row(row)
            for row in rows
            if isinstance(row[4], datetime)
        ]
        session_count = len({str(row[0]) for row in rows if row[0] is not None})
        return observations, session_count
    except Exception:
        return [], 0
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass


def _observation_from_row(row: tuple[Any, ...]) -> AISObservation:
    (
        session_id,
        mmsi,
        latitude,
        longitude,
        received_at,
        ais_timestamp_second,
        observed_at,
        sog_knots,
        cog_degrees,
        heading_degrees,
        vessel_name,
        navigational_status,
    ) = row
    return AISObservation(
        mmsi=str(mmsi),
        latitude=float(latitude),
        longitude=float(longitude),
        received_at=received_at,
        sog_knots=_float_or_none(sog_knots),
        cog_degrees=_float_or_none(cog_degrees),
        heading_degrees=_float_or_none(heading_degrees),
        vessel_name=(str(vessel_name).strip() if vessel_name else None),
        message_type="PositionReport",
        valid=True,
        navigational_status=(
            int(navigational_status) if navigational_status is not None else None
        ),
        ais_timestamp_second=(
            int(ais_timestamp_second) if ais_timestamp_second is not None else None
        ),
        observed_at=observed_at,
        raw={"session_id": str(session_id)} if session_id is not None else {},
    )


def _default_connect(database_url: str) -> Any:
    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("PostgreSQL driver is not installed") from exc
    return psycopg.connect(
        _database_url_for_connection(database_url),
        connect_timeout=10,
    )


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return None
