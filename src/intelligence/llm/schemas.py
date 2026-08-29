"""Structured response schema for Gemini multimodal vessel intelligence."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

ConfidenceLevel = Literal["low", "medium", "high"]
VALID_CONFIDENCE = {"low", "medium", "high"}


@dataclass(frozen=True)
class GeminiVesselAnalysis:
    """Interpretation-only result. Does not replace MIE detection scores."""

    summary: str
    behavior_assessment: str
    visual_assessment: str
    anomaly_context: str
    confidence: ConfidenceLevel
    evidence: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    model_name: str = ""
    mmsi: str = ""
    image_provided: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_gemini_response(
    payload: dict[str, Any],
    *,
    mmsi: str = "",
    model_name: str = "",
    image_provided: bool = False,
) -> GeminiVesselAnalysis:
    """Validate and normalize a raw JSON object into GeminiVesselAnalysis."""

    def _str(key: str, default: str = "") -> str:
        value = payload.get(key, default)
        if value is None:
            return default
        return str(value).strip()

    def _list(key: str) -> list[str]:
        value = payload.get(key, [])
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    raw_confidence = str(payload.get("confidence", "low")).strip().lower()
    if raw_confidence not in VALID_CONFIDENCE:
        raw_confidence = "low"

    return GeminiVesselAnalysis(
        summary=_str("summary", "No summary produced."),
        behavior_assessment=_str(
            "behavior_assessment",
            "Behavior assessment unavailable.",
        ),
        visual_assessment=_str(
            "visual_assessment",
            "No visual assessment available.",
        ),
        anomaly_context=_str(
            "anomaly_context",
            "No anomaly context available.",
        ),
        confidence=raw_confidence,  # type: ignore[arg-type]
        evidence=_list("evidence"),
        limitations=_list("limitations"),
        model_name=model_name,
        mmsi=mmsi,
        image_provided=image_provided,
    )


@dataclass(frozen=True)
class GeminiAvailability:
    """Client readiness without performing a generation call."""

    available: bool
    reason: str
    model_name: str = ""
