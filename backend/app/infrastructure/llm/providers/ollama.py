"""Local Ollama LLM adapter for local/offline inference."""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional, Tuple

import httpx

from app.core.config import settings
from app.infrastructure.llm.gateway import (
    ModelGatewayError,
    ModelOutputFormatError,
    ModelProviderUnavailableError,
    ModelTimeoutError,
)
from app.infrastructure.llm.providers.base import (
    BaseProviderAdapter,
    extract_and_parse_json,
)

logger = logging.getLogger(__name__)


class OllamaJsonAdapter(BaseProviderAdapter):
    """Local Ollama JSON generation adapter."""

    def __init__(
        self,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
    ):
        model_name = model or getattr(settings, "OLLAMA_MODEL_DOCUMENT", "llama3.2")
        super().__init__(provider_name="ollama", model_name=model_name)
        self.base_url = (base_url or getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")
        self.timeout_seconds = timeout_seconds or getattr(settings, "OLLAMA_REQUEST_TIMEOUT_SECONDS", 120)

    async def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_schema: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], str]:
        url = f"{self.base_url}/api/generate"
        start_time = time.perf_counter()

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    url,
                    json={
                        "model": self.model,
                        "system": system_prompt,
                        "prompt": user_prompt,
                        "format": response_schema,
                        "stream": False,
                        "options": {"temperature": 0},
                    },
                )
                response.raise_for_status()
                body = response.json()

                raw_text = body.get("response", "")
                parsed = extract_and_parse_json(raw_text)

                latency = time.perf_counter() - start_time
                self._record_usage(
                    prompt_tokens=body.get("prompt_eval_count", 0),
                    completion_tokens=body.get("eval_count", 0),
                    total_tokens=body.get("prompt_eval_count", 0) + body.get("eval_count", 0),
                    latency_seconds=latency,
                    model_name=str(body.get("model") or self.model),
                )
                return parsed, str(body.get("model") or self.model)

        except httpx.ConnectError:
            raise ModelProviderUnavailableError(
                "Cannot connect to the configured Ollama endpoint."
            ) from None
        except (httpx.TimeoutException, httpx.ConnectTimeout):
            raise ModelTimeoutError(
                f"Ollama request timed out after {self.timeout_seconds}s."
            ) from None
        except httpx.HTTPStatusError as exc:
            raise ModelGatewayError(
                f"Ollama server returned HTTP {exc.response.status_code}."
            ) from None
        except (ModelGatewayError, ModelOutputFormatError):
            raise
        except Exception as exc:
            raise ModelGatewayError(
                f"Unexpected error calling Ollama model gateway ({type(exc).__name__})."
            ) from None
