"""Embedding adapters for the Knowledge / RAG pipeline.

Provides a :class:`EmbeddingAdapter` Protocol so the rest of the codebase
remains decoupled from the concrete embedding implementation.

Production adapters:
1. :class:`CloudflareBGEEmbeddingAdapter` (configured default)
   → Calls the Cloudflare Workers AI OpenAI-compatible Embeddings API.
   → Uses ``CLOUDFLARE_ACCOUNT_ID`` and ``CLOUDFLARE_API_TOKEN``.
2. :class:`HuggingFaceAPIEmbeddingAdapter` (alternative)
   → Calls HuggingFace Serverless Inference API via HTTP POST.
   → Uses ``HUGGINGFACE_HUB_TOKEN`` from ``.env``.
   → Runs on HuggingFace servers (no local model weights or GPU needed).

2. :class:`BGEM3EmbeddingAdapter`
   → Uses ``BAAI/bge-m3`` locally via ``sentence-transformers``.
   → Model is downloaded automatically from HuggingFace on first call (~1.1 GB).

Test adapter: :class:`FakeEmbeddingAdapter`
  → Returns deterministic zero-filled vectors of the correct dimension.
  → Safe for CI and unit tests.
"""
from __future__ import annotations

import logging
import math
import os
from typing import List, Protocol, runtime_checkable

import httpx

logger = logging.getLogger(__name__)

# BGE-M3 native output dimension
BGE_M3_DIMENSION = 1024


# ---------------------------------------------------------------------------
# Protocol (Interface)
# ---------------------------------------------------------------------------

@runtime_checkable
class EmbeddingAdapter(Protocol):
    """Minimal interface every embedding adapter must satisfy."""

    @property
    def dimension(self) -> int:
        """The fixed output vector length for this adapter."""
        ...

    def embed(self, texts: List[str]) -> List[List[float]]:
        """Encode *texts* and return one embedding vector per input string."""
        ...


# ---------------------------------------------------------------------------
# Hugging Face Inference Server API Adapter (Default Remote Provider)
# ---------------------------------------------------------------------------

class HuggingFaceAPIEmbeddingAdapter:
    """HuggingFace Serverless Inference API adapter for BAAI/bge-m3 (1024 dimensions).

    Calls HuggingFace hosted Inference API endpoints over HTTP POST.
    No PyTorch, local model downloads, or local GPU required.

    Parameters
    ----------
    model_name:
        HuggingFace model identifier (default ``"BAAI/bge-m3"``).
    hf_token:
        HuggingFace access token. Reads ``HUGGINGFACE_HUB_TOKEN`` from env if not passed.
    api_url:
        API endpoint URL. Defaults to HuggingFace Router endpoint.
    """

    DIMENSION = BGE_M3_DIMENSION

    def __init__(
        self,
        model_name: str = "BAAI/bge-m3",
        hf_token: str | None = None,
        api_url: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        self._model_name = model_name
        self._hf_token = hf_token or os.environ.get("HUGGINGFACE_HUB_TOKEN")
        self._api_url = (
            api_url
            or os.environ.get("EMBEDDING_API_URL")
            or f"https://router.huggingface.co/hf-inference/models/{model_name}"
        )
        self._timeout = timeout

    @property
    def dimension(self) -> int:
        return self.DIMENSION

    def _normalize(self, vec: List[float]) -> List[float]:
        """Compute L2 normalized vector so dot-product equals cosine similarity."""
        norm = math.sqrt(sum(x * x for x in vec))
        if norm == 0:
            return vec
        return [x / norm for x in vec]

    def embed(self, texts: List[str]) -> List[List[float]]:
        """Embed *texts* via HuggingFace Inference API and return 1024-dim vectors."""
        if not texts:
            return []

        headers = {"Content-Type": "application/json"}
        if self._hf_token:
            headers["Authorization"] = f"Bearer {self._hf_token}"
        else:
            logger.warning(
                "No HUGGINGFACE_HUB_TOKEN supplied. HF Inference API calls may fail with 401."
            )

        payload = {
            "inputs": texts,
            "options": {"wait_for_model": True},
        }

        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.post(self._api_url, headers=headers, json=payload)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to connect to HuggingFace Inference API ({type(exc).__name__})."
            ) from None

        if resp.status_code == 401:
            raise RuntimeError(
                "HuggingFace API authorization failed (401 Unauthorized). "
                "Please set HUGGINGFACE_HUB_TOKEN in your backend/.env file."
            )
        elif resp.status_code == 403:
            raise RuntimeError(
                "HuggingFace API token permission error (403 Forbidden).\n"
                "Your Hugging Face Access Token needs the 'Make calls to Inference Providers' scope enabled.\n"
                "To fix this:\n"
                "1. Go to https://huggingface.co/settings/tokens\n"
                "2. Edit or create a new token with 'Make calls to Inference Providers' (or 'Inference') permission checked.\n"
                "3. Update HUGGINGFACE_HUB_TOKEN in backend/.env"
            )
        elif resp.status_code == 503:
            raise RuntimeError(
                "HuggingFace model is currently loading on HF servers (503 Service Unavailable). "
                "Please retry in a few seconds."
            )
        elif resp.status_code != 200:
            raise RuntimeError(
                f"HuggingFace Inference API returned status {resp.status_code}."
            )

        data = resp.json()
        results: List[List[float]] = []

        if not isinstance(data, list):
            raise ValueError(f"Unexpected response format from HuggingFace API: {type(data)}")

        for item in data:
            if not isinstance(item, list) or not item:
                continue

            # If 3D array (token-level embeddings), perform mean pooling
            if isinstance(item[0], list):
                dim = len(item[0])
                seq_len = len(item)
                pooled = [0.0] * dim
                for token_vec in item:
                    for d in range(dim):
                        pooled[d] += token_vec[d]
                vector = [val / seq_len for val in pooled]
            else:
                vector = item

            if len(vector) != self.DIMENSION:
                raise ValueError(
                    f"HuggingFace API returned vector dimension {len(vector)}, expected {self.DIMENSION}."
                )

            results.append(self._normalize(vector))

        return results


