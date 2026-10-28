import uuid

import pytest
import pymupdf
from sqlalchemy import select

from app.domain.cases.schemas import CaseCreate
from app.domain.cases.service import CaseService
from app.domain.documents.models import DocumentProcessingRun, ExtractedField
from app.domain.documents.processing import DocumentProcessingService
from app.domain.documents.service import DocumentService
from app.domain.processes.schemas import ProcessCreate
from app.domain.processes.service import ProcessService
from app.domain.tasks.models import Task
from app.domain.workflows.schemas import WorkflowStageCreate
from app.infrastructure.storage import LocalFileStorage


class InvoiceModel:
    async def generate_json(self, *, system_prompt, user_prompt, response_schema):
        if "class_id" in response_schema.get("properties", {}):
            return {"class_id": "invoice", "confidence": 0.98, "rationale": "invoice heading"}, "fixture-v1"
        return {
            "fields": {
                "invoice_number": {"value": "INV-44", "confidence": 0.97, "citations": [
                    {"block_index": 0, "quote": "Invoice INV-44"}
                ]},
                "supplier": {"value": "Northwind Ltd", "confidence": 0.95, "citations": [
                    {"block_index": 1, "quote": "Supplier: Northwind Ltd"}
                ]},
                "invoice_date": {"value": "2026-09-30", "confidence": 0.96, "citations": [
                    {"block_index": 2, "quote": "Date: 2026-09-30"}
                ]},
                "currency": {"value": "USD", "confidence": 0.96, "citations": [
                    {"block_index": 3, "quote": "Currency: USD"}
                ]},
                "items": {"value": [], "confidence": 0.9, "citations": [
                    {"block_index": 4, "quote": "Total: 125.50"}
                ]},
                "total": {"value": 125.5, "confidence": 0.55, "citations": [
                    {"block_index": 4, "quote": "Total: 125.50"}
                ]},
            }
        }, "fixture-v1"


def _invoice_pdf():
    document = pymupdf.open()
    page = document.new_page()
    for index, text in enumerate((
        "Invoice INV-44", "Supplier: Northwind Ltd", "Date: 2026-09-30",
        "Currency: USD", "Total: 125.50",
    )):
        page.insert_text((72, 72 + index * 24), text)
    content = document.tobytes()
    document.close()
    return content


@pytest.mark.asyncio
async def test_processing_persists_version_scoped_results_and_citations(
    db_session, test_org, test_user, tmp_path
):
    process = await ProcessService.create_process(
        db=db_session,
        organization_id=test_org.id,
        process_in=ProcessCreate(name="Document Intake", code="PROCESSING_TEST"),
    )
    process_version = (await ProcessService.get_versions_by_process_id(db_session, process.id))[0]
    await ProcessService.add_stage_to_version(
        db_session,
        process_version.id,
        WorkflowStageCreate(
            process_version_id=process_version.id,
            name="Intake", code="INTAKE", stage_order=1, is_initial=True,
        ),
    )
    await ProcessService.publish_version(db_session, process_version.id)
    case = await CaseService.create_case(
        db=db_session,
        organization_id=test_org.id,
        created_by_user_id=test_user.id,
        case_in=CaseCreate(process_version_id=process_version.id, title="Invoice processing"),
    )
    storage = LocalFileStorage(tmp_path)
    document, _ = await DocumentService.upload_document(
        db_session,
        organization_id=test_org.id,
        case_id=case.id,
        uploaded_by=test_user.id,
        document_type="invoice",
        filename="invoice.pdf",
        declared_content_type="application/pdf",
        content=_invoice_pdf(),
        storage=storage,
    )
    version = document.versions[0]

    run = await DocumentProcessingService.process_version(
        db_session,
        organization_id=test_org.id,
        document_id=document.id,
        version_id=version.id,
        storage=storage,
        adapter=InvoiceModel(),
    )

    assert run.status == "NEEDS_REVIEW"
    assert run.review_required is True
    assert run.review_task_id is not None
    assert run.predicted_document_type == "invoice"
    assert run.classifier_model == "fixture-v1"
    assert run.normalized_content_reference
    assert await storage.exists(run.normalized_content_reference)
    fields = list((await db_session.execute(
        select(ExtractedField).where(ExtractedField.processing_run_id == run.id)
    )).scalars().all())
    assert len(fields) == 6
    total = next(field for field in fields if field.field_name == "total")
    assert total.field_value == {"value": 125.5}
    assert total.source_text == "Total: 125.50"
    assert total.source_locator["page"] == 1
    review_task = await db_session.get(Task, run.review_task_id)
    assert review_task.task_type == "DOCUMENT_REVIEW"
    assert review_task.status == "PENDING"
    assert review_task.case_id == case.id
    assert await db_session.scalar(
        select(DocumentProcessingRun.id).where(DocumentProcessingRun.id == run.id)
    ) == run.id


@pytest.mark.asyncio
async def test_processing_is_organization_scoped(db_session, test_org, test_user, tmp_path):
    with pytest.raises(LookupError):
        await DocumentProcessingService.process_version(
            db_session,
            organization_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            version_id=uuid.uuid4(),
            storage=LocalFileStorage(tmp_path),
        )
