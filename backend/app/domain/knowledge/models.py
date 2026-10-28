import enum
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Enum, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base


class KnowledgeDocumentStatus(str, enum.Enum):
    PENDING = "PENDING"
    INGESTING = "INGESTING"
    INGESTED = "INGESTED"
    FAILED = "FAILED"


class KnowledgeSource(Base):
    """Source container for SOPs, compliance guidelines, and policy documents.

    An organisation can have many KnowledgeSources, each containing many
    KnowledgeDocuments.  All sources are strictly scoped to one organisation.
    """

    __tablename__ = "knowledge_sources"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(
        String(100), nullable=False, default="POLICY"
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="ACTIVE")

    documents: Mapped[List["KnowledgeDocument"]] = relationship(
        "KnowledgeDocument",
        back_populates="knowledge_source",
        cascade="all, delete-orphan",
    )


class KnowledgeDocument(Base):
    """An ingested policy or guideline document.

    After upload the document moves through the ingestion pipeline:
    PENDING → INGESTING → INGESTED (or FAILED).
    """

    __tablename__ = "knowledge_documents"

    knowledge_source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    document_version: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )
    storage_reference: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    # Ingestion lifecycle — added in migration 0006
    status: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default=KnowledgeDocumentStatus.PENDING.value,
    )
    chunk_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ingested_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    knowledge_source: Mapped["KnowledgeSource"] = relationship(
        "KnowledgeSource", back_populates="documents"
    )
    chunks: Mapped[List["KnowledgeChunk"]] = relationship(
        "KnowledgeChunk",
        back_populates="knowledge_document",
        cascade="all, delete-orphan",
    )


class KnowledgeChunk(Base):
    """A text chunk with its BAAI/bge-m3 1024-dim embedding for semantic search.

    organisation_id is denormalised here for a fast single-table WHERE filter
    before the pgvector HNSW cosine ANN query — avoiding a two-table JOIN on
    every similarity search.
    """

    __tablename__ = "knowledge_chunks"

    knowledge_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Denormalised tenant isolation — added in migration 0006
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Vector(1024) — BAAI/bge-m3 native output dimension
    embedding: Mapped[Optional[List[float]]] = mapped_column(
        Vector(1024), nullable=True
    )
    chunk_metadata: Mapped[Dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )

    knowledge_document: Mapped["KnowledgeDocument"] = relationship(
        "KnowledgeDocument", back_populates="chunks"
    )
