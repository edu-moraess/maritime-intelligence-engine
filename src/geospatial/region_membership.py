"""Shared geographic membership rules for monitored AIS regions."""

from __future__ import annotations

from typing import Sequence

from src.config.settings import RegionBBox


def contains_point(
    latitude: float | None,
    longitude: float | None,
    bbox: RegionBBox,
) -> bool:
    """Return whether a coordinate belongs to a validated monitoring bbox.

    Bounding boxes intentionally use inclusive edges. Antimeridian-crossing
    boxes are not supported by the current configuration contract because
    min_lon must be strictly less than max_lon.
    """
    if latitude is None or longitude is None:
        return False
    (min_lat, min_lon), (max_lat, max_lon) = bbox
    return (
        min_lat <= float(latitude) <= max_lat
        and min_lon <= float(longitude) <= max_lon
    )


def membership(
    latitude: float | None,
    longitude: float | None,
    bboxes: Sequence[RegionBBox],
) -> tuple[int, ...]:
    """Return all monitoring-region indexes containing the coordinate."""
    return tuple(
        index
        for index, bbox in enumerate(bboxes)
        if contains_point(latitude, longitude, bbox)
    )


def belongs_to_any(
    latitude: float | None,
    longitude: float | None,
    bboxes: Sequence[RegionBBox],
) -> bool:
    """Return whether a coordinate belongs to at least one monitoring region."""
    return bool(membership(latitude, longitude, bboxes))
