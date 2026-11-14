"""Presentation helpers for a professional, information-dense Streamlit shell."""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape

import pandas as pd
import streamlit as st

from src.ingestion.models import IngestionStatus


CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=Inter:wght@400;500;600;700&display=swap');
:root {
  --bg:#0A1118; --panel:#111E29; --panel-2:#172733; --line:#263A47;
  --text:#DCE5EA; --muted:#91A4B0; --cyan:#39A9C7; --green:#63A68A;
  --amber:#D5A34A; --red:#D45B5B;
}
html, body, [class*="css"] { font-family: Inter, sans-serif; }
.stApp { background: var(--bg); color: var(--text); }
/* Keep the app identity clear of Streamlit's native fixed header. */
.block-container { max-width: 1680px; padding: 1.5rem 1rem 2rem; }
[data-testid="stSidebar"] { background: #091820; border-right: 1px solid var(--line); }
/* Keep Streamlit's native header, toolbar and sidebar controls available. */
/* Only hide the decorative top stripe and footer; do not alter native navigation. */
div[data-testid="stDecoration"],
footer {
  display: none !important;
  visibility: hidden !important;
  height: 0 !important;
}

h1, h2, h3 { letter-spacing: -0.02em; }
h1 { font-size: 1.35rem !important; margin-bottom: .15rem !important; }
h2 { font-size: 1.0rem !important; margin-top: .35rem !important; margin-bottom: .35rem !important; }
h3 { font-size: .88rem !important; margin-top: .4rem !important; margin-bottom: .25rem !important; }
[data-testid="stMetric"] { background: var(--panel); border: 1px solid var(--line); border-radius: 3px; padding: .45rem .55rem; }
[data-testid="stMetricLabel"] { color: var(--muted); font-size: .6rem; letter-spacing: .08em; text-transform: uppercase; }
[data-testid="stMetricValue"] { color: var(--text); font-family: 'IBM Plex Mono', monospace; font-size: .95rem; }
[data-testid="stDataFrame"] { border: 1px solid var(--line); }
div[data-baseweb="select"] > div, div[data-baseweb="input"] > div, textarea { background: #0b1a21; border-color: var(--line); }
.stButton > button { border: 1px solid var(--line); background: #0e232c; color: var(--text); border-radius: 3px; font-weight: 600; }
.stButton > button:hover { border-color: var(--cyan); color: var(--cyan); }
div[data-testid="stExpander"] { background: var(--panel); border: 1px solid var(--line); border-radius: 3px; }
.operational-header { display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid var(--line); padding:.1rem 0 .55rem; margin-bottom:.55rem; }
.mie-command-header { min-height:2.7rem; gap:.4rem .65rem; flex-wrap:wrap; }
.mie-command-identity { display:contents; }
.mie-command-identity .brand { flex:0 0 100%; font-size:.88rem; letter-spacing:.14em; }
.mie-command-identity .brand small { color:var(--muted); font-size:.62rem; }
.mie-command-context { flex:1 1 auto; min-width:0; color:var(--muted); font:500 .58rem 'IBM Plex Mono',monospace; letter-spacing:.09em; }
.mie-command-status { flex:0 1 auto; display:flex; align-items:center; justify-content:flex-end; gap:.35rem; flex-wrap:nowrap; min-width:0; }
.mie-command-status .utc { white-space:nowrap; font-size:.58rem; }
.brand { font-weight:700; letter-spacing:.12em; font-size:.82rem; color:var(--text); }
.brand small { color:var(--muted); font-weight:500; letter-spacing:.04em; margin-left:.5rem; }
.utc { color:var(--muted); font-family:'IBM Plex Mono',monospace; font-size:.68rem; }
.status-pill { display:inline-flex; align-items:center; gap:.35rem; padding:.2rem .45rem; border:1px solid var(--line); background:#0b1a21; color:var(--muted); font:500 .64rem 'IBM Plex Mono',monospace; letter-spacing:.05em; }
.status-pill::before { content:''; width:.38rem; height:.38rem; border-radius:50%; background:currentColor; }
.status-live { color:var(--green); border-color:#245949; }
.status-connecting { color:var(--amber); border-color:#5d4821; }
.status-disconnected { color:var(--red); border-color:#5e2930; }
.panel { background:var(--panel); border:1px solid var(--line); padding:.65rem .75rem; min-height:100%; }
.panel-title { display:flex; justify-content:space-between; align-items:baseline; color:var(--muted); font-size:.62rem; letter-spacing:.1em; text-transform:uppercase; margin-bottom:.4rem; }
.mono { font-family:'IBM Plex Mono',monospace; }
.data-label { color:var(--muted); text-transform:uppercase; letter-spacing:.08em; font-size:.58rem; }
.data-value { color:var(--text); font-family:'IBM Plex Mono',monospace; font-size:.78rem; }
.empty-state { border:1px dashed #31505b; background:#0a1920; padding:1.5rem 1rem; text-align:center; color:var(--muted); }
.empty-state strong { display:block; color:var(--amber); font:600 .8rem 'IBM Plex Mono',monospace; letter-spacing:.08em; margin-bottom:.35rem; }
.notice { padding:.5rem .65rem; border-left:3px solid var(--amber); background:#17170e; color:#d7c99a; font-size:.74rem; line-height:1.4; }
.notice-red { border-left-color:var(--red); background:#1b1014; color:#e8b3b8; }
.notice-green { border-left-color:var(--green); background:#0e1c19; color:#b5ddc7; }
.small-note { color:var(--muted); font-size:.68rem; line-height:1.35; }
.ops-bar {
  display:grid; grid-template-columns: auto 1fr auto; gap:.75rem 1.1rem; align-items:center;
  background:var(--panel); border:1px solid var(--line); padding:.55rem .75rem; margin-bottom:.55rem;
}
.ops-live { display:flex; align-items:center; gap:.55rem; flex-wrap:wrap; }
.ops-live .region { color:var(--muted); font:500 .7rem Inter,sans-serif; letter-spacing:.04em; }
.ops-metrics { display:flex; flex-wrap:wrap; gap:.85rem 1.25rem; justify-content:center; }
.ops-metric .lbl { color:var(--muted); font-size:.55rem; letter-spacing:.1em; text-transform:uppercase; }
.ops-metric .val { font:500 .88rem 'IBM Plex Mono',monospace; color:var(--text); }
.ops-meta { text-align:right; color:var(--muted); font:400 .64rem 'IBM Plex Mono',monospace; line-height:1.45; }
.intel-status {
  display:flex; flex-wrap:wrap; gap:.35rem .55rem; align-items:center;
  background:var(--panel-2); border:1px solid var(--line); padding:.4rem .6rem; margin-bottom:.55rem;
}
.intel-status .title { color:var(--muted); font-size:.58rem; letter-spacing:.1em; text-transform:uppercase; margin-right:.35rem; }
.intel-chip {
  display:inline-flex; align-items:center; gap:.3rem; padding:.18rem .42rem;
  border:1px solid var(--line); background:#0b1a21; font:500 .62rem 'IBM Plex Mono',monospace; letter-spacing:.04em;
}
.intel-chip::before { content:''; width:.34rem; height:.34rem; border-radius:50%; background:currentColor; }
.intel-ready { color:var(--green); border-color:#245949; }
.intel-partial { color:var(--amber); border-color:#5d4821; }
.intel-waiting { color:var(--muted); border-color:var(--line); }
.intel-enabled { color:var(--cyan); border-color:#1e4a52; }
.intel-disabled { color:var(--muted); border-color:var(--line); }
.prov {
  display:inline-flex; align-items:center; gap:.28rem; padding:.12rem .4rem;
  border:1px solid var(--line); font:600 .58rem 'IBM Plex Mono',monospace; letter-spacing:.08em; vertical-align:middle;
}
.prov-live { color:var(--green); border-color:#245949; background:#0c1c18; }
.prov-historical { color:var(--cyan); border-color:#1e4a52; background:#0b1a21; }
.prov-derived { color:var(--amber); border-color:#5d4821; background:#17170e; }
.prov-insufficient { color:var(--muted); border-color:var(--line); background:#0a1419; }
.mie-map-legend {
  display:flex; flex-wrap:wrap; align-items:center; gap:.45rem 1.1rem;
  padding:.5rem .65rem; margin:.35rem 0 .25rem;
  background:var(--panel); border:1px solid var(--line);
  color:var(--muted); font:500 .58rem 'IBM Plex Mono',monospace;
  letter-spacing:.045em;
}
.mie-map-legend__group { display:flex; flex-wrap:wrap; align-items:center; gap:.4rem .7rem; }
.mie-map-legend__heading { color:var(--text); font-size:.55rem; letter-spacing:.1em; }
.mie-map-legend__item { display:inline-flex; align-items:center; gap:.32rem; white-space:nowrap; }
.mie-map-legend__swatch { width:.48rem; height:.48rem; display:inline-block; background:var(--legend-color); border-radius:1px; }
.mie-map-legend__swatch--selected { background:transparent; border:1.5px solid #fff; border-radius:50%; }
.mie-map-legend__line { width:1rem; border-top:2px solid var(--cyan); display:inline-block; }
.mie-map-legend__vector { width:1rem; border-top:2px dashed var(--amber); display:inline-block; }
@media (max-width:760px) {
  .mie-map-legend { align-items:flex-start; gap:.55rem; }
  .mie-map-legend__group { flex-basis:100%; gap:.35rem .65rem; }
}
.vessel-id { margin:.1rem 0 .45rem; }
.vessel-id .name { font:650 1.0rem Inter,sans-serif; color:var(--text); }
.vessel-id .mmsi { font:500 .66rem 'IBM Plex Mono',monospace; color:var(--muted); letter-spacing:.06em; margin-top:.12rem; }
.vessel-live-line { display:flex; flex-wrap:wrap; gap:.45rem; align-items:center; margin:.25rem 0 .55rem; }
.vessel-live-line .telem { font:500 .85rem 'IBM Plex Mono',monospace; color:var(--text); }
.section-kicker {
  color:var(--muted); font-size:.58rem; letter-spacing:.1em; text-transform:uppercase;
  margin:.55rem 0 .25rem; border-top:1px solid var(--line); padding-top:.45rem;
}
.section-kicker:first-child { border-top:none; padding-top:0; margin-top:.15rem; }
.side-header { margin:0 0 .75rem; padding-bottom:.55rem; border-bottom:1px solid var(--line); }
.side-header .brand { font-size:.92rem; letter-spacing:.14em; }
.side-subtitle { color:var(--muted); font:500 .62rem Inter,sans-serif; letter-spacing:.12em; margin:.2rem 0 .45rem; }
.side-status { display:flex; align-items:center; gap:.45rem; flex-wrap:wrap; }
.side-provider { color:var(--muted); font:500 .62rem 'IBM Plex Mono',monospace; letter-spacing:.08em; }
.side-section-title {
  color:var(--muted); font-size:.58rem; letter-spacing:.12em; text-transform:uppercase;
  margin:.85rem 0 .4rem; padding-top:.55rem; border-top:1px solid var(--line);
}
.side-section-title:first-of-type { margin-top:.35rem; }
.side-section-label {
  color:var(--muted); font-size:.58rem; letter-spacing:.1em; text-transform:uppercase;
  margin:.55rem 0 .25rem;
}
.side-muted { color:var(--muted) !important; font-size:.68rem !important; margin:.2rem 0 .15rem; }
@media (max-width: 980px) {
  .ops-bar { grid-template-columns: 1fr; }
  .ops-meta { text-align:left; }
  .ops-metrics { justify-content:flex-start; }
}
@media (max-width: 760px) {
  .block-container { padding:.65rem .55rem 1.75rem; }
  .operational-header { align-items:flex-start; gap:.4rem; }
  .brand small { display:block; margin:.12rem 0 0; }
  .mie-command-header { flex-wrap:wrap; }
  .mie-command-status { justify-content:flex-start; gap:.4rem; }
  .mie-command-context { font-size:.54rem; }
}
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def render_header(status: IngestionStatus, page_name: str) -> None:
    """Render the persistent command header from the current ingestion status."""
    state = status.state
    css_state = (
        "live" if state == "LIVE AIS"
        else "connecting" if state in {"CONNECTING", "RECONNECTING", "DEGRADED"}
        else "disconnected"
    )
    utc_now = datetime.now(timezone.utc).strftime("%Y-%m-%d · %H:%M:%S UTC")
    st.markdown(
        f"<div class='operational-header mie-command-header'>"
        f"<div class='mie-command-identity'>"
        f"<span class='brand'>MIE <small>/ ARQTECH LABS</small></span>"
        f"<span class='mie-command-context'>{escape(page_name.upper())} · MARITIME INTELLIGENCE</span>"
        f"</div>"
        f"<div class='mie-command-status'>"
        f"<span class='status-pill status-{css_state}'>{escape(state)}</span>"
        f"<span class='utc'>{utc_now}</span>"
        f"</div></div>",
        unsafe_allow_html=True,
    )


def metric_strip(values: dict[str, str | int | float]) -> None:
    cols = st.columns(len(values))
    for col, (label, value) in zip(cols, values.items()):
        with col:
            st.markdown(
                f"<div class='data-label'>{escape(label)}</div>"
                f"<div class='data-value'>{escape(str(value))}</div>",
                unsafe_allow_html=True,
            )


def panel_title(title: str, meta: str = "") -> None:
    st.markdown(
        f"<div class='panel-title'><span>{escape(title)}</span>"
        f"<span class='mono'>{escape(meta)}</span></div>",
        unsafe_allow_html=True,
    )


def empty_state(reason: str, title: str = "REAL AIS DATA UNAVAILABLE") -> None:
    st.markdown(
        f"<div class='empty-state'><strong>{escape(title)}</strong>"
        f"<span>{escape(reason)}</span></div>",
        unsafe_allow_html=True,
    )


def notice(text: str, kind: str = "") -> None:
    class_name = "notice-red" if kind == "red" else "notice-green" if kind == "green" else ""
    st.markdown(f"<div class='notice {class_name}'>{escape(text)}</div>", unsafe_allow_html=True)


def frame_for_table(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for col in result.columns:
        if pd.api.types.is_datetime64_any_dtype(result[col]):
            result[col] = result[col].dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    return result


_PROVENANCE_CLASS = {
    "LIVE": "prov-live",
    "HISTORICAL": "prov-historical",
    "DERIVED": "prov-derived",
    "INSUFFICIENT DATA": "prov-insufficient",
    "INSUFFICIENT_DATA": "prov-insufficient",
}


def provenance_badge(kind: str) -> str:
    """Return HTML for a standardized provenance badge (LIVE / HISTORICAL / DERIVED / …)."""
    label = (kind or "").strip().upper().replace("_", " ")
    if label == "INSUFFICIENTDATA":
        label = "INSUFFICIENT DATA"
    css = _PROVENANCE_CLASS.get(label, "prov-insufficient")
    display = label if label != "INSUFFICIENT DATA" else "INSUFFICIENT DATA"
    return f"<span class='prov {css}'>{escape(display)}</span>"


def section_kicker(title: str) -> None:
    st.markdown(f"<div class='section-kicker'>{escape(title)}</div>", unsafe_allow_html=True)


def render_ops_bar(
    *,
    live_state: str,
    region: str,
    vessels: int | str,
    messages: int | str,
    anomalies: int | str,
    collection: str,
    provenance: str = "AIS REAL ONLY",
    avg_speed: str | None = None,
    last_message: str | None = None,
) -> None:
    """Compact operational top strip: LIVE → region → counts → meta."""
    state = (live_state or "—").upper()
    is_live = state in {"LIVE AIS", "LIVE"}
    pill_cls = "status-live" if is_live else "status-connecting" if "CONNECT" in state else "status-disconnected"
    region_label = region or "CUSTOM / UNKNOWN"
    extra = ""
    if avg_speed is not None:
        extra += (
            f'<div class="ops-metric"><div class="lbl">Avg speed</div>'
            f'<div class="val">{escape(str(avg_speed))}</div></div>'
        )
    if last_message is not None:
        extra += (
            f'<div class="ops-metric"><div class="lbl">Last message</div>'
            f'<div class="val">{escape(str(last_message))}</div></div>'
        )
    st.markdown(
        f"""<div class="ops-bar">
  <div class="ops-live">
    <span class="status-pill {pill_cls}">{escape(state if is_live else state)}</span>
    <span class="region">{escape(str(region_label))}</span>
  </div>
  <div class="ops-metrics">
    <div class="ops-metric"><div class="lbl">Active vessels</div><div class="val">{escape(str(vessels))}</div></div>
    <div class="ops-metric"><div class="lbl">Messages</div><div class="val">{escape(str(messages))}</div></div>
    <div class="ops-metric"><div class="lbl">Anomaly events</div><div class="val">{escape(str(anomalies))}</div></div>
    {extra}
  </div>
  <div class="ops-meta">{escape(str(collection))}<br/>{escape(str(provenance))}</div>
</div>""",
        unsafe_allow_html=True,
    )


def _intel_chip_class(status: str) -> str:
    s = (status or "").upper()
    if s in {"READY", "LIVE"}:
        return "intel-ready"
    if s in {"PARTIAL", "LIMITED"}:
        return "intel-partial"
    if s == "ENABLED":
        return "intel-enabled"
    if s in {"DISABLED", "OFF", "N/A"}:
        return "intel-disabled"
    return "intel-waiting"


def render_region_comparison(comparison) -> None:
    """Render shared-session regional intelligence without ranking regions."""
    if comparison is None:
        return
    st.markdown(
        "<div class='panel-title'><span>REGIONAL INTELLIGENCE</span>"
        "<span class='mono'>SHARED SESSION · DERIVED</span></div>",
        unsafe_allow_html=True,
    )
    columns = st.columns(2)
    for column, region in zip(columns, comparison.regions):
        with column:
            st.markdown(f"**{escape(region.label)}**")
            metric_strip(
                {
                    "Observed vessels": region.unique_vessels,
                    "Reports": region.position_reports,
                    "Avg speed": (f"{region.average_speed_knots:.1f} kn" if region.average_speed_knots is not None else "N/A"),
                    "Anomaly events": region.anomalies,
                }
            )
            temporal_score = (
                f"{region.average_temporal_score:.4f}"
                if region.average_temporal_score is not None
                else "—"
            )
            top_quartile_rate = (
                f"{region.temporal_top_quartile_rate:.1%}"
                if region.temporal_top_quartile_rate is not None
                else f"N/A · {region.temporal_status}"
            )
            st.caption(
                "Temporal score: " + temporal_score
                + " · top-quartile rate: " + top_quartile_rate
                + " · anomaly rate: "
                + f"{region.anomaly_rate:.1%}"
            )
            if region.temporal_reason and (
                region.temporal_status != "READY"
                or region.temporal_top_quartile_rate is None
            ):
                st.caption("Temporal availability · " + escape(region.temporal_reason))
    exclusions = []
    if comparison.ambiguous_observations:
        exclusions.append(
            f"{comparison.ambiguous_observations:,} observation(s) inside both regions"
        )
    if comparison.unassigned_observations:
        exclusions.append(
            f"{comparison.unassigned_observations:,} observation(s) outside both regions"
        )
    if exclusions:
        st.caption(
            "Excluded from regional metrics: " + " · ".join(exclusions)
            + ". Regional reports therefore need not sum to all session messages."
        )
    else:
        st.caption("Regional metrics use the same real-AIS session and shared analytical models; all session observations were assigned to exactly one region.")


def render_regional_events(events) -> None:
    """Render a compact temporal event feed from deterministic AIS evidence."""
    if not events:
        return
    recent = list(events[-8:])[::-1]
    st.markdown(
        "<div class='panel-title'><span>REGIONAL EVENT FEED</span>"
        "<span class='mono'>REAL AIS · DERIVED</span></div>",
        unsafe_allow_html=True,
    )
    rows = []
    for event in recent:
        timestamp = event.timestamp.strftime("%H:%M:%S UTC")
        duration = f"{event.duration_seconds:.0f}s" if event.duration_seconds is not None else "—"
        rows.append(f"{timestamp} · {escape(event.mmsi)} · {escape(event.event_type)} · {escape(event.region_label)} · {duration}")
    st.code("\n".join(rows), language=None)

def render_intelligence_status(items: list[tuple[str, str]]) -> None:
    """Compact intelligence readiness strip. items = [(label, status), ...]."""
    chips = []
    for label, status in items:
        cls = _intel_chip_class(status)
        chips.append(
            f"<span class='intel-chip {cls}'>{escape(label)} · {escape(str(status))}</span>"
        )
    st.markdown(
        "<div class='intel-status'><span class='title'>Intelligence status</span>"
        + "".join(chips)
        + "</div>",
        unsafe_allow_html=True,
    )
