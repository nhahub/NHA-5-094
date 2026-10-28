"""Model Gateway interface, error types, response models, and provider factory.

Provides a unified abstraction across all LLM inference providers (Groq, LLM7,
Kilo Gateway, Gemini, Ollama, OpenAI-compatible, Fake/Mock). All agents (Document, Verification,
Workflow, Supervisor) interact with language models through this gateway.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Tuple, runtime_checkable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Error Hierarchy
# ---------------------------------------------------------------------------

class ModelGatewayError(RuntimeError):
    """Base error for all Model Gateway operations."""
    pass


class ModelAuthenticationError(ModelGatewayError):
    """Raised when provider API keys are missing, invalid, or unauthorized (HTTP 401/403)."""
    pass


class ModelRateLimitError(ModelGatewayError):
    """Raised when rate limits or quotas are exceeded across all available credentials (HTTP 429)."""
    pass


class ModelTimeoutError(ModelGatewayError):
    """Raised when a model inference request times out."""
    pass


class ModelOutputFormatError(ModelGatewayError):
    """Raised when model output is invalid JSON or does not match the expected structure."""
    pass


class ModelProviderUnavailableError(ModelGatewayError):
    """Raised when the provider endpoint cannot be reached or returns persistent 5xx errors."""
    pass


# ---------------------------------------------------------------------------
# Data Containers & Metrics
# ---------------------------------------------------------------------------

@dataclass
class ModelUsage:
    """Usage metrics and token counts for a model inference invocation."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_seconds: float = 0.0
    model_name: str = ""
    provider_name: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "latency_seconds": round(self.latency_seconds, 4),
            "model_name": self.model_name,
            "provider_name": self.provider_name,
        }


@dataclass
class ModelResponse:
    """Rich structured response from the Model Gateway."""
    data: Dict[str, Any]
    raw_text: str
    model: str
    provider: str
    usage: ModelUsage = field(default_factory=ModelUsage)


# ---------------------------------------------------------------------------
# Protocol (Contract)
# ---------------------------------------------------------------------------

@runtime_checkable
class JsonModelAdapter(Protocol):
    """Core protocol that every Model Gateway provider adapter must satisfy.

    Maintains full backward compatibility with the existing:
        async def generate_json(self, *, system_prompt: str, user_prompt: str, response_schema: Dict[str, Any]) -> Tuple[Dict[str, Any], str]
    while optionally supporting extended metadata through `last_usage`.
    """

    provider_name: str
    model: str

    async def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_schema: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], str]:
        """Generate a validated JSON object conforming to `response_schema`.

        Returns:
            Tuple[Dict[str, Any], str]: (parsed_json_object, model_identifier)
        """
        ...


# ---------------------------------------------------------------------------
# Gateway Factory & Provider Dispatcher
# ---------------------------------------------------------------------------

class ModelGateway:
    """Central factory and dispatcher for language model adapters."""

    @staticmethod
    def _enforce_data_policy(adapter: JsonModelAdapter) -> JsonModelAdapter:
        """Reject model routes that are not approved for the active environment."""
        from app.core.config import settings

        try:
            endpoint_url = (
                getattr(adapter, "api_base_url", None)
                or getattr(adapter, "base_url", None)
            )
            settings.require_model_route_allowed(
                adapter.provider_name,
                adapter.model,
                endpoint_url=endpoint_url,
            )
        except ValueError as exc:
            raise ModelGatewayError(str(exc)) from None
        return adapter

    @staticmethod
    def get_adapter(
        provider: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> JsonModelAdapter:
        """Create and return a configured model adapter.

        Args:
            provider: Provider name ('groq', 'llm7', 'kilo', 'gemini', 'ollama', 'openai', 'fake').
                      If omitted, defaults to settings.MODEL_GATEWAY_PROVIDER or
                      settings.DOCUMENT_MODEL_PROVIDER.
            model: Specific model name override.
            **kwargs: Extra parameters passed to the provider adapter constructor.

        Returns:
            JsonModelAdapter: Concrete adapter instance.
        """
        from app.core.config import settings

        selected_provider = (
            provider
            or getattr(settings, "MODEL_GATEWAY_PROVIDER", None)
            or getattr(settings, "DOCUMENT_MODEL_PROVIDER", "groq")
        ).strip().lower()

        if selected_provider == "groq":
            from app.infrastructure.llm.providers.groq import GroqJsonAdapter
            return ModelGateway._enforce_data_policy(GroqJsonAdapter(model=model, **kwargs))

        elif selected_provider == "gemini":
            from app.infrastructure.llm.providers.gemini import GeminiJsonAdapter
            return ModelGateway._enforce_data_policy(GeminiJsonAdapter(model=model, **kwargs))

        elif selected_provider == "ollama":
            from app.infrastructure.llm.providers.ollama import OllamaJsonAdapter
            return ModelGateway._enforce_data_policy(OllamaJsonAdapter(model=model, **kwargs))

        elif selected_provider in ("openai", "openai_compatible"):
            from app.infrastructure.llm.providers.openai_compatible import OpenAICompatibleJsonAdapter
            return ModelGateway._enforce_data_policy(
                OpenAICompatibleJsonAdapter(model=model, **kwargs)
            )

        elif selected_provider in ("llm7", "kilo"):
            from app.infrastructure.llm.providers.openai_compatible import OpenAICompatibleJsonAdapter

            if selected_provider == "llm7":
                return ModelGateway._enforce_data_policy(
                    OpenAICompatibleJsonAdapter(
                        model=model or settings.LLM7_DOCUMENT_MODEL,
                        api_key=settings.LLM7_API_KEY or "",
                        api_base_url=settings.LLM7_API_BASE_URL,
                        provider_name="llm7",
                    )
                )
            return ModelGateway._enforce_data_policy(
                OpenAICompatibleJsonAdapter(
                    model=model or settings.KILO_DOCUMENT_MODEL,
                    api_key=settings.KILO_API_KEY or "",
                    api_base_url=settings.KILO_API_BASE_URL,
                    provider_name="kilo",
                )
            )

        elif selected_provider in ("fake", "mock", "test"):
            from app.infrastructure.llm.providers.fake import FakeJsonModelAdapter
            return ModelGateway._enforce_data_policy(
                FakeJsonModelAdapter(model=model or "fake-model-v1", **kwargs)
            )

        else:
            raise ModelGatewayError(
                f"Unsupported model provider '{selected_provider}'. "
                f"Available providers: 'groq', 'llm7', 'kilo', 'gemini', 'ollama', 'openai', 'fake'."
            )


def get_agent_json_model_adapter(agent_type: str) -> JsonModelAdapter:
    """Build an adapter from the provider/model settings for one agent role."""
    from app.core.config import settings

    normalized = agent_type.strip().upper()
    setting_prefix = {
        "DOCUMENT": "DOCUMENT",
        "VERIFICATION": "VERIFICATION",
        "WORKFLOW": "WORKFLOW",
        "SUPERVISOR": "SUPERVISOR",
    }.get(normalized)
    if setting_prefix is None:
        raise ValueError(f"Unsupported agent type for model routing: '{agent_type}'.")

    provider = getattr(settings, f"{setting_prefix}_MODEL_PROVIDER", None)
    model = getattr(settings, f"{setting_prefix}_MODEL", None)
    return ModelGateway.get_adapter(provider=provider, model=model)


def get_json_model_adapter(
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> JsonModelAdapter:
    """Helper for FastAPI dependency injection and agent constructor defaults."""
    return ModelGateway.get_adapter(provider=provider, model=model)
