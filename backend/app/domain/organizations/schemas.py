"""Organization Pydantic schemas."""
import uuid
from datetime import datetime
from pydantic import BaseModel


class OrganizationRead(BaseModel):
    id: uuid.UUID
    name: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
