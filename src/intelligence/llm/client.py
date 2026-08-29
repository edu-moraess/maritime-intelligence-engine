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
import time
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

# Hard ceiling for a single Interactions call (Streamlit UX).
# Applied via Client http_options.timeout (milliseconds in google-genai).
REQUEST_TIMEOUT_SECONDS = 28

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


def _import_genai_types():
    """Lazy import of google.genai.types (HttpOptions, etc.)."""
    try:
        from google.genai import types  # type: ignore

        return types
    except Exception:
        return None


def _is_timeout_error(exc: BaseException) -> bool:
    """Detect timeout-like failures without depending on a specific SDK class."""
    name = type(exc).__name__.lower()
    msg = str(exc).lower()
    tokens = (
        "timeout",
        "timed out",
        "deadline",
        "read timed out",
        "connect timeout",
    )
    if "timeout" in name or "deadline" in name:
        return True
    return any(token in msg for token in tokens)


class GeminiClient:
    """Thin wrapper around google-genai Interactions API."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model_name: str = DEFAULT_MODEL,
        secrets: Any | None = None,
        timeout_seconds: int = REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        self._explicit_key = (api_key or "").strip()
        self._secrets = secrets
        self.model_name = model_name
        self.timeout_seconds = max(5, int(timeout_seconds))
        # Last operator-safe failure reason (never contains secrets).
        self.last_error: str | None = None
        self.last_duration_seconds: float | None = None

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
        On timeout, sets last_error to a clear operator message.
        """
        self.last_error = None
        self.last_duration_seconds = None

        status = self.availability()
        if not status.available:
            self.last_error = status.reason
            logger.info("Gemini analyze skipped: %s", status.reason)
            return None

        genai = _import_genai()
        types = _import_genai_types()
        if genai is None:
            self.last_error = (
                "Gemini unavailable: google-genai package is not installed"
            )
            return None

        key = self._resolved_key()
        try:
            client_kwargs: dict[str, Any] = {"api_key": key}
            # Official google-genai timeout is on Client http_options (ms).
            # Disable Speakeasy Interactions retries so a single slow call
            # cannot stack into ~60s of wall time under the Streamlit UX.
            if types is not None and hasattr(types, "HttpOptions"):
                http_opts: dict[str, Any] = {
                    "timeout": self.timeout_seconds * 1000,
                }
                if hasattr(types, "HttpRetryOptions"):
                    http_opts["retry_options"] = types.HttpRetryOptions(
                        attempts=1,
                    )
                client_kwargs["http_options"] = types.HttpOptions(**http_opts)
            client = genai.Client(**client_kwargs)
        except Exception as exc:
            self.last_error = "Gemini client initialization failed."
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

        # Compactness diagnostic only (sizes, never content).
        logger.info(
            "Gemini request prepared: prompt_chars=%s image=%s timeout_s=%s",
            len(user_prompt),
            "yes" if image_provided else "no",
            self.timeout_seconds,
        )

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

        started = time.perf_counter()
        try:
            # Explicit per-call timeout (seconds) for the Speakeasy Interactions
            # path; complements Client http_options.timeout (ms).
            interaction = client.interactions.create(
                model=self.model_name,
                system_instruction=SYSTEM_PROMPT,
                input=interaction_input,
                response_format={
                    "type": "text",
                    "mime_type": "application/json",
                    "schema": VESSEL_ANALYSIS_SCHEMA,
                },
                timeout=float(self.timeout_seconds),
            )
        except Exception as exc:
            elapsed = time.perf_counter() - started
            self.last_duration_seconds = elapsed
            err_name = type(exc).__name__
            err_msg = str(exc)
            safe_msg = re.sub(
                r"(?i)(api[_-]?key|token|bearer)\s*[:=]\s*\S+",
                r"\1=[redacted]",
                err_msg,
            )
            safe_msg = safe_msg[:200]

            if _is_timeout_error(exc):
                self.last_error = (
                    "Gemini analysis timed out. "
                    "The MIE pipeline remains operational."
                )
                logger.warning(
                    "Gemini API call timed out after %.1fs: %s",
                    elapsed,
                    err_name,
                )
            else:
                self.last_error = (
                    "Gemini did not return a usable interpretation. "
                    "Check API availability and try again."
                )
                logger.warning(
                    "Gemini API call failed after %.1fs: %s%s",
                    elapsed,
                    err_name,
                    f" — {safe_msg}" if safe_msg else "",
                )
            return None

        elapsed = time.perf_counter() - started
        self.last_duration_seconds = elapsed
        logger.info("Gemini API call completed in %.1fs", elapsed)

        text = _extract_interaction_text(interaction)
        if not text:
            self.last_error = (
                "Gemini returned an empty response. "
                "The MIE pipeline remains operational."
            )
            logger.warning(
                "Gemini returned empty response text after %.1fs",
                elapsed,
            )
            return None

        payload = _parse_json_payload(text)
        if payload is None:
            self.last_error = (
                "Gemini returned an invalid response. "
                "The MIE pipeline remains operational."
            )
            logger.warning(
                "Gemini response was not valid JSON after %.1fs",
                elapsed,
            )
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
            self.last_error = (
                "Gemini response could not be validated. "
                "The MIE pipeline remains operational."
            )
            logger.warning(
                "Gemini response schema validation failed: %s",
                type(exc).__name__,
            )
            return None


def _extract_interaction_text(interaction: Any) -> str:
    """Extract text from an Interactions API response object."""
    try:
        text = getattr(interaction, "output_text", None)
        if text:
            return str(text).strip()
    except Exception:
        pass

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
    timeout_seconds: int = REQUEST_TIMEOUT_SECONDS,
) -> GeminiClient:
    """Factory used by UI / tests."""
    return GeminiClient(
        secrets=secrets,
        model_name=model_name,
        timeout_seconds=timeout_seconds,
    )
