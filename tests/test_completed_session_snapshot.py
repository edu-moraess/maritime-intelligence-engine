from app import _select_completed_snapshot


class TestSnapshotSelection:
    def test_overview_uses_last_completed_snapshot_after_navigation(self):
        live_snapshot = object()
        completed_snapshot = object()
        session_state = {"last_completed_snapshot": completed_snapshot}

        # System reruns still receive the live engine snapshot.
        assert _select_completed_snapshot(live_snapshot, "System", session_state) is live_snapshot

        # Returning to Overview restores the completed collection result.
        assert _select_completed_snapshot(live_snapshot, "Overview", session_state) is completed_snapshot

    def test_overview_falls_back_to_live_snapshot_without_completed_result(self):
        live_snapshot = object()
        assert _select_completed_snapshot(live_snapshot, "Overview", {}) is live_snapshot

    def test_other_pages_do_not_switch_to_completed_snapshot(self):
        live_snapshot = object()
        completed_snapshot = object()
        session_state = {"last_completed_snapshot": completed_snapshot}

        for page in ("Fleet", "System", "Data Quality", "Anomalies"):
            assert _select_completed_snapshot(live_snapshot, page, session_state) is live_snapshot
