"""Pydantic schemas for the Knowledge / RAG domain (Phase 9).

These schemas match the actual SQLAlchemy ORM models in ``models.py``.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# KnowledgeSource schemas
# ---------------------------------------------------------------------------

class KnowledgeSourceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    source_type: str = Field(default="POLICY", max_length=100)
    description: Optional[str] = None


class KnowledgeSourceUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    status: Optional[str] = Field(default=None, max_length=50)


class KnowledgeSourceRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    source_type: str
    description: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class KnowledgeDocumentCreate(BaseModel):
    knowledge_source_id: uuid.UUID
    title: str = Field(..., min_length=1, max_length=255)
    document_version: Optional[str] = Field(default="1.0", max_length=50)
    storage_reference: Optional[str] = None
    content_hash: Optional[str] = None


class KnowledgeDocumentRead(BaseModel):
    id: uuid.UUID
    knowledge_source_id: uuid.UUID
    title: str
    document_version: Optional[str]
    storage_reference: Optional[str]
    content_hash: Optional[str]
    status: str
    chunk_count: Optional[int]
    ingested_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Semantic Search schemas
# ---------------------------------------------------------------------------

class KnowledgeSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    source_type: Optional[str] = None
    source_ids: Optional[List[uuid.UUID]] = None
    top_k: int = Field(default=5, ge=1, le=20)


# Backward compatibility alias
KnowledgeSearchQuery = KnowledgeSearchRequest


class KnowledgeSearchResult(BaseModel):
    chunk_id: uuid.UUID
    knowledge_document_id: uuid.UUID
    knowledge_source_id: uuid.UUID
    document_title: str
    source_name: str
    source_type: str
    chunk_index: int
    content: str
    similarity_score: float
    metadata: Dict[str, Any] = Field(default_factory=dict)


class KnowledgeSearchResponse(BaseModel):
    query: str
    top_k: int
    results: List[KnowledgeSearchResult]
