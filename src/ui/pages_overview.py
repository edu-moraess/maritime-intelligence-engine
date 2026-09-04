"""Overview compatibility/decorator layer.

The canonical Overview implementation remains in ``pages_a``. This module keeps
legacy imports stable and adds the small operator-facing anomaly signal that
should appear before the dense Overview layout.
"""

from __future__ import annotations

from src.intelligence.engine import EngineSnapshot, MaritimeIntelligenceEngine
from src.config.settings import AppSettings
from src.ui.pages_a import render_overview as _render_overview
from src.ui.presentation import notice


def render_overview(
    engine: MaritimeIntelligenceEngine,
    snapshot: EngineSnapshot,
    settings: AppSettings,
) -> None:
    """Render Overview with a concise investigation signal above the dashboard."""
    anomalies = int(snapshot.summary.get("anomalies", 0))

    if anomalies > 0:
        target_label = "target" if anomalies == 1 else "targets"
        notice(
            f"{anomalies} anomalous {target_label} detected in the current "
            "AIS session. Review Intelligence → Anomalies for investigation.",
            "red",
        )

    _render_overview(engine, snapshot, settings)


__all__ = ["render_overview"]
