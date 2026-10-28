"""Infrastructure LLM package containing Model Gateway and Embedding Adapters."""
from app.infrastructure.llm.embedding import (
    BGEM3EmbeddingAdapter,
    CloudflareBGEEmbeddingAdapter,
    EmbeddingAdapter,
    ErrorEmbeddingAdapter,
    FakeEmbeddingAdapter,
    HuggingFaceAPIEmbeddingAdapter,
    get_embedding_adapter,
)
from app.infrastructure.llm.gateway import (
    JsonModelAdapter,
    ModelAuthenticationError,
    ModelGateway,
    ModelGatewayError,
    ModelOutputFormatError,
    ModelProviderUnavailableError,
    ModelRateLimitError,
    ModelResponse,
    ModelTimeoutError,
    ModelUsage,
    get_agent_json_model_adapter,
    get_json_model_adapter,
)
from app.infrastructure.llm.providers import (
    BaseProviderAdapter,
    FakeJsonModelAdapter,
    GeminiJsonAdapter,
    GroqJsonAdapter,
    OllamaJsonAdapter,
    OpenAICompatibleJsonAdapter,
)

# Alias for convenience
CloudflareEmbeddingAdapter = CloudflareBGEEmbeddingAdapter

__all__ = [
    # Gateway & Types
    "JsonModelAdapter",
    "ModelGateway",
    "ModelUsage",
    "ModelResponse",
    "get_agent_json_model_adapter",
    "get_json_model_adapter",
    # Error Types
    "ModelGatewayError",
    "ModelAuthenticationError",
    "ModelRateLimitError",
    "ModelTimeoutError",
    "ModelOutputFormatError",
    "ModelProviderUnavailableError",
    # Providers
    "BaseProviderAdapter",
    "FakeJsonModelAdapter",
    "GeminiJsonAdapter",
    "GroqJsonAdapter",
    "OllamaJsonAdapter",
    "OpenAICompatibleJsonAdapter",
    # Embeddings
    "EmbeddingAdapter",
    "CloudflareBGEEmbeddingAdapter",
    "CloudflareEmbeddingAdapter",
    "HuggingFaceAPIEmbeddingAdapter",
    "BGEM3EmbeddingAdapter",
    "FakeEmbeddingAdapter",
    "ErrorEmbeddingAdapter",
    "get_embedding_adapter",
]
