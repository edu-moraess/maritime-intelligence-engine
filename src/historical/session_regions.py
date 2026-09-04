"""Persistence helpers for exact monitoring regions used by a collection session."""

from __future__ import annotations

import logging
from typing import Any, Callable, Sequence
from uuid import UUID

from .writer import _database_url_for_connection

LOGGER = logging.getLogger(__name__)
RegionBBox = tuple[tuple[float, float], tuple[float, float]]


def persist_collection_session_regions(
    database_url: str | None,
    session_id: str | UUID | None,
    bboxes: Sequence[RegionBBox],
    *,
    connect_fn: Callable[[str], Any] | None = None,
) -> bool:
    """Persist the exact A/B monitoring boxes for an already-written session.

    The legacy ``collection_sessions.bbox`` column remains untouched for
    compatibility. This side table is authoritative for multi-region
    provenance and is intentionally idempotent.
    """
    if not database_url or session_id is None or not bboxes:
        return False

    connection = None
    try:
        connector = connect_fn or _default_connect
        connection = connector(database_url)
        with connection.cursor() as cursor:
            for index, bbox in enumerate(bboxes):
                (min_lat, min_lon), (max_lat, max_lon) = bbox
                cursor.execute(
                    """
                    INSERT INTO collection_session_regions (session_id, region_index, bbox)
                    VALUES (%s, %s, ST_MakeEnvelope(%s, %s, %s, %s, 4326))
                    ON CONFLICT (session_id, region_index) DO UPDATE SET bbox = EXCLUDED.bbox
                    """,
                    (
                        str(session_id),
                        int(index),
                        float(min_lon),
                        float(min_lat),
                        float(max_lon),
                        float(max_lat),
                    ),
                )
        connection.commit()
        return True
    except Exception:
        LOGGER.exception("Failed to persist collection session monitoring regions")
        if connection is not None:
            try:
                connection.rollback()
            except Exception:
                pass
        return False
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
