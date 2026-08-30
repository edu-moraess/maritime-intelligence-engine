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
:root { --bg:#071116; --panel:#0d1c24; --panel-2:#10242d; --line:#1b3640; --text:#d9e6e9; --muted:#79939b; --cyan:#35c2c9; --green:#51c79b; --amber:#e9b857; --red:#ef6b73; }
html, body, [class*="css"] { font-family: Inter, sans-serif; }
.stApp { background: var(--bg); color: var(--text); }
.block-container { max-width: 1500px; padding: 1rem 1.25rem 2.5rem; }
[data-testid="stSidebar"] { background: #091820; border-right: 1px solid var(--line); }
header[data-testid="stHeader"] { background: transparent; }
h1, h2, h3 { letter-spacing: -0.025em; }
h1 { font-size: 1.65rem !important; margin-bottom: .2rem !important; }
h2 { font-size: 1.08rem !important; margin-top: .45rem !important; }
h3 { font-size: .93rem !important; }
[data-testid="stMetric"] { background: var(--panel); border: 1px solid var(--line); border-radius: 4px; padding: .55rem .7rem; }
[data-testid="stMetricLabel"] { color: var(--muted); font-size: .64rem; letter-spacing: .08em; text-transform: uppercase; }
[data-testid="stMetricValue"] { color: var(--text); font-family: 'IBM Plex Mono', monospace; font-size: 1rem; }
[data-testid="stDataFrame"] { border: 1px solid var(--line); }
div[data-baseweb="select"] > div, div[data-baseweb="input"] > div, textarea { background: #0b1a21; border-color: var(--line); }
.stButton > button { border: 1px solid var(--line); background: #0e232c; color: var(--text); border-radius: 3px; font-weight: 600; }
.stButton > button:hover { border-color: var(--cyan); color: var(--cyan); }
.operational-header { display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid var(--line); padding:.15rem 0 .8rem; margin-bottom:.85rem; }
.brand { font-weight:700; letter-spacing:.12em; font-size:.88rem; color:var(--text); }
.brand small { color:var(--muted); font-weight:500; letter-spacing:.04em; margin-left:.55rem; }
.utc { color:var(--muted); font-family:'IBM Plex Mono',monospace; font-size:.7rem; }
.status-pill { display:inline-flex; align-items:center; gap:.4rem; padding:.26rem .5rem; border:1px solid var(--line); background:#0b1a21; color:var(--muted); font:500 .66rem 'IBM Plex Mono',monospace; letter-spacing:.05em; }
.status-pill::before { content:''; width:.42rem; height:.42rem; border-radius:50%; background:currentColor; }
.status-live { color:var(--green); border-color:#245949; } .status-connecting { color:var(--amber); border-color:#5d4821; } .status-disconnected { color:var(--red); border-color:#5e2930; }
.panel { background:var(--panel); border:1px solid var(--line); padding:.8rem .9rem; min-height:100%; }
.panel-title { display:flex; justify-content:space-between; align-items:baseline; color:var(--muted); font-size:.65rem; letter-spacing:.1em; text-transform:uppercase; margin-bottom:.55rem; }
.mono { font-family:'IBM Plex Mono',monospace; }
.data-label { color:var(--muted); text-transform:uppercase; letter-spacing:.08em; font-size:.6rem; }
.data-value { color:var(--text); font-family:'IBM Plex Mono',monospace; font-size:.8rem; }
.empty-state { border:1px dashed #31505b; background:#0a1920; padding:2rem 1rem; text-align:center; color:var(--muted); }
.empty-state strong { display:block; color:var(--amber); font:600 .86rem 'IBM Plex Mono',monospace; letter-spacing:.08em; margin-bottom:.45rem; }
.notice { padding:.6rem .75rem; border-left:3px solid var(--amber); background:#17170e; color:#d7c99a; font-size:.76rem; line-height:1.45; }
.notice-red { border-left-color:var(--red); background:#1b1014; color:#e8b3b8; }
.notice-green { border-left-color:var(--green); background:#0e1c19; color:#b5ddc7; }
.small-note { color:var(--muted); font-size:.7rem; line-height:1.4; }
@media (max-width: 760px) { .block-container { padding:.75rem .65rem 2rem; } .operational-header { align-items:flex-start; gap:.5rem; } .brand small { display:block; margin:.15rem 0 0; } }
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def render_header(status: IngestionStatus, page_name: str) -> None:
    state = status.state
    css_state = "live" if state == "LIVE AIS" else "connecting" if state == "CONNECTING" else "disconnected"
    utc_now = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    st.markdown(
        f"<div class='operational-header'><div><span class='brand'>MARITIME INTELLIGENCE <small>/ {escape(page_name.upper())}</small></span></div><div style='display:flex;gap:.65rem;align-items:center'><span class='status-pill status-{css_state}'>{escape(state)}</span><span class='utc'>{utc_now}</span></div></div>",
        unsafe_allow_html=True,
    )


def metric_strip(values: dict[str, str | int | float]) -> None:
    cols = st.columns(len(values))
    for col, (label, value) in zip(cols, values.items()):
        with col:
            st.markdown(f"<div class='data-label'>{escape(label)}</div><div class='data-value'>{escape(str(value))}</div>", unsafe_allow_html=True)


def panel_title(title: str, meta: str = "") -> None:
    st.markdown(f"<div class='panel-title'><span>{escape(title)}</span><span class='mono'>{escape(meta)}</span></div>", unsafe_allow_html=True)


def empty_state(reason: str, title: str = "REAL AIS DATA UNAVAILABLE") -> None:
    st.markdown(f"<div class='empty-state'><strong>{escape(title)}</strong><span>{escape(reason)}</span></div>", unsafe_allow_html=True)


def notice(text: str, kind: str = "") -> None:
    class_name = "notice-red" if kind == "red" else "notice-green" if kind == "green" else ""
    st.markdown(f"<div class='notice {class_name}'>{escape(text)}</div>", unsafe_allow_html=True)


def frame_for_table(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for col in result.columns:
        if pd.api.types.is_datetime64_any_dtype(result[col]):
            result[col] = result[col].dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    return result
