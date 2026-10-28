"""Unit tests for TextChunker (Phase 9 Knowledge / RAG pipeline)."""
import pytest
from app.domain.knowledge.chunker import TextChunker, ChunkResult


def test_chunker_basic_splitting():
    text = "Sentence one. Sentence two. Sentence three. Sentence four."
    chunker = TextChunker(chunk_size=30, overlap=5, min_chunk_length=5)
    chunks = chunker.chunk(text)
    assert len(chunks) > 0
    for chunk in chunks:
        assert isinstance(chunk, ChunkResult)
        assert len(chunk.content) > 0


def test_chunker_empty_input():
    chunker = TextChunker()
    assert chunker.chunk("") == []
    assert chunker.chunk("   ") == []


def test_chunker_arabic_text():
    arabic_text = "هذا هو النص الأول. النص الثاني يحتوي على تفاصيل أكثر. النص الثالث يكتمل هنا."
    chunker = TextChunker(chunk_size=40, overlap=10, min_chunk_length=5)
    chunks = chunker.chunk(arabic_text)
    assert len(chunks) >= 1
    assert any("النص" in c.content for c in chunks)


def test_chunker_overlap():
    text = "First long paragraph sentence here. Second long paragraph sentence here. Third long paragraph sentence here."
    chunker = TextChunker(chunk_size=40, overlap=15, min_chunk_length=5)
    chunks = chunker.chunk(text)
    assert len(chunks) >= 2
    for i in range(len(chunks)):
        assert chunks[i].chunk_index == i
