"""Vessel operational intelligence card powered by Vessel Intelligence Profile v1."""

from __future__ import annotations

from typing import Any

import streamlit as st

from src.intelligence.profile import (
    VesselIntelligenceProfile,
    build_vessel_intelligence_profile,
)
from src.ui.presentation import metric_strip, notice, panel_title
from src.ui.behavioral_panel import _render_behavioral_intelligence


def _optional_historical_profile(mmsi: str, engine: Any | None) -> Any | None:
    """Load persisted historical profile when Etapa 2 + persistence are available.

    Returns None when history is unavailable. Never fabricates historical data.
    Compatible with main (stub build_vessel_profile) and Etapa 2
    (load_vessel_observations + session_count).
    """
    if engine is None:
        return None
    settings = getattr(engine, "settings", None)
    if settings is None:
        return None
    database_url = getattr(settings, "database_url", None)
    enabled = getattr(settings, "historical_persistence_enabled", False)
    if not database_url or not enabled:
        return None
    try:
        from src.historical.profile import build_vessel_profile
        from src.historical.reader import load_vessel_observations  # type: ignore
    except ImportError:
        try:
            from src.historical.profile import build_vessel_profile
        except ImportError:
            return None
        return None
    try:
        observations, session_count = load_vessel_observations(database_url, mmsi)
    except TypeError:
        return None
    except Exception:
        return None
    try:
        return build_vessel_profile(
            mmsi,
            observations,
            session_count=session_count,
        )
    except TypeError:
        return build_vessel_profile(mmsi, observations)


def build_profile_for_ui(
    vessel: Any,
    snapshot: Any,
    *,
    engine: Any | None = None,
) -> VesselIntelligenceProfile:
    """Assemble a VesselIntelligenceProfile from live snapshot + optional history."""
    mmsi = str(vessel.mmsi)
    observations = [
        o
        for o in (getattr(snapshot, "observations", None) or [])
        if str(getattr(o, "mmsi", "")) == mmsi
    ]
    findings = [
        f
        for f in (getattr(snapshot, "findings", None) or [])
        if str(getattr(f, "mmsi", "")) == mmsi
    ]
    historical = _optional_historical_profile(mmsi, engine)
    stale = 180
    if engine is not None and getattr(engine, "settings", None) is not None:
        stale = int(getattr(engine.settings, "stale_after_seconds", 180) or 180)
    return build_vessel_intelligence_profile(
        mmsi,
        observations,
        vessel=vessel,
        session_findings=findings,
        historical_profile=historical,
        historical_findings=(),
        stale_after_seconds=float(stale),
    )


