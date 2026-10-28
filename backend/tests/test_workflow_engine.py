"""
Integration & Unit tests for Phase 4: Deterministic Workflow Engine.
Tests the complete multi-stage lifecycle, prerequisites, approvals, role enforcement,
audit trails, and edge cases (invalid transitions, terminal states, missing requirements).
"""
import uuid
import pytest
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from httpx import AsyncClient

from app.domain.organizations.models import Organization
from app.security.models import User
from app.domain.processes.models import (
    Process,
    ProcessVersion,
    ProcessVersionStatus,
    Requirement,
    RequirementType,
)
from app.domain.processes.service import ProcessService
from app.domain.processes.schemas import ProcessCreate
from app.domain.workflows.models import WorkflowStage, WorkflowTransition
from app.domain.workflows.schemas import (
    TransitionRequest,
    WorkflowStageCreate,
    WorkflowTransitionCreate,
)
from app.domain.workflows.service import WorkflowService
from app.domain.cases.models import Case, CaseData, CaseStageHistory, CaseStatus
from app.domain.cases.service import CaseService
from app.domain.cases.schemas import CaseCreate
from app.domain.documents.models import Document
from app.domain.approvals.models import Approval, ApprovalDecision
from app.domain.verifications.models import VerificationDefinition, VerificationExecution, VerificationStatus
from app.events.models import EventRecord
from app.events.service import EventService
from app.domain.audit.models import AuditLog


