"""Public request and response schemas for the Tool Gateway."""
from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class ToolDefinition(BaseModel):
    """A tool contract exposed to an authorized agent or process."""

    name: str
    description: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    required_permission: str
    allowed_agents: list[str] = Field(default_factory=list)


class ToolExecutionRequest(BaseModel):
    tool_name: str
    case_id: uuid.UUID
    arguments: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class ToolExecutionResult(BaseModel):
    tool_name: str
    case_id: uuid.UUID
    success: bool
    output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    status: str = "SUCCESS"
    execution_id: Optional[uuid.UUID] = None
    http_status_code: int = 200

    model_config = ConfigDict(from_attributes=True)
