import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.approvals.models import Approval, ApprovalDecision
from app.domain.approvals.schemas import ApprovalCreate, ApprovalDecisionRequest
from app.domain.audit.service import AuditService
from app.domain.cases.models import Case
from app.domain.tasks.models import Task
from app.events.service import EventService


class ApprovalService:
    """Service managing human approval requests and audit-tracked decisions."""

    @staticmethod
    async def request_approval(
        db: AsyncSession,
        approval_in: ApprovalCreate,
        *,
        organization_id: uuid.UUID | None = None,
        actor_id: uuid.UUID | None = None,
        actor_type: str = "USER",
    ) -> Approval:
        case_query = select(Case).where(Case.id == approval_in.case_id)
        if organization_id is not None:
            case_query = case_query.where(Case.organization_id == organization_id)
        case = (await db.execute(case_query)).scalars().first()
        if case is None:
            raise ValueError("Case not found in the requested organization.")
        if approval_in.task_id is not None:
            task = (await db.execute(select(Task.id).where(
                Task.id == approval_in.task_id,
                Task.case_id == case.id,
            ))).first()
            if task is None:
                raise ValueError("task_id must identify a task belonging to the case.")
        approval = Approval(
            case_id=approval_in.case_id,
            task_id=approval_in.task_id,
            approval_type=approval_in.approval_type,
            requested_at=datetime.now(timezone.utc),
            decision=ApprovalDecision.PENDING,
        )
        db.add(approval)
        await db.flush()
        await EventService.emit_event(
            db=db,
            event_type="APPROVAL_REQUESTED",
            organization_id=case.organization_id,
            actor_id=actor_id,
            actor_type=actor_type,
            case_id=case.id,
            payload={"approval_id": str(approval.id), "approval_type": approval.approval_type},
        )
        await AuditService.log_action(
            db=db,
            organization_id=case.organization_id,
            action="APPROVAL_REQUESTED",
            resource_type="APPROVAL",
            resource_id=approval.id,
            actor_type=actor_type,
            actor_id=actor_id,
            after_state={"case_id": str(case.id), "approval_type": approval.approval_type,
                         "decision": ApprovalDecision.PENDING.value},
        )
        return approval

    @staticmethod
    async def decide_approval(
        db: AsyncSession,
        approval_id: uuid.UUID,
        decided_by_user_id: uuid.UUID,
        decision_in: ApprovalDecisionRequest,
        *,
        organization_id: uuid.UUID | None = None,
        actor_role: str | None = None,
    ) -> Approval | None:
        if actor_role is not None and actor_role.upper() not in {"MANAGER", "ADMIN"}:
            raise PermissionError("Only managers or administrators can decide approvals.")
        stmt = (
            select(Approval)
            .join(Case, Case.id == Approval.case_id)
            .where(Approval.id == approval_id)
        )
        if organization_id is not None:
            stmt = stmt.where(Case.organization_id == organization_id)
        result = await db.execute(stmt)
        approval = result.scalars().first()
        if not approval:
            return None

        if approval.decision != ApprovalDecision.PENDING.value:
            raise ValueError("Only pending approval requests can be decided.")

        previous_decision = approval.decision
        case_id = approval.case_id
        approval.decision = decision_in.decision
        approval.comment = decision_in.comment
        approval.decided_by = decided_by_user_id
        approval.decided_at = datetime.now(timezone.utc)

        case = (await db.execute(select(Case).where(Case.id == case_id))).scalars().first()
        assert case is not None
        case_organization_id = case.organization_id
        approval_decision = approval.decision
        approval_decision_value = (
            approval_decision.value
            if isinstance(approval_decision, ApprovalDecision)
            else str(approval_decision)
        )
        approval_comment = approval.comment
        approved_id = approval.id
        decision_event_type = (
            "APPROVAL_GRANTED"
            if approval_decision_value == ApprovalDecision.APPROVED.value
            else "APPROVAL_REJECTED"
        )
        await EventService.emit_event(
            db=db,
            event_type=decision_event_type,
            organization_id=case_organization_id,
            actor_id=decided_by_user_id,
            actor_type="USER",
            case_id=case_id,
            payload={"approval_id": str(approved_id), "decision": approval_decision_value},
            dispatch_orchestration=True,
        )
        await AuditService.log_action(
            db=db,
            organization_id=case_organization_id,
            action="APPROVAL_DECIDED",
            resource_type="APPROVAL",
            resource_id=approved_id,
            actor_type="USER",
            actor_id=decided_by_user_id,
            before_state={"decision": str(previous_decision)},
            after_state={"decision": approval_decision_value, "comment": approval_comment},
        )
        refreshed = (await db.execute(select(Approval).where(Approval.id == approved_id))).scalars().first()
        return refreshed

    @staticmethod
    async def get_approvals_by_case(db: AsyncSession, case_id: uuid.UUID) -> list[Approval]:
        stmt = (
            select(Approval)
            .where(Approval.case_id == case_id)
            .order_by(Approval.created_at.desc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_pending_approvals(
        db: AsyncSession, organization_id: uuid.UUID
    ) -> list[Approval]:
        stmt = (
            select(Approval)
            .join(Case, Case.id == Approval.case_id)
            .where(
                Case.organization_id == organization_id,
                Approval.decision == ApprovalDecision.PENDING.value,
            )
            .order_by(Approval.requested_at.asc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())
