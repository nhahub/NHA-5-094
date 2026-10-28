"""Authenticated document upload, listing, download, and extraction endpoints."""
import uuid
from typing import Any
from urllib.parse import quote

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import Response as BinaryResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.domain.cases.models import CaseStatus
from app.domain.cases.schemas import CustomerDocumentRead, CustomerDocumentUploadRead
from app.domain.documents.processing import DocumentProcessingService
from app.domain.documents.schemas import (
    DocumentProcessingRunRead,
    DocumentRead,
    DocumentUploadResult,
    ExtractedFieldCreate,
    ExtractedFieldRead,
)
from app.domain.documents.service import DocumentService
from app.domain.documents.upload import UploadValidationError, ensure_uploads_allowed
from app.infrastructure.database.session import get_db
from app.infrastructure.storage import (
    StorageBackend,
    StorageBackendUnavailable,
    StorageError,
    get_storage_backend,
)
from app.security.authorization import (
    require_accessible_case,
    require_customer,
    require_internal_user,
)
from app.security.models import User
from app.security.router import get_current_user

documents_router = APIRouter(prefix="/documents", tags=["Documents"])


def _raise_storage_unavailable(exc: Exception) -> None:
    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


def get_document_storage() -> StorageBackend:
    try:
        return get_storage_backend()
    except StorageBackendUnavailable as exc:
        _raise_storage_unavailable(exc)


