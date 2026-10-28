"""Exercise the declarative Insurance Claim process through shared APIs/services."""
from __future__ import annotations

import json
import uuid
from pathlib import Path

import pymupdf
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.domain.documents.router import get_document_storage
from app.domain.documents import intelligence
from app.domain.cases.models import Case
from app.domain.organizations.models import Organization
from app.domain.processes.configuration_loader import load_process_definition
from app.domain.verifications.models import VerificationDefinition, VerificationExecution
from app.domain.workflows.models import WorkflowStage
from app.infrastructure.storage import LocalFileStorage
from app.main import app
from app.security.models import Permission, Role, RoleEnum, RolePermission, User
from app.security.router import get_current_user
from app.security.service import AuthService
from app.tools.models import ToolExecution


class DeterministicClaimAdapter:
    """Fake only the model boundary; parsing, extraction validation and storage are real."""

    async def generate_json(self, *, system_prompt, user_prompt, response_schema):
        request = json.loads(user_prompt)
        if "class_id" in response_schema.get("properties", {}):
            class_id = str(request.get("declared_type_hint") or "unknown").casefold()
            return {"class_id": class_id, "confidence": 0.99, "rationale": "Synthetic integration fixture"}, "test-fixture"

        document_class = request["document_class"]
        blocks = request["source_blocks"]
        claim_block = next(
            (block for block in blocks if "Claim Number:" in block["text"]),
            blocks[0],
        )
        claim_number = claim_block["text"].split("Claim Number:", 1)[-1].strip()
        fields = {
            "claim_number": {
                "value": claim_number,
                "confidence": 0.99,
                "citations": [{"block_index": claim_block["block_index"], "quote": claim_block["text"]}],
            }
        }
        if document_class == "claim_form":
            claimant_block = next((block for block in blocks if "Claimant:" in block["text"]), None)
            if claimant_block:
                fields["claimant_name"] = {
                    "value": claimant_block["text"].split("Claimant:", 1)[-1].strip(),
                    "confidence": 0.99,
                    "citations": [{"block_index": claimant_block["block_index"], "quote": claimant_block["text"]}],
                }
            policy_block = next((block for block in blocks if "Policy Number:" in block["text"]), None)
            if policy_block:
                fields["policy_number"] = {
                    "value": policy_block["text"].split("Policy Number:", 1)[-1].strip(),
                    "confidence": 0.99,
                    "citations": [{"block_index": policy_block["block_index"], "quote": policy_block["text"]}],
                }
        elif document_class == "repair_estimate":
            amount_block = next((block for block in blocks if "Estimate Amount:" in block["text"]), None)
            if amount_block:
                fields["estimate_amount"] = {
                    "value": float(amount_block["text"].split("Estimate Amount:", 1)[-1].strip()),
                    "confidence": 0.99,
                    "citations": [{"block_index": amount_block["block_index"], "quote": amount_block["text"]}],
                }
        return {"fields": fields}, "test-fixture"


def _pdf(*lines: str) -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    for index, line in enumerate(lines):
        page.insert_text((72, 72 + index * 24), line)
    content = document.tobytes()
    document.close()
    return content


