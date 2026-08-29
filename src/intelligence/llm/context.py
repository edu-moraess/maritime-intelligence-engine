"""Build compact, fact-only context for Gemini from existing MIE state."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from src.ingestion.models import AnomalyFinding, VesselSnapshot
from src.intelligence.engine import EngineSnapshot
from src.ml.temporal.types import TemporalFitResult, TemporalScore
from src.trajectory.features import enrich_track, track_to_frame


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _finding_dict(finding: AnomalyFinding) -> dict[str, Any]:
    return {
        "category": finding.category,
        "score": round(float(finding.score), 4),
        "confidence": finding.confidence,
        "explanation": finding.explanation,
        "latitude": finding.latitude,
        "longitude": finding.longitude,
        "received_at": _iso(finding.received_at),
    }


def _temporal_dict(score: TemporalScore | None, temporal: TemporalFitResult | None) -> dict[str, Any]:
    if temporal is None:
        return {
            "status": "WAITING",
            "reason": "Deep temporal model has not produced a session result.",
        }
    base: dict[str, Any] = {
        "status": temporal.status,
        "reason": temporal.reason,
        "method": temporal.method,
        "n_tracks_usable": temporal.n_tracks_usable,
    }
    if score is not None:
        base["vessel"] = {
            "reconstruction_error": round(float(score.reconstruction_error), 6),
            "deep_anomaly_score": round(float(score.deep_anomaly_score), 4),
            "sequence_length": score.sequence_length,
        }
    return base


def _track_summary(track: list) -> dict[str, Any]:
    """Summarize a real AIS track without inventing features."""
    if not track:
        return {
            "point_count": 0,
            "duration_seconds": None,
            "start": None,
            "end": None,
        }

    ordered = sorted(track, key=lambda item: item.received_at)
    start = ordered[0].received_at
    end = ordered[-1].received_at
    duration = max(0.0, (end - start).total_seconds())

    summary: dict[str, Any] = {
        "point_count": len(ordered),
        "duration_seconds": round(duration, 1),
        "start": _iso(start),
        "end": _iso(end),
        "first_position": {
            "latitude": ordered[0].latitude,
            "longitude": ordered[0].longitude,
        },
        "last_position": {
            "latitude": ordered[-1].latitude,
            "longitude": ordered[-1].longitude,
        },
    }

    try:
        frame = enrich_track(track_to_frame(ordered))
        if not frame.empty:
            if "sog_knots" in frame.columns:
                sog = frame["sog_knots"].dropna()
                if not sog.empty:
                    summary["sog_knots"] = {
                        "min": round(float(sog.min()), 2),
                        "max": round(float(sog.max()), 2),
                        "mean": round(float(sog.mean()), 2),
                    }
            if "cog_degrees" in frame.columns:
                cog = frame["cog_degrees"].dropna()
                if not cog.empty:
                    summary["cog_degrees"] = {
                        "first": round(float(cog.iloc[0]), 1),
                        "last": round(float(cog.iloc[-1]), 1),
                    }
            if "heading_change" in frame.columns:
                hc = frame["heading_change"].dropna()
                if not hc.empty:
                    summary["max_abs_heading_change_deg"] = round(
                        float(hc.abs().max()),
                        1,
                    )
    except Exception:
        # Track summary is best-effort; never fail context build.
        pass

    return summary


def build_vessel_context(
    vessel: VesselSnapshot,
    snapshot: EngineSnapshot,
    track: list | None = None,
) -> dict[str, Any]:
    """
    Convert existing MIE state into a compact JSON-serializable context.

    Only includes facts present in the snapshot / vessel / track.
    Does not invent identity fields (IMO, flag, type, callsign).
    """
    track = track or []
    findings = [
        finding
        for finding in snapshot.findings
        if finding.mmsi == vessel.mmsi
    ]

    temporal_score: TemporalScore | None = None
    if snapshot.temporal is not None:
        temporal_score = snapshot.temporal.score_for(vessel.mmsi)

    identity: dict[str, Any] = {
        "mmsi": vessel.mmsi,
    }
    # Only emit name when actually present; never invent other identity fields.
    if vessel.vessel_name:
        identity["vessel_name"] = vessel.vessel_name

    context: dict[str, Any] = {
        "identity": identity,
        "telemetry": {
            "latitude": vessel.latitude,
            "longitude": vessel.longitude,
            "sog_knots": vessel.sog_knots,
            "cog_degrees": vessel.cog_degrees,
            "heading_degrees": vessel.heading_degrees,
            "last_received": _iso(vessel.last_received),
            "message_count": vessel.message_count,
            "stale": vessel.stale,
        },
        "track": _track_summary(track),
        "classical_anomalies": [_finding_dict(f) for f in findings],
        "deep_temporal": _temporal_dict(temporal_score, snapshot.temporal),
        "session": {
            "distinct_vessels": snapshot.readiness.distinct_vessels,
            "tracks_with_history": snapshot.readiness.tracks_with_history,
            "anomaly_count": snapshot.readiness.anomaly_count,
            "messages_received": snapshot.status.messages_received,
            "temporal_status": getattr(
                snapshot.readiness,
                "temporal_status",
                "WAITING",
            ),
        },
        "notes": [
            "All measurements are from real AIS observations in the current session.",
            "No synthetic tracks or labels were introduced.",
            "IMO, flag, ship type, and operator are omitted because they are not present in the current AIS identity payload.",
        ],
    }
    return context


def context_to_json(context: dict[str, Any]) -> str:
    """Serialize context compactly for the prompt."""
    return json.dumps(context, ensure_ascii=False, separators=(",", ":"), default=str)
