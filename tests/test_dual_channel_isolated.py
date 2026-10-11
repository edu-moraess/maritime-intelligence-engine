from datetime import datetime, timedelta, timezone

from src.analytics.multi_channel import filter_observations, sequence_for_track, sequence_metrics
from src.ml.hybrid import fuse_scores, rank_hybrid
from src.ingestion.models import AISObservation


def obs(mmsi: str, seconds: int, lat: float, lon: float, sog: float, cog: float) -> AISObservation:
    return AISObservation(
        mmsi=mmsi,
        latitude=lat,
        longitude=lon,
        received_at=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=seconds),
        sog_knots=sog,
        cog_degrees=cog,
        valid=True,
    )


def test_multi_channel_sequence_is_sorted_and_temporal():
    observations = [
        obs("123456789", 20, 25.10, -80.10, 12.0, 90.0),
        obs("123456789", 0, 25.00, -80.20, 10.0, 90.0),
        obs("123456789", 10, 25.05, -80.15, 11.0, 120.0),
    ]
    sequence = sequence_for_track("123456789", observations)
    metrics = sequence_metrics("123456789", observations)
    assert sequence[0]["elapsed_seconds"] == 0
    assert sequence[-1]["elapsed_seconds"] == 20
    assert metrics["points"] == 3
    assert metrics["average_sog_knots"] == 11.0
    assert metrics["speed_change_knots"] == 2.0
    assert metrics["course_change_degrees"] == 30.0
    assert metrics["course_change_events"] == 1
    assert metrics["distance_nm"] > 0


def test_channel_bbox_filters_only_real_observations():
    observations = [
        obs("123456789", 0, 25.70, -80.00, 10.0, 90.0),
        obs("987654321", 0, 40.00, -70.00, 10.0, 90.0),
    ]
    bbox = ((25.603, -80.208), (25.835, -79.879))
    filtered = filter_observations(observations, bbox)
    assert [item.mmsi for item in filtered] == ["123456789"]


def test_hybrid_fusion_renormalizes_missing_signals():
    score = fuse_scores("123456789", isolation_score=0.8, temporal_score=None, rule_scores=[0.6])
    assert 0.0 <= score.hybrid_score <= 1.0
    assert score.isolation_score == 0.8
    assert score.rule_score == 0.6


def test_hybrid_ranking_is_descending():
    scores = [
        fuse_scores("111111111", isolation_score=0.2, temporal_score=0.1),
        fuse_scores("222222222", isolation_score=0.9, temporal_score=0.8),
    ]
    ranked = rank_hybrid(scores)
    assert [item.mmsi for item in ranked] == ["222222222", "111111111"]
