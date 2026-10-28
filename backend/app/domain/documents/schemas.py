"""Document upload metadata and read schemas."""
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.domain.documents.models import DocumentStatus


class ExtractedFieldCreate(BaseModel):
    field_name: str
    field_value: Optional[Dict[str, Any]] = None
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    page_number: Optional[int] = Field(default=None, ge=1)
    bounding_box: Optional[Dict[str, Any]] = None
    extraction_method: Optional[str] = None


class ExtractedFieldRead(ExtractedFieldCreate):
    id: uuid.UUID
    document_version_id: uuid.UUID
    processing_run_id: Optional[uuid.UUID] = None
    source_text: Optional[str] = None
    source_locator: Optional[Dict[str, Any]] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentVersionRead(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    version_number: int
    file_hash: Optional[str] = None
    mime_type: Optional[str] = None
    file_size: Optional[int] = None
    uploaded_by: Optional[uuid.UUID] = None
    created_at: datetime
    extracted_fields: List[ExtractedFieldRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class DocumentRead(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    document_type: str
    name: str
    status: DocumentStatus
    uploaded_by: Optional[uuid.UUID] = None
    created_at: datetime
    versions: List[DocumentVersionRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class DocumentUploadResult(BaseModel):
    document: DocumentRead
    duplicate: bool = False


class DocumentProcessingRunRead(BaseModel):
    id: uuid.UUID
    document_version_id: uuid.UUID
    run_number: int
    status: str
    parser_name: Optional[str] = None
    parser_version: Optional[str] = None
    ocr_engine: Optional[str] = None
    predicted_document_type: Optional[str] = None
    classification_confidence: Optional[float] = None
    classifier_model: Optional[str] = None
    extractor_model: Optional[str] = None
    extraction_schema_version: Optional[str] = None
    review_required: bool
    review_reasons: List[str] = Field(default_factory=list)
    review_task_id: Optional[uuid.UUID] = None
    error_code: Optional[str] = None
    safe_error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
