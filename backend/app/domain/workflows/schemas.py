import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict


class WorkflowStageBase(BaseModel):
    name: str
    code: str
    description: Optional[str] = None
    stage_order: int = 0
    is_initial: bool = False
    is_terminal: bool = False
    config: Dict[str, Any] = {}


class WorkflowStageCreate(WorkflowStageBase):
    process_version_id: uuid.UUID


class WorkflowStageRead(WorkflowStageBase):
    id: uuid.UUID
    process_version_id: uuid.UUID
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class WorkflowTransitionBase(BaseModel):
    name: str
    code: Optional[str] = None
    condition_config: Dict[str, Any] = {}
    requires_approval: bool = False
    required_role: Optional[str] = None


class WorkflowTransitionCreate(WorkflowTransitionBase):
    process_version_id: uuid.UUID
    from_stage_id: uuid.UUID
    to_stage_id: uuid.UUID


class WorkflowTransitionRead(WorkflowTransitionBase):
    id: uuid.UUID
    process_version_id: uuid.UUID
    from_stage_id: uuid.UUID
    to_stage_id: uuid.UUID
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class TransitionViolation(BaseModel):
    code: str
    message: str
    requirement_id: Optional[uuid.UUID] = None
    requirement_type: Optional[str] = None


class TransitionRequest(BaseModel):
    case_id: uuid.UUID
    to_stage_id: uuid.UUID
    from_stage_id: Optional[uuid.UUID] = None
    actor_id: Optional[uuid.UUID] = None
    actor_role: Optional[str] = None
    actor_type: str = "USER"
    reason: Optional[str] = None
    metadata: Dict[str, Any] = {}


class TransitionResult(BaseModel):
    allowed: bool
    reason: str
    case_id: uuid.UUID
    previous_stage_id: Optional[uuid.UUID] = None
    current_stage_id: Optional[uuid.UUID] = None
    case_status: Optional[str] = None
    transition_id: Optional[uuid.UUID] = None
    history_id: Optional[uuid.UUID] = None
    violations: List[TransitionViolation] = []
