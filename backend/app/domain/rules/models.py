from __future__ import annotations
import enum
import uuid
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from sqlalchemy import ForeignKey, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base

if TYPE_CHECKING:
    from app.domain.processes.models import ProcessVersion
    from app.domain.verifications.models import VerificationRule


class RuleSeverity(str, enum.Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class BusinessRule(Base):
    """Declarative, deterministic business rule evaluated against extracted case data."""

    __tablename__ = "business_rules"

    process_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("process_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rule_type: Mapped[str] = mapped_column(String(100), nullable=False, default="EQUALITY")
    expression: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    severity: Mapped[str] = mapped_column(String(50), nullable=False, default=RuleSeverity.ERROR.value)

    process_version: Mapped["ProcessVersion"] = relationship("ProcessVersion", back_populates="rules")
    verification_rules: Mapped[List["VerificationRule"]] = relationship("VerificationRule", back_populates="rule", cascade="all, delete-orphan")


class CalculationDefinition(Base):
    """Deterministic mathematical formula definition (e.g. total = qty * unit_price)."""

    __tablename__ = "calculation_definitions"

    process_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("process_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    calculation_type: Mapped[str] = mapped_column(String(100), nullable=False, default="FORMULA")
    configuration: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    process_version: Mapped["ProcessVersion"] = relationship("ProcessVersion", back_populates="calculations")
