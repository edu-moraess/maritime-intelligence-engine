"""Isolated Gemini API client for multimodal vessel intelligence.

Uses the modern google-genai SDK with the Interactions API
(client.interactions.create), as recommended by current Google Gen AI docs.

Never hardcodes the API key. Never logs the key. Optional dependency:
if google-genai is missing or GEMINI_API_KEY is unset, the rest of the
MIE continues to operate normally.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
from typing import Any

from src.intelligence.llm.prompts import SYSTEM_PROMPT, build_user_prompt
from src.intelligence.llm.schemas import (
    GeminiAvailability,
    GeminiVesselAnalysis,
    parse_gemini_response,
)

logger = logging.getLogger(__name__)

# Multimodal Flash model documented for Interactions API
# (ai.google.dev Interactions / text-generation / structured-output, 2026).
DEFAULT_MODEL = "gemini-3.7-flash"
REQUEST_TIMEOUT_SECONDS = 45

# JSON Schema for structured vessel analysis (Interactions response_format).
VESSEL_ANALYSIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "behavior_assessment": {"type": "string"},
        "visual_assessment": {"type": "string"},
        "anomaly_context": {"type": "string"},
        "confidence": {
            "type": "string",
            "enum": ["low", "medium", "high"],
        },
        "evidence": {
            "type": "array",
            "items": {"type": "string"},
        },
        "limitations": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": [
        "summary",
        "behavior_assessment",
        "visual_assessment",
        "anomaly_context",
        "confidence",
        "evidence",
        "limitations",
    ],
}


def _read_api_key(secrets: Any | None = None) -> str:
    """Read GEMINI_API_KEY from Streamlit Secrets first, then environment."""
    if secrets is not None:
        try:
            value = secrets.get("GEMINI_API_KEY")
            if value is not None and str(value).strip():
                return str(value).strip()
        except Exception:
            pass
    return os.getenv("GEMINI_API_KEY", "").strip()


def _import_genai():
    """Lazy import of the modern google-genai package."""
    try:
        from google import genai  # type: ignore

        return genai
    except Exception:
        return None


class GeminiClient:
    """Thin wrapper around google-genai Interactions API."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model_name: str = DEFAULT_MODEL,
        secrets: Any | None = None,
    ) -> None:
        self._explicit_key = (api_key or "").strip()
        self._secrets = secrets
        self.model_name = model_name

    def _resolved_key(self) -> str:
        if self._explicit_key:
            return self._explicit_key
        return _read_api_key(self._secrets)

    def availability(self) -> GeminiAvailability:
        key = self._resolved_key()
        if not key:
            return GeminiAvailability(
                available=False,
                reason="Gemini unavailable: GEMINI_API_KEY not configured",
            )
        genai = _import_genai()
        if genai is None:
            return GeminiAvailability(
                available=False,
                reason=(
                    "Gemini unavailable: google-genai package "
                    "is not installed"
                ),
            )
        return GeminiAvailability(
            available=True,
            reason="ready",
            model_name=self.model_name,
        )

    def analyze_vessel(
        self,
        context: dict[str, Any],
        *,
        image_bytes: bytes | None = None,
        image_mime: str = "image/jpeg",
        mmsi: str = "",
    ) -> GeminiVesselAnalysis | None:
        """
        Request a structured interpretation via Interactions API.

        Returns None when the client is unavailable or the call fails.
        Never raises into the classical pipeline.
        """
        status = self.availability()
        if not status.available:
            logger.info("Gemini analyze skipped: %s", status.reason)
            return None

        genai = _import_genai()
        if genai is None:
            return None

        key = self._resolved_key()
        try:
            client = genai.Client(api_key=key)
        except Exception as exc:
            logger.warning(
                "Gemini client init failed: %s",
                type(exc).__name__,
            )
            return None

        from src.intelligence.llm.context import context_to_json

        context_json = context_to_json(context)
        image_provided = image_bytes is not None and len(image_bytes) > 0
        user_prompt = build_user_prompt(
            context_json,
            image_provided=image_provided,
        )

        # Interactions API multimodal input format (official docs).
        interaction_input: list[dict[str, Any]] = [
            {"type": "text", "text": user_prompt},
        ]
        if image_provided:
            try:
                image_b64 = base64.b64encode(image_bytes).decode("utf-8")
                interaction_input.append(
                    {
                        "type": "image",
                        "data": image_b64,
                        "mime_type": image_mime,
                    }
                )
            except Exception as exc:
                logger.warning(
                    "Gemini image encoding failed: %s",
                    type(exc).__name__,
                )
                image_provided = False
                interaction_input = [
                    {
                        "type": "text",
                        "text": build_user_prompt(
                            context_json,
                            image_provided=False,
                        ),
                    }
                ]

        try:
            interaction = client.interactions.create(
                model=self.model_name,
                system_instruction=SYSTEM_PROMPT,
                input=interaction_input,
                response_format={
                    "type": "text",
                    "mime_type": "application/json",
                    "schema": VESSEL_ANALYSIS_SCHEMA,
                },
            )
        except Exception as exc:
            err_name = type(exc).__name__
            err_msg = str(exc)
            safe_msg = re.sub(
                r"(?i)(api[_-]?key|token|bearer)\s*[:=]\s*\S+",
                r"\1=[redacted]",
                err_msg,
            )
            safe_msg = safe_msg[:200]
            logger.warning(
                "Gemini API call failed: %s%s",
                err_name,
                f" — {safe_msg}" if safe_msg else "",
            )
            return None

        text = _extract_interaction_text(interaction)
        if not text:
            logger.warning("Gemini returned empty response text")
            return None

        payload = _parse_json_payload(text)
        if payload is None:
            logger.warning("Gemini response was not valid JSON")
            return None

        try:
            return parse_gemini_response(
                payload,
                mmsi=mmsi or str(
                    context.get("identity", {}).get("mmsi", "")
                ),
                model_name=self.model_name,
                image_provided=image_provided,
            )
        except Exception as exc:
            logger.warning(
                "Gemini response schema validation failed: %s",
                type(exc).__name__,
            )
            return None


