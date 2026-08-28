from typing import Final

from .settings import _validate_bbox


RegionBBox = tuple[tuple[float, float], tuple[float, float]]

# These are operational monitoring boxes, not data sources. Selecting one only
# changes the BoundingBoxes sent on the next real AISStream subscription.
REGION_PRESETS: Final[dict[str, RegionBBox]] = {
    "Miami": ((25.603, -80.208), (25.835, -79.879)),
    "Santos": ((-24.200, -46.800), (-23.700, -46.000)),
    "Singapore": ((1.150, 103.550), (1.500, 104.200)),
    "Rotterdam": ((51.750, 3.800), (52.100, 4.800)),
    "English Channel": ((49.800, -5.500), (51.500, 2.500)),
}
REGION_OPTIONS: Final[tuple[str, ...]] = (*REGION_PRESETS.keys(), "Custom")

# Timezones are presentation metadata only. The English Channel spans several
# local zones, so UTC is the explicit non-misleading default. Custom is UTC.
REGION_TIMEZONES: Final[dict[str, str]] = {
    "Miami": "America/New_York",
    "Santos": "America/Sao_Paulo",
    "Singapore": "Asia/Singapore",
    "Rotterdam": "Europe/Amsterdam",
    "English Channel": "UTC",
    "Custom": "UTC",
}
REGION_TIMEZONE_POLICIES: Final[dict[str, str]] = {
    "English Channel": "UTC policy: the box spans international waters and multiple local time zones.",
    "Custom": "UTC policy: custom regions do not silently assume an operator or geographic timezone.",
}

for _bbox in REGION_PRESETS.values():
    _validate_bbox(_bbox)


def region_name_for_bbox(bbox: RegionBBox) -> str | None:
    for name, preset_bbox in REGION_PRESETS.items():
        if bbox == preset_bbox:
            return name
    return None


def region_timezone_for_bbox(bbox: RegionBBox) -> str:
    return REGION_TIMEZONES.get(region_name_for_bbox(bbox) or "Custom", "UTC")


def format_bbox(bbox: RegionBBox) -> str:
    (min_lat, min_lon), (max_lat, max_lon) = bbox
    return f"{min_lat:.3f}, {min_lon:.3f} → {max_lat:.3f}, {max_lon:.3f}"
