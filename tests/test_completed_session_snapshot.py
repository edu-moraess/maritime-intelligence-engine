from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app import _select_completed_snapshot
from src.ingestion.models import AISObservation
from src.intelligence.engine import MaritimeIntelligenceEngine


class TestSnapshotSelection:
    def test_overview_uses_last_completed_snapshot_after_navigation(self):
        live_snapshot = object()
        completed_snapshot = object()
        session_state = {"last_completed_snapshot": completed_snapshot}

        # System reruns still receive the live engine snapshot.
        assert (
            _select_completed_snapshot(live_snapshot, "System", session_state)
            is live_snapshot
        )

        # Returning to Overview restores the completed collection result.
        assert (
            _select_completed_snapshot(live_snapshot, "Overview", session_state)
            is completed_snapshot
        )

    def test_overview_falls_back_to_live_snapshot_without_completed_result(self):
        live_snapshot = object()
        assert _select_completed_snapshot(live_snapshot, "Overview", {}) is live_snapshot

    def test_other_pages_do_not_switch_to_completed_snapshot(self):
        live_snapshot = object()
        completed_snapshot = object()
        session_state = {"last_completed_snapshot": completed_snapshot}

        for page in ("Fleet", "System", "Data Quality", "Anomalies"):
            assert _select_completed_snapshot(live_snapshot, page, session_state) is live_snapshot


class TestCompletedCollectionStaleness:
    def test_stale_reference_is_collection_end_not_current_wall_clock(self):
        engine = object.__new__(MaritimeIntelligenceEngine)
        ended_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        observation = AISObservation(
            mmsi="123456789",
            latitude=1.0,
            longitude=2.0,
            received_at=ended_at - timedelta(seconds=120),
        )
        engine.settings = SimpleNamespace(stale_after_seconds=180, max_vessels=100)
        engine.last_collection_ended_at = ended_at

        vessels = engine._merged_vessels({"123456789": [observation]})

        assert len(vessels) == 1
        assert vessels[0].stale is False

        # The same completed session remains fresh even though the process clock
        # is now months beyond the collection window.
        assert engine.last_collection_ended_at == ended_at
