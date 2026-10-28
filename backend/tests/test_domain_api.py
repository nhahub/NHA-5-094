"""
API integration tests for Phase 3: REST API endpoints for Processes, Cases, Tasks, and Events.
Uses httpx AsyncClient with database and auth dependency overrides.
"""
import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.organizations.models import Organization
from app.security.models import User
from app.domain.processes.service import ProcessService
from app.domain.processes.schemas import (
    ProcessCreate,
    ProcessVersionCreate,
    WorkflowStageCreate,
)
from app.domain.cases.service import CaseService
from app.domain.cases.schemas import CaseCreate
from app.domain.audit.models import AuditLog
from app.events.models import EventRecord


@pytest.mark.asyncio
async def test_processes_api_endpoints(
    async_client: AsyncClient, test_org: Organization
):
    """Test Process and Process Version REST API endpoints."""
    # 1. POST /api/v1/processes
    res = await async_client.post(
        "/api/v1/processes",
        json={
            "name": "Trade Finance Process",
            "code": "TRADE_FINANCE_01",
            "description": "Letters of credit and bill of lading verification",
        },
    )
    assert res.status_code == 201, res.text
    proc_data = res.json()
    proc_id = proc_data["id"]
    assert proc_data["name"] == "Trade Finance Process"
    assert proc_data["code"] == "TRADE_FINANCE_01"

    # 2. GET /api/v1/processes
    res = await async_client.get("/api/v1/processes")
    assert res.status_code == 200
    processes = res.json()
    assert any(p["id"] == proc_id for p in processes)

    # 3. GET /api/v1/processes/{id}
    res = await async_client.get(f"/api/v1/processes/{proc_id}")
    assert res.status_code == 200
    assert res.json()["id"] == proc_id

    # 4. GET /api/v1/processes/{id}/versions — should have auto-created draft v1
    res = await async_client.get(f"/api/v1/processes/{proc_id}/versions")
    assert res.status_code == 200
    versions = res.json()
    assert len(versions) >= 1
    ver_id = versions[0]["id"]
    assert versions[0]["status"] == "DRAFT"
    assert versions[0]["version_number"] == 1  # auto-incremented integer

    # 5. POST /api/v1/processes/{id}/versions — create second draft
    res = await async_client.post(
        f"/api/v1/processes/{proc_id}/versions",
        json={"configuration": {"description": "Second draft"}},
    )
    assert res.status_code == 201, res.text
    v2 = res.json()
    assert v2["version_number"] == 2
    assert v2["status"] == "DRAFT"

    # 6. POST /api/v1/processes/versions/{ver_id}/stages
    res = await async_client.post(
        f"/api/v1/processes/versions/{ver_id}/stages",
        json={"name": "Bill of Lading Check", "code": "BOL_CHECK", "stage_order": 1, "is_initial": True},
    )
    assert res.status_code == 201, res.text
    stage_id = res.json()["id"]

    # 7. POST /api/v1/processes/versions/{ver_id}/requirements
    res = await async_client.post(
        f"/api/v1/processes/versions/{ver_id}/requirements",
        json={
            "name": "Bill of Lading",
            "code": "REQ_BOL",
            "type": "DOCUMENT",
            "required": True,
            "stage_id": stage_id,
        },
    )
    assert res.status_code == 201, res.text
    assert res.json()["name"] == "Bill of Lading"

    # 8. POST /api/v1/processes/versions/{ver_id}/rules
    res = await async_client.post(
        f"/api/v1/processes/versions/{ver_id}/rules",
        json={
            "name": "Bill of Lading Date Validity",
            "code": "BL_DATE_VALIDITY",
            "expression": {"bl_date": "recent"},
        },
    )
    assert res.status_code == 201, res.text
    assert res.json()["code"] == "BL_DATE_VALIDITY"

    # 9. POST /api/v1/processes/versions/{ver_id}/publish
    res = await async_client.post(f"/api/v1/processes/versions/{ver_id}/publish")
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "PUBLISHED"

    # 10. Test immutability via API (adding stage to published version fails)
    res = await async_client.post(
        f"/api/v1/processes/versions/{ver_id}/stages",
        json={"name": "Post Publish Stage", "code": "POST_PUB", "stage_order": 2},
    )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_cases_api_endpoints(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_org: Organization,
    test_user: User,
):
    """Test Case management REST API endpoints."""
    # Setup process with a published version and initial stage
    proc = await ProcessService.create_process(
        db=db_session,
        process_in=ProcessCreate(name="Vendor Due Diligence", code="VENDOR_DD"),
        organization_id=test_org.id,
    )
    versions = await ProcessService.get_versions_by_process_id(db=db_session, process_id=proc.id)
    ver = versions[0]
    await ProcessService.add_stage_to_version(
        db=db_session,
        version_id=ver.id,
        stage_in=WorkflowStageCreate(name="Risk Screening", code="RISK_SCREEN", stage_order=1, is_initial=True),
    )
    await ProcessService.publish_version(db=db_session, version_id=ver.id)

    # 1. POST /api/v1/cases
    res = await async_client.post(
        "/api/v1/cases",
        json={
            "process_version_id": str(ver.id),
            "title": "Acme Supplier Vetting",
            "case_metadata": {"supplier_id": "SUPP-991"},
        },
    )
    assert res.status_code == 201, res.text
    case_data = res.json()
    case_id = case_data["id"]
    assert case_data["title"] == "Acme Supplier Vetting"
    assert case_data["case_number"].startswith("CASE-")
    assert case_data["status"] == "OPEN"

    # 2. GET /api/v1/cases
    res = await async_client.get("/api/v1/cases")
    assert res.status_code == 200
    cases = res.json()
    assert any(c["id"] == case_id for c in cases)

    # 3. GET /api/v1/cases/{id}
    res = await async_client.get(f"/api/v1/cases/{case_id}")
    assert res.status_code == 200
    assert res.json()["id"] == case_id

    # 4. POST /api/v1/cases/{id}/participants
    res = await async_client.post(
        f"/api/v1/cases/{case_id}/participants",
        json={"user_id": str(test_user.id), "participant_type": "REVIEWER", "name": "Compliance Officer"},
    )
    assert res.status_code == 201, res.text
    assert res.json()["participant_type"] == "REVIEWER"

    # 5. GET /api/v1/cases/{id}/state
    res = await async_client.get(f"/api/v1/cases/{case_id}/state")
    assert res.status_code == 200, res.text
    state_data = res.json()
    assert state_data["case"]["id"] == case_id
    assert len(state_data["participants"]) == 1

    # 6. GET /api/v1/cases/{id}/events
    res = await async_client.get(f"/api/v1/cases/{case_id}/events")
    assert res.status_code == 200
    events = res.json()
    assert len(events) >= 1
    assert any(e["event_type"] == "CASE_CREATED" for e in events)

    # 7. PATCH /api/v1/cases/{id}
    res = await async_client.patch(
        f"/api/v1/cases/{case_id}",
        json={"title": "Acme Supplier Vetting (Expedited)"},
    )
    assert res.status_code == 200
    assert res.json()["title"] == "Acme Supplier Vetting (Expedited)"

    # 8. POST /api/v1/cases/{id}/close
    res = await async_client.post(
        f"/api/v1/cases/{case_id}/close",
        json={
            "status": "COMPLETED",
            "reason": "Vendor approved for tier-1 supplier status",
        },
    )
    assert res.status_code == 200
    assert res.json()["status"] == "COMPLETED"


