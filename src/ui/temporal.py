"""Presentation-only helpers for real AIS temporal semantics.

Canonical storage remains UTC. Local conversions happen only when rendering
operator-facing labels; no converted value is written back to domain models.
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


OPERATOR_TIMEZONE_OPTIONS = (
    "UTC",
    "America/Sao_Paulo",
    "America/New_York",
    "Europe/London",
    "Europe/Amsterdam",
    "Asia/Singapore",
)


def to_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def format_received(value: datetime | None) -> str:
    value = to_utc(value)
    return value.strftime("%Y-%m-%d %H:%M:%S UTC") if value is not None else "UNAVAILABLE"


def format_region_or_operator(value: datetime | None, timezone_name: str) -> str:
    value = to_utc(value)
    if value is None:
        return "UNAVAILABLE"
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("UTC")
    return value.astimezone(zone).strftime("%Y-%m-%d %H:%M:%S %Z")


def format_ais_second(value: int | None) -> str:
    if value is None:
        return "UNAVAILABLE"
    if 0 <= value <= 59:
        return f"{value:02d}"
    if 60 <= value <= 63:
        return f"{value} (AIS special state)"
    return "UNAVAILABLE"


def format_observation_time(value: datetime | None) -> str:
    return format_received(value) if value is not None else "UNAVAILABLE"
