from src.config.regions import REGION_PRESETS
from src.config.settings import AppSettings, DEFAULT_BBOX
from src.ingestion.aisstream import AISStreamProvider


def test_settings_serializes_two_monitoring_bboxes():
    settings = AppSettings(
        aisstream_api_key="k",
        bbox=REGION_PRESETS["Miami"],
        monitoring_bboxes=(REGION_PRESETS["Miami"], REGION_PRESETS["English Channel"]),
    )
    assert settings.bbox == REGION_PRESETS["Miami"]
    assert settings.bbox_payload == [
        [list(REGION_PRESETS["Miami"][0]), list(REGION_PRESETS["Miami"][1])],
        [list(REGION_PRESETS["English Channel"][0]), list(REGION_PRESETS["English Channel"][1])],
    ]


def test_single_region_remains_backward_compatible():
    settings = AppSettings(aisstream_api_key="k", bbox=DEFAULT_BBOX)
    assert settings.monitoring_bboxes == (DEFAULT_BBOX,)
    assert settings.bbox_payload == [[list(DEFAULT_BBOX[0]), list(DEFAULT_BBOX[1])]]


def test_provider_subscription_contains_both_regions():
    boxes = [
        [list(REGION_PRESETS["Miami"][0]), list(REGION_PRESETS["Miami"][1])],
        [list(REGION_PRESETS["English Channel"][0]), list(REGION_PRESETS["English Channel"][1])],
    ]
    provider = AISStreamProvider(api_key="k", bbox=boxes)
    assert provider._subscription()["BoundingBoxes"] == boxes
