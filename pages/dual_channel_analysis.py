"""Dual-channel sequential analysis using one real AISStream subscription."""

from __future__ import annotations

import streamlit as st

from src.analytics.dual_channel import compare_sequences, vessels_in_bbox
from src.config.regions import REGION_OPTIONS, REGION_PRESETS, format_bbox
from src.config.settings import AppSettings
from src.intelligence.engine import MaritimeIntelligenceEngine, create_engine


REGION_CHOICES = tuple(name for name in REGION_OPTIONS if name != "Custom")
DEFAULT_A = "Miami"
DEFAULT_B = "English Channel"


def _engine_for(settings: AppSettings) -> MaritimeIntelligenceEngine:
    signature = (
        settings.aisstream_api_key,
        tuple(settings.monitoring_bboxes),
        settings.max_messages,
        settings.max_vessels,
        settings.stale_after_seconds,
    )
    if st.session_state.get("dual_engine_signature") != signature:
        previous = st.session_state.get("dual_engine")
        if previous is not None:
            previous.historical_writer.close()
        st.session_state.dual_engine = create_engine(settings)
        st.session_state.dual_engine_signature = signature
        st.session_state.pop("dual_mmsi_a", None)
        st.session_state.pop("dual_mmsi_b", None)
    return st.session_state.dual_engine


def _settings() -> AppSettings:
    try:
        secrets = st.secrets
    except Exception:
        secrets = None
    return AppSettings.from_runtime(secrets)


def _with_regions(settings: AppSettings, region_a: str, region_b: str) -> AppSettings:
    bbox_a = REGION_PRESETS[region_a]
    bbox_b = REGION_PRESETS[region_b]
    return AppSettings(
        aisstream_api_key=settings.aisstream_api_key,
        bbox=bbox_a,
        monitoring_bboxes=(bbox_a, bbox_b),
        collection_seconds=settings.collection_seconds,
        max_messages=settings.max_messages,
        max_vessels=settings.max_vessels,
        stale_after_seconds=settings.stale_after_seconds,
        provider=settings.provider,
        config_error=settings.config_error,
        database_url=settings.database_url,
        # Historical persistence is intentionally disabled here until the
        # writer can attribute each observation to its originating region.
        historical_persistence_enabled=False,
    )


def _label(vessel) -> str:
    name = vessel.vessel_name or "UNKNOWN"
    return f"{name[:28]} · MMSI {vessel.mmsi}"


def _metric(value, suffix: str = "") -> str:
    return "—" if value is None else f"{value:.2f}{suffix}"


