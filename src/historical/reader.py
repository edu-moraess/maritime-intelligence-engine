"""Read-only hydration of persisted real AIS observations into a live session."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from src.ingestion.models import AISObservation

from .writer import _database_url_for_connection


def load_recent_observations(
    database_url: str | None,
    bbox: tuple[tuple[float, float], tuple[float, float]],
    *,
    limit: int = 3000,
    connect_fn: Callable[[str], Any] | None = None,
) -> list[AISObservation]:
    """Load recent persisted AIS observations for the active monitoring bbox.

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

        observations: list[AISObservation] = []
        for row in reversed(rows):
            (
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
            if not isinstance(received_at, datetime):
                continue
            observations.append(
                AISObservation(
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
                        int(navigational_status)
                        if navigational_status is not None
                        else None
                    ),
                    ais_timestamp_second=(
                        int(ais_timestamp_second)
                        if ais_timestamp_second is not None
                        else None
                    ),
                    observed_at=observed_at,
                    raw={},
                )
            )
        return observations
    except Exception:
        return []
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass


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
