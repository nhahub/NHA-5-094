"""Case Orchestrator — Phase 15.

Coordinates end-to-end event-driven case lifecycles:
CASE_CREATED → Document Agent (DOCUMENT_PROCESSED) → Verification Agent (VERIFICATION_COMPLETED)
→ Workflow Agent / Workflow Engine (WORKFLOW_TRANSITION) → Case Completion or Human Review.
"""
from __future__ import annotations

import asyncio
import enum
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any
from weakref import WeakValueDictionary

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.schemas import DocumentAgentRunRequest
from app.agents.service import AgentOrchestratorService
from app.domain.cases.models import Case, CaseStatus
from app.domain.documents.intelligence import JsonModelAdapter
from app.domain.documents.models import Document
from app.domain.tasks.models import Task, TaskStatus
from app.domain.verifications.models import (
    VerificationDefinition,
    VerificationExecution,
)
from app.domain.verifications.schemas import VerificationRunRequest
from app.domain.verifications.service import VerificationService
from app.domain.workflows.models import WorkflowStage, WorkflowTransition
from app.domain.workflows.schemas import TransitionRequest
from app.domain.workflows.service import WorkflowService
from app.events.models import EventRecord
from app.events.service import ORCHESTRATION_TRUST_MARKER, EventService
from app.infrastructure.storage import StorageBackend
from app.security.models import RoleEnum, User

logger = logging.getLogger(__name__)
_event_locks: WeakValueDictionary[uuid.UUID, asyncio.Lock] = WeakValueDictionary()


class OrchestrationStatus(str, enum.Enum):
    SUCCESS = "SUCCESS"
    SKIPPED = "SKIPPED"
    WAITING_ON_HUMAN = "WAITING_ON_HUMAN"
    ERROR = "ERROR"