def _headers(user: User) -> dict[str, str]:
    token = AuthService.create_access_token(
        user.id, user.organization_id, user.role, token_version=user.token_version
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_insurance_claim_runs_through_shared_case_document_workflow_verification_tools_and_review(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_org: Organization,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, "CASE_ORCHESTRATION_ENABLED", False)
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides[get_document_storage] = lambda: LocalFileStorage(root=str(tmp_path))
    monkeypatch.setattr(intelligence, "get_json_model_adapter", DeterministicClaimAdapter)

    manager = User(
        organization_id=test_org.id,
        email=f"phase24-manager-{uuid.uuid4().hex[:8]}@example.test",
        name="Phase 24 Manager",
        hashed_password="not-used-by-this-token-test",
        role=RoleEnum.MANAGER,
        status="active",
        is_active=True,
    )
    db_session.add(manager)
    await db_session.flush()
    role = Role(organization_id=test_org.id, name="MANAGER")
    permission = Permission(code="tool.check_required_documents")
    db_session.add_all([role, permission])
    await db_session.flush()
    db_session.add(RolePermission(role_id=role.id, permission_id=permission.id))
    await db_session.commit()

    process_path = Path(__file__).resolve().parents[2] / "workflows" / "insurance_claim" / "process.json"
    process, version = await load_process_definition(
        db_session, organization_id=test_org.id, path=process_path, created_by=manager.id
    )
    assert process.code == "insurance_claim"
    assert version.status == "PUBLISHED"
    assert version.configuration["extraction_schemas"].keys() == {"claim_form", "repair_estimate"}

    headers = _headers(manager)
    created = await async_client.post(
        "/api/v1/cases",
        headers=headers,
        json={"title": "Synthetic insurance claim", "process_version_id": str(version.id)},
    )
    assert created.status_code == 201, created.text
    case_id = uuid.UUID(created.json()["id"])
    case_record = await db_session.get(Case, case_id)
    assert case_record is not None
    assert case_record.process_id == process.id
    assert case_record.process_version_id == version.id

    stages = {
        stage.code: stage
        for stage in (await db_session.execute(
            select(WorkflowStage).where(WorkflowStage.process_version_id == version.id)
        )).scalars()
    }
    assert set(stages) == {
        "CLAIM_SUBMITTED", "DOCUMENT_COLLECTION", "CLAIM_VERIFICATION",
        "FINANCIAL_REVIEW", "MANAGER_APPROVAL", "PAYMENT",
    }

    for document_type, filename, lines in (
        ("CLAIM_FORM", "claim-form.pdf", ("Claim Number: CLM-2026-101", "Policy Number: PLC-882", "Claimant: Synthetic Claimant")),
        ("REPAIR_ESTIMATE", "repair-estimate.pdf", ("Claim Number: CLM-2026-101", "Estimate Amount: 1250.00")),
    ):
        uploaded = await async_client.post(
            "/api/v1/documents",
            headers=headers,
            data={"case_id": str(case_id), "document_type": document_type},
            files={"file": (filename, _pdf(*lines), "application/pdf")},
        )
        assert uploaded.status_code == 201, uploaded.text
        document = uploaded.json()["document"]
        processed = await async_client.post(
            f"/api/v1/documents/{document['id']}/versions/{document['versions'][0]['id']}/process",
            headers=headers,
        )
        assert processed.status_code == 200, processed.text
        assert processed.json()["status"] == "COMPLETED"
        assert processed.json()["review_required"] is False

    async def transition(target: str):
        return await async_client.post(
            "/api/v1/workflows/transition",
            headers=headers,
            json={"case_id": str(case_id), "to_stage_id": str(stages[target].id), "reason": f"Synthetic claim journey: {target}"},
        )

    for target in ("DOCUMENT_COLLECTION", "CLAIM_VERIFICATION"):
        moved = await transition(target)
        assert moved.status_code == 200 and moved.json()["allowed"] is True, moved.text

    tools_response = await async_client.get(f"/api/v1/tools?case_id={case_id}", headers=headers)
    assert tools_response.status_code == 200, tools_response.text
    assert "check_required_documents" in {tool["name"] for tool in tools_response.json()}
    required_docs = await async_client.post(
        "/api/v1/tools/execute",
        headers=headers,
        json={"tool_name": "check_required_documents", "case_id": str(case_id), "arguments": {}},
    )
    assert required_docs.status_code == 200, required_docs.text
    assert required_docs.json()["output"]["complete"] is True
    assert required_docs.json()["output"]["missing_document_types"] == []
    tool_execution = await db_session.get(ToolExecution, uuid.UUID(required_docs.json()["execution_id"]))
    assert tool_execution is not None and tool_execution.status == "SUCCESS"

    verification = (await db_session.execute(
        select(VerificationDefinition).where(
            VerificationDefinition.process_version_id == version.id,
            VerificationDefinition.code == "claim_reference_consistency",
        )
    )).scalars().one()
    verified = await async_client.post(
        "/api/v1/verifications/execute",
        headers=headers,
        json={"case_id": str(case_id), "verification_id": str(verification.id)},
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["status"] == "PASS"
    stored_verification = (await db_session.execute(
        select(VerificationExecution).where(
            VerificationExecution.case_id == case_id,
            VerificationExecution.verification_id == verification.id,
        )
    )).scalars().one()
    assert stored_verification.status == "PASS"

    for target in ("FINANCIAL_REVIEW", "MANAGER_APPROVAL"):
        moved = await transition(target)
        assert moved.status_code == 200 and moved.json()["allowed"] is True, moved.text

    task = await async_client.post(
        "/api/v1/tasks",
        headers=headers,
        json={"case_id": str(case_id), "task_type": "FINANCIAL_REVIEW", "title": "Review synthetic claim estimate"},
    )
    assert task.status_code == 201, task.text
    task_id = task.json()["id"]
    started = await async_client.post(f"/api/v1/tasks/{task_id}/start", headers=headers)
    assert started.status_code == 200 and started.json()["status"] == "IN_PROGRESS", started.text
    resolved = await async_client.post(
        f"/api/v1/tasks/{task_id}/resolve",
        headers=headers,
        json={"outcome": "COMPLETED", "comment": "Synthetic estimate reviewed."},
    )
    assert resolved.status_code == 200 and resolved.json()["status"] == "COMPLETED", resolved.text

    approval = await async_client.post(
        "/api/v1/approvals",
        headers=headers,
        json={"case_id": str(case_id), "approval_type": "MANAGER"},
    )
    assert approval.status_code == 201, approval.text
    decided = await async_client.post(
        f"/api/v1/approvals/{approval.json()['id']}/decide",
        headers=headers,
        json={"decision": "APPROVED", "comment": "Synthetic claim approved."},
    )
    assert decided.status_code == 200 and decided.json()["decision"] == "APPROVED", decided.text

    payment = await transition("PAYMENT")
    assert payment.status_code == 200 and payment.json()["allowed"] is True, payment.text
    final_case = await async_client.get(f"/api/v1/cases/{case_id}", headers=headers)
    assert final_case.status_code == 200
    assert final_case.json()["status"] == "COMPLETED"
    assert final_case.json()["current_stage_id"] == str(stages["PAYMENT"].id)
    events_response = await async_client.get(f"/api/v1/cases/{case_id}/events", headers=headers)
    assert events_response.status_code == 200, events_response.text
    event_types = {event["event_type"] for event in events_response.json()}
    assert {
        "CASE_CREATED",
        "DOCUMENT_UPLOADED",
        "DOCUMENT_PROCESSED",
        "WORKFLOW_TRANSITIONED",
        "VERIFICATION_STARTED",
        "VERIFICATION_COMPLETED",
        "TASK_COMPLETED",
        "APPROVAL_GRANTED",
        "CASE_COMPLETED",
    } <= event_types