@pytest.mark.asyncio
async def test_workflow_end_to_end_deterministic_execution(
    db_session: AsyncSession,
    test_org: Organization,
    test_user: User,
):
    """Test full 7-stage Import/Export verification pipeline without AI."""
    # 1. Create Process & Draft Version
    proc = await ProcessService.create_process(
        db=db_session,
        organization_id=test_org.id,
        process_in=ProcessCreate(name="Import Verification Workflow", code="IMPORT_VERIF_01"),
    )
    versions = await ProcessService.get_versions_by_process_id(db=db_session, process_id=proc.id)
    ver = versions[0]

    # 2. Setup 7 Stages:
    # 1: Document Collection (Initial)
    # 2: Document Verification
    # 3: Inventory Check
    # 4: Finance Review
    # 5: Manager Approval
    # 6: Shipping
    # 7: Completed (Terminal)
    s1 = await WorkflowService.create_stage(
        db_session,
        WorkflowStageCreate(
            process_version_id=ver.id,
            name="Document Collection",
            code="DOC_COLLECTION",
            stage_order=1,
            is_initial=True,
        ),
    )
    s2 = await WorkflowService.create_stage(
        db_session,
        WorkflowStageCreate(
            process_version_id=ver.id,
            name="Document Verification",
            code="DOC_VERIFICATION",
            stage_order=2,
        ),
    )
    s3 = await WorkflowService.create_stage(
        db_session,
        WorkflowStageCreate(
            process_version_id=ver.id,
            name="Inventory Check",
            code="INVENTORY_CHECK",
            stage_order=3,
        ),
    )
    s4 = await WorkflowService.create_stage(
        db_session,
        WorkflowStageCreate(
            process_version_id=ver.id,
            name="Finance Review",
            code="FINANCE_REVIEW",
            stage_order=4,
        ),
    )
    s5 = await WorkflowService.create_stage(
        db_session,
        WorkflowStageCreate(
            process_version_id=ver.id,
            name="Manager Approval",
            code="MANAGER_APPROVAL",
            stage_order=5,
        ),
    )
    s6 = await WorkflowService.create_stage(
        db_session,
        WorkflowStageCreate(
            process_version_id=ver.id,
            name="Shipping",
            code="SHIPPING",
            stage_order=6,
        ),
    )
    s7 = await WorkflowService.create_stage(
        db_session,
        WorkflowStageCreate(
            process_version_id=ver.id,
            name="Completed",
            code="COMPLETED",
            stage_order=7,
            is_terminal=True,
        ),
    )

    # 3. Setup Transitions between consecutive stages
    t1 = await WorkflowService.create_transition(
        db_session,
        WorkflowTransitionCreate(
            process_version_id=ver.id,
            from_stage_id=s1.id,
            to_stage_id=s2.id,
            name="Submit Documents",
        ),
    )
    t2 = await WorkflowService.create_transition(
        db_session,
        WorkflowTransitionCreate(
            process_version_id=ver.id,
            from_stage_id=s2.id,
            to_stage_id=s3.id,
            name="Documents Verified",
        ),
    )
    t3 = await WorkflowService.create_transition(
        db_session,
        WorkflowTransitionCreate(
            process_version_id=ver.id,
            from_stage_id=s3.id,
            to_stage_id=s4.id,
            name="Inventory Confirmed",
        ),
    )
    t4 = await WorkflowService.create_transition(
        db_session,
        WorkflowTransitionCreate(
            process_version_id=ver.id,
            from_stage_id=s4.id,
            to_stage_id=s5.id,
            name="Finance Cleared",
        ),
    )
    t5 = await WorkflowService.create_transition(
        db_session,
        WorkflowTransitionCreate(
            process_version_id=ver.id,
            from_stage_id=s5.id,
            to_stage_id=s6.id,
            name="Manager Authorize",
            requires_approval=True,
            required_role="MANAGER",
        ),
    )
    t6 = await WorkflowService.create_transition(
        db_session,
        WorkflowTransitionCreate(
            process_version_id=ver.id,
            from_stage_id=s6.id,
            to_stage_id=s7.id,
            name="Mark Dispatched",
        ),
    )

    # 4. Add Exit Requirement for Stage 1: Document 'COMMERCIAL_INVOICE' required
    req_doc = Requirement(
        process_version_id=ver.id,
        stage_id=s1.id,
        name="Commercial Invoice",
        code="COMMERCIAL_INVOICE",
        type=RequirementType.DOCUMENT.value,
        required=True,
    )
    db_session.add(req_doc)

    # Publish version
    await ProcessService.publish_version(db_session, ver.id)

    # 5. Create Case
    case = await CaseService.create_case(
        db=db_session,
        organization_id=test_org.id,
        created_by_user_id=test_user.id,
        case_in=CaseCreate(
            process_version_id=ver.id,
            title="Import Consignment #8820",
        ),
    )
    assert case.current_stage_id == s1.id
    assert case.status == CaseStatus.OPEN.value

    # --- STEP A: Transition S1 -> S2 (fails initially due to missing required document) ---
    res_fail = await WorkflowService.execute_transition(
        db=db_session,
        request=TransitionRequest(
            case_id=case.id,
            to_stage_id=s2.id,
            actor_id=test_user.id,
            actor_role="EMPLOYEE",
            reason="Advancing to verification",
        ),
    )
    assert res_fail.allowed is False
    assert any(v.code == "MISSING_DOCUMENT" for v in res_fail.violations)

    # Now upload the required document
    doc = Document(
        case_id=case.id,
        document_type="COMMERCIAL_INVOICE",
        name="invoice_8820.pdf",
        storage_reference="s3://bucket/invoice_8820.pdf",
        status="PROCESSED",
    )
    db_session.add(doc)
    await db_session.commit()

    # Retry S1 -> S2 (should succeed)
    res_s1_s2 = await WorkflowService.execute_transition(
        db=db_session,
        request=TransitionRequest(
            case_id=case.id,
            to_stage_id=s2.id,
            actor_id=test_user.id,
            actor_role="EMPLOYEE",
            reason="Commercial invoice attached",
        ),
    )
    assert res_s1_s2.allowed is True
    assert res_s1_s2.current_stage_id == s2.id
    assert res_s1_s2.case_status == CaseStatus.IN_PROGRESS.value

    # --- STEP B: S2 -> S3 (Inventory Check) ---
    res_s2_s3 = await WorkflowService.execute_transition(
        db=db_session,
        request=TransitionRequest(
            case_id=case.id,
            to_stage_id=s3.id,
            actor_id=test_user.id,
            actor_role="EMPLOYEE",
            reason="Doc verification passed",
        ),
    )
    assert res_s2_s3.allowed is True
    assert res_s2_s3.current_stage_id == s3.id

    # --- STEP C: S3 -> S4 (Finance Review) ---
    res_s3_s4 = await WorkflowService.execute_transition(
        db=db_session,
        request=TransitionRequest(
            case_id=case.id,
            to_stage_id=s4.id,
            actor_id=test_user.id,
            actor_role="EMPLOYEE",
            reason="Warehouse stock available",
        ),
    )
    assert res_s3_s4.allowed is True
    assert res_s3_s4.current_stage_id == s4.id

    # --- STEP D: S4 -> S5 (Manager Approval stage) ---
    res_s4_s5 = await WorkflowService.execute_transition(
        db=db_session,
        request=TransitionRequest(
            case_id=case.id,
            to_stage_id=s5.id,
            actor_id=test_user.id,
            actor_role="EMPLOYEE",
            reason="Finance audit cleared",
        ),
    )
    assert res_s4_s5.allowed is True
    assert res_s4_s5.current_stage_id == s5.id

    # --- STEP E: S5 -> S6 requires role 'MANAGER' and approval ---
    # 1. Test failure: wrong role (EMPLOYEE) + missing approval
    res_unauth = await WorkflowService.execute_transition(
        db=db_session,
        request=TransitionRequest(
            case_id=case.id,
            to_stage_id=s6.id,
            actor_id=test_user.id,
            actor_role="EMPLOYEE",
            reason="Attempting manager skip",
        ),
    )
    assert res_unauth.allowed is False
    assert any(v.code == "UNAUTHORIZED_ROLE" for v in res_unauth.violations)
    assert any(v.code == "MISSING_APPROVAL" for v in res_unauth.violations)

    # 2. Add Approval record
    appr = Approval(
        case_id=case.id,
        requested_at=datetime.now(timezone.utc),
        decided_at=datetime.now(timezone.utc),
        decision=ApprovalDecision.APPROVED.value,
        decided_by=test_user.id,
        comment="Authorized for shipment by operations manager.",
    )
    db_session.add(appr)
    await db_session.commit()

    # 3. Transition with role 'MANAGER'
    res_s5_s6 = await WorkflowService.execute_transition(
        db=db_session,
        request=TransitionRequest(
            case_id=case.id,
            to_stage_id=s6.id,
            actor_id=test_user.id,
            actor_role="MANAGER",
            reason="Executive approval provided",
        ),
    )
    assert res_s5_s6.allowed is True
    assert res_s5_s6.current_stage_id == s6.id

    # --- STEP F: S6 -> S7 (Terminal Completed stage) ---
    res_terminal = await WorkflowService.execute_transition(
        db=db_session,
        request=TransitionRequest(
            case_id=case.id,
            to_stage_id=s7.id,
            actor_id=test_user.id,
            actor_role="EMPLOYEE",
            reason="Container dispatched on vessel",
        ),
    )
    assert res_terminal.allowed is True
    assert res_terminal.current_stage_id == s7.id
    assert res_terminal.case_status == CaseStatus.COMPLETED.value

    # Verify Database state & Audit/Event records
    case_db = await db_session.get(Case, case.id)
    assert case_db is not None
    assert case_db.status == CaseStatus.COMPLETED.value
    assert case_db.completed_at is not None

    # Verify Stage History (at least 6 transitions recorded)
    history_stmt = select(CaseStageHistory).where(CaseStageHistory.case_id == case.id)
    histories = list((await db_session.execute(history_stmt)).scalars().all())
    assert len(histories) == 6

    # Verify Events emitted
    events = await EventService.get_events_for_case(db=db_session, case_id=case.id)
    assert any(e.event_type == "WORKFLOW_TRANSITIONED" for e in events)
    assert any(e.event_type == "CASE_COMPLETED" for e in events)


