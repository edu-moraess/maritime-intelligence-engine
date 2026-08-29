"""Unit tests for the isolated Gemini multimodal vessel intelligence layer.

Mocks target the modern google-genai SDK (google.genai Client).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.ingestion.models import (
    AnomalyFinding,
    IngestionStatus,
    VesselSnapshot,
)
from src.intelligence.engine import EngineSnapshot, ReadinessSnapshot
from src.intelligence.llm.client import (
    DEFAULT_MODEL,
    GeminiClient,
    _parse_json_payload,
    create_gemini_client,
)
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


def _mock_genai_stack(
    *,
    response_text: str | None = None,
    raise_on_generate: Exception | None = None,
):
    """Build fake google.genai + types modules for unit tests."""
    fake_types = MagicMock()
    fake_types.Part.from_bytes = MagicMock(
        side_effect=lambda data, mime_type: {
            "inline": data,
            "mime": mime_type,
        }
    )
    fake_types.GenerateContentConfig = MagicMock(
        side_effect=lambda **kwargs: kwargs
    )
    fake_types.HttpOptions = MagicMock(
        side_effect=lambda **kwargs: kwargs
    )

    fake_models = MagicMock()
    if raise_on_generate is not None:
        fake_models.generate_content.side_effect = raise_on_generate
    else:
        response = MagicMock()
        response.text = response_text or (
            '{"summary":"ok","behavior_assessment":"steady",'
            '"visual_assessment":"no image",'
            '"anomaly_context":"none","confidence":"low",'
            '"evidence":[],"limitations":["unit test"]}'
        )
        response.candidates = []
        fake_models.generate_content.return_value = response

    fake_client_instance = MagicMock()
    fake_client_instance.models = fake_models

    fake_genai = MagicMock()
    fake_genai.Client.return_value = fake_client_instance

    return fake_genai, fake_types, fake_models, fake_client_instance


def test_default_model_is_modern_flash():
    assert DEFAULT_MODEL == "gemini-3.7-flash"


def test_missing_api_key_unavailable(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    client = GeminiClient(api_key="")
    status = client.availability()
    assert status.available is False
    assert "GEMINI_API_KEY not configured" in status.reason


def test_missing_package_unavailable(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    client = GeminiClient(api_key="test-key-not-real")
    with patch(
        "src.intelligence.llm.client._import_genai",
        return_value=None,
    ):
        status = client.availability()
    assert status.available is False
    assert "google-genai" in status.reason


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
        model_name="gemini-3.7-flash",
        image_provided=False,
    )
    assert isinstance(analysis, GeminiVesselAnalysis)
    assert analysis.confidence == "medium"
    assert analysis.mmsi == "367000004"
    assert analysis.image_provided is False
    assert "steady SOG" in analysis.evidence

    low = parse_gemini_response({"confidence": "extreme"}, mmsi="x")
    assert low.confidence == "low"


def test_successful_generate_content_call(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    fake_genai, fake_types, fake_models, _ = _mock_genai_stack()

    client = GeminiClient(api_key="test-key-not-real")
    with (
        patch(
            "src.intelligence.llm.client._import_genai",
            return_value=fake_genai,
        ),
        patch(
            "src.intelligence.llm.client._import_genai_types",
            return_value=fake_types,
        ),
    ):
        result = client.analyze_vessel(
            {"identity": {"mmsi": "367000010"}},
            mmsi="367000010",
        )

    assert result is not None
    assert result.summary == "ok"
    assert result.model_name == DEFAULT_MODEL
    assert result.image_provided is False
    fake_genai.Client.assert_called_once()
    assert fake_models.generate_content.called
    call_kwargs = fake_models.generate_content.call_args.kwargs
    assert call_kwargs["model"] == DEFAULT_MODEL


def test_multimodal_image_attached(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    fake_genai, fake_types, fake_models, _ = _mock_genai_stack(
        response_text=(
            '{"summary":"vessel visible","behavior_assessment":"ok",'
            '"visual_assessment":"white hull","anomaly_context":"none",'
            '"confidence":"medium","evidence":["image"],'
            '"limitations":[]}'
        )
    )

    client = GeminiClient(api_key="test-key-not-real")
    image = b"\xff\xd8\xfffakejpeg"
    with (
        patch(
            "src.intelligence.llm.client._import_genai",
            return_value=fake_genai,
        ),
        patch(
            "src.intelligence.llm.client._import_genai_types",
            return_value=fake_types,
        ),
    ):
        result = client.analyze_vessel(
            {"identity": {"mmsi": "367000011"}},
            image_bytes=image,
            image_mime="image/jpeg",
            mmsi="367000011",
        )

    assert result is not None
    assert result.image_provided is True
    fake_types.Part.from_bytes.assert_called()
    call_kwargs = fake_models.generate_content.call_args.kwargs
    contents = call_kwargs["contents"]
    assert len(contents) == 2


def test_gemini_api_not_found_returns_none(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")

    class NotFound(Exception):
        pass

    fake_genai, fake_types, _, _ = _mock_genai_stack(
        raise_on_generate=NotFound("models/gemini-1.5-flash is not found")
    )

    client = GeminiClient(api_key="test-key-not-real")
    with (
        patch(
            "src.intelligence.llm.client._import_genai",
            return_value=fake_genai,
        ),
        patch(
            "src.intelligence.llm.client._import_genai_types",
            return_value=fake_types,
        ),
    ):
        result = client.analyze_vessel(
            {"identity": {"mmsi": "367000005"}},
            mmsi="367000005",
        )
    assert result is None


def test_gemini_auth_error_returns_none(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "bad-key")

    class PermissionDenied(Exception):
        pass

    fake_genai, fake_types, _, _ = _mock_genai_stack(
        raise_on_generate=PermissionDenied("API key not valid")
    )

    client = GeminiClient(api_key="bad-key")
    with (
        patch(
            "src.intelligence.llm.client._import_genai",
            return_value=fake_genai,
        ),
        patch(
            "src.intelligence.llm.client._import_genai_types",
            return_value=fake_types,
        ),
    ):
        result = client.analyze_vessel(
            {"identity": {"mmsi": "367000006"}},
            mmsi="367000006",
        )
    assert result is None


def test_invalid_json_response_returns_none(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    fake_genai, fake_types, _, _ = _mock_genai_stack(
        response_text="this is not json at all"
    )

    client = GeminiClient(api_key="test-key-not-real")
    with (
        patch(
            "src.intelligence.llm.client._import_genai",
            return_value=fake_genai,
        ),
        patch(
            "src.intelligence.llm.client._import_genai_types",
            return_value=fake_types,
        ),
    ):
        result = client.analyze_vessel(
            {"identity": {"mmsi": "367000007"}},
            mmsi="367000007",
        )
    assert result is None


def test_api_key_never_logged(caplog, monkeypatch):
    secret = "SUPER_SECRET_GEMINI_KEY_XYZ"
    monkeypatch.setenv("GEMINI_API_KEY", secret)
    client = GeminiClient(api_key=secret)

    class Boom(Exception):
        def __str__(self) -> str:
            return f"auth failed api_key={secret}"

    fake_genai, fake_types, _, _ = _mock_genai_stack(
        raise_on_generate=Boom()
    )

    with caplog.at_level(logging.DEBUG):
        client.availability()
        with (
            patch(
                "src.intelligence.llm.client._import_genai",
                return_value=fake_genai,
            ),
            patch(
                "src.intelligence.llm.client._import_genai_types",
                return_value=fake_types,
            ),
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
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    client = create_gemini_client(secrets=None)
    status = client.availability()
    assert status.available is False
    assert status.reason.startswith("Gemini unavailable:")
