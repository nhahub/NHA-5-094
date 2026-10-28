"""Groq LLM adapter with multi-credential failover, exponential retry, and token tracking."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

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


class GroqJsonAdapter(BaseProviderAdapter):
    """OpenAI-compatible Groq adapter with ordered API-key fallback and resilience."""

    def __init__(
        self,
        model: Optional[str] = None,
        api_base_url: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        max_retries: Optional[int] = None,
        retry_base_seconds: Optional[float] = None,
        api_keys: Optional[List[str]] = None,
    ):
        model_name = model or getattr(settings, "GROQ_DOCUMENT_MODEL", "qwen/qwen3.8-27b")
        super().__init__(provider_name="groq", model_name=model_name)
        self.api_base_url = api_base_url or getattr(
            settings, "GROQ_API_BASE_URL", "https://api.groq.com/openai/v1/chat/completions"
        )
        self.timeout_seconds = timeout_seconds or getattr(settings, "GROQ_REQUEST_TIMEOUT_SECONDS", 120)
        self.max_retries = max_retries if max_retries is not None else getattr(settings, "GROQ_MAX_RETRIES", 2)
        self.retry_base_seconds = retry_base_seconds or getattr(settings, "GROQ_RETRY_BASE_SECONDS", 1.0)
        self._custom_keys = api_keys

    def _get_api_keys(self) -> List[str]:
        if self._custom_keys is not None:
            return [k.strip() for k in self._custom_keys if k and k.strip()]

        keys = [
            getattr(settings, "GROQ_API_KEY", None),
            getattr(settings, "GROQ_API_KEY_FALLBACK_1", None),
            getattr(settings, "GROQ_API_KEY_FALLBACK_2", None),
        ]
        return list(dict.fromkeys(k.strip() for k in keys if k and k.strip()))

    async def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_schema: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], str]:
        keys = self._get_api_keys()
        if not keys:
            raise ModelAuthenticationError(
                "No valid Groq API key configured. Set GROQ_API_KEY or GROQ_API_KEY_FALLBACK_* in .env."
            )

        prompt = build_schema_enforced_prompt(user_prompt, response_schema)
        max_attempts = max(0, self.max_retries) + 1
        last_error: Optional[Exception] = None
        start_time = time.perf_counter()

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                for key_index, api_key in enumerate(keys):
                    for attempt in range(max_attempts):
                        try:
                            logger.debug(
                                "Calling Groq (key %d/%d, attempt %d/%d, model=%s)",
                                key_index + 1, len(keys), attempt + 1, max_attempts, self.model
                            )
                            response = await client.post(
                                self.api_base_url,
                                headers={
                                    "Authorization": f"Bearer {api_key}",
                                    "Content-Type": "application/json",
                                },
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

                            content = body["choices"][0]["message"]["content"]
                            parsed = extract_and_parse_json(content)

                            # Capture token usage
                            latency = time.perf_counter() - start_time
                            usage_meta = body.get("usage", {})
                            self._record_usage(
                                prompt_tokens=usage_meta.get("prompt_tokens", 0),
                                completion_tokens=usage_meta.get("completion_tokens", 0),
                                total_tokens=usage_meta.get("total_tokens", 0),
                                latency_seconds=latency,
                                model_name=body.get("model") or self.model,
                            )
                            return parsed, str(body.get("model") or self.model)

                        except httpx.HTTPStatusError as exc:
                            last_error = exc
                            status_code = exc.response.status_code

                            # Authentication or rate limit -> immediately rotate to next available key
                            if status_code in (401, 403):
                                logger.warning(
                                    "Groq authentication failure with key index %d (HTTP %d). Trying fallback key.",
                                    key_index, status_code
                                )
                                break
                            elif status_code == 429:
                                logger.warning(
                                    "Groq rate limit with key index %d (HTTP 429). Trying fallback key.",
                                    key_index
                                )
                                break

                            # Transient server error (408, 500, 502, 503, 504) -> retry with exponential backoff
                            retryable = status_code in (408, 500, 502, 503, 504)
                            if not retryable or (attempt + 1 >= max_attempts):
                                if status_code >= 500:
                                    raise ModelProviderUnavailableError(
                                        f"Groq API returned persistent server error (HTTP {status_code})."
                                    ) from None
                                raise ModelGatewayError(
                                    f"Groq API returned HTTP {status_code}."
                                ) from None

                            backoff = self.retry_base_seconds * (2 ** attempt)
                            logger.info("Groq returned HTTP %d. Retrying in %.2fs...", status_code, backoff)
                            await asyncio.sleep(backoff)

                        except (httpx.TimeoutException, httpx.ConnectTimeout) as exc:
                            last_error = exc
                            if attempt + 1 >= max_attempts:
                                if key_index + 1 < len(keys):
                                    break
                                raise ModelTimeoutError(
                                    f"Groq request timed out after {self.timeout_seconds}s across all attempts."
                                ) from None
                            backoff = self.retry_base_seconds * (2 ** attempt)
                            await asyncio.sleep(backoff)

                        except httpx.TransportError as exc:
                            last_error = exc
                            if attempt + 1 >= max_attempts:
                                if key_index + 1 < len(keys):
                                    break
                                raise ModelProviderUnavailableError(
                                    "Failed to connect to the configured Groq endpoint."
                                ) from None
                            backoff = self.retry_base_seconds * (2 ** attempt)
                            await asyncio.sleep(backoff)

                # If all keys were exhausted
                if isinstance(last_error, httpx.HTTPStatusError):
                    if last_error.response.status_code in (401, 403):
                        raise ModelAuthenticationError(
                            f"All configured Groq API keys were rejected (HTTP {last_error.response.status_code})."
                        ) from None
                    elif last_error.response.status_code == 429:
                        raise ModelRateLimitError(
                            "All configured Groq API keys exceeded rate limits (HTTP 429)."
                        ) from None
                    raise ModelGatewayError(
                        f"Groq API request failed after all keys exhausted (HTTP {last_error.response.status_code})."
                    ) from None

                raise ModelGatewayError(
                    f"Groq request failed after all credentials were tried ({type(last_error).__name__})."
                ) from None

        except (ModelGatewayError, ModelOutputFormatError):
            raise
        except Exception as exc:
            raise ModelGatewayError(
                f"Unexpected error calling Groq model gateway ({type(exc).__name__})."
            ) from None
