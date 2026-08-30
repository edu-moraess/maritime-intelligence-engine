"""Vessel Quick Intelligence card."""
from __future__ import annotations
import streamlit as st
from src.enrichment.vessel_photo import VesselPhoto, resolve_vessel_photo
from src.ui.presentation import notice, panel_title

def render_vessel_quick_intelligence(vessel, snapshot, *, show_gemini_hook=True):
    panel_title("Quick Intelligence", "selected target")
    if vessel is None:
        notice("Select a vessel on the map or via the target list to open Quick Intelligence.")
        return
    mmsi = str(vessel.mmsi)
    name = str(getattr(vessel, "vessel_name", None) or getattr(vessel, "name", None) or "UNKNOWN VESSEL")
    st.markdown(f"<div style='font-family:IBM Plex Mono,monospace;font-size:0.78rem;letter-spacing:.04em;color:#d9e6e9;margin-bottom:.4rem'><div style='color:#35c2c9;font-weight:600;font-size:0.9rem'>{name}</div><div>MMSI {mmsi}</div></div>", unsafe_allow_html=True)
    sog, cog, hdg = getattr(vessel,"sog_knots",None), getattr(vessel,"cog_degrees",None), getattr(vessel,"heading_degrees",None)
    lat, lon = getattr(vessel,"latitude",None), getattr(vessel,"longitude",None)
    cols = st.columns(4)
    cols[0].markdown(_kv("SOG", f"{float(sog):.1f} kn" if sog is not None else "—"))
    cols[1].markdown(_kv("COG", f"{float(cog):.0f}°" if cog is not None else "—"))
    cols[2].markdown(_kv("HDG", f"{float(hdg):.0f}°" if hdg is not None else "—"))
    cols[3].markdown(_kv("POS", f"{float(lat):.3f}, {float(lon):.3f}" if lat is not None and lon is not None else "—"))
    findings = [f for f in (snapshot.findings or []) if str(getattr(f,"mmsi","")) == mmsi]
    if findings:
        top = max(findings, key=lambda f: float(getattr(f,"score",0) or 0))
        st.markdown(f"<div style='font-family:IBM Plex Mono,monospace;font-size:0.7rem;color:#ef6b73;margin:.35rem 0'>ANOMALY · {getattr(top,'category','flagged')} · score {float(getattr(top,'score',0) or 0):.2f}</div>", unsafe_allow_html=True)
    else:
        st.markdown("<div style='font-family:IBM Plex Mono,monospace;font-size:0.7rem;color:#35c2c9;margin:.35rem 0'>STATUS NOMINAL (session)</div>", unsafe_allow_html=True)
    photo = _cached_photo(mmsi, getattr(vessel, "imo", None))
    if photo is not None:
        st.image(photo.image_bytes, width="stretch")
        st.caption(f"{photo.commons_title} · {photo.license_name} · {photo.author} · {photo.qid}")
    else:
        st.markdown("<div style='border:1px solid #1b3640;background:#0b171c;padding:1.2rem;text-align:center;font-family:IBM Plex Mono,monospace;font-size:0.72rem;color:#79939b;letter-spacing:.08em'>IMAGE UNAVAILABLE</div>", unsafe_allow_html=True)
    if show_gemini_hook:
        st.session_state["quick_intel_mmsi"] = mmsi
        if photo is not None:
            st.session_state["quick_intel_photo_bytes"] = photo.image_bytes
            st.session_state["quick_intel_photo_mime"] = photo.mime_type
        else:
            st.session_state.pop("quick_intel_photo_bytes", None)
            st.session_state.pop("quick_intel_photo_mime", None)

def _kv(label, value):
    return f"<div style='font-family:IBM Plex Mono,monospace;font-size:0.65rem;color:#79939b'><div>{label}</div><div style='color:#d9e6e9;font-size:0.78rem'>{value}</div></div>"

@st.cache_data(ttl=3600, show_spinner=False)
def _cached_photo(mmsi, imo):
    return resolve_vessel_photo(mmsi, imo=imo)
