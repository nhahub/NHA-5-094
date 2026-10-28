import random
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.cases.models import Case, CaseParticipant, CaseStatus, ParticipantType
from app.domain.cases.schemas import (
    CaseCloseRequest,
    CaseCreate,
    CaseParticipantCreate,
    CaseParticipantRead,
    CaseRead,
    CaseStateRead,
    CaseUpdate,
    CustomerCaseRead,
    CustomerDocumentRead,
    CustomerDocumentRequestRead,
)
from app.domain.documents.models import Document, Evidence
from app.domain.processes.models import (
    Process,
    ProcessStatus,
    ProcessVersion,
    ProcessVersionStatus,
    Requirement,
)
from app.domain.tasks.models import Task, TaskStatus
from app.domain.verifications.models import VerificationExecution
from app.domain.workflows.models import WorkflowStage
from app.events.service import EventService


class CaseService:
    """Service managing business case lifecycle, state tracking, and events."""

    @staticmethod
    def _generate_case_number() -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d")
        rand_suffix = random.randint(1000, 9999)
        return f"CASE-{timestamp}-{rand_suffix}"

    @classmethod
    async def create_case(
        cls,
        db: AsyncSession,
        organization_id: uuid.UUID,
        created_by_user_id: uuid.UUID | None,
        case_in: CaseCreate,
        customer_user_id: uuid.UUID | None = None,
    ) -> Case:
        # Validate process version exists
        stmt = (
            select(ProcessVersion)
            .join(Process, Process.id == ProcessVersion.process_id)
            .where(
                ProcessVersion.id == case_in.process_version_id,
                Process.organization_id == organization_id,
                Process.status == ProcessStatus.ACTIVE.value,
                ProcessVersion.status == ProcessVersionStatus.PUBLISHED.value,
            )
        )
        result = await db.execute(stmt)
        process_version = result.scalars().first()
        if not process_version:
            raise ValueError(
                "Case requires a published process version belonging to the same organization."
            )

        # Find initial stage if configured
        stage_stmt = select(WorkflowStage).where(
            WorkflowStage.process_version_id == case_in.process_version_id,
            WorkflowStage.is_initial == True,
        )
        stage_res = await db.execute(stage_stmt)
        initial_stage = stage_res.scalars().first()
        initial_stage_id = initial_stage.id if initial_stage else None

        case = Case(
            organization_id=organization_id,
            process_id=process_version.process_id,
            process_version_id=case_in.process_version_id,
            case_number=cls._generate_case_number(),
            title=case_in.title,
            status=CaseStatus.OPEN.value,
            current_stage_id=initial_stage_id,
            created_by=created_by_user_id,
            case_metadata=case_in.case_metadata or {},
        )
        db.add(case)
        if customer_user_id is not None:
            db.add(
                CaseParticipant(
                    case=case,
                    user_id=customer_user_id,
                    participant_type=ParticipantType.CUSTOMER.value,
                )
            )
        await db.flush()

        # Persist the business state and its event/outbox in one transaction.
        await EventService.emit_event(
            db=db,
            organization_id=organization_id,
            case_id=case.id,
            event_type="CASE_CREATED",
            actor_type="USER" if created_by_user_id else "SYSTEM",
            actor_id=created_by_user_id,
            payload={"case_number": case.case_number, "title": case.title},
            dispatch_orchestration=True,
        )
        await db.refresh(case)

        return case

    @staticmethod
    async def _customer_case_read(db: AsyncSession, case: Case) -> CustomerCaseRead:
        stage_name = None
        if case.current_stage_id:
            stage = await db.get(WorkflowStage, case.current_stage_id)
            stage_name = stage.name if stage else None

        documents = list((await db.scalars(
            select(Document)
            .where(Document.case_id == case.id)
            .options(selectinload(Document.versions))
            .order_by(Document.created_at.desc())
        )).all())
        received_types = {doc.document_type.strip().casefold() for doc in documents}
        requirements = list((await db.scalars(
            select(Requirement).where(
                Requirement.process_version_id == case.process_version_id,
                Requirement.type == "DOCUMENT",
                Requirement.required.is_(True),
            ).order_by(Requirement.name)
        )).all())
        document_requests = [
            CustomerDocumentRequestRead(
                code=requirement.code,
                name=requirement.name,
                description=requirement.description,
                status=(
                    "RECEIVED"
                    if requirement.code.strip().casefold() in received_types
                    or requirement.name.strip().casefold() in received_types
                    else "REQUESTED"
                ),
            )
            for requirement in requirements
        ]
        return CustomerCaseRead(
            id=case.id,
            case_number=case.case_number,
            title=case.title,
            status=case.status,
            current_stage_name=stage_name,
            created_at=case.created_at,
            updated_at=case.updated_at,
            documents=[
                CustomerDocumentRead(
                    id=document.id,
                    document_type=document.document_type,
                    name=document.name,
                    status=document.status,
                    created_at=document.created_at,
                    version_id=max(document.versions, key=lambda version: version.version_number).id
                    if document.versions else None,
                    mime_type=max(document.versions, key=lambda version: version.version_number).mime_type
                    if document.versions else None,
                )
                for document in documents
            ],
            document_requests=document_requests,
        )

    @classmethod
    async def get_customer_cases(
        cls,
        db: AsyncSession,
        *,
        organization_id: uuid.UUID,
        customer_user_id: uuid.UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> list[CustomerCaseRead]:
        stmt = (
            select(Case)
            .join(CaseParticipant, CaseParticipant.case_id == Case.id)
            .where(
                Case.organization_id == organization_id,
                CaseParticipant.user_id == customer_user_id,
                CaseParticipant.participant_type == ParticipantType.CUSTOMER.value,
            )
            .distinct()
            .order_by(Case.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        cases = list((await db.scalars(stmt)).all())
        return [await cls._customer_case_read(db, case) for case in cases]

    @classmethod
    async def get_customer_case(
        cls,
        db: AsyncSession,
        *,
        case_id: uuid.UUID,
        organization_id: uuid.UUID,
        customer_user_id: uuid.UUID,
    ) -> CustomerCaseRead | None:
        stmt = (
            select(Case)
            .join(CaseParticipant, CaseParticipant.case_id == Case.id)
            .where(
                Case.id == case_id,
                Case.organization_id == organization_id,
                CaseParticipant.user_id == customer_user_id,
                CaseParticipant.participant_type == ParticipantType.CUSTOMER.value,
            )
        )
        case = (await db.scalars(stmt)).first()
        if case is None:
            return None
        return await cls._customer_case_read(db, case)

    @staticmethod
    async def get_cases(
        db: AsyncSession,
        organization_id: uuid.UUID,
        status: str | None = None,
        current_stage_id: uuid.UUID | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[Case]:
        query = select(Case).where(Case.organization_id == organization_id)
        if status:
            query = query.where(Case.status == status)
        if current_stage_id:
            query = query.where(Case.current_stage_id == current_stage_id)

        query = query.order_by(Case.created_at.desc()).offset(skip).limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def get_case_by_id(db: AsyncSession, case_id: uuid.UUID) -> Case | None:
        stmt = select(Case).where(Case.id == case_id)
        result = await db.execute(stmt)
        return result.scalars().first()

    @staticmethod
    async def get_case_state(db: AsyncSession, case_id: uuid.UUID) -> CaseStateRead | None:
        case = await CaseService.get_case_by_id(db, case_id)
        if not case:
            return None

        # Stage details
        stage_name = None
        stage_code = None
        if case.current_stage_id:
            stage_stmt = select(WorkflowStage).where(WorkflowStage.id == case.current_stage_id)
            stage_res = await db.execute(stage_stmt)
            stage = stage_res.scalars().first()
            if stage:
                stage_name = stage.name
                stage_code = stage.code

        # Documents count
        docs_stmt = select(func.count(Document.id)).where(Document.case_id == case_id)
        docs_count = (await db.execute(docs_stmt)).scalar() or 0

        # Verifications count
        verif_stmt = select(func.count(VerificationExecution.id)).where(VerificationExecution.case_id == case_id)
        verif_count = (await db.execute(verif_stmt)).scalar() or 0

        # Open tasks count
        tasks_stmt = select(func.count(Task.id)).where(
            Task.case_id == case_id,
            Task.status.in_([TaskStatus.PENDING.value, TaskStatus.ASSIGNED.value, TaskStatus.IN_PROGRESS.value]),
        )
        tasks_count = (await db.execute(tasks_stmt)).scalar() or 0

        # Evidence count
        ev_stmt = select(func.count(Evidence.id)).where(Evidence.case_id == case_id)
        ev_count = (await db.execute(ev_stmt)).scalar() or 0

        # Participants
        part_stmt = select(CaseParticipant).where(CaseParticipant.case_id == case_id)
        part_res = await db.execute(part_stmt)
        participants = list(part_res.scalars().all())

        return CaseStateRead(
            case=CaseRead.model_validate(case),
            current_stage_name=stage_name,
            current_stage_code=stage_code,
            documents_count=docs_count,
            verifications_count=verif_count,
            open_tasks_count=tasks_count,
            evidence_count=ev_count,
            participants=[CaseParticipantRead.model_validate(p) for p in participants],
        )

    @staticmethod
    async def update_case(
        db: AsyncSession, case_id: uuid.UUID, case_update: CaseUpdate
    ) -> Case | None:
        case = await CaseService.get_case_by_id(db, case_id)
        if not case:
            return None

        # State protection: reject metadata updates to closed cases
        if case.status in [CaseStatus.COMPLETED.value, CaseStatus.CANCELLED.value]:
            raise ValueError(f"Cannot modify case in '{case.status}' status.")

        if case_update.title is not None:
            case.title = case_update.title
        if case_update.case_metadata is not None:
            updated_meta = dict(case.case_metadata or {})
            updated_meta.update(case_update.case_metadata)
            case.case_metadata = updated_meta

        await db.commit()
        await db.refresh(case)
        return case

    @classmethod
    async def close_case(
        cls,
        db: AsyncSession,
        case_id: uuid.UUID,
        close_req: CaseCloseRequest,
        actor_id: uuid.UUID | None = None,
    ) -> Case:
        case = await cls.get_case_by_id(db, case_id)
        if not case:
            raise ValueError("Case not found")

        if case.status in [CaseStatus.COMPLETED.value, CaseStatus.CANCELLED.value]:
            raise ValueError(f"Case is already closed with status '{case.status}'.")

        target_status = close_req.status.value if hasattr(close_req.status, "value") else str(close_req.status)
        case.status = target_status
        case.completed_at = datetime.now(timezone.utc)

        # Keep the terminal state and its event/outbox in the same transaction.
        event_name = "CASE_COMPLETED" if target_status == CaseStatus.COMPLETED.value else "CASE_CANCELLED"
        await EventService.emit_event(
            db=db,
            organization_id=case.organization_id,
            case_id=case.id,
            event_type=event_name,
            actor_type="USER" if actor_id else "SYSTEM",
            actor_id=actor_id,
            payload={"reason": close_req.reason},
            dispatch_orchestration=event_name == "CASE_COMPLETED",
        )
        await db.refresh(case)

        return case

    @staticmethod
    async def add_participant(
        db: AsyncSession, case_id: uuid.UUID, participant_in: CaseParticipantCreate
    ) -> CaseParticipant:
        case = await CaseService.get_case_by_id(db, case_id)
        if not case:
            raise ValueError("Case not found")

        part_type = participant_in.participant_type.value if hasattr(participant_in.participant_type, "value") else str(participant_in.participant_type)
        participant = CaseParticipant(
            case_id=case_id,
            user_id=participant_in.user_id,
            participant_type=part_type,
            name=participant_in.name,
            external_reference=participant_in.external_reference,
        )
        db.add(participant)
        await db.commit()
        await db.refresh(participant)
        return participant
