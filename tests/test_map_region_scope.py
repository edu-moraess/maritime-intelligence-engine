from src.config.regions import REGION_PRESETS
from src.geospatial.map_data import filter_rows_to_bboxes
from src.ui.dual_region_overview import _unified_map_zoom


def test_map_rows_are_limited_to_configured_regions():
    malacca = REGION_PRESETS["Malacca Strait"]
    gibraltar = REGION_PRESETS["Strait of Gibraltar"]
    rows = [
        {"latitude": 3.5, "longitude": 101.75},
        {"latitude": 36.0, "longitude": -5.35},
        {"latitude": 23.4642, "longitude": 34.2806},
    ]

    filtered = filter_rows_to_bboxes(rows, (malacca, gibraltar))

    assert filtered == rows[:2]


def test_map_rows_support_single_region_scope():
    malacca = REGION_PRESETS["Malacca Strait"]
    rows = [
        {"latitude": 3.5, "longitude": 101.75},
        {"latitude": 36.0, "longitude": -5.35},
    ]

    assert filter_rows_to_bboxes(rows, (malacca,)) == rows[:1]


def test_unified_map_zoom_expands_for_distant_real_targets():
    rows = [
        {"latitude": 48.45, "longitude": -122.98},
        {"latitude": 54.22, "longitude": 9.66},
    ]

    zoom = _unified_map_zoom(rows)

    assert 1.5 <= zoom <= 3.0


def test_unified_map_zoom_keeps_local_regions_reasonably_detailed():
    rows = [
        {"latitude": 33.75, "longitude": -118.25},
        {"latitude": 37.75, "longitude": -122.34},
    ]

    zoom = _unified_map_zoom(rows)

    assert 5.0 <= zoom <= 6.5
