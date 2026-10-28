import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.domain.approvals.models import Approval, ApprovalDecision
from app.domain.approvals.schemas import ApprovalCreate, ApprovalDecisionRequest
from app.domain.approvals.service import ApprovalService
from app.domain.audit.models import AuditLog
from app.domain.cases.schemas import CaseCreate
from app.domain.cases.service import CaseService
from app.domain.documents.models import Document, Evidence
from app.domain.processes.schemas import ProcessCreate
from app.domain.processes.service import ProcessService
from app.domain.tasks.models import TaskReviewComment
from app.domain.tasks.schemas import TaskCreate
from app.domain.tasks.service import TaskService
from app.domain.workflows.schemas import WorkflowStageCreate
from app.domain.workflows.service import WorkflowService
from app.events.models import EventDelivery, EventRecord
from app.security.models import Organization, RoleEnum, User


async def _published_case(db: AsyncSession, organization: Organization):
    process = await ProcessService.create_process(
        db, organization_id=organization.id,
        process_in=ProcessCreate(name="Human Review", code=f"HITL_{uuid.uuid4().hex[:8]}"),
    )
    version = (await ProcessService.get_versions_by_process_id(db, process.id))[0]
    await WorkflowService.create_stage(
        db,
        WorkflowStageCreate(
            process_version_id=version.id, name="Review", code="REVIEW",
            stage_order=1, is_initial=True,
        ),
    )
    await ProcessService.publish_version(db, version.id)
    case = await CaseService.create_case(
        db, organization_id=organization.id, created_by_user_id=None,
        case_in=CaseCreate(title="Review case", process_version_id=version.id),
    )
    return case


