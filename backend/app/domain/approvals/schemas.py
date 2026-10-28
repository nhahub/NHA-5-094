import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.approvals.models import ApprovalDecision


class ApprovalBase(BaseModel):
    approval_type: str
    task_id: Optional[uuid.UUID] = None


class ApprovalCreate(ApprovalBase):
    case_id: uuid.UUID


class ApprovalDecisionRequest(BaseModel):
    decision: ApprovalDecision
    comment: str = Field(min_length=1, max_length=10_000)

    @field_validator("comment")
    @classmethod
    def comment_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Decision comment cannot be blank.")
        return value


class ApprovalRead(ApprovalBase):
    id: uuid.UUID
    case_id: uuid.UUID
    decision: ApprovalDecision
    decided_by_user_id: Optional[uuid.UUID] = Field(default=None, validation_alias="decided_by")
    decided_at: Optional[datetime] = None
    comment: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
