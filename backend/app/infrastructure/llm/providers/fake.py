"""Fake/Mock JSON model adapter for testing and offline development."""
from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from app.infrastructure.llm.gateway import ModelGatewayError
from app.infrastructure.llm.providers.base import BaseProviderAdapter


class FakeJsonModelAdapter(BaseProviderAdapter):
    """Deterministic, programmable model adapter for tests and local CI."""

    def __init__(
        self,
        default_response: Optional[Dict[str, Any]] = None,
        model: str = "fake-model-v1",
        simulated_latency: float = 0.0,
        prompt_tokens: int = 150,
        completion_tokens: int = 75,
        error_to_raise: Optional[Exception] = None,
        response_factory: Optional[Callable[[str, str, Dict[str, Any]], Dict[str, Any]]] = None,
    ):
        super().__init__(provider_name="fake", model_name=model)
        self.default_response = default_response or {}
        self.simulated_latency = simulated_latency
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.error_to_raise = error_to_raise
        self.response_factory = response_factory
        self.call_history: List[Dict[str, Any]] = []

    async def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_schema: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], str]:
        self.call_history.append({
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "response_schema": response_schema,
        })

        if self.simulated_latency > 0:
            await asyncio.sleep(self.simulated_latency)

        if self.error_to_raise is not None:
            raise self.error_to_raise

        if self.response_factory is not None:
            data = self.response_factory(system_prompt, user_prompt, response_schema)
        elif self.default_response:
            data = self.default_response
        else:
            # Generate minimal stub conforming to schema properties
            data = {}
            properties = response_schema.get("properties", {})
            for prop, spec in properties.items():
                ptype = spec.get("type")
                if ptype == "string":
                    data[prop] = "mock_value"
                elif ptype in ("number", "integer"):
                    data[prop] = 1
                elif ptype == "boolean":
                    data[prop] = True
                elif ptype == "array":
                    data[prop] = []
                elif ptype == "object":
                    data[prop] = {}
                else:
                    data[prop] = None

        self._record_usage(
            prompt_tokens=self.prompt_tokens,
            completion_tokens=self.completion_tokens,
            total_tokens=self.prompt_tokens + self.completion_tokens,
            latency_seconds=self.simulated_latency,
            model_name=self.model,
        )
        return data, self.model
