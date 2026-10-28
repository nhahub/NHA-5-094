"""Generic OpenAI-compatible LLM adapter for third-party inference endpoints."""
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


class OpenAICompatibleJsonAdapter(BaseProviderAdapter):
    """Generic OpenAI-compatible structured JSON adapter."""

    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        api_base_url: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        max_retries: Optional[int] = None,
        retry_base_seconds: Optional[float] = None,
        custom_headers: Optional[Dict[str, str]] = None,
        provider_name: str = "openai_compatible",
    ):
        model_name = model or getattr(settings, "OPENAI_MODEL", "gpt-4o-mini")
        super().__init__(provider_name=provider_name, model_name=model_name)
        self.api_key = api_key or getattr(settings, "OPENAI_API_KEY", "")
        self.api_base_url = (api_base_url or getattr(
            settings, "OPENAI_API_BASE_URL", "https://api.openai.com/v1/chat/completions"
        )).rstrip("/")
        self.timeout_seconds = timeout_seconds or 120
        self.max_retries = max_retries if max_retries is not None else 2
        self.retry_base_seconds = retry_base_seconds or 1.0
        self.custom_headers = custom_headers or {}

    async def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_schema: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], str]:
        prompt = build_schema_enforced_prompt(user_prompt, response_schema)
        headers = {
            "Content-Type": "application/json",
            **self.custom_headers,
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        max_attempts = max(0, self.max_retries) + 1
        start_time = time.perf_counter()

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                for attempt in range(max_attempts):
                    try:
                        response = await client.post(
                            self.api_base_url,
                            headers=headers,
                            json={
                                "model": self.model,
                                "messages": [
                                    {"role": "system", "content": system_prompt},
                                    {"role": "user", "content": prompt},
                                ],
                                "temperature": 0,
                                "response_format": {"type": "json_object"},
                            },
                        )
                        response.raise_for_status()
                        body = response.json()

                        choices = body.get("choices", [])
                        if not choices:
                            raise ModelOutputFormatError("OpenAI-compatible endpoint returned no choices.")

                        content = choices[0]["message"]["content"]
                        parsed = extract_and_parse_json(content)

                        # Capture token usage
                        latency = time.perf_counter() - start_time
                        usage_meta = body.get("usage", {})
                        self._record_usage(
                            prompt_tokens=usage_meta.get("prompt_tokens", 0),
                            completion_tokens=usage_meta.get("completion_tokens", 0),
                            total_tokens=usage_meta.get("total_tokens", 0),
                            latency_seconds=latency,
                            model_name=str(body.get("model") or self.model),
                        )
                        return parsed, str(body.get("model") or self.model)

                    except httpx.HTTPStatusError as exc:
                        status_code = exc.response.status_code
                        if status_code in (401, 403):
                            raise ModelAuthenticationError(
                                f"Authentication failed on OpenAI-compatible endpoint (HTTP {status_code})."
                            ) from None
                        elif status_code == 429:
                            if attempt + 1 >= max_attempts:
                                raise ModelRateLimitError(
                                    "Rate limit exceeded (HTTP 429) across all retry attempts."
                                ) from None
                        elif status_code >= 500:
                            if attempt + 1 >= max_attempts:
                                raise ModelProviderUnavailableError(
                                    f"OpenAI-compatible server error (HTTP {status_code})."
                                ) from None
                        else:
                            raise ModelGatewayError(
                                f"OpenAI-compatible request failed (HTTP {status_code})."
                            ) from None

                        backoff = self.retry_base_seconds * (2 ** attempt)
                        await asyncio.sleep(backoff)

                    except (httpx.TimeoutException, httpx.ConnectTimeout):
                        if attempt + 1 >= max_attempts:
                            raise ModelTimeoutError(
                                f"Request timed out after {self.timeout_seconds}s."
                            ) from None
                        await asyncio.sleep(self.retry_base_seconds * (2 ** attempt))

                    except httpx.TransportError:
                        if attempt + 1 >= max_attempts:
                            raise ModelProviderUnavailableError(
                                "Failed to connect to the configured model endpoint."
                            ) from None
                        await asyncio.sleep(self.retry_base_seconds * (2 ** attempt))

        except (ModelGatewayError, ModelOutputFormatError):
            raise
        except Exception as exc:
            raise ModelGatewayError(
                f"Unexpected error calling OpenAI-compatible gateway ({type(exc).__name__})."
            ) from None
