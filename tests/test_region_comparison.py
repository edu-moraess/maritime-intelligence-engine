from datetime import datetime, timezone

from src.analytics.region_comparison import compare_regions
from src.ingestion.models import AISObservation, AnomalyFinding
from src.ml.temporal.types import TemporalFitResult, TemporalScore


def _obs(mmsi: str, lat: float, lon: float, speed: float = 5.0) -> AISObservation:
    return AISObservation(
        mmsi=mmsi,
        latitude=lat,
        longitude=lon,
        received_at=datetime.now(timezone.utc),
        sog_knots=speed,
    )


def _finding(mmsi: str, lat: float, lon: float) -> AnomalyFinding:
    return AnomalyFinding(
        mmsi=mmsi,
        received_at=datetime.now(timezone.utc),
        latitude=lat,
        longitude=lon,
        score=0.9,
        category="ANOMALY",
        confidence=None,
        explanation="test",
    )


def test_compare_regions_normalizes_anomalies_and_temporal_scores():
    bboxes = [((0.0, 0.0), (10.0, 10.0)), ((20.0, 20.0), (30.0, 30.0))]
    observations = [
        _obs("111000001", 5.0, 5.0, 4.0),
        _obs("111000001", 5.1, 5.1, 6.0),
        _obs("111000002", 6.0, 6.0, 8.0),
        _obs("222000001", 25.0, 25.0, 10.0),
    ]
    findings = [_finding("111000001", 5.1, 5.1), _finding("222000001", 25.0, 25.0)]
    temporal = TemporalFitResult(
        status="READY",
        reason="test",
        scores=[
            TemporalScore("111000001", 0.1, 0.2),
            TemporalScore("111000002", 0.2, 0.4),
            TemporalScore("222000001", 0.3, 0.9),
            TemporalScore("333000001", 0.4, 0.8),
        ],
    )

    comparison = compare_regions(observations, findings, bboxes, temporal)
    assert comparison is not None
    region_a, region_b = comparison.regions
    assert region_a.unique_vessels == 2
    assert region_a.position_reports == 3
    assert region_a.anomalies == 1
    assert region_a.anomaly_rate == 0.5
    assert region_b.unique_vessels == 1
    assert region_b.anomalies == 1
    assert region_b.anomaly_rate == 1.0
    assert region_a.average_temporal_score == 0.3
    assert region_b.average_temporal_score == 0.9
    assert region_b.temporal_top_quartile_rate == 1.0


def test_overlapping_observations_are_not_double_counted():
    bboxes = [((0.0, 0.0), (10.0, 10.0)), ((5.0, 5.0), (15.0, 15.0))]
    observations = [_obs("111000001", 7.0, 7.0), _obs("222000001", 12.0, 12.0)]
    comparison = compare_regions(observations, [], bboxes)
    assert comparison is not None
    assert comparison.ambiguous_observations == 1
    assert comparison.regions[0].unique_vessels == 0
    assert comparison.regions[1].unique_vessels == 1


def test_comparison_requires_exactly_two_regions():
    assert compare_regions([], [], [((0.0, 0.0), (1.0, 1.0))]) is None
