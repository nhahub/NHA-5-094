"""Tests for Phase 14: Model Gateway (Infrastructure LLM Gateway and Provider Adapters)."""
import json
import pytest
import httpx
from unittest.mock import AsyncMock, patch

from app.core.config import settings
from app.infrastructure.llm.gateway import (
    JsonModelAdapter,
    ModelAuthenticationError,
    ModelGateway,
    ModelGatewayError,
    ModelOutputFormatError,
    ModelProviderUnavailableError,
    ModelRateLimitError,
    ModelTimeoutError,
    ModelUsage,
    get_agent_json_model_adapter,
    get_json_model_adapter,
)
from app.infrastructure.llm.providers.base import (
    build_schema_enforced_prompt,
    extract_and_parse_json,
)
from app.infrastructure.llm.providers.fake import FakeJsonModelAdapter
from app.infrastructure.llm.providers.gemini import GeminiJsonAdapter
from app.infrastructure.llm.providers.groq import GroqJsonAdapter
from app.infrastructure.llm.providers.ollama import OllamaJsonAdapter
from app.infrastructure.llm.providers.openai_compatible import OpenAICompatibleJsonAdapter
import app.domain.documents.intelligence as doc_intel


def _mock_resp(status_code: int = 200, json_data: dict | None = None, text: str = "") -> httpx.Response:
    req = httpx.Request("POST", "https://api.test/v1/endpoint")
    if json_data is not None:
        return httpx.Response(status_code, json=json_data, request=req)
    return httpx.Response(status_code, text=text, request=req)


# ---------------------------------------------------------------------------
# 1. Base Utility Tests
# ---------------------------------------------------------------------------

def test_build_schema_enforced_prompt():
    schema = {
        "type": "object",
        "properties": {"decision": {"type": "string"}},
        "required": ["decision"],
    }
    prompt = build_schema_enforced_prompt("Please evaluate this document.", schema)
    assert "Please evaluate this document." in prompt
    assert "JSON Schema:" in prompt
    assert '"decision"' in prompt


def test_extract_and_parse_json_variants():
    # Clean JSON
    assert extract_and_parse_json('{"key": "value"}') == {"key": "value"}

    # Markdown wrapped JSON
    assert extract_and_parse_json('```json\n{"key": "value"}\n```') == {"key": "value"}
    assert extract_and_parse_json('```\n{"key": "value"}\n```') == {"key": "value"}

    # Preamble / Trailing text
    assert extract_and_parse_json('Here is the result:\n{"key": "value"}\nHope this helps!') == {"key": "value"}

    # Invalid cases
    with pytest.raises(ModelOutputFormatError):
        extract_and_parse_json("")

    with pytest.raises(ModelOutputFormatError):
        extract_and_parse_json("not a json string at all")

    with pytest.raises(ModelOutputFormatError):
        extract_and_parse_json("['item1', 'item2']")


# ---------------------------------------------------------------------------
# 2. Fake / Mock Adapter Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fake_model_adapter_basic():
    adapter = FakeJsonModelAdapter(default_response={"action": "APPROVE", "confidence": 0.95})
    schema = {"type": "object", "properties": {"action": {"type": "string"}}}

    data, model_name = await adapter.generate_json(
        system_prompt="sys",
        user_prompt="user",
        response_schema=schema,
    )

    assert data == {"action": "APPROVE", "confidence": 0.95}
    assert model_name == "fake-model-v1"
    assert len(adapter.call_history) == 1
    assert adapter.last_usage is not None
    assert adapter.last_usage.provider_name == "fake"
    assert adapter.last_usage.total_tokens == 225


@pytest.mark.asyncio
async def test_fake_model_adapter_programmable_factory():
    def custom_factory(sys, user, schema):
        if "invoice" in user:
            return {"type": "invoice", "total": 500}
        return {"type": "unknown"}

    adapter = FakeJsonModelAdapter(response_factory=custom_factory, simulated_latency=0.01)
    data1, _ = await adapter.generate_json(system_prompt="s", user_prompt="here is invoice", response_schema={})
    data2, _ = await adapter.generate_json(system_prompt="s", user_prompt="other text", response_schema={})

    assert data1["type"] == "invoice"
    assert data1["total"] == 500
    assert data2["type"] == "unknown"
    assert adapter.last_usage.latency_seconds >= 0.005


@pytest.mark.asyncio
async def test_fake_model_adapter_error_injection():
    adapter = FakeJsonModelAdapter(error_to_raise=ModelTimeoutError("Simulated timeout"))
    with pytest.raises(ModelTimeoutError) as exc_info:
        await adapter.generate_json(system_prompt="s", user_prompt="u", response_schema={})
    assert "Simulated timeout" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 3. ModelGateway Factory Tests