@pytest.mark.asyncio
async def test_failed_verification_can_only_route_to_configured_review_stage(
    db_session: AsyncSession,
    test_org: Organization,
    test_user: User,
):
    """A named failed check can reach human review, but cannot bypass the normal route."""
    process = await ProcessService.create_process(
        db_session,
        organization_id=test_org.id,
        process_in=ProcessCreate(name="Review Routing", code="REVIEW_ROUTING"),
    )
    version = (await ProcessService.get_versions_by_process_id(db_session, process.id))[0]
    source = await WorkflowService.create_stage(
        db_session,
        WorkflowStageCreate(
            process_version_id=version.id, name="Verification", code="VERIFICATION",
            stage_order=1, is_initial=True,
        ),
    )
    review = await WorkflowService.create_stage(
        db_session,
        WorkflowStageCreate(
            process_version_id=version.id, name="Human Review", code="HUMAN_REVIEW",
            stage_order=2, config={"review_stage": True},
        ),
    )
    normal = await WorkflowService.create_stage(
        db_session,
        WorkflowStageCreate(
            process_version_id=version.id, name="Next Stage", code="NEXT",
            stage_order=3,
        ),
    )
    await WorkflowService.create_transition(
        db_session,
        WorkflowTransitionCreate(
            process_version_id=version.id, from_stage_id=source.id,
            to_stage_id=review.id, name="Send to review",
            condition_config={"allow_failed_verifications": ["order_consistency"]},
        ),
    )
    await WorkflowService.create_transition(
        db_session,
        WorkflowTransitionCreate(
            process_version_id=version.id, from_stage_id=source.id,
            to_stage_id=normal.id, name="Continue normally",
            condition_config={"allow_failed_verifications": ["order_consistency"]},
        ),
    )
    db_session.add(Requirement(
        process_version_id=version.id, stage_id=source.id,
        name="Order verification", code="ORDER_VERIFICATION",
        type=RequirementType.VERIFICATION.value, required=True,
        configuration={"verification_code": "order_consistency"},
    ))
    verification = VerificationDefinition(
        process_version_id=version.id, name="Order consistency", code="order_consistency",
    )
    db_session.add(verification)
    await db_session.flush()
    await ProcessService.publish_version(db_session, version.id)
    case = await CaseService.create_case(
        db_session, test_org.id, test_user.id,
        CaseCreate(title="Mismatched order", process_version_id=version.id),
    )
    db_session.add(VerificationExecution(
        case_id=case.id, verification_id=verification.id,
        status=VerificationStatus.FAIL.value, executed_by_type="SYSTEM",
    ))
    await db_session.commit()

    review_result = await WorkflowService.validate_transition(
        db_session,
        TransitionRequest(case_id=case.id, to_stage_id=review.id, actor_id=test_user.id,
                          actor_role="EMPLOYEE"),
        organization_id=test_org.id,
    )
    normal_result = await WorkflowService.validate_transition(
        db_session,
        TransitionRequest(case_id=case.id, to_stage_id=normal.id, actor_id=test_user.id,
                          actor_role="EMPLOYEE"),
        organization_id=test_org.id,
    )
    assert review_result.allowed is True
    assert normal_result.allowed is False
    assert any(v.code == "FAILED_OR_MISSING_VERIFICATION" for v in normal_result.violations)

    failed_execution = (
        await db_session.execute(
            select(VerificationExecution).where(
                VerificationExecution.case_id == case.id,
                VerificationExecution.verification_id == verification.id,
            )
        )
    ).scalars().one()
    await db_session.delete(failed_execution)
    await db_session.commit()
    missing_result = await WorkflowService.validate_transition(
        db_session,
        TransitionRequest(case_id=case.id, to_stage_id=review.id, actor_id=test_user.id,
                          actor_role="EMPLOYEE"),
        organization_id=test_org.id,
    )
    assert missing_result.allowed is False
    assert any(v.code == "FAILED_OR_MISSING_VERIFICATION" for v in missing_result.violations)


