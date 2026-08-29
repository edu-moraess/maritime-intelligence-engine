"""Isolated Gemini API client for multimodal vessel intelligence.

Never hardcodes the API key. Never logs the key. Optional dependency:
if google-generativeai is missing or GEMINI_API_KEY is unset, the rest
of the MIE continues to operate normally.
"""

from __future__ import annotations

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

DEFAULT_MODEL = "gemini-1.5-flash"
REQUEST_TIMEOUT_SECONDS = 45


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
    """Lazy import so missing package does not break classical MIE paths."""
    try:
        import google.generativeai as genai  # type: ignore

        return genai
    except Exception:
        return None


class GeminiClient:
    """Thin wrapper around Gemini generate_content for vessel interpretation."""

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
                    "Gemini unavailable: google-generativeai package "
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
        Request a structured interpretation.

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
        # Configure without ever logging the key.
        try:
            genai.configure(api_key=key)
        except Exception as exc:
            logger.warning("Gemini configure failed: %s", type(exc).__name__)
            return None

        from src.intelligence.llm.context import context_to_json

        context_json = context_to_json(context)
        image_provided = image_bytes is not None and len(image_bytes) > 0
        user_prompt = build_user_prompt(
            context_json,
            image_provided=image_provided,
        )

        try:
            model = genai.GenerativeModel(
                model_name=self.model_name,
                system_instruction=SYSTEM_PROMPT,
            )
            parts: list[Any] = [user_prompt]
            if image_provided:
                parts.append(
                    {
                        "mime_type": image_mime,
                        "data": image_bytes,
                    }
                )

            response = model.generate_content(
                parts,
                generation_config={
                    "temperature": 0.2,
                    "response_mime_type": "application/json",
                },
                request_options={"timeout": REQUEST_TIMEOUT_SECONDS},
            )
        except Exception as exc:
            # Do not include request payloads or keys in logs.
            logger.warning(
                "Gemini API call failed: %s",
                type(exc).__name__,
            )
            return None

        text = _extract_text(response)
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
                mmsi=mmsi or str(context.get("identity", {}).get("mmsi", "")),
                model_name=self.model_name,
                image_provided=image_provided,
            )
        except Exception as exc:
            logger.warning(
                "Gemini response schema validation failed: %s",
                type(exc).__name__,
            )
            return None


def _extract_text(response: Any) -> str:
    try:
        text = getattr(response, "text", None)
        if text:
            return str(text).strip()
    except Exception:
        pass
    try:
        candidates = getattr(response, "candidates", None) or []
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            parts = getattr(content, "parts", None) or []
            for part in parts:
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
