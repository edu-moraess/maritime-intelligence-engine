"""Runtime configuration for the real-AIS-only application."""

from __future__ import annotations

import os
from dataclasses import dataclass
from math import isfinite
from typing import Any


# Semantic order is (min_lat, min_lon) then (max_lat, max_lon).
DEFAULT_BBOX = ((25.603, -80.208), (25.835, -79.879))
DEFAULT_COLLECTION_SECONDS = 60.0
MIN_COLLECTION_SECONDS = 30.0
MAX_COLLECTION_SECONDS = 900.0
COLLECTION_DURATION_OPTIONS = (30, 60, 120, 180, 300, 600, 900)


def _secret_or_env(name: str, secrets: Any | None = None) -> str:
    """Read a secret from Streamlit Secrets first, then from the local environment."""
    if secrets is not None:
        try:
            value = secrets.get(name)
            if value is not None and str(value) != "":
                return str(value)
        except Exception:
            pass
    return os.getenv(name, "")


def _bool_setting(name: str, default: bool = False, secrets: Any | None = None) -> bool:
    """Parse an explicit opt-in flag; unknown values fail closed."""
    raw = _secret_or_env(name, secrets).strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "y", "on"}


RegionBBox = tuple[tuple[float, float], tuple[float, float]]


@dataclass(frozen=True)
class AppSettings:
    """Application settings; no setting creates or substitutes AIS observations."""

    aisstream_api_key: str
    bbox: RegionBBox = DEFAULT_BBOX
    monitoring_bboxes: tuple[RegionBBox, ...] = (DEFAULT_BBOX,)
    collection_seconds: float = DEFAULT_COLLECTION_SECONDS
    max_messages: int = 3000
    max_vessels: int = 1000
    stale_after_seconds: int = 180
    provider: str = "aisstream"
    config_error: str | None = None
    database_url: str | None = None
    historical_persistence_enabled: bool = False

    @classmethod
    def from_runtime(cls, secrets: Any | None = None) -> "AppSettings":
        values = {
            "min_lat": _secret_or_env("AIS_AREA_MIN_LAT", secrets),
            "min_lon": _secret_or_env("AIS_AREA_MIN_LON", secrets),
            "max_lat": _secret_or_env("AIS_AREA_MAX_LAT", secrets),
            "max_lon": _secret_or_env("AIS_AREA_MAX_LON", secrets),
        }
        bbox = DEFAULT_BBOX
        config_error: str | None = None
        supplied = [values[key] for key in ("min_lat", "min_lon", "max_lat", "max_lon")]
        if any(supplied):
            if not all(supplied):
                config_error = "Bounding box settings must be provided together."
            else:
                try:
                    bbox = (
                        (float(values["min_lat"]), float(values["min_lon"])),
                        (float(values["max_lat"]), float(values["max_lon"])),
                    )
                    _validate_bbox(bbox)
                except (TypeError, ValueError) as exc:
                    config_error = str(exc)

        def int_setting(name: str, default: int) -> int:
            try:
                return max(1, int(_secret_or_env(name, secrets) or default))
            except (TypeError, ValueError):
                return default

        def float_setting(name: str, default: float) -> float:
            try:
                return max(0.5, float(_secret_or_env(name, secrets) or default))
            except (TypeError, ValueError):
                return default

        provider = (_secret_or_env("AIS_PROVIDER", secrets) or "aisstream").lower()
        if config_error is None and provider != "aisstream":
            config_error = f"Unsupported provider '{provider}'. Only AISStream is enabled."
        return cls(
            aisstream_api_key=_secret_or_env("AISSTREAM_API_KEY", secrets).strip(),
            bbox=bbox,
            monitoring_bboxes=(bbox,),
            collection_seconds=min(
                max(float_setting("AIS_COLLECTION_SECONDS", DEFAULT_COLLECTION_SECONDS), MIN_COLLECTION_SECONDS),
                MAX_COLLECTION_SECONDS,
            ),
            max_messages=min(int_setting("AIS_MAX_MESSAGES", 3000), 10000),
            max_vessels=min(int_setting("AIS_MAX_VESSELS", 1000), 5000),
            stale_after_seconds=int_setting("AIS_STALE_AFTER_SECONDS", 180),
            provider=provider,
            config_error=config_error,
            database_url=_secret_or_env("DATABASE_URL", secrets).strip() or None,
            historical_persistence_enabled=_bool_setting("HISTORICAL_PERSISTENCE_ENABLED", False, secrets),
        )

    @property
    def bbox_payload(self) -> list[list[list[float]]]:
        """Serialize every active monitoring region for one AISStream subscription."""
        return [
            [list(region[0]), list(region[1])]
            for region in self.monitoring_bboxes
        ]

    def validate_for_connection(self) -> tuple[bool, str]:
        if self.config_error:
            return False, self.config_error
        if self.provider != "aisstream":
            return False, f"Unsupported provider '{self.provider}'. Only AISStream is enabled."
        if not self.aisstream_api_key:
            return False, "AISSTREAM_API_KEY is not configured."
        if not self.monitoring_bboxes:
            return False, "At least one monitoring region is required."
        try:
            for bbox in self.monitoring_bboxes:
                _validate_bbox(bbox)
        except ValueError as exc:
            return False, str(exc)
        return True, "ready"


def _validate_bbox(bbox: RegionBBox) -> None:
    try:
        (min_lat, min_lon), (max_lat, max_lon) = bbox
        values = (float(min_lat), float(min_lon), float(max_lat), float(max_lon))
    except (TypeError, ValueError):
        raise ValueError("Bounding box must contain four numeric coordinates.") from None
    if not all(isfinite(value) for value in values):
        raise ValueError("Bounding box coordinates must be finite numbers.")
    min_lat, min_lon, max_lat, max_lon = values
    if not (-90 <= min_lat <= 90 and -90 <= max_lat <= 90):
        raise ValueError("Latitude must be between -90 and 90 degrees.")
    if not (-180 <= min_lon <= 180 and -180 <= max_lon <= 180):
        raise ValueError("Longitude must be between -180 and 180 degrees.")
    if min_lat >= max_lat:
        raise ValueError("min_lat must be strictly less than max_lat.")
    if min_lon >= max_lon:
        raise ValueError("min_lon must be strictly less than max_lon.")
