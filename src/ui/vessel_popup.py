"""Vessel operational intelligence card."""
from __future__ import annotations

import streamlit as st

from src.ui.presentation import metric_strip, notice, panel_title


def render_vessel_quick_intelligence(vessel, snapshot, *, show_gemini_hook=True):
    """Render an AIS-derived target profile without network enrichment."""
    panel_title("Vessel Intelligence", "selected target")
    if vessel is None:
        notice("Select a target on the tactical map or fleet view to inspect its operational profile.")
        return

    mmsi = str(vessel.mmsi)
    name = str(getattr(vessel, "vessel_name", None) or getattr(vessel, "name", None) or "UNKNOWN VESSEL")
    findings = [f for f in (snapshot.findings or []) if str(getattr(f, "mmsi", "")) == mmsi]
    track_count = sum(1 for o in (snapshot.observations or []) if str(getattr(o, "mmsi", "")) == mmsi)

    st.markdown(
        f"<div style='margin:.1rem 0 .7rem'><div style='font-family:Inter,sans-serif;font-size:1rem;font-weight:650;color:#d9e6e9'>{name}</div>"
        f"<div style='font-family:IBM Plex Mono,monospace;font-size:.66rem;color:#79939b;letter-spacing:.06em;margin-top:.15rem'>MMSI {mmsi}</div></div>",
        unsafe_allow_html=True,
    )

    sog = getattr(vessel, "sog_knots", None)
    cog = getattr(vessel, "cog_degrees", None)
    hdg = getattr(vessel, "heading_degrees", None)
    lat = getattr(vessel, "latitude", None)
    lon = getattr(vessel, "longitude", None)

    metric_strip({
        "SOG": f"{float(sog):.1f} kn" if sog is not None else "—",
        "COG": f"{float(cog):.0f}°" if cog is not None else "—",
        "HDG": f"{float(hdg):.0f}°" if hdg is not None else "—",
        "REPORTS": track_count,
    })

    if lat is not None and lon is not None:
        st.markdown(
            f"<div class='small-note' style='margin:.15rem 0 .65rem'>POSITION · <span class='mono'>{float(lat):.5f}, {float(lon):.5f}</span></div>",
            unsafe_allow_html=True,
        )

    if findings:
        top = max(findings, key=lambda f: float(getattr(f, "score", 0) or 0))
        category = str(getattr(top, "category", "behavioral signal"))
        score = float(getattr(top, "score", 0) or 0)
        explanation = str(getattr(top, "explanation", "Observed movement deviates from the session baseline."))
        notice(f"{category.upper()} · score {score:.2f}\n{explanation}", "red")
    else:
        notice("No behavioral anomaly is currently associated with this target in the observed session.", "green")

    if show_gemini_hook:
        st.session_state["quick_intel_mmsi"] = mmsi
        st.session_state.pop("quick_intel_photo_bytes", None)
        st.session_state.pop("quick_intel_photo_mime", None)
