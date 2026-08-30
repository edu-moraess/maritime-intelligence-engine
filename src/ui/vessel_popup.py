"""Vessel operational intelligence card."""
from __future__ import annotations

from datetime import datetime, timezone
from math import fabs

import streamlit as st

from src.ui.presentation import metric_strip, notice, panel_title


def _safe_float(value):
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _heading_delta(values):
    clean = [v for v in (_safe_float(x) for x in values) if v is not None]
    if len(clean) < 2:
        return None
    return max(min(fabs(b - a), 360.0 - fabs(b - a)) for a, b in zip(clean, clean[1:]))


def _signal_age(received_at):
    if received_at is None:
        return None
    try:
        stamp = received_at if received_at.tzinfo else received_at.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - stamp.astimezone(timezone.utc)).total_seconds())
    except (TypeError, ValueError):
        return None


def render_vessel_quick_intelligence(vessel, snapshot, *, show_gemini_hook=True):
    """Render an AIS-derived target profile; visual enrichment is explicitly lazy-loaded."""
    panel_title("Vessel Intelligence", "selected target")
    if vessel is None:
        notice("Select a target on the tactical map or fleet view to inspect its operational profile.")
        return

    mmsi = str(vessel.mmsi)
    name = str(getattr(vessel, "vessel_name", None) or getattr(vessel, "name", None) or "UNKNOWN VESSEL")
    observations = [o for o in (snapshot.observations or []) if str(getattr(o, "mmsi", "")) == mmsi]
    findings = [f for f in (snapshot.findings or []) if str(getattr(f, "mmsi", "")) == mmsi]
    reports = len(observations)

    st.markdown(
        f"<div style='margin:.1rem 0 .7rem'><div style='font-family:Inter,sans-serif;font-size:1rem;font-weight:650;color:#d9e6e9'>{name}</div>"
        f"<div style='font-family:IBM Plex Mono,monospace;font-size:.66rem;color:#79939b;letter-spacing:.06em;margin-top:.15rem'>MMSI {mmsi}</div></div>",
        unsafe_allow_html=True,
    )

    sog = _safe_float(getattr(vessel, "sog_knots", None))
    cog = _safe_float(getattr(vessel, "cog_degrees", None))
    hdg = _safe_float(getattr(vessel, "heading_degrees", None))
    lat = _safe_float(getattr(vessel, "latitude", None))
    lon = _safe_float(getattr(vessel, "longitude", None))
    nav_status = getattr(vessel, "navigational_status", None)

    speeds = [_safe_float(getattr(o, "sog_knots", None)) for o in observations]
    speeds = [x for x in speeds if x is not None]
    avg_sog = sum(speeds) / len(speeds) if speeds else None
    max_sog = max(speeds) if speeds else None
    headings = [getattr(o, "heading_degrees", None) for o in observations]
    heading_delta = _heading_delta(headings)
    latest_received = max((getattr(o, "received_at", None) for o in observations), default=getattr(vessel, "last_received", None))
    signal_age = _signal_age(latest_received)

    metric_strip({
        "SOG": f"{sog:.1f} kn" if sog is not None else "—",
        "COG": f"{cog:.0f}°" if cog is not None else "—",
        "HDG": f"{hdg:.0f}°" if hdg is not None else "—",
        "REPORTS": reports,
    })

    if lat is not None and lon is not None:
        st.markdown(
            f"<div class='small-note' style='margin:.15rem 0 .65rem'>POSITION · <span class='mono'>{lat:.5f}, {lon:.5f}</span></div>",
            unsafe_allow_html=True,
        )

    st.markdown("### Operational Status")
    metric_strip({
        "NAV STATUS": str(nav_status) if nav_status is not None else "UNKNOWN",
        "SIGNAL AGE": f"{signal_age:.0f} s" if signal_age is not None else "—",
        "DATA CONFIDENCE": "HIGH" if reports >= 3 else "LIMITED" if reports >= 2 else "LOW",
        "OBSERVATION COVERAGE": f"{reports} reports",
    })

    st.markdown("### Movement Profile")
    if reports >= 2:
        movement_state = "MOVING" if (avg_sog or 0) > 0.5 else "STOPPED"
        metric_strip({
            "STATE": movement_state,
            "AVG SOG": f"{avg_sog:.1f} kn" if avg_sog is not None else "—",
            "MAX SOG": f"{max_sog:.1f} kn" if max_sog is not None else "—",
            "HEADING VARIATION": f"{heading_delta:.0f}°" if heading_delta is not None else "—",
        })
        st.markdown("<div class='small-note' style='margin-top:.4rem'>Trajectory metrics are derived only from observations captured in the current AIS session.</div>", unsafe_allow_html=True)
    else:
        notice("INSUFFICIENT OBSERVATIONS · movement profile requires at least 2 AIS observations for this target.", "yellow")

    st.markdown("### Behavioral Signals")
    if reports >= 3:
        similar = [s for s in (snapshot.similar_tracks or []) if str(getattr(s, "mmsi", "")) == mmsi]
        score = max((float(getattr(f, "score", 0) or 0) for f in findings), default=None)
        metric_strip({
            "BEHAVIOR SCORE": f"{score:.2f}" if score is not None else "NOT SCORED",
            "CLUSTER": str(getattr(similar[0], "cluster", "NOT AVAILABLE")) if similar else "NOT AVAILABLE",
            "PATTERN": str(getattr(similar[0], "region", "NOT AVAILABLE")) if similar else "NOT AVAILABLE",
        })
    else:
        notice("INSUFFICIENT OBSERVATIONS · behavioral assessment requires at least 3 AIS observations.", "yellow")

    st.markdown("### Anomaly Assessment")
    if findings:
        top = max(findings, key=lambda f: float(getattr(f, "score", 0) or 0))
        category = str(getattr(top, "category", "behavioral signal"))
        score = float(getattr(top, "score", 0) or 0)
        confidence = _safe_float(getattr(top, "confidence", None))
        explanation = str(getattr(top, "explanation", "Observed movement deviates from the session baseline."))
        severity = "HIGH" if score >= 0.78 else "MEDIUM" if score >= 0.5 else "LOW"
        metric_strip({
            "SEVERITY": severity,
            "SCORE": f"{score:.2f}",
            "CONFIDENCE": f"{confidence:.2f}" if confidence is not None else "NOT PROVIDED",
        })
        notice(f"{category.upper()} · {explanation}", "red")
    else:
        notice("No behavioral anomaly is currently associated with this target in the observed session.", "green")

    # Keep image enrichment out of the critical selection path. It is available
    # on demand and cached in session state once resolved.
    photo_key = f"vessel_photo:{mmsi}"
    photo = st.session_state.get(photo_key)
    if photo:
        st.markdown("### Visual Identification")
        st.image(photo.image_bytes, caption=f"Visual identification · {photo.license_name} · {photo.author}", use_container_width=True)
    elif st.button("Load visual identification", key=f"load_photo:{mmsi}", use_container_width=True):
        try:
            from src.enrichment.vessel_photo import resolve_vessel_photo
            with st.spinner("Resolving verified vessel image…"):
                photo = resolve_vessel_photo(mmsi)
            if photo:
                st.session_state[photo_key] = photo
                st.rerun()
            else:
                notice("No verified vessel image was found for this MMSI.", "yellow")
        except Exception:
            notice("Visual identification is temporarily unavailable. AIS intelligence remains available.", "yellow")

    if show_gemini_hook:
        st.session_state["quick_intel_mmsi"] = mmsi
