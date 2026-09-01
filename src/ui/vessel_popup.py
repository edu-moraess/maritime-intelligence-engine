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


def _fmt_opt(value, suffix="", digits=1):
    if value is None:
        return "—"
    try:
        return f"{float(value):.{digits}f}{suffix}"
    except (TypeError, ValueError):
        return "—"


def _render_behavioral_intelligence(mmsi: str, snapshot) -> None:
    """Lean DERIVED behavioral section from session AIS observations only."""
    from src.intelligence.behavior import build_behavioral_profile

    observations = [
        obs
        for obs in getattr(snapshot, "observations", []) or []
        if str(getattr(obs, "mmsi", "")) == str(mmsi)
    ]
    profile = build_behavioral_profile(str(mmsi), observations)

    st.markdown("### Behavioral Intelligence")
    metric_strip({
        "CLASSIFICATION": profile.classification,
        "CONFIDENCE": profile.confidence,
        "PROVENANCE": profile.provenance,
    })

    if profile.classification == "INSUFFICIENT_DATA":
        notice(
            "INSUFFICIENT_DATA · behavioral features require at least 2 valid AIS positions for this target.",
            "yellow",
        )
        return

    st.markdown(
        "<div class='data-label' style='margin:.35rem 0 .15rem'>SPEED</div>",
        unsafe_allow_html=True,
    )
    metric_strip({
        "AVERAGE": _fmt_opt(profile.speed.average_sog, " kn"),
        "MAXIMUM": _fmt_opt(profile.speed.maximum_sog, " kn"),
        "VARIATION": _fmt_opt(profile.speed.speed_variation, " kn"),
        "ACCELERATION": _fmt_opt(profile.speed.approximate_acceleration, " kn/s", digits=3),
    })

    st.markdown(
        "<div class='data-label' style='margin:.35rem 0 .15rem'>COURSE</div>",
        unsafe_allow_html=True,
    )
    metric_strip({
        "CHANGE": _fmt_opt(profile.course.total_course_change, "°"),
        "CHANGE RATE": _fmt_opt(profile.course.course_change_rate, "°/min"),
        "CONSISTENCY": _fmt_opt(profile.course.heading_cog_consistency, "", digits=2),
    })

    st.markdown(
        "<div class='data-label' style='margin:.35rem 0 .15rem'>MOVEMENT</div>",
        unsafe_allow_html=True,
    )
    ratio = profile.movement.movement_stopped_ratio
    ratio_label = f"{ratio:.0%} moving" if ratio is not None else "—"
    metric_strip({
        "DISTANCE": _fmt_opt(profile.movement.traveled_distance_km, " km", digits=2),
        "EFFICIENCY": _fmt_opt(profile.movement.trajectory_efficiency, "", digits=2),
        "MOVING/STOPPED": ratio_label,
    })

    st.markdown(
        "<div class='data-label' style='margin:.35rem 0 .15rem'>EVIDENCE</div>",
        unsafe_allow_html=True,
    )
    span = profile.evidence.time_span_seconds
    span_label = f"{span / 60.0:.1f} min" if span is not None else "—"
    metric_strip({
        "OBSERVATIONS": str(profile.evidence.valid_position_count),
        "TIME SPAN": span_label,
    })
    if profile.reasons:
        st.markdown(
            "<div class='small-note' style='margin-top:.35rem'>"
            + " · ".join(profile.reasons)
            + "</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            "<div class='small-note' style='margin-top:.35rem'>"
            "Deterministic behavioral features derived only from real AIS "
            "observations in the current session."
            "</div>",
            unsafe_allow_html=True,
        )


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
    heading_delta = _heading_delta([getattr(o, "heading_degrees", None) for o in observations])
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

    _render_behavioral_intelligence(mmsi, snapshot)

    st.markdown("### Behavioral Signals")
    embedding = getattr(snapshot, "embeddings", None)
    if reports >= 3 and embedding is not None and mmsi in embedding.mmsis:
        idx = embedding.mmsis.index(mmsi)
        cluster = int(embedding.clusters[idx])
        behavior_score = float(embedding.anomaly_scores[idx])
        metric_strip({
            "BEHAVIOR SCORE": f"{behavior_score:.2f}",
            "CLUSTER": str(cluster),
            "MODEL": "PCA + KMEANS",
        })
        st.markdown("<div class='small-note' style='margin-top:.4rem'>Behavior score is a session-relative ranking signal, not a probability or calibrated confidence.</div>", unsafe_allow_html=True)
    else:
        notice("INSUFFICIENT OBSERVATIONS · behavioral assessment requires at least 3 independent real AIS trajectories.", "yellow")

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
