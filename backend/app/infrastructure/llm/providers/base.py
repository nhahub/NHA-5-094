"""Base classes and utility helpers for LLM provider adapters."""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional, Tuple

from app.infrastructure.llm.gateway import (
    ModelOutputFormatError,
    ModelUsage,
)

logger = logging.getLogger(__name__)


def build_schema_enforced_prompt(user_prompt: str, response_schema: Dict[str, Any]) -> str:
    """Construct an instruction string ensuring the model returns valid JSON conforming to the schema."""
    return (
        f"{user_prompt}\n\nReturn one JSON object matching this JSON Schema exactly. "
        "Do not include Markdown fences or additional commentary.\n"
        f"JSON Schema:\n{json.dumps(response_schema, ensure_ascii=False)}"
    )


def extract_and_parse_json(text: str) -> Dict[str, Any]:
    """Clean markdown artifacts, code blocks, or preamble and parse into a dictionary."""
    if not text or not isinstance(text, str):
        raise ModelOutputFormatError("Model returned empty or non-string response.")

    cleaned = text.strip()

    # Strip markdown code blocks if the model wrapped output in ```json ... ```
    if cleaned.startswith("```"):
        # Match ```json or ``` and remove trailing ```
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        cleaned = cleaned.strip()

    # If there are leading/trailing characters outside the outermost { ... }, extract the JSON block
    if not (cleaned.startswith("{") and cleaned.endswith("}")):
        start_idx = cleaned.find("{")
        end_idx = cleaned.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            cleaned = cleaned[start_idx : end_idx + 1]

    try:
        parsed = json.loads(cleaned)
        if not isinstance(parsed, dict):
            raise ModelOutputFormatError(
                f"Model response decoded into '{type(parsed).__name__}', expected JSON object (dict)."
            )
        return parsed
    except json.JSONDecodeError:
        raise ModelOutputFormatError(
            "Failed to parse model output as a JSON object."
        ) from None


class BaseProviderAdapter:
    """Common foundation for concrete LLM adapters."""

    def __init__(self, provider_name: str, model_name: str):
        self.provider_name = provider_name
        self.model = model_name
        self.last_usage: Optional[ModelUsage] = None

    def _record_usage(
        self,
        *,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        latency_seconds: float = 0.0,
        model_name: Optional[str] = None,
    ) -> ModelUsage:
        """Store the most recent invocation usage metrics."""
        usage = ModelUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens or (prompt_tokens + completion_tokens),
            latency_seconds=latency_seconds,
            model_name=model_name or self.model,
            provider_name=self.provider_name,
        )
        self.last_usage = usage
        return usage