class CloudflareBGEEmbeddingAdapter:
    """BGE-M3 embedding adapter for the Cloudflare Workers AI API."""

    DIMENSION = BGE_M3_DIMENSION

    def __init__(
        self,
        account_id: str | None = None,
        api_token: str | None = None,
        model_name: str = "@cf/baai/bge-m3",
        base_url: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        from app.core.config import settings

        self._account_id = account_id or settings.CLOUDFLARE_ACCOUNT_ID
        self._api_token = api_token or settings.CLOUDFLARE_API_TOKEN
        self._model_name = model_name
        self._base_url = (base_url or settings.CLOUDFLARE_AI_BASE_URL).rstrip("/")
        self._timeout = timeout

    @property
    def dimension(self) -> int:
        return self.DIMENSION

    def embed(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        if not self._account_id:
            raise RuntimeError("Set CLOUDFLARE_ACCOUNT_ID to use Cloudflare embeddings.")
        if not self._api_token:
            raise RuntimeError("Set CLOUDFLARE_API_TOKEN to use Cloudflare embeddings.")

        url = f"{self._base_url}/accounts/{self._account_id}/ai/v1/embeddings"
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(
                    url,
                    headers={"Authorization": f"Bearer {self._api_token}"},
                    json={"model": self._model_name, "input": texts},
                )
                response.raise_for_status()
                body = response.json()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"Cloudflare Workers AI embeddings request failed (HTTP {exc.response.status_code})."
            ) from None
        except httpx.HTTPError:
            raise RuntimeError("Could not connect to Cloudflare Workers AI embeddings API.") from None

        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, list) or len(data) != len(texts):
            raise ValueError("Cloudflare embeddings API returned an unexpected response shape.")
        if any(not isinstance(item, dict) for item in data):
            raise ValueError("Cloudflare embeddings API returned an unexpected response item.")
        data = sorted(data, key=lambda item: item.get("index", 0))
        vectors: List[List[float]] = []
        for item in data:
            vector = item.get("embedding") if isinstance(item, dict) else None
            if not isinstance(vector, list) or len(vector) != self.DIMENSION:
                raise ValueError(
                    f"Cloudflare embeddings API must return {self.DIMENSION}-dimensional vectors."
                )
            normalized = [float(value) for value in vector]
            if not all(math.isfinite(value) for value in normalized):
                raise ValueError("Cloudflare embeddings API returned a non-finite vector value.")
            vectors.append(self._normalize(normalized))
        return vectors

    @staticmethod
    def _normalize(vector: List[float]) -> List[float]:
        norm = math.sqrt(sum(value * value for value in vector))
        return [value / norm for value in vector] if norm else vector


# ---------------------------------------------------------------------------
# Local Sentence-Transformers Adapter (Alternative Local Provider)
# ---------------------------------------------------------------------------

