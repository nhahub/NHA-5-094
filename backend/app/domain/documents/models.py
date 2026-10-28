from __future__ import annotations
import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base

if TYPE_CHECKING:
    from app.domain.cases.models import Case
    from app.domain.verifications.models import VerificationExecution


class DocumentStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"


# Backward compatibility alias
DocumentProcessingStatus = DocumentStatus


class Document(Base):
    """Top-level document record uploaded to a Case."""

    __tablename__ = "documents"

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default=DocumentStatus.PENDING.value)
    uploaded_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    storage_reference: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    case: Mapped["Case"] = relationship("Case", back_populates="documents")
    versions: Mapped[List["DocumentVersion"]] = relationship("DocumentVersion", back_populates="document", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_documents_case_type", "case_id", "document_type"),
    )


class DocumentVersion(Base):
    """Immutable versioned file binary reference for a document."""

    __tablename__ = "document_versions"

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    storage_reference: Mapped[str] = mapped_column(Text, nullable=False)
    file_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    mime_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    file_size: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    uploaded_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    document: Mapped["Document"] = relationship("Document", back_populates="versions")
    extracted_fields: Mapped[List["ExtractedField"]] = relationship("ExtractedField", back_populates="document_version", cascade="all, delete-orphan")
    processing_runs: Mapped[List["DocumentProcessingRun"]] = relationship(
        "DocumentProcessingRun", back_populates="document_version", cascade="all, delete-orphan"
    )


class DocumentRunStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    FAILED = "FAILED"


class DocumentProcessingRun(Base):
    """Immutable processing attempt and provenance for one document version."""

    __tablename__ = "document_processing_runs"

    document_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    run_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default=DocumentRunStatus.QUEUED.value)
    parser_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    parser_version: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    ocr_engine: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    classifier_model: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    predicted_document_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    classification_confidence: Mapped[Optional[float]] = mapped_column(Numeric(5, 4), nullable=True)
    extractor_model: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    extraction_schema_version: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    configuration_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    normalized_content_reference: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    review_reasons: Mapped[List[str]] = mapped_column(JSON, nullable=False, default=list)
    review_task_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    error_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    safe_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    document_version: Mapped["DocumentVersion"] = relationship(
        "DocumentVersion", back_populates="processing_runs"
    )
    extracted_fields: Mapped[List["ExtractedField"]] = relationship(
        "ExtractedField", back_populates="processing_run"
    )

    __table_args__ = (
        UniqueConstraint("document_version_id", "run_number", name="uq_doc_processing_version_run"),
        Index("idx_doc_processing_status", "status"),
    )


class ExtractedField(Base):
    """Structured field extracted from a document version by Document Agent / OCR."""

    __tablename__ = "extracted_fields"

    document_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    field_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    field_value: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Numeric(5, 4), nullable=True)
    page_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    bounding_box: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    extraction_method: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    processing_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_processing_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_locator: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    document_version: Mapped["DocumentVersion"] = relationship("DocumentVersion", back_populates="extracted_fields")
    processing_run: Mapped[Optional["DocumentProcessingRun"]] = relationship(
        "DocumentProcessingRun", back_populates="extracted_fields"
    )


class Evidence(Base):
    """A collection of supporting facts, citations and locators for decisions."""

    __tablename__ = "evidence"

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    verification_execution_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("verification_executions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    evidence_type: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    case: Mapped["Case"] = relationship("Case", back_populates="evidence")
    verification_execution: Mapped[Optional["VerificationExecution"]] = relationship(
        "VerificationExecution", back_populates="evidence"
    )
    items: Mapped[List["EvidenceItem"]] = relationship("EvidenceItem", back_populates="evidence", cascade="all, delete-orphan")


class EvidenceItem(Base):
    """Specific line item, bounding box, or system snapshot supporting an evidence bundle."""

    __tablename__ = "evidence_items"

    evidence_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evidence.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_type: Mapped[str] = mapped_column(String(100), nullable=False)
    source_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    field_reference: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    value_snapshot: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    page_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    location: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    evidence: Mapped["Evidence"] = relationship("Evidence", back_populates="items")
