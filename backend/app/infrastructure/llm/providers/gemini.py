"""Google Gemini LLM adapter with retry resilience and token metrics."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, Optional, Tuple

import httpx

from app.core.config import settings
from app.infrastructure.llm.gateway import (
    ModelAuthenticationError,
    ModelGatewayError,
    ModelOutputFormatError,
    ModelProviderUnavailableError,
    ModelRateLimitError,
    ModelTimeoutError,
)
from app.infrastructure.llm.providers.base import (
    BaseProviderAdapter,
    build_schema_enforced_prompt,
    extract_and_parse_json,
)

logger = logging.getLogger(__name__)


class GeminiJsonAdapter(BaseProviderAdapter):
    """JSON generation adapter for the Google Gemini Developer API."""

    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        api_base_url: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        max_retries: Optional[int] = None,
        retry_base_seconds: Optional[float] = None,
    ):
        model_name = model or getattr(settings, "GEMINI_MODEL", "gemini-3.8-flash")
        super().__init__(provider_name="gemini", model_name=model_name)
        self._custom_api_key = api_key
        self.api_base_url = api_base_url or getattr(
            settings, "GEMINI_API_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/models"
        )
        self.timeout_seconds = timeout_seconds or getattr(settings, "GEMINI_REQUEST_TIMEOUT_SECONDS", 120)
        self.max_retries = max_retries if max_retries is not None else getattr(settings, "GEMINI_MAX_RETRIES", 3)
        self.retry_base_seconds = retry_base_seconds or getattr(settings, "GEMINI_RETRY_BASE_SECONDS", 1.0)

    @property
    def api_key(self) -> Optional[str]:
        if self._custom_api_key is not None:
            return self._custom_api_key
        return getattr(settings, "GEMINI_API_KEY", None)

    @api_key.setter
    def api_key(self, value: Optional[str]) -> None:
        self._custom_api_key = value

    async def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_schema: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], str]:
        active_key = self.api_key
        if not active_key:
            raise ModelAuthenticationError("Set GEMINI_API_KEY to use the Gemini Document Agent.")

        url = f"{self.api_base_url.rstrip('/')}/{self.model}:generateContent"
        prompt = build_schema_enforced_prompt(user_prompt, response_schema)
        max_attempts = max(0, self.max_retries) + 1
        start_time = time.perf_counter()

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                for attempt in range(max_attempts):
                    try:
                        response = await client.post(
                            url,
                            headers={"x-goog-api-key": active_key},
                            json={
                                "systemInstruction": {"parts": [{"text": system_prompt}]},
                                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                                "generationConfig": {
                                    "temperature": 0,
                                    "responseMimeType": "application/json",
                                },
                            },
                        )
                        response.raise_for_status()
                        body = response.json()

                        candidates = body.get("candidates", [])
                        if not candidates:
                            raise ModelOutputFormatError("Gemini returned no candidate in response.")

                        parts = candidates[0].get("content", {}).get("parts", [])
                        text = "".join(part.get("text", "") for part in parts if isinstance(part, dict))
                        parsed = extract_and_parse_json(text)

                        # Capture token usage
                        latency = time.perf_counter() - start_time
                        usage_meta = body.get("usageMetadata", {})
                        self._record_usage(
                            prompt_tokens=usage_meta.get("promptTokenCount", 0),
                            completion_tokens=usage_meta.get("candidatesTokenCount", 0),
                            total_tokens=usage_meta.get("totalTokenCount", 0),
                            latency_seconds=latency,
                            model_name=self.model,
                        )
                        return parsed, self.model

                    except httpx.HTTPStatusError as exc:
                        status_code = exc.response.status_code
                        if status_code in (401, 403):
                            raise ModelAuthenticationError(
                                f"Gemini authentication failed (HTTP {status_code}). Check GEMINI_API_KEY."
                            ) from None
                        elif status_code == 429:
                            if attempt + 1 >= max_attempts:
                                raise ModelRateLimitError(
                                    "Gemini rate limit exceeded (HTTP 429) across all retry attempts."
                                ) from None
                        elif status_code >= 500:
                            if attempt + 1 >= max_attempts:
                                raise ModelProviderUnavailableError(
                                    f"Gemini API returned persistent server error (HTTP {status_code})."
                                ) from None
                        else:
                            raise ModelGatewayError(
                                f"Gemini API request failed (HTTP {status_code})."
                            ) from None

                        backoff = self.retry_base_seconds * (2 ** attempt)
                        logger.info("Gemini HTTP %d. Retrying in %.2fs...", status_code, backoff)
                        await asyncio.sleep(backoff)

                    except (httpx.TimeoutException, httpx.ConnectTimeout):
                        if attempt + 1 >= max_attempts:
                            raise ModelTimeoutError(
                                f"Gemini request timed out after {self.timeout_seconds}s."
                            ) from None
                        await asyncio.sleep(self.retry_base_seconds * (2 ** attempt))

                    except httpx.TransportError:
                        if attempt + 1 >= max_attempts:
                            raise ModelProviderUnavailableError(
                                "Failed to connect to the configured Gemini endpoint."
                            ) from None
                        await asyncio.sleep(self.retry_base_seconds * (2 ** attempt))

        except (ModelGatewayError, ModelOutputFormatError):
            raise
        except Exception as exc:
            raise ModelGatewayError(
                f"Unexpected error calling Gemini model gateway ({type(exc).__name__})."
            ) from None
