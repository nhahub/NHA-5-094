from __future__ import annotations
import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base

if TYPE_CHECKING:
    from app.domain.rules.models import BusinessRule, CalculationDefinition
    from app.domain.verifications.models import VerificationDefinition
    from app.domain.workflows.models import WorkflowStage, WorkflowTransition


class ProcessStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    ARCHIVED = "ARCHIVED"


class ProcessVersionStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


class RequirementType(str, enum.Enum):
    DOCUMENT = "DOCUMENT"
    DATA = "DATA"
    VERIFICATION = "VERIFICATION"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    APPROVAL = "APPROVAL"


class Process(Base):
    """Business process definition (e.g. Import Order Verification, Tax Check)."""

    __tablename__ = "processes"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default=ProcessStatus.ACTIVE.value)

    versions: Mapped[List["ProcessVersion"]] = relationship("ProcessVersion", back_populates="process", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_processes_org_code"),
    )


class ProcessVersion(Base):
    """Immutable versioned snapshot of a process configuration."""

    __tablename__ = "process_versions"

    process_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("processes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default=ProcessVersionStatus.DRAFT.value)
    configuration: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    process: Mapped["Process"] = relationship("Process", back_populates="versions")
    stages: Mapped[List["WorkflowStage"]] = relationship("WorkflowStage", back_populates="process_version", cascade="all, delete-orphan")
    transitions: Mapped[List["WorkflowTransition"]] = relationship("WorkflowTransition", back_populates="process_version", cascade="all, delete-orphan")
    requirements: Mapped[List["Requirement"]] = relationship("Requirement", back_populates="process_version", cascade="all, delete-orphan")
    verifications: Mapped[List["VerificationDefinition"]] = relationship("VerificationDefinition", back_populates="process_version", cascade="all, delete-orphan")
    rules: Mapped[List["BusinessRule"]] = relationship("BusinessRule", back_populates="process_version", cascade="all, delete-orphan")
    calculations: Mapped[List["CalculationDefinition"]] = relationship("CalculationDefinition", back_populates="process_version", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("process_id", "version_number", name="uq_process_versions_proc_version"),
    )


class Requirement(Base):
    """Prerequisites that must be satisfied before stage entry/exit or process completion."""

    __tablename__ = "requirements"

    process_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("process_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stage_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_stages.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False, default=RequirementType.DOCUMENT.value)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    configuration: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    process_version: Mapped["ProcessVersion"] = relationship("ProcessVersion", back_populates="requirements")