# ---------------------------------------------------------------------------

def test_model_gateway_factory_resolution(monkeypatch):
    # Explicit provider resolutions
    fake_adapter = ModelGateway.get_adapter("fake")
    assert isinstance(fake_adapter, FakeJsonModelAdapter)

    groq_adapter = ModelGateway.get_adapter("groq")
    assert isinstance(groq_adapter, GroqJsonAdapter)

    gemini_adapter = ModelGateway.get_adapter("gemini")
    assert isinstance(gemini_adapter, GeminiJsonAdapter)

    ollama_adapter = ModelGateway.get_adapter("ollama")
    assert isinstance(ollama_adapter, OllamaJsonAdapter)

    openai_adapter = ModelGateway.get_adapter("openai")
    assert isinstance(openai_adapter, OpenAICompatibleJsonAdapter)

    monkeypatch.setattr(settings, "LLM7_API_KEY", "llm7-test-key")
    llm7_adapter = ModelGateway.get_adapter("llm7")
    assert isinstance(llm7_adapter, OpenAICompatibleJsonAdapter)
    assert llm7_adapter.provider_name == "llm7"
    assert llm7_adapter.api_key == "llm7-test-key"
    assert llm7_adapter.model == settings.LLM7_DOCUMENT_MODEL
    assert llm7_adapter.api_base_url == settings.LLM7_API_BASE_URL

    monkeypatch.setattr(settings, "KILO_API_KEY", "kilo-test-key")
    kilo_adapter = ModelGateway.get_adapter("kilo")
    assert isinstance(kilo_adapter, OpenAICompatibleJsonAdapter)
    assert kilo_adapter.provider_name == "kilo"
    assert kilo_adapter.api_key == "kilo-test-key"
    assert kilo_adapter.model == settings.KILO_DOCUMENT_MODEL
    assert kilo_adapter.api_base_url == settings.KILO_API_BASE_URL

    # Convenience helper
    helper_adapter = get_json_model_adapter(provider="fake", model="custom-fake")
    assert isinstance(helper_adapter, FakeJsonModelAdapter)
    assert helper_adapter.model == "custom-fake"

    # Unsupported provider
    with pytest.raises(ModelGatewayError) as exc_info:
        ModelGateway.get_adapter("unsupported_provider_xyz")
    assert "Unsupported model provider" in str(exc_info.value)


def test_agent_model_routing_uses_each_agents_provider_and_model(monkeypatch):
    choices = {
        "DOCUMENT": ("llm7", "gpt-oss:20b"),
        "VERIFICATION": ("groq", "qwen/qwen3.8-27b"),
        "WORKFLOW": ("kilo", "stepfun/step-3.7-flash:free"),
        "SUPERVISOR": ("groq", "qwen/qwen3.8-27b"),
    }
    for agent_type, (provider, model) in choices.items():
        monkeypatch.setattr(settings, f"{agent_type}_MODEL_PROVIDER", provider)
        monkeypatch.setattr(settings, f"{agent_type}_MODEL", model)
        adapter = get_agent_json_model_adapter(agent_type)
        assert adapter.provider_name == provider
        assert adapter.model == model

    with pytest.raises(ValueError, match="Unsupported agent type"):
        get_agent_json_model_adapter("UNKNOWN")


