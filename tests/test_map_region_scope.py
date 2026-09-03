from src.config.regions import REGION_PRESETS
from src.geospatial.map_data import filter_rows_to_bboxes


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
