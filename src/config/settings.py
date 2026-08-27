"""Runtime configuration for the real-AIS-only application."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


DEFAULT_BBOX = ((25.835, -80.208), (25.603, -79.879))


def _secret_or_env(name: str, secrets: Any | None = None) -> str:
    """Read a secret from Streamlit Secrets first, then from the local environment."""
    if secrets is not None:
        try:
            value = secrets.get(name)
            if value:
                return str(value)
        except Exception:
            pass
    return os.getenv(name, "")


@dataclass(frozen=True)
class AppSettings:
    """Application settings; no setting creates or substitutes AIS observations."""

    aisstream_api_key: str
    bbox: tuple[tuple[float, float], tuple[float, float]] = DEFAULT_BBOX
    collection_seconds: float = 2.5
    max_messages: int = 3000
    max_vessels: int = 1000
    stale_after_seconds: int = 180
    provider: str = "aisstream"

    @classmethod
    def from_runtime(cls, secrets: Any | None = None) -> "AppSettings":
        values = {
            "min_lat": _secret_or_env("AIS_AREA_MIN_LAT", secrets),
            "min_lon": _secret_or_env("AIS_AREA_MIN_LON", secrets),
            "max_lat": _secret_or_env("AIS_AREA_MAX_LAT", secrets),
            "max_lon": _secret_or_env("AIS_AREA_MAX_LON", secrets),
        }
        try:
            bbox = (
                (float(values["min_lat"]), float(values["min_lon"])),
                (float(values["max_lat"]), float(values["max_lon"])),
            )
            _validate_bbox(bbox)
        except (TypeError, ValueError):
            bbox = DEFAULT_BBOX

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

        return cls(
            aisstream_api_key=_secret_or_env("AISSTREAM_API_KEY", secrets).strip(),
            bbox=bbox,
            collection_seconds=min(float_setting("AIS_COLLECTION_SECONDS", 2.5), 10.0),
            max_messages=min(int_setting("AIS_MAX_MESSAGES", 3000), 10000),
            max_vessels=min(int_setting("AIS_MAX_VESSELS", 1000), 5000),
            stale_after_seconds=int_setting("AIS_STALE_AFTER_SECONDS", 180),
            provider=(_secret_or_env("AIS_PROVIDER", secrets) or "aisstream").lower(),
        )

    @property
    def bbox_payload(self) -> list[list[list[float]]]:
        return [[list(self.bbox[0]), list(self.bbox[1])]]

    def validate_for_connection(self) -> tuple[bool, str]:
        if self.provider != "aisstream":
            return False, f"Unsupported provider '{self.provider}'. Only AISStream is enabled."
        if not self.aisstream_api_key:
            return False, "AISSTREAM_API_KEY is not configured."
        try:
            _validate_bbox(self.bbox)
        except ValueError as exc:
            return False, str(exc)
        return True, "ready"


def _validate_bbox(bbox: tuple[tuple[float, float], tuple[float, float]]) -> None:
    (min_lat, min_lon), (max_lat, max_lon) = bbox
    if not (-90 <= min_lat <= 90 and -90 <= max_lat <= 90):
        raise ValueError("Latitude must be between -90 and 90 degrees.")
    if not (-180 <= min_lon <= 180 and -180 <= max_lon <= 180):
        raise ValueError("Longitude must be between -180 and 180 degrees.")
    if min_lat == max_lat or min_lon == max_lon:
        raise ValueError("Bounding box must have non-zero latitude and longitude spans.")
