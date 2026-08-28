"""Streamlit page renderers. All pages consume the engine snapshot and never create data."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import pydeck as pdk
import streamlit as st

from src.analytics.traffic import anomaly_counts, hourly_volume, speed_distribution
from src.config.regions import region_timezone_for_bbox
from src.config.settings import AppSettings
from src.geospatial.map_data import vessel_rows
from src.ingestion.models import AnomalyFinding, VesselSnapshot
from src.historical.writer import diagnose_database
from src.intelligence.engine import EngineSnapshot, MaritimeIntelligenceEngine
from src.trajectory.features import enrich_track, track_to_frame
from src.ui.presentation import empty_state, frame_for_table, metric_strip, notice, panel_title
from src.ui.temporal import format_ais_second, format_observation_time, format_received, format_region_or_operator