class BGEM3EmbeddingAdapter:
    """Sentence-Transformers adapter wrapping BAAI/bge-m3 locally (1024 dimensions)."""

    DIMENSION = BGE_M3_DIMENSION

    def __init__(
        self,
        model_name: str = "BAAI/bge-m3",
        hf_token: str | None = None,
        device: str = "cpu",
    ) -> None:
        self._model_name = model_name
        self._hf_token = hf_token or os.environ.get("HUGGINGFACE_HUB_TOKEN")
        self._device = device
        self._model = None  # lazy-loaded

    @property
    def dimension(self) -> int:
        return self.DIMENSION

    def _load_model(self) -> None:
        if self._model is not None:
            return

        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise RuntimeError(
                "sentence-transformers is not installed. "
                "Install the optional local provider dependencies with: "
                "pip install -r requirements-local-embeddings.txt"
            ) from None

        logger.info("Loading local embedding model '%s' on device '%s'.", self._model_name, self._device)

        if self._hf_token:
            try:
                from huggingface_hub import login
                login(token=self._hf_token, add_to_git_credential=False)
            except Exception as auth_err:
                logger.warning(
                    "HuggingFace Hub login warning (%s).",
                    type(auth_err).__name__,
                )

        self._model = SentenceTransformer(self._model_name, device=self._device)

    def embed(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []

        self._load_model()
        raw: List[List[float]] = self._model.encode(  # type: ignore[union-attr]
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        ).tolist()

        if raw and len(raw[0]) != self.DIMENSION:
            raise ValueError(
                f"Embedding model returned vector dimension {len(raw[0])}, expected {self.DIMENSION}."
            )

        return raw


# ---------------------------------------------------------------------------
# Test Adapters
# ---------------------------------------------------------------------------

class FakeEmbeddingAdapter:
    """Deterministic embedding adapter for unit and integration tests."""

    def __init__(self, dimension: int = BGE_M3_DIMENSION) -> None:
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, texts: List[str]) -> List[List[float]]:
        return [[0.0] * self._dimension for _ in texts]


class ErrorEmbeddingAdapter:
    """Always raises RuntimeError for testing failure paths."""

    def __init__(self, dimension: int = BGE_M3_DIMENSION) -> None:
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, texts: List[str]) -> List[List[float]]:
        raise RuntimeError("Simulated embedding failure for testing.")


# ---------------------------------------------------------------------------
# Factory Function
# ---------------------------------------------------------------------------

def get_embedding_adapter() -> EmbeddingAdapter:
    """Return the configured embedding adapter based on app settings.

    Reads ``EMBEDDING_PROVIDER`` from settings:
    - ``"cloudflare"`` (default) → :class:`CloudflareBGEEmbeddingAdapter`
    - ``"huggingface_api"`` (default) → :class:`HuggingFaceAPIEmbeddingAdapter`
    - ``"local"`` → :class:`BGEM3EmbeddingAdapter`
    """
    from app.core.config import settings

    provider = getattr(settings, "EMBEDDING_PROVIDER", "huggingface_api").lower()
    model_name = getattr(settings, "EMBEDDING_MODEL_NAME", "BAAI/bge-m3")
    hf_token = getattr(settings, "HUGGINGFACE_HUB_TOKEN", None)

    if provider == "cloudflare":
        adapter = CloudflareBGEEmbeddingAdapter(
            model_name=model_name,
            account_id=getattr(settings, "CLOUDFLARE_ACCOUNT_ID", None),
            api_token=getattr(settings, "CLOUDFLARE_API_TOKEN", None),
            base_url=getattr(settings, "CLOUDFLARE_AI_BASE_URL", None),
        )
        settings.require_embedding_route_allowed(
            provider, model_name, endpoint_url=adapter._base_url
        )
        return adapter

    if provider == "local":
        device = getattr(settings, "EMBEDDING_DEVICE", "cpu")
        return BGEM3EmbeddingAdapter(model_name=model_name, hf_token=hf_token, device=device)

    if provider != "huggingface_api":
        raise ValueError(
            f"Unsupported EMBEDDING_PROVIDER '{provider}'. "
            "Use 'cloudflare', 'huggingface_api', or 'local'."
        )

    api_url = getattr(settings, "EMBEDDING_API_URL", None)
    adapter = HuggingFaceAPIEmbeddingAdapter(
        model_name=model_name,
        hf_token=hf_token,
        api_url=api_url,
    )
    settings.require_embedding_route_allowed(
        provider, model_name, endpoint_url=adapter._api_url
    )
    return adapter