def main() -> None:
    st.set_page_config(page_title="MIE · Dual-Channel Analysis", page_icon="◈", layout="wide")
    st.title("Dual-Channel Sequential Analysis")
    st.caption("Two real AIS regions · one AISStream subscription · sequence-based vessel comparison")

    base = _settings()
    col_a, col_b = st.columns(2)
    with col_a:
        region_a = st.selectbox("Channel A", REGION_CHOICES, index=REGION_CHOICES.index(DEFAULT_A), key="dual_region_a")
        st.caption(format_bbox(REGION_PRESETS[region_a]))
    with col_b:
        choices_b = tuple(name for name in REGION_CHOICES if name != region_a)
        default_b = DEFAULT_B if DEFAULT_B != region_a else choices_b[0]
        region_b = st.selectbox("Channel B", choices_b, index=choices_b.index(default_b), key="dual_region_b")
        st.caption(format_bbox(REGION_PRESETS[region_b]))

    settings = _with_regions(base, region_a, region_b)
    engine = _engine_for(settings)

    control_a, control_b = st.columns(2)
    with control_a:
        collect = st.button("Collect Real AIS · 2 Channels", type="primary", use_container_width=True, disabled=settings.config_error is not None)
    with control_b:
        clear = st.button("Clear Dual-Channel Session", use_container_width=True)

    if clear:
        engine.clear_session_data()
        st.session_state.pop("dual_mmsi_a", None)
        st.session_state.pop("dual_mmsi_b", None)
        st.rerun()

    if collect:
        with st.spinner(f"Collecting real AIS from {region_a} + {region_b} for {int(settings.collection_seconds)} seconds…"):
            received = engine.collect(settings.collection_seconds)
        if received:
            st.success(f"Received {received:,} real AIS PositionReport(s) across both channels.")
        else:
            st.warning("REAL AIS DATA UNAVAILABLE — no observations were received in this window.")

    snapshot = engine.snapshot()
    tracks = engine.store.tracks()
    vessels_a = vessels_in_bbox(snapshot.vessels, REGION_PRESETS[region_a])
    vessels_b = vessels_in_bbox(snapshot.vessels, REGION_PRESETS[region_b])

    st.divider()
    st.subheader("Vessel focus")
    sel_a, sel_b = st.columns(2)
    with sel_a:
        options_a = [v.mmsi for v in vessels_a]
        current_a = st.session_state.get("dual_mmsi_a")
        idx_a = options_a.index(current_a) if current_a in options_a else 0
        mmsi_a = st.selectbox("Vessel A · Channel A", options_a, index=idx_a, format_func=lambda m: _label(next(v for v in vessels_a if v.mmsi == m)), key="dual_mmsi_a") if options_a else None
    with sel_b:
        options_b = [v.mmsi for v in vessels_b]
        current_b = st.session_state.get("dual_mmsi_b")
        idx_b = options_b.index(current_b) if current_b in options_b else 0
        mmsi_b = st.selectbox("Vessel B · Channel B", options_b, index=idx_b, format_func=lambda m: _label(next(v for v in vessels_b if v.mmsi == m)), key="dual_mmsi_b") if options_b else None

    if not mmsi_a or not mmsi_b:
        st.info("Colete dados reais até existir pelo menos uma embarcação observada em cada canal.")
        st.caption(f"Channel A: {len(vessels_a)} vessel(s) · Channel B: {len(vessels_b)} vessel(s)")
        return

    sequence_a, sequence_b = compare_sequences(tracks.get(mmsi_a, []), tracks.get(mmsi_b, []))
    metrics_a = sequence_a.metrics
    metrics_b = sequence_b.metrics

    st.subheader("Current state")
    current_a, current_b = st.columns(2)
    vessel_a = next(v for v in vessels_a if v.mmsi == mmsi_a)
    vessel_b = next(v for v in vessels_b if v.mmsi == mmsi_b)
    with current_a:
        st.markdown(f"**{region_a} · {vessel_a.mmsi}**")
        st.write(f"Position: `{vessel_a.latitude:.5f}, {vessel_a.longitude:.5f}`")
        st.write(f"SOG: **{_metric(vessel_a.sog_knots, ' kn')}** · COG: **{_metric(vessel_a.cog_degrees, '°')}**")
    with current_b:
        st.markdown(f"**{region_b} · {vessel_b.mmsi}**")
        st.write(f"Position: `{vessel_b.latitude:.5f}, {vessel_b.longitude:.5f}`")
        st.write(f"SOG: **{_metric(vessel_b.sog_knots, ' kn')}** · COG: **{_metric(vessel_b.cog_degrees, '°')}**")

    st.subheader("Sequential comparison")
    metric_rows = {
        "Observed points": [metrics_a.points, metrics_b.points],
        "Track duration (s)": [metrics_a.duration_seconds, metrics_b.duration_seconds],
        "Distance observed (nm)": [metrics_a.distance_nm, metrics_b.distance_nm],
        "Average SOG (kn)": [metrics_a.average_sog_knots, metrics_b.average_sog_knots],
        "Maximum SOG (kn)": [metrics_a.max_sog_knots, metrics_b.max_sog_knots],
        "Speed change (kn)": [metrics_a.speed_change_knots, metrics_b.speed_change_knots],
        "Cumulative course change (°)": [metrics_a.course_change_degrees, metrics_b.course_change_degrees],
        "Course-change events ≥15°": [metrics_a.course_change_events, metrics_b.course_change_events],
        "Mean sample interval (s)": [metrics_a.mean_sample_interval_seconds, metrics_b.mean_sample_interval_seconds],
    }
    st.dataframe({"Metric": list(metric_rows), region_a: [row[0] for row in metric_rows.values()], region_b: [row[1] for row in metric_rows.values()]}, use_container_width=True, hide_index=True)

    if sequence_a.samples or sequence_b.samples:
        st.subheader("Time-normalized sequence")
        chart_a, chart_b = st.columns(2)
        with chart_a:
            st.caption(f"{region_a} · SOG over observed sequence")
            st.line_chart({"SOG (kn)": [sample["sog_knots"] for sample in sequence_a.samples]})
            st.caption(f"{region_a} · COG over observed sequence")
            st.line_chart({"COG (°)": [sample["cog_degrees"] for sample in sequence_a.samples]})
        with chart_b:
            st.caption(f"{region_b} · SOG over observed sequence")
            st.line_chart({"SOG (kn)": [sample["sog_knots"] for sample in sequence_b.samples]})
            st.caption(f"{region_b} · COG over observed sequence")
            st.line_chart({"COG (°)": [sample["cog_degrees"] for sample in sequence_b.samples]})

    st.caption("All metrics above are derived exclusively from real AIS observations received in this session. No synthetic, mock, or fallback data is used.")


if __name__ == "__main__":
    main()
