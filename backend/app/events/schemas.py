import uuid
from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict


class EventRecordBase(BaseModel):
    event_type: str
    actor_type: str = "SYSTEM"
    actor_id: Optional[uuid.UUID] = None
    payload: Dict[str, Any] = {}


class EventRecordCreate(EventRecordBase):
    organization_id: uuid.UUID
    case_id: Optional[uuid.UUID] = None


class EventRecordRead(EventRecordBase):
    id: uuid.UUID
    organization_id: uuid.UUID
    case_id: Optional[uuid.UUID] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