@pytest.mark.asyncio
async def test_tasks_api_endpoints(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_org: Organization,
    test_user: User,
):
    """Test Task REST API endpoints."""
    # Setup process & case
    proc = await ProcessService.create_process(
        db=db_session,
        process_in=ProcessCreate(name="Insurance Claim", code="INS_CLAIM"),
        organization_id=test_org.id,
    )
    versions = await ProcessService.get_versions_by_process_id(db=db_session, process_id=proc.id)
    ver = versions[0]
    await ProcessService.add_stage_to_version(
        db_session,
        ver.id,
        WorkflowStageCreate(name="Intake", code="CLAIM_INTAKE_API", stage_order=1, is_initial=True),
    )
    await ProcessService.publish_version(db_session, ver.id)
    case = await CaseService.create_case(
        db=db_session,
        organization_id=test_org.id,
        created_by_user_id=test_user.id,
        case_in=CaseCreate(process_version_id=ver.id, title="Water Damage Claim #301"),
    )

    # 1. POST /api/v1/tasks
    res = await async_client.post(
        "/api/v1/tasks",
        json={
            "case_id": str(case.id),
            "task_type": "AUDIT",
            "title": "Review Property Photos",
            "priority": "HIGH",
            "assigned_user_id": str(test_user.id),
        },
    )
    assert res.status_code == 201, res.text
    task_data = res.json()
    task_id = task_data["id"]
    assert task_data["title"] == "Review Property Photos"
    assert task_data["status"] == "ASSIGNED"
    assert task_data["priority"] == "HIGH"

    # 2. GET /api/v1/tasks?case_id=...
    res = await async_client.get(f"/api/v1/tasks?case_id={case.id}")
    assert res.status_code == 200
    tasks = res.json()
    assert len(tasks) >= 1
    assert any(t["id"] == task_id for t in tasks)

    # 3. GET /api/v1/tasks/my
    res = await async_client.get("/api/v1/tasks/my")
    assert res.status_code == 200
    assert any(t["id"] == task_id for t in res.json())

    # 4. GET /api/v1/tasks/case/{case_id}
    res = await async_client.get(f"/api/v1/tasks/case/{case.id}")
    assert res.status_code == 200
    assert any(t["id"] == task_id for t in res.json())

    # 5. GET /api/v1/tasks/{id}
    res = await async_client.get(f"/api/v1/tasks/{task_id}")
    assert res.status_code == 200
    assert res.json()["id"] == task_id

    # 6. Resolve the task through the human-review completion endpoint.
    res = await async_client.post(
        f"/api/v1/tasks/{task_id}/resolve",
        json={
            "outcome": "COMPLETED",
            "comment": "Verified photo count and evidence.",
        },
    )
    assert res.status_code == 200
    result = res.json()
    assert result["status"] == "COMPLETED"
    assert result["completed_at"] is not None
    assert result["completion_metadata"]["human_resolution"]["comment"] == "Verified photo count and evidence."


