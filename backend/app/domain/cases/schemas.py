import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict

from app.domain.cases.models import CaseStatus, ParticipantType


class CaseBase(BaseModel):
    title: str
    case_metadata: Dict[str, Any] = {}


class CaseCreate(CaseBase):
    process_version_id: uuid.UUID


class CaseUpdate(BaseModel):
    title: Optional[str] = None
    case_metadata: Optional[Dict[str, Any]] = None


class CaseCloseRequest(BaseModel):
    status: CaseStatus = CaseStatus.COMPLETED
    reason: Optional[str] = None


class CaseParticipantCreate(BaseModel):
    user_id: Optional[uuid.UUID] = None
    participant_type: ParticipantType = ParticipantType.CUSTOMER
    name: Optional[str] = None
    external_reference: Optional[str] = None


class CaseParticipantRead(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    user_id: Optional[uuid.UUID] = None
    participant_type: str
    name: Optional[str] = None
    external_reference: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CaseRead(CaseBase):
    id: uuid.UUID
    organization_id: uuid.UUID
    process_id: uuid.UUID
    process_version_id: uuid.UUID
    case_number: str
    status: str
    current_stage_id: Optional[uuid.UUID] = None
    created_by: Optional[uuid.UUID] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CaseStateRead(BaseModel):
    case: CaseRead
    current_stage_name: Optional[str] = None
    current_stage_code: Optional[str] = None
    documents_count: int = 0
    verifications_count: int = 0
    open_tasks_count: int = 0
    evidence_count: int = 0
    participants: List[CaseParticipantRead] = []


class CustomerDocumentRead(BaseModel):
    id: uuid.UUID
    document_type: str
    name: str
    status: str
    created_at: datetime
    version_id: Optional[uuid.UUID] = None
    mime_type: Optional[str] = None


class CustomerDocumentUploadRead(BaseModel):
    document: CustomerDocumentRead
    duplicate: bool = False


class CustomerDocumentRequestRead(BaseModel):
    code: str
    name: str
    description: Optional[str] = None
    status: str


class CustomerCaseRead(BaseModel):
    """Minimal case view for its linked customer; excludes internal metadata and review data."""

    id: uuid.UUID
    case_number: str
    title: str
    status: str
    current_stage_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    documents: List[CustomerDocumentRead] = []
    document_requests: List[CustomerDocumentRequestRead] = []
