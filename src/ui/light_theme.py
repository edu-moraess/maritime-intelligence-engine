"""Light observatory presentation layer inspired by the ENSO Intelligence UI."""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

LIGHT_CSS = """
<style>
:root { --mie-bg:#f5f7fa; --mie-panel:#fff; --mie-panel-soft:#f8fafc; --mie-line:#e5e7eb; --mie-line-strong:#dbe2ea; --mie-text:#111827; --mie-muted:#64748b; --mie-blue:#2563eb; --mie-green:#047857; --mie-amber:#b45309; --mie-red:#b91c1c; }
html, body, [class*="css"] { font-family: Inter, sans-serif; }
.stApp { background:var(--mie-bg)!important; color:var(--mie-text)!important; }
.block-container { max-width:1400px!important; padding:1.25rem 1.5rem 2.5rem!important; }
[data-testid="stSidebar"] { background:#fff!important; border-right:1px solid var(--mie-line)!important; }
header[data-testid="stHeader"] { background:transparent!important; }
h1,h2,h3,p,label { color:var(--mie-text); } h1{font-weight:700!important;} h2,h3{font-weight:650!important;}
[data-testid="stMetric"] { background:#fff!important; border:1px solid var(--mie-line)!important; border-radius:10px!important; box-shadow:0 1px 2px rgba(15,23,42,.04); }
[data-testid="stMetricLabel"] { color:var(--mie-muted)!important; } [data-testid="stMetricValue"]{color:var(--mie-text)!important;}
[data-testid="stDataFrame"] { border:1px solid var(--mie-line)!important; border-radius:10px; overflow:hidden; }
div[data-baseweb="select"]>div,div[data-baseweb="input"]>div,textarea { background:#fff!important; border-color:var(--mie-line)!important; color:var(--mie-text)!important; }
.stButton>button { background:#fff!important; color:var(--mie-text)!important; border:1px solid var(--mie-line-strong)!important; border-radius:8px!important; }
.stButton>button:hover { border-color:var(--mie-blue)!important; color:var(--mie-blue)!important; }
.stButton>button[kind="primary"] { background:var(--mie-blue)!important; border-color:var(--mie-blue)!important; color:#fff!important; }
div[data-testid="stExpander"] { background:#fff!important; border:1px solid var(--mie-line)!important; border-radius:10px!important; }
.operational-header{border-bottom-color:var(--mie-line-strong)!important}.brand{color:var(--mie-text)!important}.brand small,.utc{color:var(--mie-muted)!important}
.status-pill{background:#f8fafc!important;border-color:var(--mie-line)!important}.status-live{color:var(--mie-green)!important;border-color:#a7f3d0!important;background:#ecfdf5!important}.status-connecting{color:var(--mie-amber)!important;border-color:#fde68a!important;background:#fffbeb!important}.status-disconnected{color:var(--mie-red)!important;border-color:#fecaca!important;background:#fef2f2!important}
.panel{background:#fff!important;border-color:var(--mie-line)!important;border-radius:10px;box-shadow:0 1px 2px rgba(15,23,42,.03)}
.panel-title,.data-label,.ops-metric .lbl,.section-kicker,.side-section-title,.side-section-label{color:var(--mie-muted)!important}.data-value,.ops-metric .val{color:var(--mie-text)!important}
.empty-state{background:#f8fafc!important;border-color:#cbd5e1!important;color:var(--mie-muted)!important;border-radius:10px}.empty-state strong{color:var(--mie-amber)!important}
.notice{background:#fffbeb!important;color:#92400e!important;border-left-color:#f59e0b!important;border-radius:0 8px 8px 0}.notice-red{background:#fef2f2!important;color:#991b1b!important;border-left-color:#dc2626!important}.notice-green{background:#ecfdf5!important;color:#065f46!important;border-left-color:#059669!important}
.ops-bar{background:#fff!important;border-color:var(--mie-line)!important;border-radius:10px;box-shadow:0 1px 2px rgba(15,23,42,.03)}.intel-status{background:#f8fafc!important;border-color:var(--mie-line)!important;border-radius:10px}.intel-chip{background:#fff!important;border-color:var(--mie-line)!important}.intel-ready{color:var(--mie-green)!important;border-color:#a7f3d0!important}.intel-partial{color:var(--mie-amber)!important;border-color:#fde68a!important}.intel-enabled{color:var(--mie-blue)!important;border-color:#bfdbfe!important}.intel-disabled,.intel-waiting{color:var(--mie-muted)!important}
.prov-live{color:var(--mie-green)!important;background:#ecfdf5!important;border-color:#a7f3d0!important}.prov-historical{color:var(--mie-blue)!important;background:#eff6ff!important;border-color:#bfdbfe!important}.prov-derived{color:var(--mie-amber)!important;background:#fffbeb!important;border-color:#fde68a!important}.prov-insufficient{color:var(--mie-muted)!important;background:#f8fafc!important;border-color:var(--mie-line)!important}
.side-header{border-bottom-color:var(--mie-line)!important}.side-section-title{border-top-color:var(--mie-line)!important}hr{border-top-color:var(--mie-line)!important}
[data-testid="stSlider"] [role="slider"]{background:var(--mie-blue)!important}[data-testid="stCheckbox"] label,[data-testid="stRadio"] label{color:var(--mie-text)!important}[data-testid="stCaptionContainer"]{color:var(--mie-muted)!important}
@media(max-width:760px){.block-container{padding:.9rem .75rem 2rem!important}}
</style>
"""

def _light_plotly(fig):
    if not isinstance(fig, go.Figure): return fig
    fig.update_layout(paper_bgcolor="#fff",plot_bgcolor="#fff",font={"family":"Inter, sans-serif","color":"#334155","size":11},title={"font":{"size":13,"color":"#111827"},"x":0},xaxis={"gridcolor":"#e5e7eb","zerolinecolor":"#cbd5e1","linecolor":"#cbd5e1"},yaxis={"gridcolor":"#e5e7eb","zerolinecolor":"#cbd5e1","linecolor":"#cbd5e1"},hoverlabel={"bgcolor":"#fff","font":{"color":"#111827"}})
    return fig

def inject_light_theme():
    if getattr(st,"_mie_light_theme_installed",False): return
    original_plotly_chart=st.plotly_chart
    original_pydeck_chart=st.pydeck_chart
    def light_plotly_chart(figure_or_data,*args,**kwargs): return original_plotly_chart(_light_plotly(figure_or_data),*args,**kwargs)
    def compatible_pydeck_chart(*args,**kwargs):
        kwargs.pop("height",None)
        deck=args[0] if args else kwargs.get("deck")
        if deck is not None and hasattr(deck,"map_style") and isinstance(deck.map_style,str) and "dark-matter-gl-style" in deck.map_style:
            deck.map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"
        return original_pydeck_chart(*args,**kwargs)
    st.plotly_chart=light_plotly_chart
    st.pydeck_chart=compatible_pydeck_chart
    st.session_state.setdefault("map_style","Positron")
    st._mie_light_theme_installed=True
    st.markdown(LIGHT_CSS,unsafe_allow_html=True)
