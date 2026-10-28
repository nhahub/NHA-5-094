from __future__ import annotations
import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base

if TYPE_CHECKING:
    from app.domain.cases.models import Case
    from app.domain.processes.models import ProcessVersion
    from app.domain.rules.models import BusinessRule, CalculationDefinition
    from app.domain.documents.models import Evidence


class VerificationStatus(str, enum.Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    REVIEW = "REVIEW"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    INCONCLUSIVE = "INCONCLUSIVE"


class VerificationDefinition(Base):
    """Specification of a verification check required in a business process."""

    __tablename__ = "verification_definitions"

    process_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("process_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stage_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_stages.id", ondelete="SET NULL"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    result_policy: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    process_version: Mapped["ProcessVersion"] = relationship("ProcessVersion", back_populates="verifications")
    verification_rules: Mapped[List["VerificationRule"]] = relationship("VerificationRule", back_populates="verification", cascade="all, delete-orphan")


class VerificationRule(Base):
    """Associates business rules with a verification check."""

    __tablename__ = "verification_rules"

    verification_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("verification_definitions.id", ondelete="CASCADE"),
        nullable=False,
        primary_key=True,
    )
    rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_rules.id", ondelete="CASCADE"),
        nullable=False,
        primary_key=True,
    )
    execution_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    verification: Mapped["VerificationDefinition"] = relationship("VerificationDefinition", back_populates="verification_rules")
    rule: Mapped["BusinessRule"] = relationship("BusinessRule", back_populates="verification_rules")


class VerificationExecution(Base):
    """Runtime execution instance of a verification definition on a Case."""

    __tablename__ = "verification_executions"

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    verification_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("verification_definitions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False, default=VerificationStatus.INCONCLUSIVE.value)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    executed_by_type: Mapped[str] = mapped_column(String(50), nullable=False, default="SYSTEM")
    executed_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    inputs: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    case: Mapped["Case"] = relationship("Case", back_populates="verifications")
    results: Mapped[List["VerificationResult"]] = relationship("VerificationResult", back_populates="verification_execution", cascade="all, delete-orphan")
    rule_executions: Mapped[List["RuleExecution"]] = relationship("RuleExecution", back_populates="verification_execution", cascade="all, delete-orphan")
    calculation_executions: Mapped[List["CalculationExecution"]] = relationship("CalculationExecution", back_populates="verification_execution", cascade="all, delete-orphan")
    evidence: Mapped[List["Evidence"]] = relationship(
        "Evidence", back_populates="verification_execution", cascade="all, delete-orphan"
    )


class VerificationResult(Base):
    """Outcome and summary of a completed verification execution."""

    __tablename__ = "verification_results"

    verification_execution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("verification_executions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    result: Mapped[str] = mapped_column(String(50), nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Numeric(5, 4), nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    verification_execution: Mapped["VerificationExecution"] = relationship("VerificationExecution", back_populates="results")


class RuleExecution(Base):
    """Detailed trace of an individual rule check within a verification run."""

    __tablename__ = "rule_executions"

    verification_execution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("verification_executions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_rules.id", ondelete="CASCADE"),
        nullable=False,
    )
    input_data: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    result: Mapped[str] = mapped_column(String(50), nullable=False)
    output_data: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    execution_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    verification_execution: Mapped["VerificationExecution"] = relationship("VerificationExecution", back_populates="rule_executions")


class CalculationExecution(Base):
    """Detailed trace of an individual calculation within a verification run."""

    __tablename__ = "calculation_executions"

    verification_execution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("verification_executions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    calculation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("calculation_definitions.id", ondelete="CASCADE"),
        nullable=False,
    )
    input_data: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    output_data: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    execution_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    verification_execution: Mapped["VerificationExecution"] = relationship("VerificationExecution", back_populates="calculation_executions")
