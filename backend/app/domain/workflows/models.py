from __future__ import annotations
import uuid
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from sqlalchemy import Boolean, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base

if TYPE_CHECKING:
    from app.domain.processes.models import ProcessVersion


class WorkflowStage(Base):
    """Discrete state/stage in a process lifecycle."""

    __tablename__ = "workflow_stages"

    process_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("process_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    stage_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_initial: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_terminal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    config: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    process_version: Mapped["ProcessVersion"] = relationship("ProcessVersion", back_populates="stages")


class WorkflowTransition(Base):
    """Deterministic, validated route between workflow stages."""

    __tablename__ = "workflow_transitions"

    process_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("process_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    from_stage_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_stages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    to_stage_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_stages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    condition_config: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    required_role: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    process_version: Mapped["ProcessVersion"] = relationship("ProcessVersion", back_populates="transitions")
