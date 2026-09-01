from typing import Final

from .settings import _validate_bbox


RegionBBox = tuple[tuple[float, float], tuple[float, float]]

# These are operational monitoring boxes, not data sources. Selecting one only
# changes the BoundingBoxes sent on the next real AISStream subscription.
#
# The first ten are the main/highlighted monitoring areas. The remaining
# presets provide broader coverage while keeping the selector to 30 regions.
MAIN_REGION_PRESETS: Final[tuple[str, ...]] = (
    "Singapore",
    "Suez Canal",
    "Strait of Gibraltar",
    "Bosphorus",
    "Santos",
    "Malacca Strait",
    "Panama Canal",
    "English Channel",
    "Danish Straits",
    "Houston Ship Channel",
)

REGION_PRESETS: Final[dict[str, RegionBBox]] = {
    # Main / highlighted regions
    "Singapore": ((1.150, 103.550), (1.500, 104.200)),
    "Suez Canal": ((29.700, 32.100), (31.400, 32.700)),
    "Strait of Gibraltar": ((35.700, -5.800), (36.300, -4.900)),
    "Bosphorus": ((40.800, 28.700), (41.400, 29.400)),
    "Santos": ((-24.200, -46.800), (-23.700, -46.000)),
    "Malacca Strait": ((1.000, 99.500), (6.000, 104.000)),
    "Panama Canal": ((8.800, -79.900), (9.400, -79.400)),
    "English Channel": ((49.800, -5.500), (51.500, 2.500)),
    "Danish Straits": ((54.500, 8.000), (58.200, 13.000)),
    "Houston Ship Channel": ((28.800, -95.700), (29.900, -94.400)),

    # Additional operational regions
    "Miami": ((25.603, -80.208), (25.835, -79.879)),
    "Rotterdam": ((51.750, 3.800), (52.100, 4.800)),
    "Strait of Messina": ((37.800, 15.000), (38.500, 15.700)),
    "Strait of Hormuz": ((25.500, 55.500), (27.300, 57.000)),
    "Bab-el-Mandeb": ((12.000, 42.500), (13.700, 44.000)),
    "Kiel Canal": ((53.700, 8.300), (54.500, 10.500)),
    "Corinth Canal": ((37.700, 22.900), (38.100, 23.500)),
    "Skagerrak": ((56.800, 7.000), (59.200, 12.500)),
    "Kattegat": ((55.500, 10.500), (58.000, 12.800)),
    "Dover Strait": ((50.800, 1.000), (51.200, 2.200)),
    "Irish Sea": ((51.200, -6.500), (55.700, -2.000)),
    "North Sea": ((51.000, -4.500), (61.000, 9.000)),
    "Gulf of Aden": ((11.000, 43.000), (15.500, 52.000)),
    "Gulf of Panama": ((7.000, -81.200), (9.000, -78.800)),
    "Strait of Juan de Fuca": ((47.500, -125.000), (49.000, -122.500)),
    "San Francisco Bay": ((37.400, -123.200), (38.300, -121.500)),
    "Los Angeles / Long Beach": ((33.300, -118.800), (34.200, -117.800)),
    "Mississippi / New Orleans": ((28.500, -91.500), (30.500, -89.000)),
    "Guanabara Bay": ((-23.300, -43.500), (-22.600, -42.700)),
    "Strait of Magellan": ((-53.000, -74.000), (-52.000, -69.000)),
}

# Keep the main regions first in the operator selector, followed by the
# additional regions. Custom remains the final non-preset option.
_OTHER_REGION_PRESETS: Final[tuple[str, ...]] = tuple(
    name for name in REGION_PRESETS if name not in MAIN_REGION_PRESETS
)
REGION_OPTIONS: Final[tuple[str, ...]] = (
    *MAIN_REGION_PRESETS,
    *_OTHER_REGION_PRESETS,
    "Custom",
)

# Timezones are presentation metadata only. Regions spanning multiple local
# zones use UTC rather than silently choosing a misleading local timezone.
REGION_TIMEZONES: Final[dict[str, str]] = {
    "Miami": "America/New_York",
    "Santos": "America/Sao_Paulo",
    "Singapore": "Asia/Singapore",
    "Rotterdam": "Europe/Amsterdam",
    "English Channel": "UTC",
    "Suez Canal": "Africa/Cairo",
    "Strait of Gibraltar": "UTC",
    "Bosphorus": "Europe/Istanbul",
    "Malacca Strait": "UTC",
    "Panama Canal": "America/Panama",
    "Danish Straits": "UTC",
    "Houston Ship Channel": "America/Chicago",
    "Strait of Messina": "Europe/Rome",
    "Strait of Hormuz": "UTC",
    "Bab-el-Mandeb": "UTC",
    "Kiel Canal": "Europe/Berlin",
    "Corinth Canal": "Europe/Athens",
    "Skagerrak": "UTC",
    "Kattegat": "UTC",
    "Dover Strait": "UTC",
    "Irish Sea": "UTC",
    "North Sea": "UTC",
    "Gulf of Aden": "UTC",
    "Gulf of Panama": "America/Panama",
    "Strait of Juan de Fuca": "UTC",
    "San Francisco Bay": "America/Los_Angeles",
    "Los Angeles / Long Beach": "America/Los_Angeles",
    "Mississippi / New Orleans": "America/Chicago",
    "Guanabara Bay": "America/Sao_Paulo",
    "Strait of Magellan": "America/Punta_Arenas",
    "Custom": "UTC",
}
REGION_TIMEZONE_POLICIES: Final[dict[str, str]] = {
    "English Channel": "UTC policy: the box spans international waters and multiple local time zones.",
    "Strait of Gibraltar": "UTC policy: the box spans international waters and multiple local zones.",
    "Malacca Strait": "UTC policy: the box spans international waters and multiple local zones.",
    "Danish Straits": "UTC policy: the monitoring box spans multiple Danish straits and local zones.",
    "Strait of Hormuz": "UTC policy: the box spans international waters and multiple local zones.",
    "Bab-el-Mandeb": "UTC policy: the box spans international waters and multiple local zones.",
    "Skagerrak": "UTC policy: the box spans waters shared by multiple coastal states.",
    "Kattegat": "UTC policy: the box spans waters shared by Denmark and Sweden.",
    "Dover Strait": "UTC policy: the box spans UK/French waters.",
    "Irish Sea": "UTC policy: the box spans waters around multiple coastal jurisdictions.",
    "North Sea": "UTC policy: the box spans multiple countries and time zones.",
    "Gulf of Aden": "UTC policy: the box spans international waters and multiple local zones.",
    "Strait of Juan de Fuca": "UTC policy: the box spans US/Canadian waters.",
    "Strait of Magellan": "UTC policy: the monitoring box spans a broad international maritime area.",
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