@pytest.mark.asyncio
async def test_approval_api_persists_decisions_and_audit_trail(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_org: Organization,
    test_user: User,
):
    process = await ProcessService.create_process(
        db_session,
        test_org.id,
        ProcessCreate(name="Approval Lifecycle", code="APPROVAL_LIFECYCLE"),
    )
    version = (await ProcessService.get_versions_by_process_id(db_session, process.id))[0]
    await ProcessService.add_stage_to_version(
        db_session,
        version.id,
        WorkflowStageCreate(name="Review", code="APPROVAL_REVIEW", stage_order=1, is_initial=True),
    )
    await ProcessService.publish_version(db_session, version.id)
    case = await CaseService.create_case(
        db_session,
        organization_id=test_org.id,
        created_by_user_id=test_user.id,
        case_in=CaseCreate(process_version_id=version.id, title="Approval test"),
    )

    requested = await async_client.post(
        "/api/v1/approvals",
        json={"case_id": str(case.id), "approval_type": "MANAGER_REVIEW"},
    )
    assert requested.status_code == 201, requested.text
    approval = requested.json()
    assert approval["approval_type"] == "MANAGER_REVIEW"
    assert approval["decision"] == "PENDING"

    decided = await async_client.post(
        f"/api/v1/approvals/{approval['id']}/decide",
        json={"decision": "APPROVED", "comment": "Reviewed and approved."},
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["decision"] == "APPROVED"
    assert decided.json()["decided_by_user_id"] == str(test_user.id)

    events = list((await db_session.execute(
        select(EventRecord).where(EventRecord.case_id == case.id)
    )).scalars().all())
    assert {"APPROVAL_REQUESTED", "APPROVAL_GRANTED"} <= {event.event_type for event in events}
    audit_rows = list((await db_session.execute(
        select(AuditLog).where(AuditLog.resource_id == uuid.UUID(approval["id"]))
    )).scalars().all())
    assert {"APPROVAL_REQUESTED", "APPROVAL_DECIDED"} <= {row.action for row in audit_rows}

    duplicate_decision = await async_client.post(
        f"/api/v1/approvals/{approval['id']}/decide",
        json={"decision": "REJECTED", "comment": "Duplicate decision"},
    )
    assert duplicate_decision.status_code == 409
