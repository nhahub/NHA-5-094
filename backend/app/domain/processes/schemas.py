import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict

from app.domain.processes.models import (
    ProcessStatus,
    ProcessVersionStatus,
    RequirementType,
)
from app.domain.rules.models import RuleSeverity


# --- Process Schemas ---
class ProcessBase(BaseModel):
    name: str
    code: str
    description: Optional[str] = None
    status: ProcessStatus = ProcessStatus.ACTIVE


class ProcessCreate(ProcessBase):
    pass


class ProcessRead(ProcessBase):
    id: uuid.UUID
    organization_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CustomerProcessOptionRead(BaseModel):
    process_id: uuid.UUID
    process_version_id: uuid.UUID
    name: str
    description: Optional[str] = None


# --- Process Version Schemas ---
class ProcessVersionBase(BaseModel):
    configuration: Dict[str, Any] = {}


class ProcessVersionCreate(ProcessVersionBase):
    pass


class RequirementBase(BaseModel):
    name: str
    code: str
    type: RequirementType = RequirementType.DOCUMENT
    description: Optional[str] = None
    required: bool = True
    configuration: Dict[str, Any] = {}
    stage_id: Optional[uuid.UUID] = None


class RequirementCreate(RequirementBase):
    pass


class RequirementRead(RequirementBase):
    id: uuid.UUID
    process_version_id: uuid.UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WorkflowStageCreate(BaseModel):
    name: str
    code: str
    description: Optional[str] = None
    stage_order: int = 0
    is_initial: bool = False
    is_terminal: bool = False
    config: Dict[str, Any] = {}


class WorkflowStageRead(WorkflowStageCreate):
    id: uuid.UUID
    process_version_id: uuid.UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WorkflowTransitionCreate(BaseModel):
    from_stage_id: uuid.UUID
    to_stage_id: uuid.UUID
    name: str
    code: Optional[str] = None
    condition_config: Dict[str, Any] = {}
    requires_approval: bool = False
    required_role: Optional[str] = None


class WorkflowTransitionRead(WorkflowTransitionCreate):
    id: uuid.UUID
    process_version_id: uuid.UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class VerificationDefinitionCreate(BaseModel):
    name: str
    code: str
    description: Optional[str] = None
    stage_id: Optional[uuid.UUID] = None
    result_policy: Dict[str, Any] = {}


class VerificationDefinitionRead(VerificationDefinitionCreate):
    id: uuid.UUID
    process_version_id: uuid.UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BusinessRuleCreate(BaseModel):
    name: str
    code: str
    description: Optional[str] = None
    rule_type: str = "EQUALITY"
    expression: Dict[str, Any] = {}
    severity: RuleSeverity = RuleSeverity.ERROR


class BusinessRuleRead(BusinessRuleCreate):
    id: uuid.UUID
    process_version_id: uuid.UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProcessVersionRead(BaseModel):
    id: uuid.UUID
    process_id: uuid.UUID
    version_number: int
    status: ProcessVersionStatus
    configuration: Dict[str, Any]
    created_by: Optional[uuid.UUID] = None
    published_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProcessVersionDetailRead(ProcessVersionRead):
    stages: List[WorkflowStageRead] = []
    transitions: List[WorkflowTransitionRead] = []
    requirements: List[RequirementRead] = []
    verifications: List[VerificationDefinitionRead] = []
    rules: List[BusinessRuleRead] = []
