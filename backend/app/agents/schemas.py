import uuid
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


class AgentProposal(BaseModel):
    agent_name: str
    case_id: uuid.UUID
    proposed_action: str
    suggested_target_stage_id: Optional[uuid.UUID] = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    rationale: str
    evidence_references: List[str] = Field(default_factory=list)
    payload: Dict[str, Any] = Field(default_factory=dict)


class DocumentAgentRunRequest(BaseModel):
    case_id: uuid.UUID
    document_id: uuid.UUID
    document_version_id: Optional[uuid.UUID] = None
    user_guidance: Optional[str] = None


class DocumentAgentResult(BaseModel):
    case_id: uuid.UUID
    document_id: uuid.UUID
    document_version_id: uuid.UUID
    predicted_document_type: str
    classification_confidence: float
    extracted_fields: Dict[str, Any] = Field(default_factory=dict)
    review_required: bool = False
    review_reasons: List[str] = Field(default_factory=list)
    review_task_id: Optional[uuid.UUID] = None
    proposals: List[AgentProposal] = Field(default_factory=list)
    execution_id: Optional[uuid.UUID] = None


class AgentRunRequest(BaseModel):
    case_id: uuid.UUID
    agent_type: str  # supervisor, document, verification, workflow
    document_id: Optional[uuid.UUID] = None
    document_version_id: Optional[uuid.UUID] = None
    user_prompt: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


class AgentRunResponse(BaseModel):
    case_id: uuid.UUID
    agent_type: str
    success: bool
    summary: str
    proposals: List[AgentProposal] = Field(default_factory=list)
    result_data: Dict[str, Any] = Field(default_factory=dict)
    execution_id: Optional[uuid.UUID] = None


class SupervisorDelegation(BaseModel):
    """One bounded request to an existing specialized agent."""

    model_config = ConfigDict(extra="forbid")

    agent_type: Literal["DOCUMENT", "VERIFICATION", "WORKFLOW"]
    document_id: Optional[uuid.UUID] = None
    document_version_id: Optional[uuid.UUID] = None
    rationale: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_document_target(self) -> "SupervisorDelegation":
        if self.agent_type == "DOCUMENT":
            if self.document_id is None:
                raise ValueError("DOCUMENT delegation requires document_id.")
        elif self.document_id is not None or self.document_version_id is not None:
            raise ValueError("Only DOCUMENT delegation may include document identifiers.")
        if self.document_version_id is not None and self.document_id is None:
            raise ValueError("document_version_id requires document_id.")
        return self


class SupervisorPlan(BaseModel):
    """Finite model output used only to select allowlisted agent capabilities."""

    model_config = ConfigDict(extra="forbid")

    delegations: List[SupervisorDelegation] = Field(default_factory=list, max_length=3)
    rationale: str = Field(min_length=1, max_length=1200)


class SupervisorChildResult(BaseModel):
    """Safe summary and trace references for one delegated child execution."""

    model_config = ConfigDict(extra="forbid")

    agent_type: Literal["DOCUMENT", "VERIFICATION", "WORKFLOW"]
    execution_id: Optional[uuid.UUID] = None
    status: Literal["SUCCESS", "FAILED"]
    summary: str = Field(max_length=1200)
    result_summary: Dict[str, Any] = Field(default_factory=dict)
    tool_execution_ids: List[uuid.UUID] = Field(default_factory=list, max_length=8)


class SupervisorResult(BaseModel):
    """Stable public result returned for one synchronous Supervisor run."""

    model_config = ConfigDict(extra="forbid")

    case_id: uuid.UUID
    execution_id: uuid.UUID
    correlation_id: uuid.UUID
    decision: Literal["CONTINUE", "ESCALATE", "COMPLETE", "NEEDS_INFORMATION"]
    summary: str = Field(max_length=2000)
    delegations: List[SupervisorChildResult] = Field(default_factory=list, max_length=3)
    authoritative_case_status: str
