"""Unit tests for the isolated Gemini multimodal vessel intelligence layer."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.ingestion.models import (
    AnomalyFinding,
    IngestionStatus,
    VesselSnapshot,
)
from src.intelligence.engine import EngineSnapshot, ReadinessSnapshot
from src.intelligence.llm.client import GeminiClient, _parse_json_payload, create_gemini_client
from src.intelligence.llm.context import build_vessel_context, context_to_json
from src.intelligence.llm.schemas import (
    GeminiVesselAnalysis,
    parse_gemini_response,
)
from src.ml.temporal.types import TemporalFitResult, TemporalScore
from src.processing.quality import QualityReport


def _status() -> IngestionStatus:
    return IngestionStatus(
        state="LIVE AIS",
        reason="",
        connected_at=datetime.now(timezone.utc),
        last_received_at=datetime.now(timezone.utc),
        messages_received=10,
        active_vessels=2,
        latency_seconds=1.0,
        websocket_status="open",
    )


def _vessel(mmsi: str = "367000001") -> VesselSnapshot:
    return VesselSnapshot(
        mmsi=mmsi,
        latitude=25.76,
        longitude=-80.19,
        last_received=datetime.now(timezone.utc),
        sog_knots=8.5,
        cog_degrees=90.0,
        heading_degrees=92.0,
        vessel_name="TEST VESSEL",
        message_count=6,
        stale=False,
    )


def _snapshot(
    vessel: VesselSnapshot | None = None,
    findings: list[AnomalyFinding] | None = None,
    temporal: TemporalFitResult | None = None,
) -> EngineSnapshot:
    vessel = vessel or _vessel()
    findings = findings or []
    return EngineSnapshot(
        observations=[],
        vessels=[vessel],
        findings=findings,
        quality=QualityReport(
            messages_processed=10,
            invalid_records=0,
            duplicate_records=0,
            missing_values=0,
            receive_time_gaps=0,
            invalid_mmsi=0,
            impossible_speeds=0,
            impossible_jumps=0,
            stale_records=0,
            quality_percent=100.0,
        ),
        status=_status(),
        embeddings=None,
        summary={},
        readiness=ReadinessSnapshot(
            distinct_vessels=1,
            tracks_with_history=1,
            trajectory_ready=True,
            embeddings_ready=False,
            embedding_status="WAITING",
            anomaly_count=len(findings),
            temporal_status=temporal.status if temporal else "WAITING",
        ),
        last_collection_seconds=60.0,
        historical_status="disabled",
        historical_result=None,
        temporal=temporal,
    )


def test_missing_api_key_unavailable(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    client = GeminiClient(api_key="")
    status = client.availability()
    assert status.available is False
    assert "GEMINI_API_KEY not configured" in status.reason


def test_context_without_optional_fields():
    vessel = VesselSnapshot(
        mmsi="367000002",
        latitude=25.7,
        longitude=-80.2,
        last_received=datetime.now(timezone.utc),
        sog_knots=None,
        cog_degrees=None,
        heading_degrees=None,
        vessel_name=None,
        message_count=1,
        stale=True,
    )
    snapshot = _snapshot(vessel=vessel)
    context = build_vessel_context(vessel, snapshot, track=[])
    assert context["identity"]["mmsi"] == "367000002"
    assert "vessel_name" not in context["identity"]
    assert "imo" not in context["identity"]
    assert "flag" not in context["identity"]
    assert context["classical_anomalies"] == []
    assert context["deep_temporal"]["status"] == "WAITING"
    # Must be JSON-serializable.
    payload = context_to_json(context)
    assert "367000002" in payload


def test_context_with_deep_temporal():
    vessel = _vessel("367000003")
    temporal = TemporalFitResult(
        status="READY",
        reason="trained",
        n_tracks_usable=10,
        scores=[
            TemporalScore(
                mmsi="367000003",
                reconstruction_error=0.42,
                deep_anomaly_score=0.81,
            )
        ],
    )
    snapshot = _snapshot(vessel=vessel, temporal=temporal)
    context = build_vessel_context(vessel, snapshot, track=[])
    deep = context["deep_temporal"]
    assert deep["status"] == "READY"
    assert deep["vessel"]["deep_anomaly_score"] == 0.81
    assert deep["vessel"]["reconstruction_error"] == 0.42


def test_schema_validation_and_defaults():
    analysis = parse_gemini_response(
        {
            "summary": "Stable transit.",
            "behavior_assessment": "Steady course.",
            "visual_assessment": "No image provided.",
            "anomaly_context": "No classical findings.",
            "confidence": "medium",
            "evidence": ["steady SOG"],
            "limitations": ["short track"],
        },
        mmsi="367000004",
        model_name="gemini-1.5-flash",
        image_provided=False,
    )
    assert isinstance(analysis, GeminiVesselAnalysis)
    assert analysis.confidence == "medium"
    assert analysis.mmsi == "367000004"
    assert analysis.image_provided is False
    assert "steady SOG" in analysis.evidence

    # Invalid confidence falls back to low.
    low = parse_gemini_response({"confidence": "extreme"}, mmsi="x")
    assert low.confidence == "low"


def test_gemini_api_error_returns_none(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")

    class BoomModel:
        def __init__(self, *args, **kwargs):
            pass

        def generate_content(self, *args, **kwargs):
            raise RuntimeError("simulated API failure")

    fake_genai = MagicMock()
    fake_genai.configure = MagicMock()
    fake_genai.GenerativeModel = BoomModel

    client = GeminiClient(api_key="test-key-not-real")
    with patch(
        "src.intelligence.llm.client._import_genai",
        return_value=fake_genai,
    ):
        result = client.analyze_vessel(
            {"identity": {"mmsi": "367000005"}},
            mmsi="367000005",
        )
    assert result is None


def test_api_key_never_logged(caplog, monkeypatch):
    secret = "SUPER_SECRET_GEMINI_KEY_XYZ"
    monkeypatch.setenv("GEMINI_API_KEY", secret)
    client = GeminiClient(api_key=secret)

    with caplog.at_level(logging.DEBUG):
        status = client.availability()
        # Force a failing call path that logs warnings.
        with patch(
            "src.intelligence.llm.client._import_genai",
            return_value=None,
        ):
            client.analyze_vessel({"identity": {"mmsi": "1"}})

    combined = " ".join(record.getMessage() for record in caplog.records)
    assert secret not in combined
    assert "SUPER_SECRET" not in combined


def test_parse_json_with_markdown_fence():
    text = '```json\n{"summary": "ok", "confidence": "low"}\n```'
    payload = _parse_json_payload(text)
    assert payload is not None
    assert payload["summary"] == "ok"


def test_ui_unavailable_message_contract(monkeypatch):
    """UI contract: availability reason must be operator-clear."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    client = create_gemini_client(secrets=None)
    status = client.availability()
    assert status.available is False
    assert status.reason.startswith("Gemini unavailable:")