@pytest.mark.asyncio
async def test_review_bundle_comments_evidence_and_resolution(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_org: Organization,
    test_user: User,
):
    case = await _published_case(db_session, test_org)
    task = await TaskService.create_task(
        db_session,
        TaskCreate(case_id=case.id, task_type="DOCUMENT_REVIEW", title="Review invoice",
                   assigned_user_id=test_user.id),
        created_by_type="SYSTEM",
    )
    evidence = Evidence(case_id=case.id, evidence_type="DOCUMENT", description="Invoice source")
    db_session.add(evidence)
    await db_session.commit()
    await db_session.refresh(evidence)

    response = await async_client.post(
        f"/api/v1/tasks/{task.id}/comments",
        json={"comment": "The invoice total matches.", "evidence_ids": [str(evidence.id)]},
    )
    assert response.status_code == 201, response.text
    assert response.json()["evidence_ids"] == [str(evidence.id)]

    response = await async_client.post(
        f"/api/v1/tasks/{task.id}/resolve",
        json={"outcome": "COMPLETED", "comment": "Verified against source.",
              "evidence_ids": [str(evidence.id)]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "COMPLETED"
    assert response.json()["completion_metadata"]["human_resolution"]["resolved_by"] == str(test_user.id)

    bundle_response = await async_client.get(f"/api/v1/cases/{case.id}/review")
    assert bundle_response.status_code == 200, bundle_response.text
    bundle = bundle_response.json()
    assert bundle["case"]["id"] == str(case.id)
    assert bundle["review_tasks"][0]["comments"]
    assert bundle["evidence"][0]["id"] == str(evidence.id)
    assert "discrepancies" in bundle and "recommendations" in bundle

    assert (await db_session.execute(
        select(EventRecord).where(EventRecord.case_id == case.id, EventRecord.event_type == "TASK_COMPLETED")
    )).scalars().first() is not None
    assert (await db_session.execute(
        select(AuditLog).where(AuditLog.resource_id == task.id, AuditLog.action == "TASK_RESOLVED")
    )).scalars().first() is not None

    comments = (await db_session.execute(
        select(TaskReviewComment).where(TaskReviewComment.task_id == task.id)
    )).scalars().all()
    assert len(comments) == 2  # discussion entry plus immutable resolution record


@pytest.mark.asyncio
async def test_review_evidence_links_must_be_from_same_case(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_org: Organization,
):
    case = await _published_case(db_session, test_org)
    other_case = await _published_case(db_session, test_org)
    task = await TaskService.create_task(
        db_session, TaskCreate(case_id=case.id, title="Review evidence"), created_by_type="SYSTEM"
    )
    evidence = Evidence(case_id=other_case.id, evidence_type="DOCUMENT")
    db_session.add(evidence)
    await db_session.commit()
    await db_session.refresh(evidence)

    response = await async_client.post(
        f"/api/v1/tasks/{task.id}/comments",
        json={"comment": "Cross-case evidence must fail.", "evidence_ids": [str(evidence.id)]},
    )
    assert response.status_code == 409

    foreign_org = Organization(
        name="Foreign Evidence Organization",
        slug=f"foreign-evidence-{uuid.uuid4().hex[:8]}",
        status="active",
        settings={},
        is_active=True,
    )
    db_session.add(foreign_org)
    await db_session.flush()
    foreign_case = await _published_case(db_session, foreign_org)
    foreign_evidence = Evidence(
        case_id=foreign_case.id,
        evidence_type="DOCUMENT",
        description="Must not be attached across tenants.",
    )
    db_session.add(foreign_evidence)
    await db_session.commit()

    foreign_response = await async_client.post(
        f"/api/v1/tasks/{task.id}/comments",
        json={
            "comment": "Cross-tenant evidence must fail.",
            "evidence_ids": [str(foreign_evidence.id)],
        },
    )
    assert foreign_response.status_code == 409


@pytest.mark.asyncio
async def test_only_manager_can_decide_approval(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_org: Organization,
    test_user: User,
):
    case = await _published_case(db_session, test_org)
    approval = await ApprovalService.request_approval(
        db_session, ApprovalCreate(case_id=case.id, approval_type="PAYMENT"),
        organization_id=test_org.id, actor_id=test_user.id,
    )
    test_user.role = RoleEnum.EMPLOYEE
    pending_response = await async_client.get("/api/v1/approvals/pending")
    assert pending_response.status_code == 403
    response = await async_client.post(
        f"/api/v1/approvals/{approval.id}/decide",
        json={"decision": "APPROVED", "comment": "Looks correct."},
    )
    assert response.status_code == 403
    stored = await db_session.get(Approval, approval.id)
    assert stored.decision == "PENDING"

    test_user.role = RoleEnum.MANAGER
    pending_response = await async_client.get("/api/v1/approvals/pending")
    assert pending_response.status_code == 200
    assert any(item["id"] == str(approval.id) for item in pending_response.json())
    response = await async_client.post(
        f"/api/v1/approvals/{approval.id}/decide",
        json={"decision": "APPROVED", "comment": "Looks correct."},
    )
    assert response.status_code == 200, response.text
    assert response.json()["decided_by_user_id"] == str(test_user.id)


@pytest.mark.asyncio
async def test_rejected_approval_keeps_case_in_human_review(
    db_session: AsyncSession,
    test_org: Organization,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, "CASE_ORCHESTRATION_ENABLED", True)
    case = await _published_case(db_session, test_org)
    approval = await ApprovalService.request_approval(
        db_session, ApprovalCreate(case_id=case.id, approval_type="FINAL"),
        organization_id=test_org.id, actor_id=test_user.id,
    )
    await ApprovalService.decide_approval(
        db_session, approval.id, test_user.id,
        ApprovalDecisionRequest(decision=ApprovalDecision.REJECTED, comment="Evidence is incomplete."),
        organization_id=test_org.id, actor_role="MANAGER",
    )
    rejection_event = (await db_session.execute(
        select(EventRecord).where(
            EventRecord.case_id == case.id,
            EventRecord.event_type == "APPROVAL_REJECTED",
        )
    )).scalars().one()
    assert rejection_event.payload["decision"] == "REJECTED"
    delivery = (await db_session.execute(
        select(EventDelivery).where(EventDelivery.event_id == rejection_event.id)
    )).scalars().one()
    assert delivery.status == "COMPLETED", delivery.last_error_code
    refreshed_case = await CaseService.get_case_by_id(db_session, case.id)
    assert refreshed_case.status == "PENDING_REVIEW"


@pytest.mark.asyncio
async def test_manager_can_assign_review_task_to_active_org_user(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_org: Organization,
    test_user: User,
):
    case = await _published_case(db_session, test_org)
    task = await TaskService.create_task(
        db_session, TaskCreate(case_id=case.id, title="Assign this review"), created_by_type="SYSTEM"
    )
    assignee = User(
        organization_id=test_org.id, email="reviewer@verifia.ai", name="Reviewer",
        role=RoleEnum.EMPLOYEE, hashed_password="unused", status="active", is_active=True,
    )
    db_session.add(assignee)
    await db_session.commit()
    await db_session.refresh(assignee)

    response = await async_client.post(
        f"/api/v1/tasks/{task.id}/assign", json={"assigned_user_id": str(assignee.id)}
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ASSIGNED"
    assert response.json()["assigned_user_id"] == str(assignee.id)

    test_user.role = RoleEnum.EMPLOYEE
    response = await async_client.post(f"/api/v1/tasks/{task.id}/start")
    assert response.status_code == 403

    unassigned = await TaskService.create_task(
        db_session, TaskCreate(case_id=case.id, title="Claim this review"), created_by_type="SYSTEM"
    )
    response = await async_client.post(f"/api/v1/tasks/{unassigned.id}/start")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "IN_PROGRESS"
    assert response.json()["assigned_user_id"] == str(test_user.id)


@pytest.mark.asyncio
async def test_review_bundle_task_document_and_evidence_are_organization_scoped(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_org: Organization,
):
    other_org = Organization(
        name="Other Organization", slug=f"other-{uuid.uuid4().hex[:8]}",
        status="active", settings={}, is_active=True,
    )
    db_session.add(other_org)
    await db_session.commit()
    case = await _published_case(db_session, other_org)
    task = await TaskService.create_task(
        db_session, TaskCreate(case_id=case.id, title="Private review"), created_by_type="SYSTEM"
    )
    document = Document(
        case_id=case.id,
        document_type="INVOICE",
        name="foreign-private-invoice.pdf",
        status="PENDING",
    )
    evidence = Evidence(
        case_id=case.id,
        evidence_type="DOCUMENT",
        description="Foreign case evidence must remain private.",
    )
    db_session.add_all([document, evidence])
    await db_session.commit()

    review_bundle = await async_client.get(f"/api/v1/cases/{case.id}/review")
    assert review_bundle.status_code == 404
    assert (await async_client.get(f"/api/v1/tasks/{task.id}")).status_code == 404
    assert (await async_client.get(f"/api/v1/documents/{document.id}")).status_code == 404
    # Evidence has no standalone API; it is returned only through case/task review bundles.
    assert "Foreign case evidence" not in review_bundle.text
