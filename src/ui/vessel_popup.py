"""Vessel operational intelligence card — Operations Workstation hierarchy."""
from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from math import fabs

import streamlit as st

from src.ui.presentation import (
    metric_strip,
    notice,
    panel_title,
    provenance_badge,
    section_kicker,
)


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
    heading_delta = _heading_delta([getattr(o, "heading_degrees", None) for o in observations])
    latest_received = max(
        (getattr(o, "received_at", None) for o in observations),
        default=getattr(vessel, "last_received", None),
    )
    signal_age = _signal_age(latest_received)

    confidence = "HIGH" if reports >= 3 else "LIMITED" if reports >= 2 else "LOW"
    telem_parts = []
    if sog is not None:
        telem_parts.append(f"{sog:.1f} kn")
    if cog is not None:
        telem_parts.append(f"{cog:.0f}°")
    elif hdg is not None:
        telem_parts.append(f"HDG {hdg:.0f}°")
    telem = " · ".join(telem_parts) if telem_parts else "—"

    st.markdown(
        f"<div class='vessel-id'>"
        f"<div class='name'>{escape(name)}</div>"
        f"<div class='mmsi'>MMSI {escape(mmsi)}</div>"
        f"</div>"
        f"<div class='vessel-live-line'>{provenance_badge('LIVE')}"
        f"<span class='telem'>{escape(telem)}</span></div>",
        unsafe_allow_html=True,
    )

    section_kicker("Data confidence")
    metric_strip({
        "CONFIDENCE": confidence,
        "REPORTS": reports,
        "NAV STATUS": str(nav_status) if nav_status is not None else "UNKNOWN",
    })

    section_kicker("Current")
    metric_strip({
        "SIGNAL AGE": f"{signal_age:.0f} s" if signal_age is not None else "—",
        "SOG": f"{sog:.1f} kn" if sog is not None else "—",
        "COG": f"{cog:.0f}°" if cog is not None else "—",
        "HDG": f"{hdg:.0f}°" if hdg is not None else "—",
    })
    if lat is not None and lon is not None:
        st.markdown(
            f"<div class='small-note'>POSITION · <span class='mono'>{lat:.5f}, {lon:.5f}</span></div>",
            unsafe_allow_html=True,
        )

    with st.expander("Movement profile", expanded=reports >= 2):
        st.markdown(provenance_badge("DERIVED"), unsafe_allow_html=True)
        if reports >= 2:
            movement_state = "MOVING" if (avg_sog or 0) > 0.5 else "STOPPED"
            metric_strip({
                "STATE": movement_state,
                "AVG SOG": f"{avg_sog:.1f} kn" if avg_sog is not None else "—",
                "MAX SOG": f"{max_sog:.1f} kn" if max_sog is not None else "—",
                "HDG Δ": f"{heading_delta:.0f}°" if heading_delta is not None else "—",
            })
            st.markdown(
                "<div class='small-note'>Derived from current-session AIS only.</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(provenance_badge("INSUFFICIENT DATA"), unsafe_allow_html=True)
            notice(
                "Movement profile requires at least 2 AIS observations for this target.",
                "yellow",
            )

    with st.expander("Behavioral signals", expanded=False):
        st.markdown(provenance_badge("DERIVED"), unsafe_allow_html=True)
        embedding = getattr(snapshot, "embeddings", None)
        if reports >= 3 and embedding is not None and mmsi in embedding.mmsis:
            idx = embedding.mmsis.index(mmsi)
            cluster = int(embedding.clusters[idx])
            behavior_score = float(embedding.anomaly_scores[idx])
            metric_strip({
                "SCORE": f"{behavior_score:.2f}",
                "CLUSTER": str(cluster),
                "MODEL": "PCA + KMEANS",
            })
            st.markdown(
                "<div class='small-note'>Session-relative ranking — not a calibrated probability.</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(provenance_badge("INSUFFICIENT DATA"), unsafe_allow_html=True)
            notice(
                "Behavioral assessment requires at least 3 independent real AIS trajectories.",
                "yellow",
            )

    with st.expander("Anomaly assessment", expanded=bool(findings)):
        if findings:
            st.markdown(provenance_badge("DERIVED"), unsafe_allow_html=True)
            top = max(findings, key=lambda f: float(getattr(f, "score", 0) or 0))
            category = str(getattr(top, "category", "behavioral signal"))
            score = float(getattr(top, "score", 0) or 0)
            conf = _safe_float(getattr(top, "confidence", None))
            explanation = str(
                getattr(top, "explanation", "Observed movement deviates from the session baseline.")
            )
            severity = "HIGH" if score >= 0.78 else "MEDIUM" if score >= 0.5 else "LOW"
            metric_strip({
                "SEVERITY": severity,
                "SCORE": f"{score:.2f}",
                "CONFIDENCE": f"{conf:.2f}" if conf is not None else "NOT PROVIDED",
            })
            notice(f"{category.upper()} · {explanation}", "red")
        else:
            notice(
                "No behavioral anomaly is currently associated with this target in the observed session.",
                "green",
            )

    with st.expander("Visual identification", expanded=False):
        photo_key = f"vessel_photo:{mmsi}"
        photo = st.session_state.get(photo_key)
        if photo:
            st.image(
                photo.image_bytes,
                caption=f"Visual identification · {photo.license_name} · {photo.author}",
                use_container_width=True,
            )
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
                notice(
                    "Visual identification is temporarily unavailable. AIS intelligence remains available.",
                    "yellow",
                )

    if show_gemini_hook:
        st.session_state["quick_intel_mmsi"] = mmsi
