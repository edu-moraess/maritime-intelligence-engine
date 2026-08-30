"""On-demand Gemini multimodal panel for Vessel Intelligence."""

from __future__ import annotations

import streamlit as st

from src.intelligence.engine import EngineSnapshot, MaritimeIntelligenceEngine
from src.intelligence.llm import build_vessel_context, create_gemini_client
from src.ui.presentation import metric_strip, notice, panel_title


def render_gemini_vessel_panel(
    engine: MaritimeIntelligenceEngine,
    snapshot: EngineSnapshot,
    vessel,
    track: list,
) -> None:
    """On-demand Gemini multimodal interpretation (never auto-called)."""
    st.write("")
    panel_title(
        "Gemini multimodal intelligence",
        "interpretation only",
    )

    secrets = None
    try:
        secrets = st.secrets
    except Exception:
        secrets = None

    client = create_gemini_client(secrets=secrets)
    availability = client.availability()

    if not availability.available:
        notice(availability.reason, "red")
        return

    notice(
        "Gemini provides interpretation only. It does not replace "
        "Rules, IsolationForest, or Deep Temporal scores.",
    )

    cache_key = f"gemini_analysis_{vessel.mmsi}"
    error_key = f"gemini_error_{vessel.mmsi}"
    run = st.button(
        "Analyze with Gemini",
        key=f"gemini_btn_{vessel.mmsi}",
        type="primary",
    )

    if run:
        with st.spinner(
            "Requesting Gemini interpretation "
            f"(timeout {client.timeout_seconds}s)..."
        ):
            context = build_vessel_context(
                vessel,
                snapshot,
                track=track,
            )
            # Optional image slot — no external scraping in this phase.
            image_bytes = st.session_state.get(
                f"gemini_image_{vessel.mmsi}"
            )
            image_mime = "image/jpeg"
            if image_bytes is None and st.session_state.get(
                "quick_intel_mmsi"
            ) == getattr(vessel, "mmsi", None):
                image_bytes = st.session_state.get("quick_intel_photo_bytes")
                image_mime = st.session_state.get(
                    "quick_intel_photo_mime", "image/jpeg"
                )
            result = client.analyze_vessel(
                context,
                image_bytes=image_bytes,
                image_mime=image_mime,
                mmsi=vessel.mmsi,
            )
            st.session_state[cache_key] = result
            st.session_state[error_key] = client.last_error
            if client.last_duration_seconds is not None:
                st.session_state[f"gemini_duration_{vessel.mmsi}"] = (
                    client.last_duration_seconds
                )

    result = st.session_state.get(cache_key)
    last_error = st.session_state.get(error_key)
    duration = st.session_state.get(f"gemini_duration_{vessel.mmsi}")

    if result is None and not run:
        st.caption(
            "Select Analyze with Gemini to request an interpretation "
            "for the currently selected vessel."
        )
        return

    if result is None:
        message = last_error or (
            "Gemini did not return a usable interpretation. "
            "Check API availability and try again."
        )
        notice(message, "red")
        return

    metric_strip(
        {
            "CONFIDENCE": result.confidence.upper(),
            "MODEL": result.model_name or "—",
            "IMAGE": "YES" if result.image_provided else "NO",
        }
    )
    if duration is not None:
        st.caption(f"Gemini API call completed in {duration:.1f}s")

    st.markdown("**Summary**")
    st.write(result.summary)

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**Behavior assessment**")
        st.write(result.behavior_assessment)
        st.markdown("**Anomaly context**")
        st.write(result.anomaly_context)
    with col_b:
        st.markdown("**Visual assessment**")
        st.write(result.visual_assessment)
        if result.evidence:
            st.markdown("**Evidence**")
            for item in result.evidence:
                st.markdown(f"- {item}")
        if result.limitations:
            st.markdown("**Limitations**")
            for item in result.limitations:
                st.markdown(f"- {item}")
