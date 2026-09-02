"""Multi-channel mission page isolated from the stable MIE core.

The page orchestrates normal MaritimeIntelligenceEngine instances without
modifying AppSettings, app.py, or the production engine contract.
Only real AIS PositionReport observations are used.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pandas as pd
import streamlit as st

from src.analytics.multi_channel import filter_vessels, sequence_for_track, sequence_metrics
from src.config.settings import AppSettings
from src.intelligence.engine import MaritimeIntelligenceEngine
from src.ml.hybrid import fuse_scores, rank_hybrid


REGIONS: dict[str, tuple[tuple[float, float], tuple[float, float]]] = {
    "Miami": ((25.603, -80.208), (25.835, -79.879)),
    "English Channel": ((49.800, -5.500), (51.500, 2.500)),
}
ALL_CHANNELS = "All Channels"


def _settings_for(base: AppSettings, region: str) -> AppSettings:
    return replace(base, bbox=REGIONS[region], historical_persistence_enabled=False)


def _engine(base: AppSettings, region: str) -> MaritimeIntelligenceEngine:
    key = (base.aisstream_api_key, region, base.max_messages, base.max_vessels, base.stale_after_seconds)
    state_key = f"multi_engine_{region.lower().replace(' ', '_')}_v1"
    key_key = f"{state_key}_key"
    existing = st.session_state.get(state_key)
    if existing is None or st.session_state.get(key_key) != key:
        if existing is not None:
            existing.historical_writer.close()
        existing = MaritimeIntelligenceEngine(_settings_for(base, region))
        st.session_state[state_key] = existing
        st.session_state[key_key] = key
    return existing


def _collect(engines: dict[str, MaritimeIntelligenceEngine], seconds: float) -> dict[str, int]:
    with ThreadPoolExecutor(max_workers=len(engines), thread_name_prefix="mie-multi") as pool:
        futures = {name: pool.submit(engine.collect, seconds) for name, engine in engines.items()}
        return {name: future.result() for name, future in futures.items()}


def _resolve_channels(selection: list[str]) -> list[str]:
    if not selection or ALL_CHANNELS in selection:
        return list(REGIONS)
    return [name for name in selection if name in REGIONS]


def _snapshot_data(engines: dict[str, MaritimeIntelligenceEngine]) -> dict[str, object]:
    return {name: engine.snapshot() for name, engine in engines.items()}


def _vessel_label(vessel) -> str:
    return f"{vessel.mmsi} · {(vessel.vessel_name or 'UNKNOWN').strip()}"


def _hybrid_scores(snapshot) -> list:
    isolation = {}
    if snapshot.embeddings is not None:
        isolation = dict(zip(snapshot.embeddings.mmsis, snapshot.embeddings.anomaly_scores))
    temporal = {}
    if snapshot.temporal is not None:
        temporal = {score.mmsi: score.deep_anomaly_score for score in snapshot.temporal.scores}
    rules: dict[str, list[float]] = {}
    for finding in snapshot.findings:
        rules.setdefault(finding.mmsi, []).append(float(finding.score))
    mmsis = set(isolation) | set(temporal) | set(rules)
    return rank_hybrid([
        fuse_scores(
            mmsi,
            isolation_score=float(isolation[mmsi]) if mmsi in isolation else None,
            temporal_score=float(temporal[mmsi]) if mmsi in temporal else None,
            rule_scores=rules.get(mmsi),
        )
        for mmsi in mmsis
    ])


def main() -> None:
    st.set_page_config(page_title="Multi-Channel Mission", page_icon="⚓", layout="wide")
    st.title("Multi-Channel Maritime Mission")
    st.caption("Isolated feature · real AIS only · the stable MIE core is not modified")

    base = AppSettings.from_runtime(st.secrets)
    if not base.aisstream_api_key:
        st.error("AISSTREAM_API_KEY is not configured.")
        return

    selected = st.multiselect(
        "Mission channels",
        [ALL_CHANNELS, *REGIONS.keys()],
        default=[ALL_CHANNELS],
        help="All Channels collects every configured region in the same mission window.",
    )
    channels = _resolve_channels(selected)
    duration = st.select_slider("Collection window (seconds)", options=[30, 60, 120, 180, 300, 600, 900], value=900)

    engines = {name: _engine(base, name) for name in channels}
    controls, action = st.columns([3, 1])
    with controls:
        st.markdown("### Mission Controls")
        st.caption(f"{len(channels)} channel(s) selected · {duration}s bounded real-AIS collection")
    with action:
        collect = st.button("Collect Real AIS", type="primary", use_container_width=True)

    if collect:
        with st.spinner(f"Collecting {duration}s from {', '.join(channels)}..."):
            counts = _collect(engines, float(duration))
        st.success(" · ".join(f"{name}: {count} PositionReports" for name, count in counts.items()))

    snapshots = _snapshot_data(engines)
    if not snapshots:
        st.info("Select at least one configured channel.")
        return

    st.divider()
    st.subheader("Mission Overview")
    overview_rows = []
    for name, snapshot in snapshots.items():
        overview_rows.append({
            "Channel": name,
            "Active vessels": snapshot.readiness.distinct_vessels,
            "PositionReports": snapshot.status.position_reports_received,
            "Accepted": snapshot.status.position_reports_accepted,
            "Anomalies": snapshot.readiness.anomaly_count,
            "Tracks ≥2 points": snapshot.readiness.tracks_with_history,
            "Temporal ML": snapshot.readiness.temporal_status,
        })
    st.dataframe(pd.DataFrame(overview_rows), use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Map Controls")
    map_col, data_col = st.columns([2, 1])
    with map_col:
        channel_filter = st.selectbox("Channel", [ALL_CHANNELS, *channels], key="mission_channel_filter")
    with data_col:
        show_anomalies = st.checkbox("Show anomaly vessels", value=True)

    visible_channels = channels if channel_filter == ALL_CHANNELS else [channel_filter]
    visible_rows = []
    for name in visible_channels:
        snapshot = snapshots[name]
        for vessel in filter_vessels(snapshot.vessels, REGIONS[name]):
            visible_rows.append({
                "channel": name,
                "mmsi": vessel.mmsi,
                "latitude": vessel.latitude,
                "longitude": vessel.longitude,
                "sog_knots": vessel.sog_knots,
                "cog_degrees": vessel.cog_degrees,
                "vessel_name": vessel.vessel_name or "UNKNOWN",
            })
    visible_df = pd.DataFrame(visible_rows)
    if not visible_df.empty:
        st.map(visible_df.rename(columns={"latitude": "lat", "longitude": "lon"})[["lat", "lon"]])
    else:
        st.info("No current real AIS vessel position is inside the selected channel region.")

    st.subheader("Channel Analytics")
    analytics_cols = st.columns(max(1, len(visible_channels)))
    for index, name in enumerate(visible_channels):
        snapshot = snapshots[name]
        with analytics_cols[index]:
            st.markdown(f"**{name}**")
            st.metric("Vessels", snapshot.readiness.distinct_vessels)
            st.metric("Anomalies", snapshot.readiness.anomaly_count)
            st.metric("Avg speed (kn)", round(float(snapshot.summary.get("avg_speed_knots", 0.0)), 2))

    st.divider()
    st.subheader("Hybrid ML — Behavioral Ranking")
    st.caption("IsolationForest + Temporal Autoencoder + rule evidence. The hybrid score is a session-relative ranking signal, not a probability or calibrated confidence.")
    hybrid_rows = []
    for name in visible_channels:
        for score in _hybrid_scores(snapshots[name])[:10]:
            hybrid_rows.append({
                "Channel": name,
                "MMSI": score.mmsi,
                "Hybrid score": score.hybrid_score,
                "IsolationForest": score.isolation_score,
                "Temporal": score.temporal_score,
                "Rule score": score.rule_score,
                "Evidence": ", ".join(score.evidence) or "mixed/low signal",
            })
    if hybrid_rows:
        st.dataframe(pd.DataFrame(hybrid_rows), use_container_width=True, hide_index=True)
    else:
        st.info("Hybrid ranking needs enough real AIS tracks for at least one model signal.")

    st.divider()
    st.subheader("Vessel Sequential Analysis")
    available: dict[str, dict[str, str]] = {}
    for name in visible_channels:
        vessels = filter_vessels(snapshots[name].vessels, REGIONS[name])
        available[name] = {_vessel_label(vessel): vessel.mmsi for vessel in vessels}
    usable = {name: labels for name, labels in available.items() if labels}
    if not usable:
        st.info("Collect more real AIS data before selecting a vessel.")
        return

    channel_for_vessel = st.selectbox("Analysis channel", list(usable), key="sequence_channel")
    labels = usable[channel_for_vessel]
    selected_label = st.selectbox("Vessel", list(labels), key="sequence_vessel")
    selected_mmsi = labels[selected_label]
    snapshot = snapshots[channel_for_vessel]
    samples = sequence_for_track(selected_mmsi, snapshot.observations)
    metrics = sequence_metrics(selected_mmsi, snapshot.observations)
    st.dataframe(pd.DataFrame([metrics]), use_container_width=True, hide_index=True)

    if samples:
        seq_df = pd.DataFrame(samples).set_index("elapsed_seconds").sort_index()
        st.line_chart(seq_df[["sog_knots", "cog_degrees"]], y_label="AIS value", x_label="Elapsed seconds")

    if show_anomalies:
        findings = [f for name in visible_channels for f in snapshots[name].findings if f.mmsi == selected_mmsi]
        if findings:
            st.write("**Observed anomaly evidence**")
            st.dataframe(pd.DataFrame([{
                "Time": f.received_at,
                "Category": f.category,
                "Score": f.score,
                "Explanation": f.explanation,
            } for f in findings]), use_container_width=True, hide_index=True)

    st.caption("All displayed observations originate from live AISStream PositionReport data. No synthetic, mock, or fallback data is generated.")


if __name__ == "__main__":
    main()
