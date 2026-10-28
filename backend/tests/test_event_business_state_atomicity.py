"""Domain state must not commit without its required event record."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.approvals.models import Approval, ApprovalDecision
from app.domain.approvals.schemas import ApprovalCreate, ApprovalDecisionRequest
from app.domain.approvals.service import ApprovalService
from app.domain.cases.models import Case, CaseStatus
from app.domain.cases.schemas import CaseCloseRequest, CaseCreate
from app.domain.cases.service import CaseService
from app.domain.organizations.models import Organization
from app.domain.processes.schemas import ProcessCreate
from app.domain.processes.service import ProcessService
from app.domain.tasks.models import Task, TaskReviewComment, TaskStatus
from app.domain.tasks.schemas import (
    TaskAssignmentRequest,
    TaskCreate,
    TaskResolutionRequest,
    TaskReviewCommentCreate,
)
from app.domain.tasks.service import TaskService
from app.domain.workflows.schemas import WorkflowStageCreate
from app.domain.workflows.service import WorkflowService
from app.events.service import EventService
from app.security.models import User


async def _published_case(
    db: AsyncSession, organization: Organization, user: User, *, suffix: str
) -> Case:
    process = await ProcessService.create_process(
        db,
        organization_id=organization.id,
        process_in=ProcessCreate(
            name=f"Atomic Event {suffix}", code=f"atomic_{suffix}_{uuid.uuid4().hex[:8]}"
        ),
        created_by=user.id,
    )
    version = (await ProcessService.get_versions_by_process_id(db, process.id))[0]
    await WorkflowService.create_stage(
        db,
        WorkflowStageCreate(
            process_version_id=version.id,
            name="Intake",
            code="INTAKE",
            stage_order=1,
            is_initial=True,
        ),
    )
    await ProcessService.publish_version(db, version.id)
    return await CaseService.create_case(
        db,
        organization_id=organization.id,
        created_by_user_id=user.id,
        case_in=CaseCreate(process_version_id=version.id, title=f"Atomic case {suffix}"),
    )


async def _fail_event_insert(*args, **kwargs):
    raise RuntimeError("simulated event insert failure")


@pytest.mark.asyncio
async def test_case_creation_rolls_back_when_event_insert_fails(
    db_session: AsyncSession,
    test_org: Organization,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
):
    process = await ProcessService.create_process(
        db_session,
        organization_id=test_org.id,
        process_in=ProcessCreate(name="Create Atomic Case", code=f"create_{uuid.uuid4().hex[:8]}"),
        created_by=test_user.id,
    )
    version = (await ProcessService.get_versions_by_process_id(db_session, process.id))[0]
    await WorkflowService.create_stage(
        db_session,
        WorkflowStageCreate(
            process_version_id=version.id,
            name="Intake",
            code="INTAKE",
            stage_order=1,
            is_initial=True,
        ),
    )
    await ProcessService.publish_version(db_session, version.id)
    monkeypatch.setattr(EventService, "add_event", _fail_event_insert)

    with pytest.raises(RuntimeError, match="simulated event insert failure"):
        await CaseService.create_case(
            db_session,
            organization_id=test_org.id,
            created_by_user_id=test_user.id,
            case_in=CaseCreate(process_version_id=version.id, title="must roll back"),
        )

    await db_session.rollback()
    assert await db_session.scalar(select(Case.id).where(Case.title == "must roll back")) is None


@pytest.mark.asyncio
async def test_case_close_rolls_back_when_event_insert_fails(
    db_session: AsyncSession,
    test_org: Organization,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
):
    case = await _published_case(db_session, test_org, test_user, suffix="close")
    case_id = case.id
    monkeypatch.setattr(EventService, "add_event", _fail_event_insert)

    with pytest.raises(RuntimeError, match="simulated event insert failure"):
        await CaseService.close_case(
            db_session,
            case_id,
            CaseCloseRequest(status=CaseStatus.COMPLETED, reason="close test"),
            actor_id=test_user.id,
        )

    await db_session.rollback()
    refreshed = await db_session.get(Case, case_id)
    assert refreshed is not None and refreshed.status == CaseStatus.OPEN.value


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["request", "decide"])
async def test_approval_state_rolls_back_when_event_insert_fails(
    operation: str,
    db_session: AsyncSession,
    test_org: Organization,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
):
    case = await _published_case(db_session, test_org, test_user, suffix=f"approval-{operation}")
    case_id = case.id
    approval = None
    if operation == "decide":
        approval = await ApprovalService.request_approval(
            db_session,
            ApprovalCreate(case_id=case_id, approval_type="MANAGER_REVIEW"),
            organization_id=test_org.id,
            actor_id=test_user.id,
        )
    monkeypatch.setattr(EventService, "add_event", _fail_event_insert)

    with pytest.raises(RuntimeError, match="simulated event insert failure"):
        if operation == "request":
            await ApprovalService.request_approval(
                db_session,
                ApprovalCreate(case_id=case_id, approval_type="MANAGER_REVIEW"),
                organization_id=test_org.id,
                actor_id=test_user.id,
            )
        else:
            assert approval is not None
            approval_id = approval.id
            await ApprovalService.decide_approval(
                db_session,
                approval_id,
                test_user.id,
                ApprovalDecisionRequest(decision=ApprovalDecision.APPROVED, comment="atomic test"),
                organization_id=test_org.id,
                actor_role="ADMIN",
            )

    await db_session.rollback()
    if operation == "request":
        assert await db_session.scalar(
            select(Approval.id).where(Approval.case_id == case_id)
        ) is None
    else:
        refreshed = await db_session.get(Approval, approval_id)
        assert refreshed is not None and refreshed.decision == ApprovalDecision.PENDING.value


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["assign", "start", "comment", "resolve"])
async def test_task_state_rolls_back_when_event_insert_fails(
    operation: str,
    db_session: AsyncSession,
    test_org: Organization,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
):
    case = await _published_case(db_session, test_org, test_user, suffix=f"task-{operation}")
    task = await TaskService.create_task(
        db_session,
        TaskCreate(case_id=case.id, task_type="REVIEW", title=f"{operation} task"),
        created_by_id=test_user.id,
        organization_id=test_org.id,
    )
    task_id = task.id
    monkeypatch.setattr(EventService, "add_event", _fail_event_insert)

    with pytest.raises(RuntimeError, match="simulated event insert failure"):
        if operation == "assign":
            await TaskService.assign_task(
                db_session,
                task_id,
                TaskAssignmentRequest(assigned_user_id=test_user.id),
                organization_id=test_org.id,
                actor=test_user,
            )
        elif operation == "start":
            await TaskService.start_task(
                db_session, task_id, organization_id=test_org.id, actor=test_user
            )
        elif operation == "comment":
            await TaskService.add_review_comment(
                db_session,
                task_id,
                TaskReviewCommentCreate(comment="review note"),
                organization_id=test_org.id,
                actor=test_user,
            )
        else:
            await TaskService.resolve_task(
                db_session,
                task_id,
                TaskResolutionRequest(outcome="COMPLETED", comment="review complete"),
                organization_id=test_org.id,
                actor=test_user,
            )

    await db_session.rollback()
    refreshed = await db_session.get(Task, task_id)
    assert refreshed is not None
    if operation == "assign":
        assert refreshed.assigned_user_id is None
        assert refreshed.status == TaskStatus.PENDING.value
    elif operation == "start":
        assert refreshed.status == TaskStatus.PENDING.value
    elif operation == "resolve":
        assert refreshed.status == TaskStatus.PENDING.value
        assert refreshed.completed_at is None
    else:
        assert await db_session.scalar(
            select(TaskReviewComment.id).where(TaskReviewComment.task_id == task_id)
        ) is None