def _extract_interaction_text(interaction: Any) -> str:
    """Extract text from an Interactions API response object."""
    # Preferred sugar on current schema (SDK >= 2.x).
    try:
        text = getattr(interaction, "output_text", None)
        if text:
            return str(text).strip()
    except Exception:
        pass

    # Fallback: outputs list (older / alternate response shapes).
    try:
        outputs = getattr(interaction, "outputs", None) or []
        for output in reversed(list(outputs)):
            if isinstance(output, dict):
                if output.get("type") == "text" and output.get("text"):
                    return str(output["text"]).strip()
                continue
            out_type = getattr(output, "type", None)
            out_text = getattr(output, "text", None)
            if out_text and (out_type in (None, "text") or out_type == "text"):
                return str(out_text).strip()
    except Exception:
        pass

    # Fallback: steps timeline (model_output content parts).
    try:
        steps = getattr(interaction, "steps", None) or []
        for step in reversed(list(steps)):
            step_type = (
                step.get("type")
                if isinstance(step, dict)
                else getattr(step, "type", None)
            )
            if step_type not in ("model_output", None):
                continue
            content = (
                step.get("content")
                if isinstance(step, dict)
                else getattr(step, "content", None)
            ) or []
            for part in content:
                if isinstance(part, dict):
                    if part.get("type") == "text" and part.get("text"):
                        return str(part["text"]).strip()
                else:
                    part_text = getattr(part, "text", None)
                    if part_text:
                        return str(part_text).strip()
    except Exception:
        pass

    return ""


def _parse_json_payload(text: str) -> dict[str, Any] | None:
    """Parse JSON, tolerating accidental markdown fences."""
    cleaned = text.strip()
    fence = re.match(
        r"^```(?:json)?\s*([\s\S]*?)\s*```$",
        cleaned,
        flags=re.IGNORECASE,
    )
    if fence:
        cleaned = fence.group(1).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data


def create_gemini_client(
    secrets: Any | None = None,
    model_name: str = DEFAULT_MODEL,
) -> GeminiClient:
    """Factory used by UI / tests."""
    return GeminiClient(secrets=secrets, model_name=model_name)
