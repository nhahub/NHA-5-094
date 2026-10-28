import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict
from app.domain.verifications.models import VerificationStatus


class VerificationRuleLink(BaseModel):
    rule_id: uuid.UUID
    execution_order: int = 0
    required: bool = True


class VerificationDefinitionBase(BaseModel):
    name: str
    code: str
    description: Optional[str] = None
    stage_id: Optional[uuid.UUID] = None
    result_policy: Dict[str, Any] = {}


class VerificationDefinitionCreate(VerificationDefinitionBase):
    process_version_id: uuid.UUID
    rules: List[VerificationRuleLink] = []


class VerificationDefinitionRead(VerificationDefinitionBase):
    id: uuid.UUID
    process_version_id: uuid.UUID
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class RuleExecutionRead(BaseModel):
    id: uuid.UUID
    rule_id: uuid.UUID
    input_data: Dict[str, Any]
    result: str
    output_data: Dict[str, Any]
    executed_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CalculationExecutionRead(BaseModel):
    id: uuid.UUID
    calculation_id: uuid.UUID
    input_data: Dict[str, Any]
    output_data: Dict[str, Any]
    status: str
    executed_at: datetime

    model_config = ConfigDict(from_attributes=True)


class VerificationResultRead(BaseModel):
    id: uuid.UUID
    result: str
    summary: Optional[str] = None
    confidence: Optional[float] = None
    reason: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class EvidenceItemRead(BaseModel):
    id: uuid.UUID
    source_type: str
    source_id: Optional[uuid.UUID] = None
    field_reference: Optional[str] = None
    value_snapshot: Optional[Dict[str, Any]] = None
    page_number: Optional[int] = None
    location: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)


class EvidenceRead(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    verification_execution_id: Optional[uuid.UUID] = None
    evidence_type: str
    description: Optional[str] = None
    items: List[EvidenceItemRead] = []

    model_config = ConfigDict(from_attributes=True)


class VerificationExecutionRead(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    verification_id: uuid.UUID
    status: VerificationStatus
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    executed_by_type: str
    executed_by_id: Optional[uuid.UUID] = None
    inputs: Dict[str, Any]
    results: List[VerificationResultRead] = []
    rule_executions: List[RuleExecutionRead] = []
    calculation_executions: List[CalculationExecutionRead] = []
    evidence: List[EvidenceRead] = []
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class VerificationRunRequest(BaseModel):
    case_id: uuid.UUID
    verification_id: uuid.UUID
    inputs: Dict[str, Any] = {}
    tool_execution_ids: List[uuid.UUID] = []
    actor_type: str = "SYSTEM"
    actor_id: Optional[uuid.UUID] = None
