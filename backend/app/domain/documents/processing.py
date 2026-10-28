"""Version-scoped document parsing, OCR, classification, and extraction pipeline."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.domain.cases.models import Case
from app.domain.documents.intelligence import (
    JsonModelAdapter,
    classify_document,
    extract_document_fields,
    resolve_document_classes,
)
from app.domain.documents.models import (
    Document,
    DocumentProcessingRun,
    DocumentRunStatus,
    DocumentStatus,
    DocumentVersion,
    ExtractedField,
)
from app.domain.documents.ocr import apply_ocr
from app.domain.documents.parsing import parse_document_content
from app.domain.processes.models import ProcessVersion
from app.domain.tasks.models import Task, TaskPriority, TaskStatus
from app.events.models import EventRecord
from app.events.service import EventService
from app.infrastructure.storage import StorageBackend

logger = logging.getLogger(settings.APP_NAME)


class DocumentProcessingService:
    """Process one immutable version, keeping source, model, and schema provenance."""

    @classmethod
    async def process_version(
        cls,
        db: AsyncSession,
        *,
        organization_id: uuid.UUID,
        document_id: uuid.UUID,
        version_id: uuid.UUID,
        storage: StorageBackend,
        adapter: JsonModelAdapter | None = None,
    ) -> DocumentProcessingRun:
        row = (await db.execute(
            select(DocumentVersion, Document, Case, ProcessVersion.configuration)
            .join(Document, Document.id == DocumentVersion.document_id)
            .join(Case, Case.id == Document.case_id)
            .join(ProcessVersion, ProcessVersion.id == Case.process_version_id)
            .where(
                Document.id == document_id,
                DocumentVersion.id == version_id,
                Case.organization_id == organization_id,
            )
        )).first()
        if row is None:
            raise LookupError("Document version not found.")
        version, document, case, raw_configuration = row
        case_pk = case.id
        document_pk = document.id
        version_pk = version.id
        configuration = raw_configuration or {}
        last_run_number = await db.scalar(
            select(func.max(DocumentProcessingRun.run_number)).where(
                DocumentProcessingRun.document_version_id == version.id
            )
        )
        run = DocumentProcessingRun(
            id=uuid.uuid4(),
            document_version_id=version.id,
            run_number=(last_run_number or 0) + 1,
            status=DocumentRunStatus.RUNNING.value,
            started_at=datetime.now(UTC),
            configuration_hash=hashlib.sha256(
                json.dumps(configuration, sort_keys=True, default=str).encode("utf-8")
            ).hexdigest(),
        )
        run_id = run.id
        document.status = DocumentStatus.PROCESSING.value
        db.add(run)
        await db.commit()
        await db.refresh(run)

        normalized_reference: str | None = None
        review_task_event: EventRecord | None = None
        processing_completed_event: EventRecord | None = None
        try:
            source = await storage.download(version.storage_reference)
            parsed = await asyncio.to_thread(_parse_with_ocr, document.name, source)
            run.parser_name = parsed.parser_name
            run.parser_version = parsed.parser_version
            if parsed.source_format in {"pdf", "png", "jpg", "jpeg"}:
                run.ocr_engine = settings.OCR_ENGINE

            prediction = await classify_document(
                parsed,
                catalog=resolve_document_classes(configuration),
                declared_type=document.document_type,
                adapter=adapter,
            )
            run.predicted_document_type = prediction.class_id
            run.classification_confidence = prediction.confidence
            run.classifier_model = prediction.model

            extraction = None
            if prediction.class_id in (configuration.get("extraction_schemas") or {}) or prediction.class_id in {
                "invoice", "purchase_order", "packing_list"
            }:
                extraction = await extract_document_fields(
                    parsed,
                    document_class=prediction.class_id,
                    configuration=configuration,
                    adapter=adapter,
                )

            review_reasons = list(parsed.warnings)
            review_required = (
                prediction.confidence < settings.DOCUMENT_REVIEW_CONFIDENCE_THRESHOLD
                or bool(review_reasons)
            )
            if review_required:
                review_reasons.append("Classification confidence is below the review threshold.")
            if extraction is None:
                review_required = True
                review_reasons.append(
                    f"No extraction schema is configured for '{prediction.class_id}'."
                )
            else:
                review_required = review_required or extraction.review_required
                review_reasons.extend(extraction.review_reasons)
                run.extractor_model = extraction.model
                run.extraction_schema_version = extraction.schema_version
                for field_name, extracted in extraction.fields.items():
                    citation = extracted.citations[0] if extracted.citations else None
                    block = parsed.blocks[citation.block_index] if citation else None
                    db.add(ExtractedField(
                        document_version_id=version.id,
                        processing_run_id=run.id,
                        field_name=field_name,
                        field_value={"value": extracted.value},
                        confidence=extracted.confidence,
                        page_number=(block.source.get("page") if block else None),
                        bounding_box=(
                            {"bbox": block.source["bbox"], "coordinate_system": block.source.get("coordinate_system")}
                            if block and "bbox" in block.source else None
                        ),
                        extraction_method=f"{prediction.model}",
                        source_text=citation.quote if citation else None,
                        source_locator=block.source if block else None,
                    ))

            normalized_reference = (
                f"organizations/{organization_id}/cases/{case.id}/documents/"
                f"{document.id}/versions/{version.version_number}/processing/{run.id}/normalized.json"
            )
            normalized_reference = await storage.upload(
                normalized_reference,
                parsed.to_json().encode("utf-8"),
                "application/json",
            )
            run.normalized_content_reference = normalized_reference
            run.review_required = review_required
            run.review_reasons = list(dict.fromkeys(review_reasons))
            run.status = (
                DocumentRunStatus.NEEDS_REVIEW.value
                if review_required else DocumentRunStatus.COMPLETED.value
            )
            run.completed_at = datetime.now(UTC)
            document.document_type = prediction.class_id.upper()
            document.status = DocumentStatus.PROCESSED.value
            if review_required:
                review_task = Task(
                    case_id=case.id,
                    task_type="DOCUMENT_REVIEW",
                    title="Review extracted document data",
                    description=(
                        f"Document {document.name!r} (version {version.version_number}) "
                        f"requires review. Processing run {run.run_number}: "
                        + "; ".join(run.review_reasons)
                    ),
                    priority=TaskPriority.HIGH.value
                    if prediction.confidence < settings.DOCUMENT_REVIEW_CONFIDENCE_THRESHOLD
                    else TaskPriority.MEDIUM.value,
                    status=TaskStatus.PENDING.value,
                    created_by_type="SYSTEM",
                    created_by_id=None,
                )
                db.add(review_task)
                await db.flush()
                run.review_task_id = review_task.id
                review_task_event = await EventService.add_event(
                    db,
                    event_type="DOCUMENT_REVIEW_TASK_CREATED",
                    actor_type="SYSTEM",
                    organization_id=organization_id,
                    case_id=case.id,
                    dispatch_orchestration=True,
                    payload={
                        "document_id": str(document.id),
                        "document_version_id": str(version.id),
                        "processing_run_id": str(run.id),
                        "task_id": str(review_task.id),
                    },
                )
            processing_completed_event = await EventService.add_event(
                db,
                event_type="DOCUMENT_PROCESSED",
                actor_type="SYSTEM",
                organization_id=organization_id,
                case_id=case.id,
                dispatch_orchestration=True,
                payload={
                    "document_id": str(document.id),
                    "document_version_id": str(version.id),
                    "processing_run_id": str(run.id),
                    "predicted_document_type": prediction.class_id,
                    "review_required": review_required,
                },
            )
            await db.commit()
            await db.refresh(run)
            if review_task_event is not None:
                await EventService.dispatch_persisted_event(
                    db,
                    review_task_event,
                    storage=storage,
                    model_adapter=adapter,
                )
            if processing_completed_event is not None:
                await EventService.dispatch_persisted_event(
                    db,
                    processing_completed_event,
                    storage=storage,
                    model_adapter=adapter,
                )
            # Event orchestration shares the request session and can roll it back
            # after a downstream failure. Refresh the committed run before returning
            # so callers never trigger implicit async ORM I/O on expired attributes.
            await db.refresh(run)
            return run
        except Exception as exc:
            logger.error("Document processing run %s failed (%s).", run_id, type(exc).__name__)
            await db.rollback()
            if normalized_reference:
                await storage.delete(normalized_reference)
            run = await db.get(DocumentProcessingRun, run_id)
            document = await db.get(Document, document_pk)
            if run is not None:
                run.status = DocumentRunStatus.FAILED.value
                run.error_code = type(exc).__name__[:100]
                run.safe_error = "Document processing failed. Check service availability and retry."
                run.completed_at = datetime.now(UTC)
            if document is not None:
                document.status = DocumentStatus.FAILED.value
                await EventService.add_event(
                    db,
                    event_type="DOCUMENT_PROCESSING_FAILED",
                    actor_type="SYSTEM",
                    organization_id=organization_id,
                    case_id=case_pk,
                    payload={
                        "document_id": str(document_pk),
                        "document_version_id": str(version_pk),
                        "processing_run_id": str(run_id),
                        "error_code": type(exc).__name__[:100],
                    },
                )
            await db.commit()
            if run is None:
                raise
            await db.refresh(run)
            return run


def _parse_with_ocr(filename: str, content: bytes):
    parsed = parse_document_content(filename, content)
    return apply_ocr(filename, content, parsed)
