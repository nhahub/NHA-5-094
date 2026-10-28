import uuid
import pytest
from app.infrastructure.queue import JobPayload, JobQueueService, JobType


@pytest.mark.asyncio
async def test_job_queue_definitions() -> None:
    """Verify that all asynchronous jobs can be constructed and dispatched."""
    case_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    org_id = uuid.uuid4()
    def_id = uuid.uuid4()

    doc_job = await JobQueueService.process_document_job(document_id=doc_id, case_id=case_id)
    assert doc_job.job_type == JobType.DOCUMENT_PROCESSING
    assert doc_job.case_id == case_id
    assert doc_job.document_id == doc_id

    ocr_job = await JobQueueService.run_ocr_job(document_id=doc_id, case_id=case_id, ocr_engine="paddleocr")
    assert ocr_job.job_type == JobType.OCR_EXTRACTION
    assert ocr_job.parameters["ocr_engine"] == "paddleocr"

    emb_job = await JobQueueService.generate_embeddings_job(knowledge_id=doc_id, organization_id=org_id)
    assert emb_job.job_type == JobType.KNOWLEDGE_EMBEDDINGS
    assert emb_job.parameters["organization_id"] == str(org_id)

    verif_job = await JobQueueService.execute_long_running_verification(case_id=case_id, definition_id=def_id)
    assert verif_job.job_type == JobType.LONG_RUNNING_VERIFICATION
    assert verif_job.parameters["definition_id"] == str(def_id)
