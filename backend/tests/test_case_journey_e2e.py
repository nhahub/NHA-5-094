"""A disposable authenticated API journey through document review and approval."""
from __future__ import annotations

import uuid

import pymupdf
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.domain.audit.service import AuditService
from app.domain.documents.router import get_document_storage
from app.domain.organizations.models import Organization
from app.domain.processes.schemas import (
    BusinessRuleCreate,
    ProcessCreate,
    RequirementCreate,
    VerificationDefinitionCreate,
)
from app.domain.processes.service import ProcessService
from app.domain.workflows.schemas import WorkflowStageCreate, WorkflowTransitionCreate
from app.domain.workflows.service import WorkflowService
from app.infrastructure.storage import LocalFileStorage
from app.main import app
from app.security.models import RoleEnum, User
from app.security.router import get_current_user
from app.security.service import AuthService


class DeterministicInvoiceAdapter:
    """Test double for the model boundary; parsing and persistence stay real."""

    async def generate_json(self, *, system_prompt, user_prompt, response_schema):
        if "class_id" in response_schema.get("properties", {}):
            return {
                "class_id": "invoice",
                "confidence": 0.99,
                "rationale": "Deterministic integration-test fixture",
            }, "test-fixture"

        return {
            "fields": {
                "invoice_number": {
                    "value": "INV-2026-001",
                    "confidence": 0.99,
                    "citations": [{"block_index": 0, "quote": "Invoice INV-2026-001"}],
                },
                "supplier": {
                    "value": "Acme Global Trading",
                    "confidence": 0.99,
                    "citations": [{"block_index": 1, "quote": "Supplier: Acme Global Trading"}],
                },
                "invoice_date": {
                    "value": "2026-10-01",
                    "confidence": 0.99,
                    "citations": [{"block_index": 2, "quote": "Date: 2026-10-01"}],
                },
                "currency": {
                    "value": "USD",
                    "confidence": 0.99,
                    "citations": [{"block_index": 3, "quote": "Currency: USD"}],
                },
                "items": {
                    "value": [],
                    "confidence": 0.99,
                    "citations": [{"block_index": 4, "quote": "Total: 5000.00"}],
                },
                "total": {
                    "value": 5000.00,
                    "confidence": 0.99,
                    "citations": [{"block_index": 4, "quote": "Total: 5000.00"}],
                },
            }
        }, "test-fixture"


def _invoice_pdf() -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    for index, line in enumerate((
        "Invoice INV-2026-001",
        "Supplier: Acme Global Trading",
        "Date: 2026-10-01",
        "Currency: USD",
        "Total: 5000.00",
    )):
        page.insert_text((72, 72 + index * 24), line)
    content = document.tobytes()
    document.close()
    return content


