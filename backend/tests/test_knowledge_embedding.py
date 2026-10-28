"""Unit tests for EmbeddingAdapters (Phase 9 Knowledge / RAG pipeline)."""
import pytest
from app.infrastructure.llm.embedding import (
    FakeEmbeddingAdapter,
    ErrorEmbeddingAdapter,
    HuggingFaceAPIEmbeddingAdapter,
    get_embedding_adapter,
    BGE_M3_DIMENSION,
)


def test_fake_embedding_adapter():
    adapter = FakeEmbeddingAdapter()
    assert adapter.dimension == 1024
    vecs = adapter.embed(["hello", "world"])
    assert len(vecs) == 2
    assert len(vecs[0]) == 1024
    assert vecs[0] == [0.0] * 1024


def test_fake_embedding_empty_input():
    adapter = FakeEmbeddingAdapter()
    assert adapter.embed([]) == []


def test_error_embedding_adapter():
    adapter = ErrorEmbeddingAdapter()
    with pytest.raises(RuntimeError, match="Simulated embedding failure"):
        adapter.embed(["test"])


def test_factory_returns_configured_adapter():
    adapter = get_embedding_adapter()
    assert adapter.dimension == BGE_M3_DIMENSION
    assert hasattr(adapter, "embed")
