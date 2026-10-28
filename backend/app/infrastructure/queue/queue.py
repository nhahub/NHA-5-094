import enum
import logging
import uuid
from typing import Any, Dict, Optional
from pydantic import BaseModel
from app.core.config import settings

logger = logging.getLogger(settings.APP_NAME)


class JobType(str, enum.Enum):
    DOCUMENT_PROCESSING = "DOCUMENT_PROCESSING"
    OCR_EXTRACTION = "OCR_EXTRACTION"
    KNOWLEDGE_EMBEDDINGS = "KNOWLEDGE_EMBEDDINGS"
    LONG_RUNNING_VERIFICATION = "LONG_RUNNING_VERIFICATION"
    AGENT_DELIBERATION = "AGENT_DELIBERATION"


class JobPayload(BaseModel):
    job_id: str
    job_type: JobType
    case_id: Optional[uuid.UUID] = None
    document_id: Optional[uuid.UUID] = None
    parameters: Dict[str, Any] = {}


class JobQueueService:
    """Service defining and dispatching asynchronous background tasks."""

    @staticmethod
    async def enqueue_job(job: JobPayload) -> bool:
        """Enqueues a background job into Redis queue."""
        logger.info("Enqueued job [%s] of type [%s] for case [%s]", job.job_id, job.job_type, job.case_id)
        # In full production, this pushes to a Redis list / Celery / RQ
        return True

    @staticmethod
    async def process_document_job(document_id: uuid.UUID, case_id: uuid.UUID) -> JobPayload:
        job = JobPayload(
            job_id=str(uuid.uuid4()),
            job_type=JobType.DOCUMENT_PROCESSING,
            case_id=case_id,
            document_id=document_id,
        )
        await JobQueueService.enqueue_job(job)
        return job

    @staticmethod
    async def run_ocr_job(document_id: uuid.UUID, case_id: uuid.UUID, ocr_engine: str = "tesseract") -> JobPayload:
        job = JobPayload(
            job_id=str(uuid.uuid4()),
            job_type=JobType.OCR_EXTRACTION,
            case_id=case_id,
            document_id=document_id,
            parameters={"ocr_engine": ocr_engine},
        )
        await JobQueueService.enqueue_job(job)
        return job

    @staticmethod
    async def generate_embeddings_job(knowledge_id: uuid.UUID, organization_id: uuid.UUID) -> JobPayload:
        job = JobPayload(
            job_id=str(uuid.uuid4()),
            job_type=JobType.KNOWLEDGE_EMBEDDINGS,
            parameters={"knowledge_id": str(knowledge_id), "organization_id": str(organization_id)},
        )
        await JobQueueService.enqueue_job(job)
        return job

    @staticmethod
    async def execute_long_running_verification(case_id: uuid.UUID, definition_id: uuid.UUID) -> JobPayload:
        job = JobPayload(
            job_id=str(uuid.uuid4()),
            job_type=JobType.LONG_RUNNING_VERIFICATION,
            case_id=case_id,
            parameters={"definition_id": str(definition_id)},
        )
        await JobQueueService.enqueue_job(job)
        return job
