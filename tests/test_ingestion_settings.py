from src.config.settings import AppSettings


def test_ingestion_queue_capacity_is_configurable_and_bounded(monkeypatch):
    monkeypatch.setenv("AIS_INGESTION_QUEUE_CAPACITY", "1234")
    settings = AppSettings.from_runtime(secrets={})
    assert settings.ingestion_queue_capacity == 1234

    monkeypatch.setenv("AIS_INGESTION_QUEUE_CAPACITY", "999999")
    bounded = AppSettings.from_runtime(secrets={})
    assert bounded.ingestion_queue_capacity == 50000


def test_invalid_ingestion_queue_capacity_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("AIS_INGESTION_QUEUE_CAPACITY", "not-an-integer")
    settings = AppSettings.from_runtime(secrets={})
    assert settings.ingestion_queue_capacity == 5000
