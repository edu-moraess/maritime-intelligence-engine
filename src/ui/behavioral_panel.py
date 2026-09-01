"""Lean Behavioral Intelligence panel (session AIS only)."""
from __future__ import annotations

import streamlit as st

from src.ui.presentation import metric_strip, notice


def _fmt_opt(value, suffix="", digits=1):
    """Format optional numeric feature for presentation; never invent values."""
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
