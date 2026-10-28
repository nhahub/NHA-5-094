import uuid
from datetime import datetime
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.tasks.models import TaskPriority, TaskStatus


class TaskBase(BaseModel):
    task_type: str = "REVIEW"
    title: str
    description: Optional[str] = None
    priority: TaskPriority = TaskPriority.MEDIUM
    stage_id: Optional[uuid.UUID] = None
    assigned_user_id: Optional[uuid.UUID] = None
    assigned_role_id: Optional[uuid.UUID] = None
    assigned_department_id: Optional[uuid.UUID] = None
    due_at: Optional[datetime] = None


class TaskCreate(TaskBase):
    case_id: uuid.UUID


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[TaskStatus] = None
    priority: Optional[TaskPriority] = None
    assigned_user_id: Optional[uuid.UUID] = None
    assigned_role_id: Optional[uuid.UUID] = None
    assigned_department_id: Optional[uuid.UUID] = None
    due_at: Optional[datetime] = None
    completion_metadata: Optional[Dict[str, Any]] = None


class TaskRead(TaskBase):
    id: uuid.UUID
    case_id: uuid.UUID
    status: str
    priority: str
    created_by_type: str
    created_by_id: Optional[uuid.UUID] = None
    completed_at: Optional[datetime] = None
    completion_metadata: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TaskAssignmentRequest(BaseModel):
    assigned_user_id: uuid.UUID


class TaskReviewCommentCreate(BaseModel):
    comment: str = Field(min_length=1, max_length=10_000)
    evidence_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)

    @field_validator("comment")
    @classmethod
    def comment_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Comment cannot be blank.")
        return value


class TaskReviewCommentRead(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    author_id: uuid.UUID
    comment: str
    evidence_ids: list[uuid.UUID]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TaskResolutionRequest(BaseModel):
    outcome: Literal["COMPLETED", "REJECTED"]
    comment: str = Field(min_length=1, max_length=10_000)
    evidence_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)

    @field_validator("comment")
    @classmethod
    def comment_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Resolution comment cannot be blank.")
        return value
