import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base


class ToolDefinition(Base):
    """Registered capability usable by AI agents via Tool Gateway."""

    __tablename__ = "tool_definitions"

    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tool_type: Mapped[str] = mapped_column(String(100), nullable=False, default="DETERMINISTIC")
    input_schema: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    output_schema: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    permission_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ToolExecution(Base):
    """Auditable log of every tool execution invoked by agents or system."""

    __tablename__ = "tool_executions"

    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    case_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    tool_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tool_definitions.id", ondelete="CASCADE"),
        nullable=False,
    )
    requested_by_type: Mapped[str] = mapped_column(String(50), nullable=False, default="AGENT")
    requested_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    input_data: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    output_data: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="SUCCESS")
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class Integration(Base):
    """External organizational system connection (ERP, Finance, Logistics)."""

    __tablename__ = "integrations"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    integration_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="ACTIVE")

    configs: Mapped[List["IntegrationConfig"]] = relationship("IntegrationConfig", back_populates="integration", cascade="all, delete-orphan")


class IntegrationConfig(Base):
    """Metadata and credential references for an integration adapter."""

    __tablename__ = "integration_configs"

    integration_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("integrations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    config_metadata: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    secret_reference: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    integration: Mapped["Integration"] = relationship("Integration", back_populates="configs")
