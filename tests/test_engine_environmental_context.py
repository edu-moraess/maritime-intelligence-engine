from datetime import datetime, timezone

from src.config.settings import AppSettings, DEFAULT_BBOX
from src.ingestion.models import EnvironmentalObservation
from src.intelligence.engine import MaritimeIntelligenceEngine


SECOND_BBOX = ((50.8, 1.0), (51.2, 2.2))


class FakeEnvironmentalProvider:
    def current(self, latitude: float, longitude: float, region: str | None = None) -> EnvironmentalObservation:
        return EnvironmentalObservation(
            source="test-environment",
            observed_at=datetime(2026, 9, 25, 3, 0, tzinfo=timezone.utc),
            latitude=latitude,
            longitude=longitude,
            region=region,
            wave_height_m=1.0,
        )


class FailingEnvironmentalProvider:
    def current(self, latitude: float, longitude: float, region: str | None = None) -> EnvironmentalObservation:
        raise RuntimeError("provider unavailable")


def test_engine_exposes_environmental_context_per_monitoring_region() -> None:
    settings = AppSettings(
        aisstream_api_key="",
        bbox=DEFAULT_BBOX,
        monitoring_bboxes=(DEFAULT_BBOX, SECOND_BBOX),
    )
    engine = MaritimeIntelligenceEngine(settings)
    engine.environmental_provider = FakeEnvironmentalProvider()

    engine._refresh_environmental_contexts()
    snapshot = engine.snapshot()

    assert set(snapshot.environmental_contexts) == {"region_1", "region_2"}
    assert snapshot.environmental_contexts["region_1"].status == "AVAILABLE"
    assert snapshot.environmental_contexts["region_2"].status == "AVAILABLE"
    assert snapshot.environmental_contexts["region_2"].latest is not None


def test_environmental_provider_failure_keeps_context_unavailable() -> None:
    engine = MaritimeIntelligenceEngine(
        AppSettings(aisstream_api_key="", bbox=DEFAULT_BBOX)
    )
    engine.environmental_provider = FailingEnvironmentalProvider()

    engine._refresh_environmental_contexts()

    context = engine.environmental_contexts["region_1"]
    assert context.status == "UNAVAILABLE"
    assert context.latest is None
