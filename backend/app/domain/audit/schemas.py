import uuid
from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, field_validator


class AuditLogBase(BaseModel):
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    ip_address: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class AuditLogCreate(AuditLogBase):
    organization_id: uuid.UUID
    user_id: Optional[uuid.UUID] = None


class AuditLogRead(AuditLogBase):
    id: uuid.UUID
    organization_id: uuid.UUID
    user_id: Optional[uuid.UUID] = None
    created_at: datetime

    @field_validator("resource_id", mode="before")
    @classmethod
    def serialize_resource_id(cls, value: Any) -> str | None:
        return str(value) if value is not None else None

    model_config = ConfigDict(from_attributes=True)
