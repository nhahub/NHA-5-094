"""Case-scoped document upload, versioning, and storage-reference services."""
from __future__ import annotations

import hashlib
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.domain.cases.models import Case
from app.domain.documents.models import (
    Document,
    DocumentStatus,
    DocumentVersion,
    ExtractedField,
)
from app.domain.documents.schemas import ExtractedFieldCreate
from app.domain.documents.upload import UploadValidationError, validate_upload
from app.events.service import EventService
from app.infrastructure.storage import StorageBackend


class DocumentService:
    """Manage document binaries through storage adapters and metadata in PostgreSQL."""

    @staticmethod
    async def _case_for_organization(
        db: AsyncSession, case_id: uuid.UUID, organization_id: uuid.UUID
    ) -> Case | None:
        return (await db.execute(select(Case).where(
            Case.id == case_id,
            Case.organization_id == organization_id,
        ))).scalars().first()

    @staticmethod
    def _normalize_document_type(value: str) -> str:
        normalized = value.strip().upper()
        if not normalized or len(normalized) > 100 or any(ord(char) < 32 for char in normalized):
            raise UploadValidationError(
                "document_type must contain between 1 and 100 printable characters."
            )
        return normalized

    @classmethod
    async def upload_document(
        cls,
        db: AsyncSession,
        *,
        organization_id: uuid.UUID,
        case_id: uuid.UUID,
        uploaded_by: uuid.UUID,
        document_type: str,
        filename: str | None,
        declared_content_type: str | None,
        content: bytes,
        storage: StorageBackend,
        dispatch_orchestration: bool = False,
    ) -> tuple[Document, bool]:
        case = await cls._case_for_organization(db, case_id, organization_id)
        if case is None:
            raise LookupError("Case not found.")
        normalized_type = cls._normalize_document_type(document_type)
        safe_name, mime_type, extension = validate_upload(
            filename,
            content,
            declared_content_type,
            settings.DOCUMENT_MAX_FILE_SIZE_BYTES,
        )
        file_hash = hashlib.sha256(content).hexdigest()

        existing = (await db.execute(
            select(Document)
            .join(DocumentVersion, DocumentVersion.document_id == Document.id)
            .where(
                Document.case_id == case_id,
                Document.document_type == normalized_type,
                DocumentVersion.file_hash == file_hash,
            )
            .options(selectinload(Document.versions).selectinload(DocumentVersion.extracted_fields))
        )).scalars().first()
        if existing is not None:
            return existing, True

        document = Document(
            id=uuid.uuid4(),
            case_id=case.id,
            document_type=normalized_type,
            name=safe_name,
            status=DocumentStatus.PENDING.value,
            uploaded_by=uploaded_by,
        )
        storage_reference = cls._storage_key(
            organization_id, case_id, document.id, 1, extension
        )
        storage_reference = await storage.upload(storage_reference, content, mime_type)
        document.storage_reference = storage_reference
        version = DocumentVersion(
            document_id=document.id,
            version_number=1,
            storage_reference=storage_reference,
            file_hash=file_hash,
            mime_type=mime_type,
            file_size=len(content),
            uploaded_by=uploaded_by,
        )
        db.add_all([document, version])
        try:
            await db.flush()
            await EventService.emit_event(
                db=db,
                event_type="DOCUMENT_UPLOADED",
                organization_id=organization_id,
                actor_type="USER",
                actor_id=uploaded_by,
                case_id=case_id,
                payload={
                    "document_id": str(document.id),
                    "document_version_id": str(version.id),
                    "document_type": normalized_type,
                    "version_number": 1,
                    "file_name": safe_name,
                    "file_size": len(content),
                    "mime_type": mime_type,
                    "sha256": file_hash,
                },
                dispatch_orchestration=dispatch_orchestration,
                storage=storage,
            )
        except Exception:
            await db.rollback()
            await storage.delete(storage_reference)
            raise
        return await cls.get_document_by_id(db, document.id, organization_id), False

    @classmethod
    async def upload_new_version(
        cls,
        db: AsyncSession,
        *,
        organization_id: uuid.UUID,
        document_id: uuid.UUID,
        uploaded_by: uuid.UUID,
        filename: str | None,
        declared_content_type: str | None,
        content: bytes,
        storage: StorageBackend,
        dispatch_orchestration: bool = False,
    ) -> tuple[Document, bool]:
        document = await cls.get_document_by_id(db, document_id, organization_id)
        if document is None:
            raise LookupError("Document not found.")
        safe_name, mime_type, extension = validate_upload(
            filename,
            content,
            declared_content_type,
            settings.DOCUMENT_MAX_FILE_SIZE_BYTES,
        )
        file_hash = hashlib.sha256(content).hexdigest()
        if any(version.file_hash == file_hash for version in document.versions):
            return document, True

        version_number = max((version.version_number for version in document.versions), default=0) + 1
        case = await cls._case_for_organization(db, document.case_id, organization_id)
        if case is None:
            raise LookupError("Document not found.")
        storage_reference = cls._storage_key(
            organization_id, case.id, document.id, version_number, extension
        )
        storage_reference = await storage.upload(storage_reference, content, mime_type)
        version = DocumentVersion(
            document_id=document.id,
            version_number=version_number,
            storage_reference=storage_reference,
            file_hash=file_hash,
            mime_type=mime_type,
            file_size=len(content),
            uploaded_by=uploaded_by,
        )
        db.add(version)
        document.name = safe_name
        document.status = DocumentStatus.PENDING.value
        document.storage_reference = storage_reference
        try:
            await db.flush()
            await EventService.emit_event(
                db=db,
                event_type="DOCUMENT_UPLOADED",
                organization_id=organization_id,
                actor_type="USER",
                actor_id=uploaded_by,
                case_id=case.id,
                payload={
                    "document_id": str(document.id),
                    "document_version_id": str(version.id),
                    "document_type": document.document_type,
                    "version_number": version_number,
                    "file_name": safe_name,
                    "file_size": len(content),
                    "mime_type": mime_type,
                    "sha256": file_hash,
                },
                dispatch_orchestration=dispatch_orchestration,
                storage=storage,
            )
        except Exception:
            await db.rollback()
            await storage.delete(storage_reference)
            raise
        return await cls.get_document_by_id(db, document.id, organization_id), False

    @staticmethod
    def _storage_key(
        organization_id: uuid.UUID,
        case_id: uuid.UUID,
        document_id: uuid.UUID,
        version_number: int,
        extension: str,
    ) -> str:
        object_id = uuid.uuid4().hex
        return (
            f"organizations/{organization_id}/cases/{case_id}/documents/"
            f"{document_id}/versions/{version_number}/{object_id}{extension}"
        )

    @staticmethod
    async def get_documents_by_case(
        db: AsyncSession, case_id: uuid.UUID, organization_id: uuid.UUID
    ) -> list[Document]:
        stmt = (
            select(Document)
            .join(Case, Case.id == Document.case_id)
            .where(Document.case_id == case_id, Case.organization_id == organization_id)
            .options(selectinload(Document.versions).selectinload(DocumentVersion.extracted_fields))
            .order_by(Document.created_at.desc())
        )
        return list((await db.execute(stmt)).scalars().all())

    @staticmethod
    async def get_document_by_id(
        db: AsyncSession,
        document_id: uuid.UUID,
        organization_id: uuid.UUID | None = None,
    ) -> Document | None:
        stmt = select(Document).where(Document.id == document_id).options(
            selectinload(Document.versions).selectinload(DocumentVersion.extracted_fields)
        ).execution_options(populate_existing=True)
        if organization_id is not None:
            stmt = stmt.join(Case, Case.id == Document.case_id).where(
                Case.organization_id == organization_id
            )
        return (await db.execute(stmt)).scalars().first()

    @staticmethod
    async def download_version(
        db: AsyncSession,
        *,
        organization_id: uuid.UUID,
        document_id: uuid.UUID,
        version_id: uuid.UUID,
        storage: StorageBackend,
    ) -> tuple[Document, DocumentVersion, bytes]:
        row = (await db.execute(
            select(Document, DocumentVersion)
            .join(Case, Case.id == Document.case_id)
            .join(DocumentVersion, DocumentVersion.document_id == Document.id)
            .where(
                Document.id == document_id,
                DocumentVersion.id == version_id,
                Case.organization_id == organization_id,
            )
        )).first()
        if row is None:
            raise LookupError("Document version not found.")
        document, version = row
        data = await storage.download(version.storage_reference)
        return document, version, data

    @staticmethod
    async def add_extracted_fields(
        db: AsyncSession,
        organization_id: uuid.UUID,
        document_version_id: uuid.UUID,
        fields_in: list[ExtractedFieldCreate],
    ) -> list[ExtractedField]:
        row = (await db.execute(
            select(DocumentVersion, Document)
            .join(Document, Document.id == DocumentVersion.document_id)
            .join(Case, Case.id == Document.case_id)
            .where(
                DocumentVersion.id == document_version_id,
                Case.organization_id == organization_id,
            )
        )).first()
        if row is None:
            raise LookupError("Document version not found.")
        version, document = row
        created_fields = [
            ExtractedField(
                document_version_id=version.id,
                field_name=item.field_name,
                field_value=item.field_value,
                confidence=item.confidence,
                page_number=item.page_number,
                bounding_box=item.bounding_box,
                extraction_method=item.extraction_method,
            )
            for item in fields_in
        ]
        db.add_all(created_fields)
        document.status = DocumentStatus.PROCESSED.value
        await db.commit()
        for field in created_fields:
            await db.refresh(field)
        return created_fields
