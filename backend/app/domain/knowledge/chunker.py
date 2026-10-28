"""Text chunking utilities for the Knowledge / RAG pipeline.

Splits raw document text into overlapping, sentence-aware chunks for
embedding.  Supports Arabic and Latin punctuation boundaries.

No third-party dependencies — pure Python + ``re``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List


# Sentence-ending punctuation for both Latin and Arabic scripts
_SENTENCE_END = re.compile(r"(?<=[.!?؟؛\n])\s+")


@dataclass
class ChunkResult:
    """A single text chunk produced by :class:`TextChunker`."""

    chunk_index: int
    content: str
    char_start: int
    char_end: int
    metadata: dict = field(default_factory=dict)


class TextChunker:
    """Sentence-aware, fixed-size text chunker with configurable overlap.

    Algorithm
    ---------
    1.  Split the input text on sentence boundaries (. ! ? ؟ ؛ and blank
        lines) so chunks always end at a natural sentence end when possible.
    2.  Accumulate sentences until the running length would exceed
        ``chunk_size`` characters.
    3.  Start the next chunk with ``overlap`` characters from the tail of the
        previous chunk so context is preserved across boundaries.
    4.  Discard any trailing micro-chunks shorter than ``min_chunk_length``.

    Parameters
    ----------
    chunk_size:
        Target maximum character length per chunk (default 800).
        Larger values → richer context per embedding; smaller values →
        more granular retrieval.
    overlap:
        Characters of overlap between consecutive chunks (default 100).
    min_chunk_length:
        Chunks shorter than this are discarded (default 50).
    """

    def __init__(
        self,
        chunk_size: int = 800,
        overlap: int = 100,
        min_chunk_length: int = 50,
    ) -> None:
        if chunk_size < 1:
            raise ValueError("chunk_size must be >= 1")
        if overlap < 0:
            raise ValueError("overlap must be >= 0")
        if overlap >= chunk_size:
            raise ValueError("overlap must be smaller than chunk_size")
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.min_chunk_length = min_chunk_length

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def chunk(self, text: str) -> List[ChunkResult]:
        """Split *text* into overlapping chunks and return a list of
        :class:`ChunkResult` objects.

        Returns an empty list for empty or whitespace-only input.
        """
        text = text.strip()
        if not text:
            return []

        sentences = self._split_sentences(text)
        raw_chunks = self._build_chunks(sentences)
        return self._to_results(raw_chunks, text)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _split_sentences(self, text: str) -> List[str]:
        """Split text on sentence boundaries, preserving each sentence."""
        parts = _SENTENCE_END.split(text)
        # Re-attach any trailing punctuation stripped by the regex
        return [p.strip() for p in parts if p.strip()]

    def _build_chunks(self, sentences: List[str]) -> List[str]:
        """Accumulate sentences into chunks, honouring chunk_size and
        overlap constraints."""
        chunks: List[str] = []
        current_parts: List[str] = []
        current_len = 0

        for sentence in sentences:
            sentence_len = len(sentence)

            # If adding this sentence would exceed chunk_size, flush
            if current_parts and current_len + sentence_len + 1 > self.chunk_size:
                chunk_text = " ".join(current_parts)
                chunks.append(chunk_text)

                # Start next chunk from the tail of the current chunk
                # (overlap) plus the current sentence
                tail = chunk_text[-self.overlap:] if self.overlap > 0 else ""
                if tail:
                    current_parts = [tail, sentence]
                    current_len = len(tail) + sentence_len + 1
                else:
                    current_parts = [sentence]
                    current_len = sentence_len
            else:
                current_parts.append(sentence)
                current_len += sentence_len + 1  # +1 for the space

        # Flush remaining sentences
        if current_parts:
            chunk_text = " ".join(current_parts)
            chunks.append(chunk_text)

        return chunks

    def _to_results(self, raw_chunks: List[str], original_text: str) -> List[ChunkResult]:
        """Convert raw chunk strings into :class:`ChunkResult` objects,
        dropping micro-chunks and computing character offsets."""
        results: List[ChunkResult] = []
        search_start = 0
        idx = 0

        for chunk_text in raw_chunks:
            stripped = chunk_text.strip()
            if len(stripped) < self.min_chunk_length:
                continue

            # Find the approximate character position in the original text
            pos = original_text.find(stripped[:30], search_start)
            if pos == -1:
                pos = search_start  # fallback

            char_end = min(pos + len(stripped), len(original_text))
            results.append(
                ChunkResult(
                    chunk_index=idx,
                    content=stripped,
                    char_start=pos,
                    char_end=char_end,
                )
            )
            search_start = max(0, char_end - self.overlap)
            idx += 1

        return results
