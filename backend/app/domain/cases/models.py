from __future__ import annotations
import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from sqlalchemy import DateTime, ForeignKey, Index, JSON, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base

if TYPE_CHECKING:
    from app.domain.approvals.models import Approval
    from app.domain.documents.models import Document, Evidence
    from app.domain.tasks.models import Task
    from app.domain.verifications.models import VerificationExecution


class CaseStatus(str, enum.Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    PENDING_REVIEW = "PENDING_REVIEW"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class CasePriority(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"


class ParticipantType(str, enum.Enum):
    CUSTOMER = "CUSTOMER"
    ASSIGNEE = "ASSIGNEE"
    REVIEWER = "REVIEWER"
    OBSERVER = "OBSERVER"


class Case(Base):
    """A running execution instance of a Process bound to an immutable ProcessVersion."""

    __tablename__ = "cases"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    process_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("processes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    process_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("process_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    case_number: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default=CaseStatus.OPEN.value, index=True)
    current_stage_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_stages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    case_metadata: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    # Relationships
    participants: Mapped[List["CaseParticipant"]] = relationship("CaseParticipant", back_populates="case", cascade="all, delete-orphan")
    case_data: Mapped[List["CaseData"]] = relationship("CaseData", back_populates="case", cascade="all, delete-orphan")
    stage_history: Mapped[List["CaseStageHistory"]] = relationship("CaseStageHistory", back_populates="case", cascade="all, delete-orphan")
    documents: Mapped[List["Document"]] = relationship("Document", back_populates="case", cascade="all, delete-orphan")
    evidence: Mapped[List["Evidence"]] = relationship("Evidence", back_populates="case", cascade="all, delete-orphan")
    verifications: Mapped[List["VerificationExecution"]] = relationship("VerificationExecution", back_populates="case", cascade="all, delete-orphan")
    tasks: Mapped[List["Task"]] = relationship("Task", back_populates="case", cascade="all, delete-orphan")
    approvals: Mapped[List["Approval"]] = relationship("Approval", back_populates="case", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_cases_org_status", "organization_id", "status"),
        Index("idx_cases_org_stage", "organization_id", "current_stage_id"),
    )


class CaseParticipant(Base):
    """People or actors involved in a specific case."""

    __tablename__ = "case_participants"

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    participant_type: Mapped[str] = mapped_column(String(50), nullable=False, default=ParticipantType.CUSTOMER.value)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    external_reference: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    case: Mapped["Case"] = relationship("Case", back_populates="participants")


class CaseData(Base):
    """Dynamic key-value or extracted structured facts accumulated for a case."""

    __tablename__ = "case_data"

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    field_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    field_value: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    source_type: Mapped[str] = mapped_column(String(100), nullable=False, default="DOCUMENT")
    source_reference: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Numeric(5, 4), nullable=True)

    case: Mapped["Case"] = relationship("Case", back_populates="case_data")


class CaseStageHistory(Base):
    """Direct, auditable business state stage transitions history."""

    __tablename__ = "case_stage_history"

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    from_stage_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_stages.id", ondelete="SET NULL"),
        nullable=True,
    )
    to_stage_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_stages.id", ondelete="CASCADE"),
        nullable=False,
    )
    transition_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_transitions.id", ondelete="SET NULL"),
        nullable=True,
    )
    triggered_by_type: Mapped[str] = mapped_column(String(50), nullable=False, default="SYSTEM")
    triggered_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    case: Mapped["Case"] = relationship("Case", back_populates="stage_history")