def render_vessel_quick_intelligence(
    vessel,
    snapshot,
    *,
    show_gemini_hook: bool = True,
    engine=None,
):
    """Render an AIS-derived target profile; LLM remains optional and external."""
    panel_title("Vessel Intelligence", "selected target")
    if vessel is None:
        notice(
            "Select a target on the tactical map or fleet view to inspect "
            "its operational profile."
        )
        return

    profile = build_profile_for_ui(vessel, snapshot, engine=engine)
    identity = profile.identity
    telemetry = profile.telemetry
    historical = profile.historical
    movement = profile.movement
    anomalies = profile.anomalies
    confidence = profile.confidence

    name = identity.vessel_name or "UNKNOWN VESSEL"
    st.markdown(
        f"<div style='margin:.1rem 0 .7rem'>"
        f"<div style='font-family:Inter,sans-serif;font-size:1rem;font-weight:650;"
        f"color:#d9e6e9'>{name}</div>"
        f"<div style='font-family:IBM Plex Mono,monospace;font-size:.66rem;"
        f"color:#79939b;letter-spacing:.06em;margin-top:.15rem'>"
        f"MMSI {identity.mmsi}</div></div>",
        unsafe_allow_html=True,
    )

    st.markdown("### Identity")
    identity_metrics = {
        "MMSI": identity.mmsi,
        "NAME": identity.vessel_name or "—",
        "IMO": identity.imo or "—",
        "CALLSIGN": identity.callsign or "—",
        "NAV STATUS": (
            str(identity.navigational_status)
            if identity.navigational_status is not None
            else "—"
        ),
    }
    metric_strip(identity_metrics)
    st.caption(f"Provenance · {identity.provenance}")

    st.markdown("### Current Telemetry")
    st.caption("LIVE · latest valid session observation")
    if not telemetry.available:
        notice("No valid session observation for this MMSI.", "yellow")
    else:
        metric_strip(
            {
                "SOG": (
                    f"{telemetry.sog_knots:.1f} kn"
                    if telemetry.sog_knots is not None
                    else "—"
                ),
                "COG": (
                    f"{telemetry.cog_degrees:.0f}°"
                    if telemetry.cog_degrees is not None
                    else "—"
                ),
                "HDG": (
                    f"{telemetry.heading_degrees:.0f}°"
                    if telemetry.heading_degrees is not None
                    else "—"
                ),
                "REPORTS": telemetry.observation_count,
            }
        )
        if telemetry.latitude is not None and telemetry.longitude is not None:
            st.markdown(
                f"<div class='small-note' style='margin:.15rem 0 .65rem'>"
                f"POSITION · <span class='mono'>"
                f"{telemetry.latitude:.5f}, {telemetry.longitude:.5f}"
                f"</span></div>",
                unsafe_allow_html=True,
            )
        metric_strip(
            {
                "NAV STATUS": (
                    str(telemetry.navigational_status)
                    if telemetry.navigational_status is not None
                    else "—"
                ),
                "SIGNAL AGE": (
                    f"{telemetry.signal_age_seconds:.0f} s"
                    if telemetry.signal_age_seconds is not None
                    else "—"
                ),
            }
        )

    st.markdown("### Historical Profile")
    st.caption("HISTORICAL · persisted real AIS only")
    if not historical.available or historical.status == "N/A":
        notice("N/A — no persisted historical profile for this MMSI.", "gray")
    else:
        metric_strip(
            {
                "STATUS": historical.status,
                "OBSERVATIONS": historical.observation_count,
                "SESSIONS": historical.session_count,
            }
        )
        metric_strip(
            {
                "FIRST SEEN": (
                    historical.first_seen_at.isoformat()
                    if historical.first_seen_at
                    else "—"
                ),
                "LAST SEEN": (
                    historical.last_seen_at.isoformat()
                    if historical.last_seen_at
                    else "—"
                ),
                "DISTANCE": (
                    f"{historical.distance_km:.2f} km"
                    if historical.distance_km is not None
                    else "—"
                ),
                "AVG SOG": (
                    f"{historical.average_sog_knots:.1f} kn"
                    if historical.average_sog_knots is not None
                    else "—"
                ),
                "MAX SOG": (
                    f"{historical.max_sog_knots:.1f} kn"
                    if historical.max_sog_knots is not None
                    else "—"
                ),
            }
        )

    st.markdown("### Movement")
    st.caption("DERIVED · current session positions only")
    if movement.status == "INSUFFICIENT_DATA":
        notice(
            "MOVEMENT = INSUFFICIENT_DATA · at least 2 valid session "
            "positions are required.",
            "yellow",
        )
    else:
        metric_strip(
            {
                "DISTANCE": (
                    f"{movement.distance_km:.2f} km"
                    if movement.distance_km is not None
                    else "—"
                ),
                "AVG SOG": (
                    f"{movement.average_sog_knots:.1f} kn"
                    if movement.average_sog_knots is not None
                    else "—"
                ),
                "MAX SOG": (
                    f"{movement.max_sog_knots:.1f} kn"
                    if movement.max_sog_knots is not None
                    else "—"
                ),
                "HDG Δ": (
                    f"{movement.heading_change_degrees:.0f}°"
                    if movement.heading_change_degrees is not None
                    else "—"
                ),
                "SOG Δ": (
                    f"{movement.speed_change_knots:.1f} kn"
                    if movement.speed_change_knots is not None
                    else "—"
                ),
            }
        )

    _render_behavioral_intelligence(identity.mmsi, snapshot)

    st.markdown("### Behavioral Signals")
    embedding = getattr(snapshot, "embeddings", None)
    mmsi = identity.mmsi
    reports = profile.session_observation_count
    if reports >= 3 and embedding is not None and mmsi in getattr(embedding, "mmsis", []):
        idx = embedding.mmsis.index(mmsi)
        cluster = int(embedding.clusters[idx])
        behavior_score = float(embedding.anomaly_scores[idx])
        metric_strip(
            {
                "BEHAVIOR SCORE": f"{behavior_score:.2f}",
                "CLUSTER": str(cluster),
                "MODEL": "PCA + KMEANS",
            }
        )
        st.caption(
            "Session-relative ranking signal only — not a calibrated probability."
        )
    else:
        notice(
            "INSUFFICIENT OBSERVATIONS · behavioral assessment requires at least "
            "3 independent real AIS trajectories in-session.",
            "yellow",
        )

    st.markdown("### Anomalies")
    st.markdown("**Current session**")
    if anomalies.current_session:
        top = max(
            anomalies.current_session,
            key=lambda f: float(getattr(f, "score", 0) or 0),
        )
        score = float(getattr(top, "score", 0) or 0)
        severity = "HIGH" if score >= 0.78 else "MEDIUM" if score >= 0.5 else "LOW"
        conf = getattr(top, "confidence", None)
        metric_strip(
            {
                "SEVERITY": severity,
                "SCORE": f"{score:.2f}",
                "CONFIDENCE": f"{conf:.2f}" if conf is not None else "NOT PROVIDED",
                "CATEGORY": str(getattr(top, "category", "—")),
            }
        )
        notice(str(getattr(top, "explanation", "")), "red")
    else:
        notice("No current-session anomaly associated with this MMSI.", "green")

    st.markdown("**Historical**")
    if anomalies.historical:
        top_h = max(
            anomalies.historical,
            key=lambda f: float(getattr(f, "score", 0) or 0),
        )
        notice(
            f"{getattr(top_h, 'category', 'anomaly').upper()} · "
            f"{getattr(top_h, 'explanation', '')}",
            "yellow",
        )
    else:
        notice("N/A — no historical anomaly records for this MMSI.", "gray")

    st.markdown("### Confidence")
    st.caption("DERIVED · deterministic rules (no ML)")
    metric_strip({"LEVEL": confidence.level})
    for reason in confidence.reasons:
        st.caption(f"· {reason}")

    photo_key = f"vessel_photo:{mmsi}"
    photo = st.session_state.get(photo_key)
    if photo:
        st.markdown("### Visual Identification")
        st.image(
            photo.image_bytes,
            caption=f"Visual identification · {photo.license_name} · {photo.author}",
            use_container_width=True,
        )
    elif st.button(
        "Load visual identification",
        key=f"load_photo:{mmsi}",
        use_container_width=True,
    ):
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
                "Visual identification is temporarily unavailable. "
                "AIS intelligence remains available.",
                "yellow",
            )

    if show_gemini_hook:
        st.session_state["quick_intel_mmsi"] = mmsi