@dataclass
class OrchestrationResult:
    """Standardized response from the Case Orchestrator for an event invocation."""
    event_type: str
    status: OrchestrationStatus
    actions_taken: list[str] = field(default_factory=list)
    case_id: uuid.UUID | None = None
    event_id: uuid.UUID | None = None
    details: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class CaseOrchestrator:
    """Central event-driven saga orchestrator driving cases across workflow stages."""

    @classmethod
    async def dispatch_event(
        cls,
        db: AsyncSession,
        event: EventRecord,
        actor: User | None = None,
        storage: StorageBackend | None = None,
        model_adapter: JsonModelAdapter | None = None,
    ) -> OrchestrationResult:
        """Process a trusted event once per process, recording its completed outcome."""
        if event is None:
            return await cls._dispatch_event_untracked(db, event, actor, storage, model_adapter)

        lock = _event_locks.get(event.id)
        if lock is None:
            lock = asyncio.Lock()
            _event_locks[event.id] = lock

        async with lock:
            event_id = event.id
            org_id = event.organization_id
            case_id = event.case_id
            event_type = event.event_type
            existing = await cls._find_completed_dispatch(db, event_id, org_id, case_id)
            if existing is not None:
                return OrchestrationResult(
                    event_type=event_type,
                    event_id=event_id,
                    case_id=case_id,
                    status=OrchestrationStatus.SKIPPED,
                    details={
                        "reason": "Event was already orchestrated.",
                        "previous_status": existing.get("status"),
                    },
                )

            token = EventService.begin_orchestration()
            try:
                result = await cls._dispatch_event_untracked(
                    db=db,
                    event=event,
                    actor=actor,
                    storage=storage,
                    model_adapter=model_adapter,
                )
                if result.status in {
                    OrchestrationStatus.SUCCESS,
                    OrchestrationStatus.WAITING_ON_HUMAN,
                    OrchestrationStatus.SKIPPED,
                }:
                    await EventService.emit_event(
                        db=db,
                        organization_id=org_id,
                        case_id=case_id,
                        event_type="ORCHESTRATION_RESULT",
                        actor_type="SYSTEM",
                        payload={
                            "source_event_id": str(event_id),
                            "source_event_type": event_type,
                            "status": result.status.value,
                            "actions_taken": result.actions_taken,
                            "details": result.details,
                        },
                    )
                elif result.status == OrchestrationStatus.ERROR:
                    await EventService.emit_event(
                        db=db,
                        organization_id=org_id,
                        case_id=case_id,
                        event_type="ORCHESTRATION_FAILED",
                        actor_type="SYSTEM",
                        payload={
                            "source_event_id": str(event_id),
                            "source_event_type": event_type,
                            "error": result.error or "Orchestration failed.",
                        },
                    )
                return result
            finally:
                EventService.end_orchestration(token)

    @classmethod
    async def resume_event(
        cls,
        db: AsyncSession,
        event_id: uuid.UUID,
        *,
        storage: StorageBackend | None = None,
        model_adapter: JsonModelAdapter | None = None,
    ) -> OrchestrationResult:
        """Reload and retry a trusted persisted event after a failed or interrupted run."""
        event = await db.get(EventRecord, event_id)
        if event is None:
            raise LookupError("Orchestration event not found.")
        if not (event.payload or {}).get(ORCHESTRATION_TRUST_MARKER):
            raise PermissionError("Only trusted domain events can be resumed.")
        from app.core.config import settings

        if not settings.CASE_ORCHESTRATION_ENABLED:
            return OrchestrationResult(
                event_type=event.event_type,
                event_id=event.id,
                case_id=event.case_id,
                status=OrchestrationStatus.SKIPPED,
                details={"reason": "Case orchestration is disabled."},
            )
        from app.events.delivery import replay_trusted_event

        result = await replay_trusted_event(
            db=db,
            event=event,
            storage=storage,
            model_adapter=model_adapter,
        )
        if result is not None:
            return result
        return OrchestrationResult(
            event_type=event.event_type,
            event_id=event.id,
            case_id=event.case_id,
            status=OrchestrationStatus.SKIPPED,
            details={"reason": "Event delivery is already complete or currently leased."},
        )

    @staticmethod
    async def _find_completed_dispatch(
        db: AsyncSession,
        event_id: uuid.UUID,
        organization_id: uuid.UUID | None,
        case_id: uuid.UUID | None,
    ) -> dict[str, Any] | None:
        """Find a durable outcome record used to ignore sequential duplicate delivery."""
        stmt = select(EventRecord).where(
            EventRecord.event_type == "ORCHESTRATION_RESULT",
            EventRecord.payload["source_event_id"].as_string() == str(event_id),
        )
        if organization_id is not None:
            stmt = stmt.where(EventRecord.organization_id == organization_id)
        if case_id is not None:
            stmt = stmt.where(EventRecord.case_id == case_id)
        rows = (await db.execute(stmt)).scalars().all()
        return dict(rows[0].payload) if rows else None

    @classmethod
    async def _dispatch_event_untracked(
        cls,
        db: AsyncSession,
        event: EventRecord,
        actor: User | None = None,
        storage: StorageBackend | None = None,
        model_adapter: JsonModelAdapter | None = None,
    ) -> OrchestrationResult:
        """Main entrypoint routing an EventRecord to its dedicated saga handler."""
        if not event:
            return OrchestrationResult(
                event_type="UNKNOWN",
                status=OrchestrationStatus.SKIPPED,
                error="Empty event provided.",
            )

        # Pre-extract all scalar attributes to prevent post-commit lazy-loading issues
        event_id = event.id
        event_type = getattr(event, "event_type", "") or ""
        event_type_upper = event_type.strip().upper()
        case_id = event.case_id
        org_id = event.organization_id
        payload = dict(event.payload or {})
        actor_id = event.actor_id
        actor_type = str(event.actor_type or "SYSTEM").upper()
        if (
            event_type_upper == "TASK_UPDATED"
            and str(payload.get("status", "")).upper() == TaskStatus.COMPLETED.value
            and "status" in payload.get("updated_fields", [])
        ):
            event_type_upper = "TASK_COMPLETED"

        if not event_type_upper:
            return OrchestrationResult(
                event_type="UNKNOWN",
                event_id=event_id,
                status=OrchestrationStatus.SKIPPED,
                error="Invalid or empty event_type provided.",
            )

        # Skip events that are not associated with a specific case
        if not case_id and event_type_upper not in ("CASE_CREATED",):
            return OrchestrationResult(
                event_type=event_type_upper,
                event_id=event_id,
                status=OrchestrationStatus.SKIPPED,
                details={"reason": "Event has no associated case_id."},
            )

        try:
            # Resolve and validate event identity before applying any business action.
            resolved_actor = await cls._resolve_actor(db, actor_id, actor_type, org_id, actor)
            if event_type_upper == "CASE_CREATED":
                return await cls.handle_case_created(
                    db=db,
                    event_id=event_id,
                    case_id=case_id,
                    org_id=org_id,
                    payload=payload,
                    actor=resolved_actor,
                    storage=storage,
                    model_adapter=model_adapter,
                )
            elif event_type_upper == "DOCUMENT_UPLOADED":
                return await cls.handle_document_uploaded(
                    db=db,
                    event_id=event_id,
                    case_id=case_id,
                    org_id=org_id,
                    payload=payload,
                    actor=resolved_actor,
                    storage=storage,
                    model_adapter=model_adapter,
                )
            elif event_type_upper in ("DOCUMENT_PROCESSED", "DOCUMENT_PROCESSING_COMPLETED"):
                return await cls.handle_document_processed(
                    db=db,
                    event_id=event_id,
                    case_id=case_id,
                    org_id=org_id,
                    payload=payload,
                    actor=resolved_actor,
                    storage=storage,
                    model_adapter=model_adapter,
                )
            elif event_type_upper == "VERIFICATION_STARTED":
                return await cls.handle_verification_started(
                    db=db,
                    event_id=event_id,
                    case_id=case_id,
                    org_id=org_id,
                    payload=payload,
                    actor=resolved_actor,
                )
            elif event_type_upper == "VERIFICATION_COMPLETED":
                return await cls.handle_verification_completed(
                    db=db,
                    event_id=event_id,
                    case_id=case_id,
                    org_id=org_id,
                    payload=payload,
                    actor=resolved_actor,
                    storage=storage,
                    model_adapter=model_adapter,
                )
            elif event_type_upper in ("TASK_CREATED", "DOCUMENT_REVIEW_TASK_CREATED"):
                return await cls.handle_task_created(
                    db=db,
                    event_id=event_id,
                    case_id=case_id,
                    org_id=org_id,
                    payload=payload,
                    actor=resolved_actor,
                )
            elif event_type_upper == "TASK_REJECTED" or (
                event_type_upper == "TASK_UPDATED"
                and str(payload.get("status", "")).upper() == "REJECTED"
            ):
                return await cls.handle_task_rejected(
                    db=db,
                    event_id=event_id,
                    case_id=case_id,
                    org_id=org_id,
                    payload=payload,
                    actor=resolved_actor,
                )
            elif event_type_upper == "TASK_COMPLETED" or (
                event_type_upper == "TASK_UPDATED"
                and str(payload.get("status", "")).upper() == "COMPLETED"
            ):
                return await cls.handle_task_completed(
                    db=db,
                    event_id=event_id,
                    case_id=case_id,
                    org_id=org_id,
                    payload=payload,
                    actor=resolved_actor,
                    storage=storage,
                    model_adapter=model_adapter,
                )
            elif event_type_upper in (
                "APPROVAL_COMPLETED", "APPROVAL_DECIDED", "APPROVAL_GRANTED", "APPROVAL_REJECTED"
            ):
                return await cls.handle_approval_completed(
                    db=db,
                    event_id=event_id,
                    case_id=case_id,
                    org_id=org_id,
                    payload=payload,
                    actor=resolved_actor,
                    storage=storage,
                    model_adapter=model_adapter,
                )
            elif event_type_upper in ("WORKFLOW_TRANSITION", "WORKFLOW_TRANSITIONED"):
                return await cls.handle_workflow_transition(
                    db=db,
                    event_id=event_id,
                    case_id=case_id,
                    org_id=org_id,
                    payload=payload,
                    actor=resolved_actor,
                    storage=storage,
                    model_adapter=model_adapter,
                )
            elif event_type_upper in ("CASE_COMPLETED", "CASE_CLOSED"):
                return await cls.handle_case_completed(
                    db=db,
                    event_id=event_id,
                    case_id=case_id,
                    org_id=org_id,
                    payload=payload,
                    actor=resolved_actor,
                )
            else:
                return OrchestrationResult(
                    event_type=event_type_upper,
                    event_id=event_id,
                    case_id=case_id,
                    status=OrchestrationStatus.SKIPPED,
                    details={"reason": f"No registered handler for event type '{event_type_upper}'."},
                )

        except Exception as exc:
            logger.exception("Orchestrator error processing event %s (case_id=%s)", event_id, case_id)
            try:
                await db.rollback()
            except Exception:
                logger.exception("Could not roll back failed orchestration event %s.", event_id)
            return OrchestrationResult(
                event_type=event_type_upper,
                event_id=event_id,
                case_id=case_id,
                status=OrchestrationStatus.ERROR,
                error=f"Orchestration failed ({type(exc).__name__}).",
            )

    # -----------------------------------------------------------------------
    # Event Handlers
    # -----------------------------------------------------------------------

    @classmethod
    async def handle_case_created(
        cls,
        db: AsyncSession,
        event_id: uuid.UUID,
        case_id: uuid.UUID | None,
        org_id: uuid.UUID,
        payload: dict[str, Any],
        actor: User,
        storage: StorageBackend | None = None,
        model_adapter: JsonModelAdapter | None = None,
    ) -> OrchestrationResult:
        """Handle CASE_CREATED: Verify initial stage entry and initialize stage requirements."""
        actions: list[str] = []
        case = await cls._load_case(db, case_id, org_id)
        if not case:
            return OrchestrationResult(
                event_type="CASE_CREATED",
                event_id=event_id,
                status=OrchestrationStatus.ERROR,
                error=f"Case {case_id} not found.",
            )

        # If current stage is not set, initialize to the process initial stage
        if not case.current_stage_id:
            init_stage_stmt = select(WorkflowStage).where(
                WorkflowStage.process_version_id == case.process_version_id,
                WorkflowStage.is_initial == True,
            )
            res = await db.execute(init_stage_stmt)
            initial_stage = res.scalars().first()
            if initial_stage:
                trans_res = await WorkflowService.execute_transition(
                    db=db,
                    request=TransitionRequest(
                        case_id=case.id,
                        to_stage_id=initial_stage.id,
                        actor_id=actor.id,
                        actor_role=getattr(actor.role, "value", str(actor.role)),
                        rationale="Initial stage entry on case creation",
                    ),
                )
                if trans_res.allowed:
                    actions.append(f"INITIALIZED_STAGE:{initial_stage.code}")

        return OrchestrationResult(
            event_type="CASE_CREATED",
            event_id=event_id,
            case_id=case.id,
            status=OrchestrationStatus.SUCCESS,
            actions_taken=actions,
            details={"case_number": case.case_number, "current_stage_id": str(case.current_stage_id)},
        )

    @classmethod
    async def handle_document_uploaded(
        cls,
        db: AsyncSession,
        event_id: uuid.UUID,
        case_id: uuid.UUID | None,
        org_id: uuid.UUID,
        payload: dict[str, Any],
        actor: User,
        storage: StorageBackend | None = None,
        model_adapter: JsonModelAdapter | None = None,
    ) -> OrchestrationResult:
        """Handle DOCUMENT_UPLOADED: Trigger Document Agent for classification and extraction."""
        actions: list[str] = []
        doc_id_raw = payload.get("document_id") or payload.get("entity_id")
        doc_ver_id_raw = payload.get("document_version_id")

        if not doc_id_raw or not case_id:
            return OrchestrationResult(
                event_type="DOCUMENT_UPLOADED",
                event_id=event_id,
                case_id=case_id,
                status=OrchestrationStatus.SKIPPED,
                details={"reason": "Missing document_id or case_id in event payload."},
            )

        document_id = uuid.UUID(str(doc_id_raw))
        version_id = uuid.UUID(str(doc_ver_id_raw)) if doc_ver_id_raw else None

        # Execute Document Agent
        doc_result = await AgentOrchestratorService.process_document(
            db=db,
            actor=actor,
            request=DocumentAgentRunRequest(
                case_id=case_id,
                document_id=document_id,
                document_version_id=version_id,
            ),
            storage=storage,
            model_adapter=model_adapter,
        )

        actions.append(f"DOCUMENT_PROCESSED:doc_id={document_id}:class={doc_result.predicted_document_type}")
        if doc_result.review_required:
            actions.append("REVIEW_TASK_CREATED:LOW_CONFIDENCE")
            return OrchestrationResult(
                event_type="DOCUMENT_UPLOADED",
                event_id=event_id,
                case_id=case_id,
                status=OrchestrationStatus.WAITING_ON_HUMAN,
                actions_taken=actions,
                details={"review_reasons": doc_result.review_reasons},
            )

        # Trigger downstream document processed handler
        doc_proc_res = await cls.handle_document_processed(
            db=db,
            event_id=event_id,
            case_id=case_id,
            org_id=org_id,
            payload=payload,
            actor=actor,
            storage=storage,
            model_adapter=model_adapter,
        )
        actions.extend(doc_proc_res.actions_taken)

        return OrchestrationResult(
            event_type="DOCUMENT_UPLOADED",
            event_id=event_id,
            case_id=case_id,
            status=doc_proc_res.status,
            actions_taken=actions,
            details={"document_id": str(document_id), "downstream": doc_proc_res.details},
        )

    @classmethod
    async def handle_document_processed(
        cls,
        db: AsyncSession,
        event_id: uuid.UUID,
        case_id: uuid.UUID | None,
        org_id: uuid.UUID,
        payload: dict[str, Any],
        actor: User,
        storage: StorageBackend | None = None,
        model_adapter: JsonModelAdapter | None = None,
    ) -> OrchestrationResult:
        """Handle DOCUMENT_PROCESSED: Evaluate whether required stage documents are ready and run verifications."""
        actions: list[str] = []
        case = await cls._load_case(db, case_id, org_id)
        if not case or case.status in (CaseStatus.COMPLETED.value, CaseStatus.REJECTED.value, CaseStatus.CANCELLED.value):
            return OrchestrationResult(
                event_type="DOCUMENT_PROCESSED",
                event_id=event_id,
                case_id=case_id,
                status=OrchestrationStatus.SKIPPED,
                details={"reason": "Case is in terminal state or not found."},
            )

        # Check if there are active pending human review tasks for this case
        if await cls._has_blocking_tasks(db, case.id):
            return OrchestrationResult(
                event_type="DOCUMENT_PROCESSED",
                event_id=event_id,
                case_id=case.id,
                status=OrchestrationStatus.WAITING_ON_HUMAN,
                actions_taken=["WAITING_ON_EXISTING_TASKS"],
            )

        # Run applicable verifications for the current stage
        verif_executions = await cls._run_stage_verifications(db, case, actor)
        for vx in verif_executions:
            actions.append(f"VERIFICATION_EXECUTED:id={vx.id}:status={vx.status}")

        # Evaluate workflow progression directly
        wf_res = await cls._evaluate_and_progress_workflow(
            db=db,
            case=case,
            actor=actor,
            model_adapter=model_adapter,
        )
        actions.extend(wf_res.actions_taken)

        return OrchestrationResult(
            event_type="DOCUMENT_PROCESSED",
            event_id=event_id,
            case_id=case.id,
            status=wf_res.status,
            actions_taken=actions,
            details={"verifications_run": len(verif_executions), "workflow": wf_res.details},
        )

    @classmethod
    async def handle_verification_started(
        cls,
        db: AsyncSession,
        event_id: uuid.UUID,
        case_id: uuid.UUID | None,
        org_id: uuid.UUID,
        payload: dict[str, Any],
        actor: User,
    ) -> OrchestrationResult:
        """Handle VERIFICATION_STARTED: Log verification lifecycle."""
        return OrchestrationResult(
            event_type="VERIFICATION_STARTED",
            event_id=event_id,
            case_id=case_id,
            status=OrchestrationStatus.SUCCESS,
            actions_taken=["VERIFICATION_AUDIT_LOGGED"],
        )

    @classmethod
    async def handle_verification_completed(
        cls,
        db: AsyncSession,
        event_id: uuid.UUID,
        case_id: uuid.UUID | None,
        org_id: uuid.UUID,
        payload: dict[str, Any],
        actor: User,
        storage: StorageBackend | None = None,
        model_adapter: JsonModelAdapter | None = None,
    ) -> OrchestrationResult:
        """Handle VERIFICATION_COMPLETED: Consult Workflow Agent to advance stage or trigger human review."""
        actions: list[str] = []
        case = await cls._load_case(db, case_id, org_id)
        if not case or case.status in (CaseStatus.COMPLETED.value, CaseStatus.REJECTED.value, CaseStatus.CANCELLED.value):
            return OrchestrationResult(
                event_type="VERIFICATION_COMPLETED",
                event_id=event_id,
                case_id=case_id,
                status=OrchestrationStatus.SKIPPED,
                details={"reason": "Case in terminal state or not found."},
            )

        # Delegate to workflow progression evaluation
        wf_res = await cls._evaluate_and_progress_workflow(
            db=db,
            case=case,
            actor=actor,
            model_adapter=model_adapter,
        )
        actions.extend(wf_res.actions_taken)

        return OrchestrationResult(
            event_type="VERIFICATION_COMPLETED",
            event_id=event_id,
            case_id=case.id,
            status=wf_res.status,
            actions_taken=actions,
            details=wf_res.details,
        )

    @classmethod
    async def handle_task_created(
        cls,
        db: AsyncSession,
        event_id: uuid.UUID,
        case_id: uuid.UUID | None,
        org_id: uuid.UUID,
        payload: dict[str, Any],
        actor: User,
    ) -> OrchestrationResult:
        """Handle TASK_CREATED: Set case status to PENDING_REVIEW if appropriate."""
        actions: list[str] = []
        case = await cls._load_case(db, case_id, org_id)
        if case and case.status == CaseStatus.OPEN.value:
            case.status = CaseStatus.PENDING_REVIEW.value
            await db.commit()
            actions.append("CASE_STATUS_UPDATED:PENDING_REVIEW")

        return OrchestrationResult(
            event_type="TASK_CREATED",
            event_id=event_id,
            case_id=case_id,
            status=OrchestrationStatus.WAITING_ON_HUMAN,
            actions_taken=actions,
        )

    @classmethod
    async def handle_task_completed(
        cls,
        db: AsyncSession,
        event_id: uuid.UUID,
        case_id: uuid.UUID | None,
        org_id: uuid.UUID,
        payload: dict[str, Any],
        actor: User,
        storage: StorageBackend | None = None,
        model_adapter: JsonModelAdapter | None = None,
    ) -> OrchestrationResult:
        """Handle TASK_COMPLETED: Re-evaluate workflow progression when a human task is resolved."""
        actions: list[str] = []
        case = await cls._load_case(db, case_id, org_id)
        if not case:
            return OrchestrationResult(
                event_type="TASK_COMPLETED",
                event_id=event_id,
                case_id=case_id,
                status=OrchestrationStatus.ERROR,
                error="Case not found.",
            )

        # Check if remaining blocking tasks exist
        has_remaining = await cls._has_blocking_tasks(db, case.id)
        if has_remaining:
            return OrchestrationResult(
                event_type="TASK_COMPLETED",
                event_id=event_id,
                case_id=case.id,
                status=OrchestrationStatus.WAITING_ON_HUMAN,
                actions_taken=["WAITING_ON_REMAINING_TASKS"],
            )

        # Restore case status from PENDING_REVIEW back to IN_PROGRESS or OPEN if appropriate
        if case.status == CaseStatus.PENDING_REVIEW.value:
            case.status = CaseStatus.IN_PROGRESS.value
            await db.commit()
            actions.append("CASE_STATUS_UPDATED:IN_PROGRESS")

        # Re-evaluate workflow progression
        wf_res = await cls._evaluate_and_progress_workflow(
            db=db,
            case=case,
            actor=actor,
            model_adapter=model_adapter,
        )
        actions.extend(wf_res.actions_taken)

        return OrchestrationResult(
            event_type="TASK_COMPLETED",
            event_id=event_id,
            case_id=case.id,
            status=wf_res.status,
            actions_taken=actions,
            details=wf_res.details,
        )

    @classmethod
    async def handle_approval_completed(
        cls,
        db: AsyncSession,
        event_id: uuid.UUID,
        case_id: uuid.UUID | None,
        org_id: uuid.UUID,
        payload: dict[str, Any],
        actor: User,
        storage: StorageBackend | None = None,
        model_adapter: JsonModelAdapter | None = None,
    ) -> OrchestrationResult:
        """Handle APPROVAL_COMPLETED: Advance workflow if approval clears transition blockers."""
        actions: list[str] = []
        case = await cls._load_case(db, case_id, org_id)
        if not case:
            return OrchestrationResult(
                event_type="APPROVAL_COMPLETED",
                event_id=event_id,
                case_id=case_id,
                status=OrchestrationStatus.ERROR,
                error="Case not found.",
            )

        decision = str(payload.get("decision", "")).upper()
        if decision == "REJECTED":
            case.status = CaseStatus.PENDING_REVIEW.value
            await db.commit()
            return OrchestrationResult(
                event_type="APPROVAL_REJECTED",
                event_id=event_id,
                case_id=case.id,
                status=OrchestrationStatus.WAITING_ON_HUMAN,
                actions_taken=["APPROVAL_REJECTED", "CASE_STATUS_UPDATED:PENDING_REVIEW"],
                details={"approval_id": payload.get("approval_id"), "decision": decision},
            )

        # Re-evaluate workflow progression with granted approval
        wf_res = await cls._evaluate_and_progress_workflow(
            db=db,
            case=case,
            actor=actor,
            model_adapter=model_adapter,
        )
        actions.extend(wf_res.actions_taken)

        return OrchestrationResult(
            event_type="APPROVAL_COMPLETED",
            event_id=event_id,
            case_id=case.id,
            status=wf_res.status,
            actions_taken=actions,
            details=wf_res.details,
        )

    @classmethod
    async def handle_workflow_transition(
        cls,
        db: AsyncSession,
        event_id: uuid.UUID,
        case_id: uuid.UUID | None,
        org_id: uuid.UUID,
        payload: dict[str, Any],
        actor: User,
        storage: StorageBackend | None = None,
        model_adapter: JsonModelAdapter | None = None,
    ) -> OrchestrationResult:
        """Handle WORKFLOW_TRANSITION: Execute entering stage tasks and check terminal states."""
        actions: list[str] = []
        case = await cls._load_case(db, case_id, org_id)
        if not case:
            return OrchestrationResult(
                event_type="WORKFLOW_TRANSITION",
                event_id=event_id,
                case_id=case_id,
                status=OrchestrationStatus.ERROR,
                error="Case not found.",
            )

        to_stage_id_raw = payload.get("to_stage_id") or (str(case.current_stage_id) if case.current_stage_id else None)

        if not to_stage_id_raw:
            return OrchestrationResult(
                event_type="WORKFLOW_TRANSITION",
                event_id=event_id,
                case_id=case.id,
                status=OrchestrationStatus.SUCCESS,
                actions_taken=["TRANSITION_RECORDED"],
            )

        to_stage = await WorkflowService.get_stage_by_id(db, uuid.UUID(str(to_stage_id_raw)))
        if (
            to_stage is None
            or to_stage.process_version_id != case.process_version_id
            or case.current_stage_id != to_stage.id
        ):
            return OrchestrationResult(
                event_type="WORKFLOW_TRANSITION",
                event_id=event_id,
                case_id=case.id,
                status=OrchestrationStatus.SKIPPED,
                details={"reason": "Transition event is stale or targets another process version."},
            )

        if to_stage.is_terminal:
            actions.append(f"TERMINAL_STAGE_ENTERED:{to_stage.code}")
            return OrchestrationResult(
                event_type="WORKFLOW_TRANSITION",
                event_id=event_id,
                case_id=case.id,
                status=OrchestrationStatus.SUCCESS,
                actions_taken=actions,
                details={"terminal": True, "stage_code": to_stage.code},
            )

        # Automatically check if entering stage has immediate verifications ready to run
        verif_executions = await cls._run_stage_verifications(db, case, actor)
        if verif_executions:
            for vx in verif_executions:
                actions.append(f"STAGE_ENTRY_VERIFICATION:{vx.id}")
            # Progress after verifications
            wf_res = await cls._evaluate_and_progress_workflow(
                db=db,
                case=case,
                actor=actor,
                model_adapter=model_adapter,
            )
            actions.extend(wf_res.actions_taken)

        return OrchestrationResult(
            event_type="WORKFLOW_TRANSITION",
            event_id=event_id,
            case_id=case.id,
            status=OrchestrationStatus.SUCCESS,
            actions_taken=actions,
            details={"to_stage_id": str(to_stage.id) if to_stage else None},
        )

    @classmethod
    async def handle_case_completed(
        cls,
        db: AsyncSession,
        event_id: uuid.UUID,
        case_id: uuid.UUID | None,
        org_id: uuid.UUID,
        payload: dict[str, Any],
        actor: User,
    ) -> OrchestrationResult:
        """Handle CASE_COMPLETED / CASE_CLOSED: Clean up open tasks and finalize."""
        actions: list[str] = []
        case = await cls._load_case(db, case_id, org_id)
        if case and case.status != CaseStatus.COMPLETED.value:
            case.status = CaseStatus.COMPLETED.value
            await db.commit()
            actions.append("CASE_STATUS_FINALIZED:COMPLETED")

        return OrchestrationResult(
            event_type="CASE_COMPLETED",
            event_id=event_id,
            case_id=case_id,
            status=OrchestrationStatus.SUCCESS,
            actions_taken=actions,
        )

    @classmethod
    async def handle_task_rejected(
        cls,
        db: AsyncSession,
        event_id: uuid.UUID,
        case_id: uuid.UUID | None,
        org_id: uuid.UUID,
        payload: dict[str, Any],
        actor: User,
        storage: StorageBackend | None = None,
        model_adapter: JsonModelAdapter | None = None,
    ) -> OrchestrationResult:
        """Keep rejected human work in review and prevent workflow progression."""
        case = await cls._load_case(db, case_id, org_id)
        if case is None:
            return OrchestrationResult(
                event_type="TASK_REJECTED", event_id=event_id, case_id=case_id,
                status=OrchestrationStatus.ERROR, error="Case not found.",
            )
        case.status = CaseStatus.PENDING_REVIEW.value
        await db.commit()
        return OrchestrationResult(
            event_type="TASK_REJECTED", event_id=event_id, case_id=case.id,
            status=OrchestrationStatus.WAITING_ON_HUMAN,
            actions_taken=["TASK_REJECTED", "CASE_STATUS_UPDATED:PENDING_REVIEW"],
            details={"task_id": payload.get("task_id"), "resolution": "REJECTED"},
        )

    # -----------------------------------------------------------------------
    # Internal Helpers & Saga Step Execution
    # -----------------------------------------------------------------------

    @classmethod
    async def _evaluate_and_progress_workflow(
        cls,
        db: AsyncSession,
        case: Case,
        actor: User,
        model_adapter: JsonModelAdapter | None = None,
    ) -> OrchestrationResult:
        """Evaluate configured transitions and let the workflow service enforce them."""
        actions: list[str] = []

        if not case.current_stage_id:
            return OrchestrationResult(
                event_type="WORKFLOW_EVALUATION",
                case_id=case.id,
                status=OrchestrationStatus.SKIPPED,
                details={"reason": "Case has no current stage."},
            )

        # Find outgoing configured transitions from current stage
        trans_stmt = select(WorkflowTransition).where(
            WorkflowTransition.process_version_id == case.process_version_id,
            WorkflowTransition.from_stage_id == case.current_stage_id,
        )
        t_res = await db.execute(trans_stmt)
        transitions = list(t_res.scalars().all())

        if not transitions:
            return OrchestrationResult(
                event_type="WORKFLOW_EVALUATION",
                case_id=case.id,
                status=OrchestrationStatus.SUCCESS,
                actions_taken=["NO_OUTGOING_TRANSITIONS"],
            )

        # Check candidate transition eligibility deterministically
        actor_role = getattr(actor.role, "value", str(actor.role))
        for trans in transitions:
            # Test transition feasibility
            test_req = TransitionRequest(
                case_id=case.id,
                from_stage_id=case.current_stage_id,
                to_stage_id=trans.to_stage_id,
                actor_id=actor.id,
                actor_role=actor_role,
                rationale="Automated case orchestration progression check",
            )
            trans_result = await WorkflowService.execute_transition(db=db, request=test_req)

            if trans_result.allowed:
                actions.append(f"WORKFLOW_TRANSITION_EXECUTED:to_stage={trans.to_stage_id}")
                return OrchestrationResult(
                    event_type="WORKFLOW_EVALUATION",
                    case_id=case.id,
                    status=OrchestrationStatus.SUCCESS,
                    actions_taken=actions,
                    details={"new_stage_id": str(trans.to_stage_id)},
                )
            else:
                # If blocked by human approval or missing document, record reasons
                missing_doc_violations = [v for v in trans_result.violations if v.code == "MISSING_DOCUMENT"]
                missing_appr_violations = [v for v in trans_result.violations if v.code == "MISSING_APPROVAL"]
                failed_verif_violations = [v for v in trans_result.violations if v.code == "FAILED_OR_MISSING_VERIFICATION"]

                if missing_doc_violations:
                    actions.append(f"WAITING_ON_REQUIRED_DOCUMENTS:{len(missing_doc_violations)}")
                if missing_appr_violations:
                    actions.append("WAITING_ON_APPROVAL")
                if failed_verif_violations:
                    actions.append(f"VERIFICATION_REQUIREMENTS_UNMET:{len(failed_verif_violations)}")

        return OrchestrationResult(
            event_type="WORKFLOW_EVALUATION",
            case_id=case.id,
            status=OrchestrationStatus.WAITING_ON_HUMAN if actions else OrchestrationStatus.SUCCESS,
            actions_taken=actions or ["TRANSITIONS_EVALUATED_NO_ELIGIBLE_TARGET"],
        )

    @classmethod
    async def _run_stage_verifications(
        cls,
        db: AsyncSession,
        case: Case,
        actor: User,
    ) -> list[VerificationExecution]:
        """Find and execute all verification definitions mapped to the case's current stage."""
        if not case.current_stage_id:
            return []

        verif_defs_stmt = select(VerificationDefinition).where(
            VerificationDefinition.process_version_id == case.process_version_id,
            (VerificationDefinition.stage_id == case.current_stage_id) | (VerificationDefinition.stage_id.is_(None)),
        )
        res = await db.execute(verif_defs_stmt)
        definitions = list(res.scalars().all())

        executions: list[VerificationExecution] = []
        for defn in definitions:
            try:
                exec_record = await VerificationService.run_verification(
                    db=db,
                    request=VerificationRunRequest(
                        case_id=case.id,
                        verification_code=defn.code,
                        actor_type="SYSTEM",
                        actor_id=actor.id,
                    ),
                )
                executions.append(exec_record)
            except Exception as e:  # noqa: BLE001 - isolate one verifier failure from the rest of the stage.
                logger.warning("Verification %s failed during case orchestration: %s", defn.code, e)

        return executions

    @classmethod
    async def _has_blocking_tasks(cls, db: AsyncSession, case_id: uuid.UUID) -> bool:
        """Check if any unresolved pending or in-progress tasks exist for the case."""
        stmt = select(Task).where(
            Task.case_id == case_id,
            Task.status.in_(
                [TaskStatus.PENDING.value, TaskStatus.ASSIGNED.value, TaskStatus.IN_PROGRESS.value]
            ),
        )
        res = await db.execute(stmt)
        return res.scalars().first() is not None

    @classmethod
    async def _load_case(
        cls,
        db: AsyncSession,
        case_id: uuid.UUID | None,
        organization_id: uuid.UUID | None,
    ) -> Case | None:
        """Safely fetch a case with its relationships loaded."""
        if not case_id:
            return None

        stmt = (
            select(Case)
            .options(
                selectinload(Case.documents).selectinload(Document.versions),
                selectinload(Case.case_data),
            )
            .where(Case.id == case_id)
        )
        if organization_id:
            stmt = stmt.where(Case.organization_id == organization_id)

        res = await db.execute(stmt)
        return res.scalars().first()

    @classmethod
    async def _resolve_actor(
        cls,
        db: AsyncSession,
        actor_id: uuid.UUID | None,
        actor_type: str,
        org_id: uuid.UUID,
        actor: User | None,
    ) -> User:
        """Ensure a valid User instance is available for audit trail attribution."""
        if actor:
            if actor.organization_id != org_id or not actor.is_active:
                raise ValueError("Event actor is not active in the event organization.")
            return actor

        if actor_id and actor_type == "USER":
            user_stmt = select(User).where(
                User.id == actor_id,
                User.organization_id == org_id,
                User.is_active.is_(True),
            )
            user_res = await db.execute(user_stmt)
            user_obj = user_res.scalars().first()
            if user_obj:
                return user_obj
            raise ValueError("Event references an unknown or inactive organization user.")

        # Fallback system actor representation
        return User(
            id=actor_id or uuid.uuid4(),
            organization_id=org_id,
            email="system@verifia.ai",
            name="System Orchestrator",
            role=RoleEnum.EMPLOYEE,
            is_active=True,
            status="active",
        )
