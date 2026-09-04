from src.intelligence.engine import ReadinessSnapshot


def _readiness(*, tracks: int, anomalies: int) -> ReadinessSnapshot:
    return ReadinessSnapshot(
        distinct_vessels=max(tracks, 0),
        tracks_with_history=tracks,
        trajectory_ready=tracks > 0,
        embeddings_ready=tracks >= 1,
        embedding_status="READY" if tracks else "WAITING",
        anomaly_count=anomalies,
    )


def test_anomaly_readiness_waits_for_real_multitrack_context() -> None:
    assert _readiness(tracks=0, anomalies=0).anomaly_status == "WAITING"
    assert _readiness(tracks=1, anomalies=0).anomaly_status == "PARTIAL"
    assert _readiness(tracks=3, anomalies=0).anomaly_status == "READY"


def test_anomaly_findings_make_anomaly_surface_ready() -> None:
    assert _readiness(tracks=1, anomalies=1).anomaly_status == "READY"