@pytest.mark.asyncio
async def test_workflow_error_conditions_and_invariants(
    db_session: AsyncSession,
    test_org: Organization,
    test_user: User,
):
    """Test all error guards: invalid transition paths, repeated transitions, terminal state modifications."""
    proc = await ProcessService.create_process(
        db=db_session,
        organization_id=test_org.id,
        process_in=ProcessCreate(name="Loan Check", code="LOAN_CHK"),
    )
    versions = await ProcessService.get_versions_by_process_id(db=db_session, process_id=proc.id)
    ver = versions[0]

    stg_start = await WorkflowService.create_stage(
        db_session,
        WorkflowStageCreate(process_version_id=ver.id, name="Start", code="ST_START", stage_order=1, is_initial=True),
    )
    stg_mid = await WorkflowService.create_stage(
        db_session,
        WorkflowStageCreate(process_version_id=ver.id, name="Underwrite", code="ST_MID", stage_order=2),
    )
    stg_end = await WorkflowService.create_stage(
        db_session,
        WorkflowStageCreate(process_version_id=ver.id, name="Disbursed", code="ST_END", stage_order=3, is_terminal=True),
    )

    # Only transition from start -> mid exists
    await WorkflowService.create_transition(
        db_session,
        WorkflowTransitionCreate(process_version_id=ver.id, from_stage_id=stg_start.id, to_stage_id=stg_mid.id, name="Start to Mid"),
    )
    await ProcessService.publish_version(db_session, ver.id)

    case = await CaseService.create_case(
        db=db_session,
        organization_id=test_org.id,
        created_by_user_id=test_user.id,
        case_in=CaseCreate(process_version_id=ver.id, title="Personal Loan #101"),
    )

    # 1. Invalid transition (trying to jump directly from start -> end)
    res_jump = await WorkflowService.execute_transition(
        db=db_session,
        request=TransitionRequest(case_id=case.id, to_stage_id=stg_end.id),
    )
    assert res_jump.allowed is False
    assert "No configured transition" in res_jump.reason

    # 2. Repeated transition (transitioning to current stage)
    res_repeat = await WorkflowService.execute_transition(
        db=db_session,
        request=TransitionRequest(case_id=case.id, to_stage_id=stg_start.id),
    )
    assert res_repeat.allowed is False
    assert "already in stage" in res_repeat.reason

    # 3. Non-existent target stage ID
    res_fake = await WorkflowService.execute_transition(
        db=db_session,
        request=TransitionRequest(case_id=case.id, to_stage_id=uuid.uuid4()),
    )
    assert res_fake.allowed is False

    # 4. Source stage mismatch
    res_mismatch = await WorkflowService.execute_transition(
        db=db_session,
        request=TransitionRequest(case_id=case.id, from_stage_id=stg_mid.id, to_stage_id=stg_mid.id),
    )
    assert res_mismatch.allowed is False
    assert "mismatch" in res_mismatch.reason

    # 5. Closed case mutation protection
    case.status = CaseStatus.COMPLETED.value
    await db_session.commit()

    res_closed = await WorkflowService.execute_transition(
        db=db_session,
        request=TransitionRequest(case_id=case.id, to_stage_id=stg_mid.id),
    )
    assert res_closed.allowed is False
    assert "terminal status" in res_closed.reason


