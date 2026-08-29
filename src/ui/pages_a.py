"""Streamlit page renderers — overview, vessels, trajectory, behavior."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.config.settings import AppSettings
from src.geospatial.map_data import vessel_rows
from src.intelligence.engine import (
    EngineSnapshot,
    MaritimeIntelligenceEngine,
)
from src.intelligence.llm import (
    build_vessel_context,
    create_gemini_client,
)

from src.ui.pages_helpers import (
    MAP_STYLES,
    _no_real_data_reason,
    _plot_layout,
    _render_readiness,
    _render_similarity_search,
    _render_speed_chart,
    _render_track_chart,
    _render_vessel_map,
    _select_vessel,
    _selected_vessel,
    _track_readiness_reason,
    _utc,
    _vessel_compact,
    _vessel_label,
)

from src.ui.presentation import (
    empty_state,
    frame_for_table,
    metric_strip,
    notice,
    panel_title,
)
