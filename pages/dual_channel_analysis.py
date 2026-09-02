"""Optional dual-channel page isolated from the MIE core configuration.

The page owns two normal MaritimeIntelligenceEngine instances. It does not modify
AppSettings, app.py, the shared navigation, or the single-region engine contract.
Only real AIS observations are displayed or analyzed.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pandas as pd
import streamlit as st

from src.analytics.dual_channel import sequence_for_track, vessels_in_bbox
from src.config.settings import AppSettings
from src.intelligence.engine import MaritimeIntelligenceEngine

REGIONS: dict[str, tuple[tuple[float, float], tuple[float, float]]] = {
    "Miami": ((25.603, -80.208), (25.835, -79.879)),
    "English Channel": ((49.800, -5.500), (51.500, 2.500)),
}


def _settings_for(base: AppSettings, bbox: tuple[tuple[float, float], tuple[float, float]]) -> AppSettings:
    """Clone normal application settings without changing the shared AppSettings model."""
    return replace(base, bbox=bbox, historical_persistence_enabled=False)


def _engine_key(base: AppSettings, region: str) -> tuple[object, ...]:
    return (
        base.aisstream_api_key,
        region,
        base.max_messages,
        base.max_vessels,
        base.stale_after_seconds,
    )


def _get_engine(base: AppSettings, region: str) -> MaritimeIntelligenceEngine:
    key = _engine_key(base, region)
    state_key = f"dual_engine_{region.lower().replace(' ', '_')}"
    key_key = f"{state_key}_key"
    existing = st.session_state.get(state_key)
    if existing is None or st.session_state.get(key_key) != key:
        if existing is not None:
            existing.historical_writer.close()
        existing = MaritimeIntelligenceEngine(_settings_for(base, REGIONS[region]))
        st.session_state[state_key] = existing
        st.session_state[key_key] = key
    return existing


def _collect_pair(first: MaritimeIntelligenceEngine, second: MaritimeIntelligenceEngine, seconds: float) -> tuple[int, int]:
    """Collect both regions concurrently, each through the unchanged engine contract."""
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="mie-dual") as pool:
        future_first = pool.submit(first.collect, seconds)
        future_second = pool.submit(second.collect, seconds)
        return future_first.result(), future_second.result()


def _vessel_label(vessel) -> str:
    name = (vessel.vessel_name or "UNKNOWN").strip()
    return f"{vessel.mmsi} · {name}"


def _current_state(vessel) -> dict[str, object]:
    return {
        "MMSI": vessel.mmsi,
        "Name": vessel.vessel_name or "UNKNOWN",
        "Latitude": round(vessel.latitude, 5),
        "Longitude": round(vessel.longitude, 5),
        "SOG (kn)": round(vessel.sog_knots, 2) if vessel.sog_knots is not None else None,
        "COG (°)": round(vessel.cog_degrees, 2) if vessel.cog_degrees is not None else None,
        "Messages": vessel.message_count,
    }


def main() -> None:
    st.set_page_config(page_title="Dual-Channel Sequential Analysis", page_icon="⚓", layout="wide")
    st.title("Dual-Channel Sequential Analysis")
    st.caption("Optional feature · two independent real-AIS engines · no changes to the MIE core")

    base = AppSettings.from_runtime(st.secrets)
    if not base.aisstream_api_key:
        st.error("AISSTREAM_API_KEY is not configured.")
        return

    left, right = st.columns(2)
    with left:
        region_a = st.selectbox("Channel A", list(REGIONS), index=0)
    with right:
        choices_b = [region for region in REGIONS if region != region_a]
        region_b = st.selectbox("Channel B", choices_b, index=0)

    duration = st.select_slider(
        "Collection window (seconds)",
        options=[30, 60, 120, 180],
        value=int(base.collection_seconds) if int(base.collection_seconds) in [30, 60, 120, 180] else 60,
    )

    engine_a = _get_engine(base, region_a)
    engine_b = _get_engine(base, region_b)

    collect_col, clear_col = st.columns(2)
    with collect_col:
        collect = st.button("Collect Real AIS", type="primary", use_container_width=True)
    with clear_col:
        clear = st.button("Clear Dual Session", use_container_width=True)

    if clear:
        engine_a.clear_session_data()
        engine_b.clear_session_data()
        st.session_state.pop("dual_vessel_a", None)
        st.session_state.pop("dual_vessel_b", None)
        st.rerun()

    if collect:
        with st.spinner(f"Collecting {duration}s of real AIS from {region_a} and {region_b}..."):
            count_a, count_b = _collect_pair(engine_a, engine_b, float(duration))
        st.success(f"Real AIS received — {region_a}: {count_a} · {region_b}: {count_b}")

    snapshot_a = engine_a.snapshot()
    snapshot_b = engine_b.snapshot()
    vessels_a = vessels_in_bbox(snapshot_a.vessels, REGIONS[region_a])
    vessels_b = vessels_in_bbox(snapshot_b.vessels, REGIONS[region_b])

    st.divider()
    st.subheader("Current operational state")
    state_a, state_b = st.columns(2)
    with state_a:
        st.markdown(f"**{region_a}**")
        st.metric("Active vessels", snapshot_a.readiness.distinct_vessels)
        st.caption(f"AIS state: {snapshot_a.status.state} · messages: {snapshot_a.status.messages_received}")
    with state_b:
        st.markdown(f"**{region_b}**")
        st.metric("Active vessels", snapshot_b.readiness.distinct_vessels)
        st.caption(f"AIS state: {snapshot_b.status.state} · messages: {snapshot_b.status.messages_received}")

    if not vessels_a or not vessels_b:
        st.info("Collect more real AIS data before selecting one vessel from each channel.")
        return

    labels_a = {_vessel_label(v): v.mmsi for v in vessels_a}
    labels_b = {_vessel_label(v): v.mmsi for v in vessels_b}
    select_a, select_b = st.columns(2)
    with select_a:
        selected_label_a = st.selectbox("Vessel A", list(labels_a), key="dual_vessel_a")
    with select_b:
        available_b = [label for label in labels_b if labels_b[label] != labels_a[selected_label_a]]
        if not available_b:
            st.warning("Channel B has no distinct vessel available yet.")
            return
        selected_label_b = st.selectbox("Vessel B", available_b, key="dual_vessel_b")

    mmsi_a = labels_a[selected_label_a]
    mmsi_b = labels_b[selected_label_b]
    seq_a = sequence_for_track(mmsi_a, snapshot_a.observations)
    seq_b = sequence_for_track(mmsi_b, snapshot_b.observations)

    st.divider()
    st.subheader("Vessel comparison")
    current_a = next(v for v in vessels_a if v.mmsi == mmsi_a)
    current_b = next(v for v in vessels_b if v.mmsi == mmsi_b)
    st.dataframe(pd.DataFrame([_current_state(current_a), _current_state(current_b)]), use_container_width=True, hide_index=True)

    metrics = pd.DataFrame(
        [
            {"Metric": "Points", region_a: seq_a.metrics.points, region_b: seq_b.metrics.points},
            {"Metric": "Duration (s)", region_a: round(seq_a.metrics.duration_seconds, 1), region_b: round(seq_b.metrics.duration_seconds, 1)},
            {"Metric": "Distance (NM)", region_a: round(seq_a.metrics.distance_nm, 3), region_b: round(seq_b.metrics.distance_nm, 3)},
            {"Metric": "Average SOG (kn)", region_a: seq_a.metrics.average_sog_knots, region_b: seq_b.metrics.average_sog_knots},
            {"Metric": "Max SOG (kn)", region_a: seq_a.metrics.max_sog_knots, region_b: seq_b.metrics.max_sog_knots},
            {"Metric": "Speed change (kn)", region_a: seq_a.metrics.speed_change_knots, region_b: seq_b.metrics.speed_change_knots},
            {"Metric": "Course change (°)", region_a: seq_a.metrics.course_change_degrees, region_b: seq_b.metrics.course_change_degrees},
            {"Metric": "Course events ≥15°", region_a: seq_a.metrics.course_change_events, region_b: seq_b.metrics.course_change_events},
        ]
    )
    st.dataframe(metrics, use_container_width=True, hide_index=True)

    chart_a = pd.DataFrame(seq_a.samples)
    chart_b = pd.DataFrame(seq_b.samples)
    st.subheader("Time-normalized sequence")
    chart = pd.DataFrame(
        {
            region_a: chart_a.set_index("elapsed_seconds")["sog_knots"],
            region_b: chart_b.set_index("elapsed_seconds")["sog_knots"],
        }
    ).sort_index()
    st.line_chart(chart, y_label="SOG (knots)", x_label="Elapsed seconds")

    st.caption("Source: live AISStream PositionReport observations only. No synthetic, mock, or fallback data.")


if __name__ == "__main__":
    main()