@documents_router.post("", response_model=DocumentUploadResult, status_code=status.HTTP_201_CREATED)
async def upload_document(
    response: Response,
    case_id: uuid.UUID = Form(...),
    document_type: str = Form(..., min_length=1, max_length=100),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    storage: StorageBackend = Depends(get_document_storage),
) -> Any:
    require_internal_user(current_user)
    try:
        ensure_uploads_allowed()
    except UploadValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    content = await file.read(settings.DOCUMENT_MAX_FILE_SIZE_BYTES + 1)
    try:
        document, duplicate = await DocumentService.upload_document(
            db,
            organization_id=current_user.organization_id,
            case_id=case_id,
            uploaded_by=current_user.id,
            document_type=document_type,
            filename=file.filename,
            declared_content_type=file.content_type,
            content=content,
            storage=storage,
            dispatch_orchestration=True,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except UploadValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except (StorageBackendUnavailable, StorageError) as exc:
        _raise_storage_unavailable(exc)
    response.status_code = status.HTTP_200_OK if duplicate else status.HTTP_201_CREATED
    return DocumentUploadResult(document=document, duplicate=duplicate)


@documents_router.post("/mine", response_model=CustomerDocumentUploadRead, status_code=status.HTTP_201_CREATED)
async def upload_customer_document(
    response: Response,
    case_id: uuid.UUID = Form(...),
    document_type: str = Form(..., min_length=1, max_length=100),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    storage: StorageBackend = Depends(get_document_storage),
) -> CustomerDocumentUploadRead:
    require_customer(current_user)
    case = await require_accessible_case(db, case_id, current_user)
    if case.status in {
        CaseStatus.COMPLETED.value,
        CaseStatus.REJECTED.value,
        CaseStatus.CANCELLED.value,
    }:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This case no longer accepts documents.")
    try:
        ensure_uploads_allowed()
    except UploadValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    content = await file.read(settings.DOCUMENT_MAX_FILE_SIZE_BYTES + 1)
    try:
        document, duplicate = await DocumentService.upload_document(
            db,
            organization_id=current_user.organization_id,
            case_id=case_id,
            uploaded_by=current_user.id,
            document_type=document_type,
            filename=file.filename,
            declared_content_type=file.content_type,
            content=content,
            storage=storage,
            dispatch_orchestration=True,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.") from exc
    except UploadValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except (StorageBackendUnavailable, StorageError) as exc:
        _raise_storage_unavailable(exc)
    response.status_code = status.HTTP_200_OK if duplicate else status.HTTP_201_CREATED
    return CustomerDocumentUploadRead(
        document=CustomerDocumentRead(
            id=document.id,
            document_type=document.document_type,
            name=document.name,
            status=document.status,
            created_at=document.created_at,
            version_id=max(document.versions, key=lambda version: version.version_number).id
            if document.versions else None,
            mime_type=max(document.versions, key=lambda version: version.version_number).mime_type
            if document.versions else None,
        ),
        duplicate=duplicate,
    )


@documents_router.post(
    "/{document_id}/versions",
    response_model=DocumentUploadResult,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document_version(
    document_id: uuid.UUID,
    response: Response,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    storage: StorageBackend = Depends(get_document_storage),
) -> Any:
    require_internal_user(current_user)
    try:
        ensure_uploads_allowed()
    except UploadValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    content = await file.read(settings.DOCUMENT_MAX_FILE_SIZE_BYTES + 1)
    try:
        document, duplicate = await DocumentService.upload_new_version(
            db,
            organization_id=current_user.organization_id,
            document_id=document_id,
            uploaded_by=current_user.id,
            filename=file.filename,
            declared_content_type=file.content_type,
            content=content,
            storage=storage,
            dispatch_orchestration=True,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except UploadValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except (StorageBackendUnavailable, StorageError) as exc:
        _raise_storage_unavailable(exc)
    response.status_code = status.HTTP_200_OK if duplicate else status.HTTP_201_CREATED
    return DocumentUploadResult(document=document, duplicate=duplicate)


@documents_router.get("/case/{case_id}", response_model=list[DocumentRead])
async def list_documents_for_case(
    case_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    require_internal_user(current_user)
    # Import locally to avoid package initialization cycles through workflow models.
    from app.domain.cases.service import CaseService

    case = await CaseService.get_case_by_id(db, case_id)
    if case is None or case.organization_id != current_user.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    return await DocumentService.get_documents_by_case(db, case_id, current_user.organization_id)


@documents_router.get(
    "/{document_id}/versions/{version_id}/content",
    response_class=BinaryResponse,
)
async def download_document_version(
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    storage: StorageBackend = Depends(get_document_storage),
) -> BinaryResponse:
    document_record = await DocumentService.get_document_by_id(
        db, document_id, current_user.organization_id
    )
    if document_record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document version not found.")
    await require_accessible_case(db, document_record.case_id, current_user)
    try:
        document, version, content = await DocumentService.download_version(
            db,
            organization_id=current_user.organization_id,
            document_id=document_id,
            version_id=version_id,
            storage=storage,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (StorageBackendUnavailable, StorageError) as exc:
        _raise_storage_unavailable(exc)
    safe_filename = quote(document.name, safe="")
    return BinaryResponse(
        content=content,
        media_type=version.mime_type or "application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename=\"document\"; filename*=UTF-8''{safe_filename}",
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@documents_router.get("/{document_id}", response_model=DocumentRead)
async def get_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    require_internal_user(current_user)
    document = await DocumentService.get_document_by_id(
        db, document_id, current_user.organization_id
    )
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document


@documents_router.post(
    "/{version_id}/fields",
    response_model=list[ExtractedFieldRead],
    status_code=status.HTTP_201_CREATED,
)
async def add_extracted_fields(
    version_id: uuid.UUID,
    fields_in: list[ExtractedFieldCreate],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    require_internal_user(current_user)
    try:
        return await DocumentService.add_extracted_fields(
            db, current_user.organization_id, version_id, fields_in
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@documents_router.post(
    "/{document_id}/versions/{version_id}/process",
    response_model=DocumentProcessingRunRead,
)
async def process_document_version(
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    storage: StorageBackend = Depends(get_document_storage),
) -> DocumentProcessingRunRead:
    require_internal_user(current_user)
    try:
        run = await DocumentProcessingService.process_version(
            db,
            organization_id=current_user.organization_id,
            document_id=document_id,
            version_id=version_id,
            storage=storage,
        )
        return DocumentProcessingRunRead.model_validate(run)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        # The run stores a safe failure record; do not expose parser/model internals.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document processing failed. Check the processing run and retry.",
        ) from exc
