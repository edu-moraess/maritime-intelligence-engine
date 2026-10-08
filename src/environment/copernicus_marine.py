"""Optional Copernicus Marine ocean-state provider.

The provider is fail-closed: without the Toolbox package or valid Copernicus
credentials, it raises instead of substituting another source.
"""

from __future__ import annotations

import os
import math
from datetime import datetime, timedelta, timezone

from src.environment.open_meteo_marine import EnvironmentalProvider
from src.ingestion.models import EnvironmentalObservation

DATASET_ID = "cmems_mod_glo_phy_anfc_merged-uv_PT1H-i"
VARIABLES = ("uo", "vo")


class CopernicusMarineProvider(EnvironmentalProvider):
    """Retrieve nearest surface current from Copernicus Marine."""

    def __init__(self, timeout_seconds: float = 20.0) -> None:
        self.timeout_seconds = timeout_seconds

    @property
    def enabled(self) -> bool:
        return os.getenv("MIE_COPERNICUS_MARINE_ENABLED", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    def current(
        self,
        latitude: float,
        longitude: float,
        region: str | None = None,
    ) -> EnvironmentalObservation:
        if not self.enabled:
            raise RuntimeError("Copernicus Marine provider is disabled.")

        try:
            import copernicusmarine
        except ImportError as exc:
            raise RuntimeError(
                "Copernicus Marine provider requires the copernicusmarine package."
            ) from exc

        valid_time = datetime.now(timezone.utc).replace(
            minute=0, second=0, microsecond=0
        )
        # Keep the request deliberately small: one surface-current point and
        # one hourly time step. The Toolbox handles authentication.
        dataset = copernicusmarine.open_dataset(
            dataset_id=DATASET_ID,
            variables=list(VARIABLES),
            minimum_longitude=longitude - 0.05,
            maximum_longitude=longitude + 0.05,
            minimum_latitude=latitude - 0.05,
            maximum_latitude=latitude + 0.05,
            start_datetime=valid_time.strftime("%Y-%m-%dT%H:%M:%S"),
            end_datetime=(valid_time + timedelta(hours=1)).strftime(
                "%Y-%m-%dT%H:%M:%S"
            ),
            minimum_depth=0,
            maximum_depth=1,
        )

        try:
            point = dataset.sel(
                latitude=latitude,
                longitude=longitude,
                method="nearest",
            )
            if "depth" in point.dims:
                point = point.isel(depth=0)
            if "time" in point.dims:
                point = point.isel(time=0)

            east = float(point["uo"].values)
            north = float(point["vo"].values)
            speed = (east * east + north * north) ** 0.5
            # uo/vo are eastward/northward velocity components; this is
            # the bearing toward which the vector points.
            direction = math.degrees(math.atan2(east, north)) % 360.0

            timestamp = point["time"].values
            observed_at = _datetime_from_value(timestamp)

            return EnvironmentalObservation(
                source="copernicus-marine",
                observed_at=observed_at,
                latitude=float(point["latitude"].values),
                longitude=float(point["longitude"].values),
                region=region,
                ocean_current_velocity=speed,
                ocean_current_direction_deg=direction,
                product=DATASET_ID,
                data_kind="numerical_model_analysis_forecast",
                retrieved_at=datetime.now(timezone.utc),
                forecast=True,
            )
        finally:
            close = getattr(dataset, "close", None)
            if callable(close):
                close()


def _datetime_from_value(value: object) -> datetime:
    if hasattr(value, "astype"):
        value = value.astype("datetime64[us]").tolist()
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    raise ValueError(f"Unsupported Copernicus timestamp type: {type(value)!r}")
