from datetime import datetime, timezone

from src.analytics.traffic import traffic_summary
from src.ingestion.models import AISObservation, AnomalyFinding, VesselSnapshot


def test_traffic_summary_uses_fresh_vessels_and_configured_region_count():
    now = datetime.now(timezone.utc)
    vessels = [
        VesselSnapshot("111111111", 1.0, 2.0, now, 10.0, 90.0, 90.0, "FRESH", 3, stale=False),
        VesselSnapshot("222222222", 1.1, 2.1, now, 20.0, 90.0, 90.0, "STALE", 2, stale=True),
    ]
    observations = [
        AISObservation("111111111", 1.0, 2.0, now),
        AISObservation("111111111", 1.0, 2.0, now.replace(microsecond=1)),
        AISObservation("222222222", 1.1, 2.1, now),
    ]
    findings = [
        AnomalyFinding("111111111", now, 1.0, 2.0, 0.9, "SPEED", 0.9, "test"),
        AnomalyFinding("111111111", now, 1.0, 2.0, 0.8, "HEADING", 0.8, "test"),
    ]

    summary = traffic_summary(
        vessels,
        observations,
        findings,
        monitoring_regions=2,
    )

    assert summary["active_vessels"] == 1
    assert summary["observed_vessels"] == 2
    assert summary["unique_vessels"] == 2
    assert summary["messages"] == 3
    assert summary["speed_sample_count"] == 1
    assert summary["average_speed_knots"] == 10.0
    assert summary["anomalies"] == 2
    assert summary["anomaly_vessels"] == 1
    assert summary["stale_vessels"] == 1
    assert summary["regions"] == 2

def test_speed_distribution_excludes_stale_last_known_positions():
    from src.analytics.traffic import speed_distribution

    now = datetime.now(timezone.utc)
    vessels = [
        VesselSnapshot("111111111", 1.0, 2.0, now, 8.0, 90.0, 90.0, "FRESH", 2, stale=False),
        VesselSnapshot("222222222", 1.1, 2.1, now, 18.0, 90.0, 90.0, "STALE", 2, stale=True),
    ]

    frame = speed_distribution(vessels)

    assert frame["mmsi"].tolist() == ["111111111"]
    assert frame["sog_knots"].tolist() == [8.0]