@pytest.mark.asyncio
async def test_workflow_api_endpoints(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_org: Organization,
    test_user: User,
):
    """Test /api/v1/workflows endpoints (stages, transitions, validate, execute)."""
    proc = await ProcessService.create_process(
        db=db_session,
        organization_id=test_org.id,
        process_in=ProcessCreate(name="KYC Pipeline", code="KYC_PIPE"),
    )
    versions = await ProcessService.get_versions_by_process_id(db=db_session, process_id=proc.id)
    ver = versions[0]

    # 1. POST /api/v1/workflows/stages
    res = await async_client.post(
        "/api/v1/workflows/stages",
        json={
            "process_version_id": str(ver.id),
            "name": "ID Upload",
            "code": "ID_UPLOAD",
            "stage_order": 1,
            "is_initial": True,
        },
    )
    assert res.status_code == 201, res.text
    s1_id = res.json()["id"]

    res = await async_client.post(
        "/api/v1/workflows/stages",
        json={
            "process_version_id": str(ver.id),
            "name": "ID Verified",
            "code": "ID_VERIFIED",
            "stage_order": 2,
            "is_terminal": True,
        },
    )
    assert res.status_code == 201
    s2_id = res.json()["id"]

    # 2. GET /api/v1/workflows/stages/version/{id}
    res = await async_client.get(f"/api/v1/workflows/stages/version/{ver.id}")
    assert res.status_code == 200
    assert len(res.json()) == 2

    # 3. POST /api/v1/workflows/transitions
    res = await async_client.post(
        "/api/v1/workflows/transitions",
        json={
            "process_version_id": str(ver.id),
            "from_stage_id": s1_id,
            "to_stage_id": s2_id,
            "name": "Verify Identity",
        },
    )
    assert res.status_code == 201, res.text

    # 4. GET /api/v1/workflows/transitions/version/{id}
    res = await async_client.get(f"/api/v1/workflows/transitions/version/{ver.id}")
    assert res.status_code == 200
    assert len(res.json()) == 1

    # Publish version
    await ProcessService.publish_version(db_session, ver.id)

    case = await CaseService.create_case(
        db=db_session,
        organization_id=test_org.id,
        created_by_user_id=test_user.id,
        case_in=CaseCreate(process_version_id=ver.id, title="Customer #77 KYC"),
    )

    # 5. POST /api/v1/workflows/validate
    res = await async_client.post(
        "/api/v1/workflows/validate",
        json={"case_id": str(case.id), "to_stage_id": s2_id},
    )
    assert res.status_code == 200
    assert res.json()["allowed"] is True

    # 6. POST /api/v1/workflows/transition
    res = await async_client.post(
        "/api/v1/workflows/transition",
        json={"case_id": str(case.id), "to_stage_id": s2_id, "reason": "Passed facial recognition"},
    )
    assert res.status_code == 200, res.text
    result = res.json()
    assert result["allowed"] is True
    assert result["current_stage_id"] == s2_id
    assert result["case_status"] == "COMPLETED"