def _authorization(user: User) -> dict[str, str]:
    token = AuthService.create_access_token(
        user.id,
        user.organization_id,
        user.role,
        token_version=user.token_version,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_authenticated_case_journey_persists_processing_verification_and_approval(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_org: Organization,
    test_user: User,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    """Use the actual API and isolated SQLite fixture; only the model is faked."""
    monkeypatch.setattr(settings, "CASE_ORCHESTRATION_ENABLED", False)

    employee = User(
        organization_id=test_org.id,
        email="journey-employee@example.test",
        name="Journey Employee",
        hashed_password="not-used-by-this-token-test",
        role=RoleEnum.EMPLOYEE,
        status="active",
        is_active=True,
    )
    manager = User(
        organization_id=test_org.id,
        email="journey-manager@example.test",
        name="Journey Manager",
        hashed_password="not-used-by-this-token-test",
        role=RoleEnum.MANAGER,
        status="active",
        is_active=True,
    )
    customer = User(
        organization_id=test_org.id,
        email="journey-customer@example.test",
        name="Journey Customer",
        hashed_password="not-used-by-this-token-test",
        role=RoleEnum.CUSTOMER,
        status="active",
        is_active=True,
    )
    admin = User(
        organization_id=test_org.id,
        email="journey-admin@example.test",
        name="Journey Admin",
        hashed_password="not-used-by-this-token-test",
        role=RoleEnum.ADMIN,
        status="active",
        is_active=True,
    )
    db_session.add_all([employee, manager, customer, admin])
    await db_session.commit()
    for user in (employee, manager, customer, admin):
        await db_session.refresh(user)

    # Replace the ordinary fixture's identity override with the real JWT lookup.
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides[get_document_storage] = lambda: LocalFileStorage(root=str(tmp_path))
    from app.domain.documents import intelligence

    monkeypatch.setattr(intelligence, "get_json_model_adapter", DeterministicInvoiceAdapter)

    process = await ProcessService.create_process(
        db_session,
        organization_id=test_org.id,
        process_in=ProcessCreate(name="Journey Import Review", code=f"journey_{uuid.uuid4().hex[:8]}"),
        created_by=manager.id,
    )
    version = (await ProcessService.get_versions_by_process_id(db_session, process.id))[0]
    stages = {}
    for code, order, initial, terminal in (
        ("INTAKE", 1, True, False),
        ("DOCUMENT_REVIEW", 2, False, False),
        ("VERIFICATION", 3, False, False),
        ("MANAGER_APPROVAL", 4, False, False),
        ("COMPLETED", 5, False, True),
    ):
        stages[code] = await WorkflowService.create_stage(
            db_session,
            WorkflowStageCreate(
                process_version_id=version.id,
                name=code.replace("_", " ").title(),
                code=code,
                stage_order=order,
                is_initial=initial,
                is_terminal=terminal,
            ),
        )

    transitions = (
        ("INTAKE", "DOCUMENT_REVIEW", None, False),
        ("DOCUMENT_REVIEW", "VERIFICATION", None, False),
        ("VERIFICATION", "MANAGER_APPROVAL", "MANAGER", False),
        ("MANAGER_APPROVAL", "COMPLETED", "MANAGER", True),
    )
    for source, target, role, requires_approval in transitions:
        await WorkflowService.create_transition(
            db_session,
            WorkflowTransitionCreate(
                process_version_id=version.id,
                from_stage_id=stages[source].id,
                to_stage_id=stages[target].id,
                name=f"{source} to {target}",
                required_role=role,
                requires_approval=requires_approval,
            ),
        )

    await ProcessService.add_rule_to_version(
        db_session,
        version.id,
        BusinessRuleCreate(
            name="Invoice currency is USD",
            code="invoice_currency_is_usd",
            expression={
                "operator": "EQUAL",
                "left_field": "documents.invoice.currency",
                "expected_value": "USD",
                "missing_policy": "fail",
            },
        ),
    )
    verification = await ProcessService.add_verification_to_version(
        db_session,
        version.id,
        VerificationDefinitionCreate(
            process_version_id=version.id,
            stage_id=stages["VERIFICATION"].id,
            name="Invoice consistency",
            code="invoice_currency",
        ),
    )
    await ProcessService.add_requirement_to_version(
        db_session,
        version.id,
        RequirementCreate(
            name="Invoice verification passes",
            code="invoice_currency",
            type="VERIFICATION",
            stage_id=stages["VERIFICATION"].id,
            configuration={"verification_code": "invoice_currency"},
        ),
    )
    await ProcessService.publish_version(db_session, version.id)

    employee_headers = _authorization(employee)
    manager_headers = _authorization(manager)
    customer_headers = _authorization(customer)
    admin_headers = _authorization(admin)

    created = await async_client.post(
        "/api/v1/cases",
        headers=employee_headers,
        json={"title": "Authenticated synthetic invoice journey", "process_version_id": str(version.id)},
    )
    assert created.status_code == 201, created.text
    case_id = uuid.UUID(created.json()["id"])
    assert created.json()["created_by"] == str(employee.id)
    assert (await async_client.get(f"/api/v1/cases/{case_id}", headers=customer_headers)).status_code == 403

    async def transition(headers: dict[str, str], target: str, *, spoof_admin: bool = False):
        return await async_client.post(
            "/api/v1/workflows/transition",
            headers=headers,
            json={
                "case_id": str(case_id),
                "to_stage_id": str(stages[target].id),
                "reason": f"Journey test: {target}",
                "actor_id": str(test_user.id if spoof_admin else employee.id),
                "actor_role": "ADMIN" if spoof_admin else "EMPLOYEE",
                "actor_type": "AGENT" if spoof_admin else "USER",
            },
        )

    uploaded = await async_client.post(
        "/api/v1/documents",
        headers=employee_headers,
        data={"case_id": str(case_id), "document_type": "INVOICE"},
        files={"file": ("invoice.pdf", _invoice_pdf(), "application/pdf")},
    )
    assert uploaded.status_code == 201, uploaded.text
    document = uploaded.json()["document"]
    document_id = uuid.UUID(document["id"])
    version_id = uuid.UUID(document["versions"][0]["id"])
    processed = await async_client.post(
        f"/api/v1/documents/{document_id}/versions/{version_id}/process",
        headers=employee_headers,
    )
    assert processed.status_code == 200, processed.text
    assert processed.json()["status"] == "COMPLETED"
    assert processed.json()["review_required"] is False

    for target in ("DOCUMENT_REVIEW", "VERIFICATION"):
        moved = await transition(employee_headers, target)
        assert moved.status_code == 200 and moved.json()["allowed"] is True, moved.text

    verified = await async_client.post(
        "/api/v1/verifications/execute",
        headers=employee_headers,
        json={"case_id": str(case_id), "verification_id": str(verification.id)},
    )
    assert verified.status_code == 200, verified.text

    created_task = await async_client.post(
        "/api/v1/tasks",
        headers=employee_headers,
        json={
            "case_id": str(case_id),
            "task_type": "MANUAL_REVIEW",
            "title": "Review verification evidence",
        },
    )
    assert created_task.status_code == 201, created_task.text
    task_id = created_task.json()["id"]
    started_task = await async_client.post(
        f"/api/v1/tasks/{task_id}/start", headers=employee_headers
    )
    assert started_task.status_code == 200, started_task.text
    assert started_task.json()["status"] == "IN_PROGRESS"
    resolved_task = await async_client.post(
        f"/api/v1/tasks/{task_id}/resolve",
        headers=employee_headers,
        json={"outcome": "COMPLETED", "comment": "Evidence reviewed."},
    )
    assert resolved_task.status_code == 200, resolved_task.text
    assert resolved_task.json()["status"] == "COMPLETED"
    assert verified.json()["status"] == "PASS"

    denied_transition = await transition(employee_headers, "MANAGER_APPROVAL", spoof_admin=True)
    assert denied_transition.status_code == 400
    assert "UNAUTHORIZED_ROLE" in str(denied_transition.json()["detail"])
    moved = await transition(manager_headers, "MANAGER_APPROVAL")
    assert moved.status_code == 200, moved.text

    premature_completion = await transition(manager_headers, "COMPLETED")
    assert premature_completion.status_code == 400
    assert "MISSING_APPROVAL" in str(premature_completion.json()["detail"])

    requested = await async_client.post(
        "/api/v1/approvals",
        headers=manager_headers,
        json={"case_id": str(case_id), "approval_type": "MANAGER"},
    )
    assert requested.status_code == 201, requested.text
    approval_id = uuid.UUID(requested.json()["id"])
    forbidden_decision = await async_client.post(
        f"/api/v1/approvals/{approval_id}/decide",
        headers=employee_headers,
        json={"decision": "APPROVED", "comment": "Employee cannot approve"},
    )
    assert forbidden_decision.status_code == 403
    decided = await async_client.post(
        f"/api/v1/approvals/{approval_id}/decide",
        headers=manager_headers,
        json={"decision": "APPROVED", "comment": "Synthetic test approval"},
    )
    assert decided.status_code == 200 and decided.json()["decision"] == "APPROVED"

    completed = await transition(manager_headers, "COMPLETED")
    assert completed.status_code == 200, completed.text
    final_case = await async_client.get(f"/api/v1/cases/{case_id}", headers=manager_headers)
    assert final_case.status_code == 200
    assert final_case.json()["status"] == "COMPLETED"
    assert final_case.json()["current_stage_id"] == str(stages["COMPLETED"].id)

    event_response = await async_client.get(
        f"/api/v1/cases/{case_id}/events", headers=manager_headers
    )
    assert event_response.status_code == 200, event_response.text
    events = event_response.json()
    event_types = {event["event_type"] for event in events}
    assert {
        "CASE_CREATED",
        "WORKFLOW_TRANSITIONED",
        "DOCUMENT_UPLOADED",
        "DOCUMENT_PROCESSED",
        "VERIFICATION_STARTED",
        "VERIFICATION_COMPLETED",
        "TASK_CREATED",
        "TASK_STARTED",
        "APPROVAL_REQUESTED",
        "APPROVAL_GRANTED",
        "CASE_COMPLETED",
    } <= event_types
    completed_task_event = next(
        event for event in events
        if event["event_type"] == "TASK_COMPLETED"
        and event["payload"].get("status") == "COMPLETED"
    )
    assert completed_task_event["actor_id"] == str(employee.id)
    assert all(event["created_at"] for event in events)
    created_event = next(event for event in events if event["event_type"] == "CASE_CREATED")
    assert created_event["actor_id"] == str(employee.id)
    decision_event = next(event for event in events if event["event_type"] == "APPROVAL_GRANTED")
    assert decision_event["actor_id"] == str(manager.id)
    verification_started = next(
        event for event in events if event["event_type"] == "VERIFICATION_STARTED"
    )
    assert verification_started["actor_id"] == str(employee.id)

    forbidden_audit = await async_client.get("/api/v1/audit", headers=employee_headers)
    assert forbidden_audit.status_code == 403
    audit_response = await async_client.get("/api/v1/audit", headers=admin_headers)
    assert audit_response.status_code == 200, audit_response.text
    assert any(
        row["action"] == "APPROVAL_DECIDED" and row["resource_id"] == str(approval_id)
        for row in audit_response.json()
    )

    foreign_org = Organization(
        name="Journey Other Organization",
        slug=f"journey-other-{uuid.uuid4().hex[:10]}",
        status="active",
        settings={},
        is_active=True,
    )
    foreign_admin = User(
        organization=foreign_org,
        email=f"journey-other-{uuid.uuid4().hex[:8]}@example.test",
        name="Foreign Admin",
        hashed_password="not-used-by-this-token-test",
        role=RoleEnum.ADMIN,
        status="active",
        is_active=True,
    )
    db_session.add_all([foreign_org, foreign_admin])
    await db_session.commit()
    await db_session.refresh(foreign_admin)
    await AuditService.log_action(
        db_session,
        organization_id=foreign_org.id,
        action="FOREIGN_MARKER",
        resource_type="CASE",
        actor_id=foreign_admin.id,
    )
    foreign_headers = _authorization(foreign_admin)
    foreign_case_events = await async_client.get(
        f"/api/v1/cases/{case_id}/events", headers=foreign_headers
    )
    assert foreign_case_events.status_code == 404
    scoped_audit = await async_client.get("/api/v1/audit", headers=admin_headers)
    assert scoped_audit.status_code == 200
    assert all(row["organization_id"] == str(test_org.id) for row in scoped_audit.json())
    assert all(row["action"] != "FOREIGN_MARKER" for row in scoped_audit.json())
