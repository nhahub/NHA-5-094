"""Knowledge / RAG API router — Phase 9.

9 endpoints:
  Source management  → POST / GET / GET/{id} / PATCH/{id}
  Document mgmt      → POST (upload) / GET (list) / GET/{id} / DELETE
  Ingestion          → POST /documents/{id}/ingest
  Search             → POST /search
"""
from __future__ import annotations

import uuid
from typing import Any, List

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.domain.documents.upload import UploadValidationError, ensure_uploads_allowed, validate_upload
from app.domain.knowledge.schemas import (
    KnowledgeDocumentRead,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    KnowledgeSourceCreate,
    KnowledgeSourceRead,
    KnowledgeSourceUpdate,
)
from app.domain.knowledge.service import KnowledgeService
from app.infrastructure.database.session import get_db
from app.infrastructure.llm.embedding import EmbeddingAdapter, get_embedding_adapter
from app.infrastructure.storage import StorageBackend, get_storage_backend
from app.security.models import User
from app.security.router import get_current_user

knowledge_router = APIRouter(prefix="/knowledge", tags=["Knowledge"])

# Allowed MIME/extension types for knowledge documents
_ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".csv"}


def _require_manager(current_user: User) -> User:
    """Raise 403 if the user is not MANAGER or ADMIN."""
    role_val = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    if str(role_val).upper() not in ("MANAGER", "ADMIN"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only MANAGER or ADMIN can perform this action.",
        )
    return current_user


# =====================================================================
# Knowledge Source endpoints
# =====================================================================

@knowledge_router.post(
    "/sources",
    response_model=KnowledgeSourceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a knowledge source",
)
async def create_knowledge_source(
    source_in: KnowledgeSourceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    _require_manager(current_user)
    return await KnowledgeService.create_source(
        db, current_user.organization_id, source_in
    )


@knowledge_router.get(
    "/sources",
    response_model=List[KnowledgeSourceRead],
    summary="List knowledge sources (org-scoped)",
)
async def list_knowledge_sources(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    return await KnowledgeService.get_sources(
        db, current_user.organization_id, skip=skip, limit=limit
    )


@knowledge_router.get(
    "/sources/{source_id}",
    response_model=KnowledgeSourceRead,
    summary="Get a knowledge source by ID",
)
async def get_knowledge_source(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    source = await KnowledgeService.get_source_by_id(
        db, source_id, current_user.organization_id
    )
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge source not found.")
    return source


@knowledge_router.patch(
    "/sources/{source_id}",
    response_model=KnowledgeSourceRead,
    summary="Update a knowledge source",
)
async def update_knowledge_source(
    source_id: uuid.UUID,
    update_in: KnowledgeSourceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    _require_manager(current_user)
    source = await KnowledgeService.update_source(
        db, source_id, current_user.organization_id, update_in
    )
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge source not found.")
    return source


# =====================================================================
# Knowledge Document endpoints
# =====================================================================

@knowledge_router.post(
    "/sources/{source_id}/documents",
    response_model=KnowledgeDocumentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a knowledge document",
)
async def upload_knowledge_document(
    source_id: uuid.UUID,
    file: UploadFile = File(...),
    title: str = Form(..., min_length=1, max_length=255),
    document_version: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    storage: StorageBackend = Depends(get_storage_backend),
) -> Any:
    _require_manager(current_user)

    # Validate file extension
    filename = file.filename or ""
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported file type '{ext}'. Allowed: {sorted(_ALLOWED_EXTENSIONS)}",
        )

    max_size = settings.DOCUMENT_MAX_FILE_SIZE_BYTES
    try:
        ensure_uploads_allowed()
        file_bytes = await file.read(max_size + 1)
        filename, _, _ = validate_upload(filename, file_bytes, file.content_type, max_size)
    except UploadValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    try:
        doc = await KnowledgeService.upload_document(
            db=db,
            source_id=source_id,
            org_id=current_user.organization_id,
            file_bytes=file_bytes,
            filename=filename,
            title=title,
            document_version=document_version,
            storage=storage,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    return doc


@knowledge_router.post(
    "/documents/{document_id}/ingest",
    response_model=KnowledgeDocumentRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Run the ingestion pipeline for a document",
)
async def ingest_knowledge_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    storage: StorageBackend = Depends(get_storage_backend),
    embedding_adapter: EmbeddingAdapter = Depends(get_embedding_adapter),
) -> Any:
    _require_manager(current_user)
    try:
        doc = await KnowledgeService.ingest_document(
            db=db,
            doc_id=document_id,
            org_id=current_user.organization_id,
            storage=storage,
            embedding_adapter=embedding_adapter,
        )
    except ValueError as exc:
        detail = str(exc)
        if "not found" in detail.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
        if "already being ingested" in detail.lower():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ingestion failed: {exc}",
        )
    return doc


@knowledge_router.get(
    "/sources/{source_id}/documents",
    response_model=List[KnowledgeDocumentRead],
    summary="List documents in a knowledge source",
)
async def list_knowledge_documents(
    source_id: uuid.UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    return await KnowledgeService.get_documents_by_source(
        db, source_id, current_user.organization_id, skip=skip, limit=limit
    )


@knowledge_router.get(
    "/documents/{document_id}",
    response_model=KnowledgeDocumentRead,
    summary="Get a knowledge document by ID",
)
async def get_knowledge_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    doc = await KnowledgeService.get_document_by_id(
        db, document_id, current_user.organization_id
    )
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge document not found.")
    return doc


@knowledge_router.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a knowledge document and its chunks",
)
async def delete_knowledge_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    storage: StorageBackend = Depends(get_storage_backend),
) -> None:
    _require_manager(current_user)
    deleted = await KnowledgeService.delete_document(
        db, document_id, current_user.organization_id, storage
    )
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge document not found.")


# =====================================================================
# Semantic Search
# =====================================================================

@knowledge_router.post(
    "/search",
    response_model=KnowledgeSearchResponse,
    summary="Semantic search across organisation knowledge base",
)
async def search_knowledge(
    request: KnowledgeSearchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    embedding_adapter: EmbeddingAdapter = Depends(get_embedding_adapter),
) -> Any:
    return await KnowledgeService.search_knowledge(
        db=db,
        org_id=current_user.organization_id,
        request=request,
        embedding_adapter=embedding_adapter,
    )