# ---------------------------------------------------------------------------
# 4. Groq Provider Adapter Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_groq_adapter_success_and_token_metrics():
    adapter = GroqJsonAdapter(
        model="qwen/qwen3.8-27b",
        api_keys=["gsk_mock_test_key_1"],
    )

    mock_response = {
        "id": "chatcmpl-mock",
        "model": "qwen/qwen3.8-27b",
        "choices": [{
            "message": {"content": '{"classification": "invoice", "confidence": 0.98}'}
        }],
        "usage": {
            "prompt_tokens": 120,
            "completion_tokens": 45,
            "total_tokens": 165,
        }
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _mock_resp(200, json_data=mock_response)

        data, model = await adapter.generate_json(
            system_prompt="sys",
            user_prompt="Classify this invoice.",
            response_schema={"type": "object"},
        )

        assert data == {"classification": "invoice", "confidence": 0.98}
        assert model == "qwen/qwen3.8-27b"
        assert adapter.last_usage is not None
        assert adapter.last_usage.prompt_tokens == 120
        assert adapter.last_usage.completion_tokens == 45
        assert adapter.last_usage.total_tokens == 165
        assert adapter.last_usage.provider_name == "groq"


@pytest.mark.asyncio
async def test_groq_adapter_multi_key_rotation_on_401():
    # Key 1 will fail with 401; Key 2 will succeed
    adapter = GroqJsonAdapter(
        model="qwen/qwen3.8-27b",
        api_keys=["gsk_bad_key_1", "gsk_good_key_2"],
        retry_base_seconds=0.001,
    )

    resp_401 = _mock_resp(401, json_data={"error": "Invalid API Key"})
    resp_200 = _mock_resp(200, json_data={
        "choices": [{"message": {"content": '{"result": "success_from_key_2"}'}}],
        "usage": {"total_tokens": 50},
        "model": "qwen/qwen3.8-27b",
    })

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = [resp_401, resp_200]
        data, _ = await adapter.generate_json(
            system_prompt="s",
            user_prompt="u",
            response_schema={},
        )
        assert data == {"result": "success_from_key_2"}


@pytest.mark.asyncio
async def test_groq_adapter_multi_key_rotation_on_429():
    # Key 1 rate limited (429); Key 2 succeeds
    adapter = GroqJsonAdapter(
        model="qwen/qwen3.8-27b",
        api_keys=["gsk_rate_limited_1", "gsk_backup_2"],
        retry_base_seconds=0.001,
    )

    resp_429 = _mock_resp(429, json_data={"error": "Rate limit exceeded"})
    resp_200 = _mock_resp(200, json_data={
        "choices": [{"message": {"content": '{"rate_limit_handled": true}'}}],
        "usage": {"total_tokens": 80},
    })

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = [resp_429, resp_200]
        data, _ = await adapter.generate_json(
            system_prompt="s",
            user_prompt="u",
            response_schema={},
        )
        assert data == {"rate_limit_handled": True}


@pytest.mark.asyncio
async def test_groq_adapter_all_keys_exhausted_raises_auth_error():
    adapter = GroqJsonAdapter(
        model="qwen/qwen3.8-27b",
        api_keys=["gsk_bad_1", "gsk_bad_2"],
        retry_base_seconds=0.001,
    )

    resp_401_a = _mock_resp(401, json_data={"error": "Unauthorized 1"})
    resp_401_b = _mock_resp(401, json_data={"error": "Unauthorized 2"})

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = [resp_401_a, resp_401_b]
        with pytest.raises(ModelAuthenticationError) as exc_info:
            await adapter.generate_json(system_prompt="s", user_prompt="u", response_schema={})
        assert "All configured Groq API keys were rejected" in str(exc_info.value)


@pytest.mark.asyncio
async def test_groq_adapter_retry_on_500_server_error():
    adapter = GroqJsonAdapter(
        model="qwen/qwen3.8-27b",
        api_keys=["gsk_valid_key"],
        max_retries=2,
        retry_base_seconds=0.001,
    )

    resp_500 = _mock_resp(500, text="Internal Server Error")
    resp_200 = _mock_resp(200, json_data={
        "choices": [{"message": {"content": '{"recovered": true}'}}],
    })

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = [resp_500, resp_200]
        data, _ = await adapter.generate_json(system_prompt="s", user_prompt="u", response_schema={})
        assert data == {"recovered": True}


@pytest.mark.asyncio
async def test_groq_adapter_malformed_json_raises_format_error():
    adapter = GroqJsonAdapter(
        model="qwen/qwen3.8-27b",
        api_keys=["gsk_valid_key"],
    )

    resp_invalid = _mock_resp(200, json_data={
        "choices": [{"message": {"content": 'I am unable to output JSON: [error]'}}],
    })

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = resp_invalid
        with pytest.raises(ModelOutputFormatError):
            await adapter.generate_json(system_prompt="s", user_prompt="u", response_schema={})


# ---------------------------------------------------------------------------
# 5. Gemini Provider Adapter Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_gemini_adapter_success_and_token_usage():
    adapter = GeminiJsonAdapter(
        model="gemini-3.8-flash",
        api_key="mock-gemini-key",
        retry_base_seconds=0.001,
    )

    mock_gemini_resp = {
        "candidates": [{
            "content": {"parts": [{"text": '{"action": "EXTRACT", "confidence": 0.99}'}]}
        }],
        "usageMetadata": {
            "promptTokenCount": 200,
            "candidatesTokenCount": 60,
            "totalTokenCount": 260,
        }
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _mock_resp(200, json_data=mock_gemini_resp)
        data, model = await adapter.generate_json(
            system_prompt="s",
            user_prompt="u",
            response_schema={},
        )
        assert data == {"action": "EXTRACT", "confidence": 0.99}
        assert model == "gemini-3.8-flash"
        assert adapter.last_usage.total_tokens == 260
        assert adapter.last_usage.provider_name == "gemini"


@pytest.mark.asyncio
async def test_gemini_adapter_missing_key_raises_auth_error():
    adapter = GeminiJsonAdapter(api_key="")
    adapter.api_key = None
    with patch("app.core.config.settings.GEMINI_API_KEY", None):
        with pytest.raises(ModelAuthenticationError) as exc_info:
            await adapter.generate_json(system_prompt="s", user_prompt="u", response_schema={})
        assert "Set GEMINI_API_KEY" in str(exc_info.value)


@pytest.mark.asyncio
async def test_gemini_adapter_retry_on_429_exhausted():
    adapter = GeminiJsonAdapter(
        api_key="mock-key",
        max_retries=1,
        retry_base_seconds=0.001,
    )
    resp_429_a = _mock_resp(429, text="Quota exceeded 1")
    resp_429_b = _mock_resp(429, text="Quota exceeded 2")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = [resp_429_a, resp_429_b]
        with pytest.raises(ModelRateLimitError) as exc_info:
            await adapter.generate_json(system_prompt="s", user_prompt="u", response_schema={})
        assert "Gemini rate limit exceeded" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 6. Ollama Provider Adapter Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ollama_adapter_success_and_token_usage():
    adapter = OllamaJsonAdapter(
        model="llama3.2",
        base_url="http://localhost:11434",
    )

    mock_ollama_resp = {
        "model": "llama3.2",
        "response": '{"summary": "local processing done"}',
        "prompt_eval_count": 85,
        "eval_count": 30,
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _mock_resp(200, json_data=mock_ollama_resp)
        data, model = await adapter.generate_json(
            system_prompt="s",
            user_prompt="u",
            response_schema={},
        )
        assert data == {"summary": "local processing done"}
        assert model == "llama3.2"
        assert adapter.last_usage.total_tokens == 115
        assert adapter.last_usage.provider_name == "ollama"


@pytest.mark.asyncio
async def test_ollama_adapter_connection_failure():
    adapter = OllamaJsonAdapter(base_url="http://non-existent-host:11434")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.ConnectError("Connection refused")
        with pytest.raises(ModelProviderUnavailableError) as exc_info:
            await adapter.generate_json(system_prompt="s", user_prompt="u", response_schema={})
        assert str(exc_info.value) == "Cannot connect to the configured Ollama endpoint."
        assert "non-existent-host" not in str(exc_info.value)


# ---------------------------------------------------------------------------
# 7. OpenAI-Compatible Adapter Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_openai_compatible_adapter_success():
    adapter = OpenAICompatibleJsonAdapter(
        model="gpt-4o-mini",
        api_key="sk-mock-openai-key",
        api_base_url="https://api.openai.com/v1/chat/completions",
        custom_headers={"X-Custom-Client": "VerifiaAI"},
    )

    mock_resp = {
        "model": "gpt-4o-mini",
        "choices": [{"message": {"content": '{"decision": "ALLOW"}'}}],
        "usage": {
            "prompt_tokens": 150,
            "completion_tokens": 25,
            "total_tokens": 175,
        }
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _mock_resp(200, json_data=mock_resp)

        data, model = await adapter.generate_json(
            system_prompt="s",
            user_prompt="u",
            response_schema={},
        )

        assert data == {"decision": "ALLOW"}
        assert model == "gpt-4o-mini"
        assert adapter.last_usage.total_tokens == 175
        assert adapter.last_usage.provider_name == "openai_compatible"

        # Verify custom header and authorization were sent
        headers_sent = mock_post.call_args[1]["headers"]
        assert headers_sent["Authorization"] == "Bearer sk-mock-openai-key"
        assert headers_sent["X-Custom-Client"] == "VerifiaAI"


# ---------------------------------------------------------------------------
# 8. Backward Compatibility Re-export Tests
# ---------------------------------------------------------------------------

def test_intelligence_module_backward_compatibility():
    """Verify that domain.documents.intelligence maintains re-exports for existing agents and callers."""
    assert hasattr(doc_intel, "JsonModelAdapter")
    assert hasattr(doc_intel, "get_json_model_adapter")
    assert hasattr(doc_intel, "GroqJsonAdapter")
    assert hasattr(doc_intel, "GeminiJsonAdapter")
    assert hasattr(doc_intel, "OllamaJsonAdapter")
    assert hasattr(doc_intel, "ModelGateway")

    # Confirm it returns a working adapter
    adapter = doc_intel.get_json_model_adapter(provider="fake")
    assert isinstance(adapter, FakeJsonModelAdapter)
