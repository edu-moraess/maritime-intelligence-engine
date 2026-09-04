"""Global light presentation layer for the Maritime Intelligence Engine."""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

LIGHT_CSS = """
<style>
:root{--mie-bg:#f5f7fa;--mie-panel:#fff;--mie-panel-soft:#f8fafc;--mie-line:#e5e7eb;--mie-line-strong:#dbe2ea;--mie-text:#111827;--mie-muted:#64748b;--mie-blue:#2563eb;--mie-green:#047857;--mie-amber:#b45309;--mie-red:#b91c1c}
html,body,[class*="css"]{font-family:Inter,sans-serif}
.stApp,[data-testid="stAppViewContainer"],[data-testid="stMain"]{background:var(--mie-bg)!important;color:var(--mie-text)!important}
.block-container{max-width:1400px!important;padding:1.25rem 1.5rem 2.5rem!important}
[data-testid="stSidebar"]{background:#fff!important;border-right:1px solid var(--mie-line)!important} header[data-testid="stHeader"]{background:#fff!important}
h1,h2,h3,h4,h5,h6,p,label,span{color:var(--mie-text)}
[data-testid="stCaptionContainer"],.small-note,.data-label,.panel-title{color:var(--mie-muted)!important}
[data-testid="stMetric"],.panel,.ops-bar,div[data-testid="stExpander"]{background:#fff!important;border:1px solid var(--mie-line)!important;border-radius:10px!important;box-shadow:0 1px 2px rgba(15,23,42,.04)}
[data-testid="stMetricLabel"]{color:var(--mie-muted)!important}[data-testid="stMetricValue"],.data-value,.ops-metric .val{color:var(--mie-text)!important}
[data-testid="stDataFrame"]{border:1px solid var(--mie-line)!important;border-radius:10px!important;overflow:hidden}
div[data-baseweb="select"]>div,div[data-baseweb="input"]>div,textarea{background:#fff!important;border-color:var(--mie-line)!important;color:var(--mie-text)!important}
.stButton>button{background:#fff!important;color:var(--mie-text)!important;border:1px solid var(--mie-line-strong)!important;border-radius:8px!important}.stButton>button:hover{border-color:var(--mie-blue)!important;color:var(--mie-blue)!important}.stButton>button[kind="primary"]{background:var(--mie-blue)!important;color:#fff!important}
.operational-header{border-bottom-color:var(--mie-line-strong)!important}.brand{color:var(--mie-text)!important}.brand small,.utc{color:var(--mie-muted)!important}
.status-pill{background:#f8fafc!important;border-color:var(--mie-line)!important}.status-live{color:var(--mie-green)!important;background:#ecfdf5!important;border-color:#a7f3d0!important}.status-connecting{color:var(--mie-amber)!important;background:#fffbeb!important;border-color:#fde68a!important}.status-disconnected{color:var(--mie-red)!important;background:#fef2f2!important;border-color:#fecaca!important}
.panel-title,.data-label,.ops-metric .lbl,.section-kicker,.side-section-title,.side-section-label{color:var(--mie-muted)!important}.empty-state{background:#f8fafc!important;border-color:#cbd5e1!important;color:var(--mie-muted)!important;border-radius:10px!important}.empty-state strong{color:var(--mie-amber)!important}
.notice{background:#fffbeb!important;color:#92400e!important;border-left-color:#f59e0b!important}.notice-red{background:#fef2f2!important;color:#991b1b!important;border-left-color:#dc2626!important}.notice-green{background:#ecfdf5!important;color:#065f46!important;border-left-color:#059669!important}
.ops-bar,.intel-status{background:#fff!important;border-color:var(--mie-line)!important}.intel-chip{background:#fff!important;border-color:var(--mie-line)!important}.prov-live{color:var(--mie-green)!important;background:#ecfdf5!important;border-color:#a7f3d0!important}.prov-historical{color:var(--mie-blue)!important;background:#eff6ff!important;border-color:#bfdbfe!important}.prov-derived{color:var(--mie-amber)!important;background:#fffbeb!important;border-color:#fde68a!important}.prov-insufficient{color:var(--mie-muted)!important;background:#f8fafc!important;border-color:var(--mie-line)!important}
.side-header{border-bottom-color:var(--mie-line)!important}.side-section-title{border-top-color:var(--mie-line)!important}hr{border-top-color:var(--mie-line)!important}[data-testid="stCheckbox"] label,[data-testid="stRadio"] label{color:var(--mie-text)!important}
@media(max-width:760px){.block-container{padding:.9rem .75rem 2rem!important}}
</style>
"""

POSITRON_STYLE="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"

def _light_plotly(fig):
    if not isinstance(fig,go.Figure): return fig
    fig.update_layout(paper_bgcolor="#fff",plot_bgcolor="#fff",font={"family":"Inter, sans-serif","color":"#334155","size":11},title={"font":{"size":13,"color":"#111827"},"x":0},xaxis={"gridcolor":"#e5e7eb","zerolinecolor":"#cbd5e1","linecolor":"#cbd5e1"},yaxis={"gridcolor":"#e5e7eb","zerolinecolor":"#cbd5e1","linecolor":"#cbd5e1"},hoverlabel={"bgcolor":"#fff","font":{"color":"#111827"}})
    fig.update_geos(showland=True,landcolor="#e2e8f0",showocean=True,oceancolor="#f1f5f9",showcountries=True,countrycolor="#94a3b8",coastlinecolor="#64748b")
    return fig

def _force_light_deck(deck):
    if deck is None:return deck
    if hasattr(deck,"map_style"): deck.map_style=POSITRON_STYLE
    tooltip=getattr(deck,"tooltip",None)
    if isinstance(tooltip,dict):
        style=dict(tooltip.get("style") or {});style.update({"backgroundColor":"#fff","color":"#111827","border":"1px solid #e5e7eb"});tooltip["style"]=style;deck.tooltip=tooltip
    return deck

def inject_light_theme():
    if getattr(st,"_mie_light_theme_installed",False):return
    original_plotly_chart=st.plotly_chart;original_pydeck_chart=st.pydeck_chart
    def light_plotly_chart(figure_or_data,*args,**kwargs):return original_plotly_chart(_light_plotly(figure_or_data),*args,**kwargs)
    def light_pydeck_chart(*args,**kwargs):
        kwargs.pop("height",None)
        if args:args=(_force_light_deck(args[0]),*args[1:])
        elif "deck" in kwargs:kwargs["deck"]=_force_light_deck(kwargs["deck"])
        return original_pydeck_chart(*args,**kwargs)
    st.plotly_chart=light_plotly_chart;st.pydeck_chart=light_pydeck_chart
    st.session_state["map_style"]="Positron";st._mie_light_theme_installed=True
    st.markdown(LIGHT_CSS,unsafe_allow_html=True)
