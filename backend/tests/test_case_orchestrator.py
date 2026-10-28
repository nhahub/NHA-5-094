"""Tests for Case Orchestrator (Phase 15).

Validates end-to-end event-driven saga coordination:
- Case creation and initial stage setup
- Document upload -> extraction -> verification -> workflow progression
- Low confidence extraction -> review task generation -> waiting on human
- Task and approval resolution resuming workflow transitions
- Terminal stage entry and case completion
- Resilience, error isolation, and failure event audit trails
"""
import uuid

import pymupdf
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.domain.approvals.models import ApprovalDecision
from app.domain.approvals.schemas import ApprovalCreate, ApprovalDecisionRequest
from app.domain.approvals.service import ApprovalService
from app.domain.cases.models import Case
from app.domain.cases.orchestrator import (
    CaseOrchestrator,
    OrchestrationStatus,
)
from app.domain.cases.schemas import CaseCreate
from app.domain.cases.service import CaseService
from app.domain.documents.service import DocumentService
from app.domain.processes.schemas import ProcessCreate
from app.domain.processes.service import ProcessService
from app.domain.tasks.models import Task, TaskPriority, TaskStatus
from app.domain.tasks.schemas import TaskCreate, TaskUpdate
from app.domain.tasks.service import TaskService
from app.domain.workflows.schemas import WorkflowStageCreate, WorkflowTransitionCreate
from app.domain.workflows.service import WorkflowService
from app.events.models import EventRecord
from app.events.service import EventService
from app.infrastructure.storage import LocalFileStorage
from app.security.models import Organization, User


def _create_sample_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    lines = [
        "Invoice INV-2026-001",
        "Supplier: Acme Global Trading",
        "Date: 2026-10-01",
        "Currency: USD",
        "Total: 5000.00",
    ]
    for idx, text in enumerate(lines):
        page.insert_text((72, 72 + idx * 24), text)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


class CleanInvoiceModel:
    """Simulates high confidence extraction with valid citations."""

    async def generate_json(self, *, system_prompt, user_prompt, response_schema):
        if "class_id" in response_schema.get("properties", {}):
            return {"class_id": "invoice", "confidence": 0.99, "rationale": "Clear invoice header"}, "mock-v1"
        return {
            "fields": {
                "invoice_number": {
                    "value": "INV-2026-001",
                    "confidence": 0.98,
                    "citations": [{"block_index": 0, "quote": "Invoice INV-2026-001"}],
                },
                "supplier": {
                    "value": "Acme Global Trading",
                    "confidence": 0.95,
                    "citations": [{"block_index": 1, "quote": "Supplier: Acme Global Trading"}],
                },
                "invoice_date": {
                    "value": "2026-10-01",
                    "confidence": 0.96,
                    "citations": [{"block_index": 2, "quote": "Date: 2026-10-01"}],
                },
                "currency": {
                    "value": "USD",
                    "confidence": 0.99,
                    "citations": [{"block_index": 3, "quote": "Currency: USD"}],
                },
                "items": {"value": [], "confidence": 0.92, "citations": [{"block_index": 4, "quote": "Total: 5000.00"}]},
                "total": {
                    "value": 5000.00,
                    "confidence": 0.95,
                    "citations": [{"block_index": 4, "quote": "Total: 5000.00"}],
                },
            }
        }, "mock-v1"


class LowConfidenceInvoiceModel:
    """Simulates low confidence extraction triggering human review."""

    async def generate_json(self, *, system_prompt, user_prompt, response_schema):
        if "class_id" in response_schema.get("properties", {}):
            return {"class_id": "invoice", "confidence": 0.35, "rationale": "Low confidence classification"}, "mock-v1"
        return {
            "fields": {
                "invoice_number": {
                    "value": "INV-2026-002",
                    "confidence": 0.40,
                    "citations": [{"block_index": 0, "quote": "Invoice INV-2026-001"}],
                },
                "supplier": {
                    "value": "Acme Global Trading",
                    "confidence": 0.40,
                    "citations": [{"block_index": 1, "quote": "Supplier: Acme Global Trading"}],
                },
                "invoice_date": {
                    "value": "2026-10-01",
                    "confidence": 0.40,
                    "citations": [{"block_index": 2, "quote": "Date: 2026-10-01"}],
                },
                "currency": {
                    "value": "USD",
                    "confidence": 0.40,
                    "citations": [{"block_index": 3, "quote": "Currency: USD"}],
                },
                "items": {"value": [], "confidence": 0.40, "citations": [{"block_index": 4, "quote": "Total: 5000.00"}]},
                "total": {
                    "value": 5000.00,
                    "confidence": 0.40,
                    "citations": [{"block_index": 4, "quote": "Total: 5000.00"}],
                },
            }
        }, "mock-v1"


@pytest.mark.asyncio
async def test_orchestrator_skips_invalid_or_unknown_events(
    db_session: AsyncSession, test_org: Organization, test_user: User
):
    """Orchestrator should cleanly skip unknown event types without raising exceptions."""
    event = EventRecord(
        organization_id=test_org.id,
        case_id=uuid.uuid4(),
        event_type="UNREGISTERED_CUSTOM_EVENT",
        actor_type="SYSTEM",
        payload={},
    )
    db_session.add(event)
    await db_session.commit()
    await db_session.refresh(event)

    result = await CaseOrchestrator.dispatch_event(db=db_session, event=event, actor=test_user)
    assert result.status == OrchestrationStatus.SKIPPED
    assert "No registered handler" in result.details.get("reason", "")


@pytest.mark.asyncio
async def test_orchestrator_case_created_initializes_stage(
    db_session: AsyncSession, test_org: Organization, test_user: User
):
    """CASE_CREATED event should verify and initialize the initial workflow stage."""
    # 1. Create Process & Published Version
    proc = await ProcessService.create_process(
        db=db_session,
        organization_id=test_org.id,
        process_in=ProcessCreate(name="Order Verification", code="order_verif"),
    )
    versions = await ProcessService.get_versions_by_process_id(db_session, proc.id)
    pv = versions[0]

    # 2. Configure Stages
    stage_intake = await WorkflowService.create_stage(
        db_session,
        WorkflowStageCreate(
            process_version_id=pv.id,
            name="Intake Stage",
            code="INTAKE",
            stage_order=1,
            is_initial=True,
        ),
    )
    await ProcessService.publish_version(db_session, pv.id)

    # 3. Create Case
    case = await CaseService.create_case(
        db=db_session,
        organization_id=test_org.id,
        created_by_user_id=test_user.id,
        case_in=CaseCreate(title="Test Case Intake", process_version_id=pv.id),
    )

    # Retrieve CASE_CREATED event
    events = await EventService.get_events_for_case(db_session, case.id)
    case_created_event = next(e for e in events if e.event_type == "CASE_CREATED")

    # Dispatch event through orchestrator
    result = await CaseOrchestrator.dispatch_event(
        db=db_session,
        event=case_created_event,
        actor=test_user,
    )

    assert result.status == OrchestrationStatus.SUCCESS
    assert result.case_id == case.id
    assert str(case.current_stage_id) == str(stage_intake.id)


@pytest.mark.asyncio
async def test_trusted_case_event_dispatches_and_duplicate_delivery_is_skipped(
    db_session: AsyncSession,
    test_org: Organization,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
):
    """Trusted domain events run the saga and persist a deduplication result."""
    monkeypatch.setattr(settings, "CASE_ORCHESTRATION_ENABLED", True)
    process = await ProcessService.create_process(
        db_session,
        organization_id=test_org.id,
        process_in=ProcessCreate(name="Dispatch Process", code="dispatch_process"),
    )
    version = (await ProcessService.get_versions_by_process_id(db_session, process.id))[0]
    stage = await WorkflowService.create_stage(
        db_session,
        WorkflowStageCreate(
            process_version_id=version.id,
            name="Intake",
            code="INTAKE",
            stage_order=1,
            is_initial=True,
        ),
    )
    stage_id = stage.id
    await ProcessService.publish_version(db_session, version.id)

    original_handler = CaseOrchestrator.handle_case_created.__func__
    attempts = 0

    async def fail_once(cls, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("temporary orchestration failure")
        return await original_handler(cls, **kwargs)

    monkeypatch.setattr(CaseOrchestrator, "handle_case_created", classmethod(fail_once))
    case = await CaseService.create_case(
        db_session,
        organization_id=test_org.id,
        created_by_user_id=test_user.id,
        case_in=CaseCreate(title="Automatically dispatched", process_version_id=version.id),
    )
    case_result = await db_session.execute(
        select(Case).where(Case.title == "Automatically dispatched")
    )
    case = case_result.scalar_one()
    case_id = case.id
    events = await EventService.get_events_for_case(db_session, case_id)
    created_event = next(event for event in events if event.event_type == "CASE_CREATED")
    failures = [
        event
        for event in events
        if event.event_type == "ORCHESTRATION_FAILED"
        and event.payload.get("source_event_id") == str(created_event.id)
    ]
    assert len(failures) == 1

    retried = await CaseOrchestrator.resume_event(db_session, created_event.id)
    assert retried.status == OrchestrationStatus.SUCCESS
    events = await EventService.get_events_for_case(db_session, case_id)
    outcomes = [
        event
        for event in events
        if event.event_type == "ORCHESTRATION_RESULT"
        and event.payload.get("source_event_id") == str(created_event.id)
    ]
    assert len(outcomes) == 1
    assert outcomes[0].payload["status"] == OrchestrationStatus.SUCCESS.value
    await db_session.refresh(case)
    assert case.current_stage_id == stage_id

    duplicate = await CaseOrchestrator.dispatch_event(db_session, created_event, actor=test_user)
    assert duplicate.status == OrchestrationStatus.SKIPPED
    assert duplicate.details["previous_status"] == OrchestrationStatus.SUCCESS.value


@pytest.mark.asyncio
async def test_orchestrator_document_upload_drives_verification_and_transition(
    db_session: AsyncSession, test_org: Organization, test_user: User, tmp_path
):
    """DOCUMENT_UPLOADED event drives extraction -> stage verifications -> workflow progression."""
    storage = LocalFileStorage(root=str(tmp_path))

    # 1. Setup Process, Version, Stages & Transitions
    proc = await ProcessService.create_process(
        db=db_session,
        organization_id=test_org.id,
        process_in=ProcessCreate(name="Invoice Approval Process", code="inv_proc"),
    )
    versions = await ProcessService.get_versions_by_process_id(db_session, proc.id)
    pv = versions[0]

    stage_1 = await WorkflowService.create_stage(
        db_session,
        WorkflowStageCreate(
            process_version_id=pv.id,
            name="Doc Review Stage",
            code="DOC_REVIEW",
            stage_order=1,
            is_initial=True,
        ),
    )
    stage_2 = await WorkflowService.create_stage(
        db_session,
        WorkflowStageCreate(
            process_version_id=pv.id,
            name="Approved Stage",
            code="APPROVED",
            stage_order=2,
            is_terminal=True,
        ),
    )
    await WorkflowService.create_transition(
        db_session,
        WorkflowTransitionCreate(
            process_version_id=pv.id,
            from_stage_id=stage_1.id,
            to_stage_id=stage_2.id,
            name="To Approved",
        ),
    )
    await ProcessService.publish_version(db_session, pv.id)

    # 2. Setup Case
    case = await CaseService.create_case(
        db=db_session,
        organization_id=test_org.id,
        created_by_user_id=test_user.id,
        case_in=CaseCreate(title="Automated Transition Case", process_version_id=pv.id),
    )

    # 3. Upload Document
    pdf_bytes = _create_sample_pdf()
    doc, _ = await DocumentService.upload_document(
        db=db_session,
        organization_id=test_org.id,
        case_id=case.id,
        uploaded_by=test_user.id,
        document_type="INVOICE",
        filename="invoice.pdf",
        declared_content_type="application/pdf",
        content=pdf_bytes,
        storage=storage,
    )
    doc_id = doc.id
    version_id = doc.versions[0].id

    # 4. Emit & Dispatch DOCUMENT_UPLOADED Event
    upload_event = await EventService.emit_event(
        db=db_session,
        organization_id=test_org.id,
        case_id=case.id,
        event_type="DOCUMENT_UPLOADED",
        actor_type="USER",
        actor_id=test_user.id,
        payload={"document_id": str(doc_id), "document_version_id": str(version_id)},
    )

    result = await CaseOrchestrator.dispatch_event(
        db=db_session,
        event=upload_event,
        actor=test_user,
        storage=storage,
        model_adapter=CleanInvoiceModel(),
    )

    assert result.status == OrchestrationStatus.SUCCESS, f"Expected SUCCESS but got {result.status}, error: {result.error}"
    # Verify stage advanced to APPROVED (terminal stage)
    await db_session.refresh(case)
    assert case.current_stage_id == stage_2.id


@pytest.mark.asyncio
async def test_orchestrator_low_confidence_extraction_creates_review_task(
    db_session: AsyncSession, test_org: Organization, test_user: User, tmp_path
):
    """Low confidence extraction halts automated transition and creates a human review task."""
    storage = LocalFileStorage(root=str(tmp_path))

    proc = await ProcessService.create_process(
        db=db_session,
        organization_id=test_org.id,
        process_in=ProcessCreate(name="Low Confidence Process", code="low_conf"),
    )
    versions = await ProcessService.get_versions_by_process_id(db_session, proc.id)
    pv = versions[0]

    await WorkflowService.create_stage(
        db_session,
        WorkflowStageCreate(process_version_id=pv.id, name="Intake", code="INTAKE", stage_order=1, is_initial=True),
    )
    await ProcessService.publish_version(db_session, pv.id)

    case = await CaseService.create_case(
        db=db_session,
        organization_id=test_org.id,
        created_by_user_id=test_user.id,
        case_in=CaseCreate(title="Low Conf Case", process_version_id=pv.id),
    )

    pdf_bytes = _create_sample_pdf()
    doc, _ = await DocumentService.upload_document(
        db=db_session,
        organization_id=test_org.id,
        case_id=case.id,
        uploaded_by=test_user.id,
        document_type="INVOICE",
        filename="blurry.pdf",
        declared_content_type="application/pdf",
        content=pdf_bytes,
        storage=storage,
    )
    doc_id = doc.id
    version_id = doc.versions[0].id

    upload_event = await EventService.emit_event(
        db=db_session,
        organization_id=test_org.id,
        case_id=case.id,
        event_type="DOCUMENT_UPLOADED",
        payload={"document_id": str(doc_id), "document_version_id": str(version_id)},
    )

    result = await CaseOrchestrator.dispatch_event(
        db=db_session,
        event=upload_event,
        actor=test_user,
        storage=storage,
        model_adapter=LowConfidenceInvoiceModel(),
    )

    assert result.status == OrchestrationStatus.WAITING_ON_HUMAN, f"Expected WAITING_ON_HUMAN but got {result.status}, error: {result.error}"
    assert any("REVIEW_TASK_CREATED" in action for action in result.actions_taken)

    # Verify Task created in database
    tasks_res = await db_session.execute(select(Task).where(Task.case_id == case.id))
    tasks = list(tasks_res.scalars().all())
    assert len(tasks) == 1
    assert tasks[0].task_type == "DOCUMENT_REVIEW"


@pytest.mark.asyncio
async def test_orchestrator_task_completion_advances_waiting_case(
    db_session: AsyncSession, test_org: Organization, test_user: User
):
    """Completing a human review task unblocks case and progresses workflow."""
    proc = await ProcessService.create_process(
        db=db_session,
        organization_id=test_org.id,
        process_in=ProcessCreate(name="Task Progression Process", code="task_prog"),
    )
    versions = await ProcessService.get_versions_by_process_id(db_session, proc.id)
    pv = versions[0]

    stage_1 = await WorkflowService.create_stage(
        db_session,
        WorkflowStageCreate(process_version_id=pv.id, name="Review Stage", code="REVIEW", stage_order=1, is_initial=True),
    )
    stage_2 = await WorkflowService.create_stage(
        db_session,
        WorkflowStageCreate(process_version_id=pv.id, name="Done Stage", code="DONE", stage_order=2, is_terminal=True),
    )
    await WorkflowService.create_transition(
        db_session,
        WorkflowTransitionCreate(
            process_version_id=pv.id,
            from_stage_id=stage_1.id,
            to_stage_id=stage_2.id,
            name="Approve Transition",
        ),
    )
    await ProcessService.publish_version(db_session, pv.id)

    case = await CaseService.create_case(
        db=db_session,
        organization_id=test_org.id,
        created_by_user_id=test_user.id,
        case_in=CaseCreate(title="Task Blocking Case", process_version_id=pv.id),
    )

    # Create a task on the case
    task = await TaskService.create_task(
        db=db_session,
        task_in=TaskCreate(
            case_id=case.id,
            task_type="HUMAN_REVIEW",
            title="Approve Exception",
            priority=TaskPriority.HIGH,
        ),
        created_by_id=test_user.id,
    )

    # Complete the task
    await TaskService.update_task(
        db=db_session,
        task_id=task.id,
        task_update=TaskUpdate(status=TaskStatus.COMPLETED),
        actor_id=test_user.id,
        actor_type="USER",
    )

    # Dispatch the TASK_UPDATED event produced by TaskService for the completion.
    task_events = await EventService.get_events_for_case(db_session, case.id)
    task_comp_event = next(
        event
        for event in task_events
        if event.event_type == "TASK_UPDATED"
        and event.payload.get("status") == TaskStatus.COMPLETED.value
    )

    result = await CaseOrchestrator.dispatch_event(
        db=db_session,
        event=task_comp_event,
        actor=test_user,
    )

    assert result.status == OrchestrationStatus.SUCCESS
    await db_session.refresh(case)
    assert case.current_stage_id == stage_2.id


@pytest.mark.asyncio
async def test_orchestrator_error_isolation_records_failure_event(
    db_session: AsyncSession, test_org: Organization, test_user: User
):
    """Unhandled handler exceptions record an ORCHESTRATION_FAILED event and return ERROR status."""
    event = EventRecord(
        organization_id=test_org.id,
        case_id=uuid.uuid4(),  # Non-existent case
        event_type="CASE_CREATED",
        actor_type="USER",
        actor_id=test_user.id,
        payload={},
    )
    db_session.add(event)
    await db_session.commit()
    await db_session.refresh(event)

    result = await CaseOrchestrator.dispatch_event(
        db=db_session,
        event=event,
        actor=test_user,
    )

    assert result.status == OrchestrationStatus.ERROR
    assert "not found" in (result.error or "")


@pytest.mark.asyncio
async def test_orchestrator_approval_decided_advances_stage(
    db_session: AsyncSession, test_org: Organization, test_user: User
):
    """APPROVAL_DECIDED event with an APPROVED decision progresses workflow."""
    proc = await ProcessService.create_process(
        db=db_session,
        organization_id=test_org.id,
        process_in=ProcessCreate(name="Approval Process", code="appr_proc"),
    )
    versions = await ProcessService.get_versions_by_process_id(db_session, proc.id)
    pv = versions[0]

    stage_1 = await WorkflowService.create_stage(
        db_session,
        WorkflowStageCreate(process_version_id=pv.id, name="Pending Approval", code="PEND_APPR", stage_order=1, is_initial=True),
    )
    stage_2 = await WorkflowService.create_stage(
        db_session,
        WorkflowStageCreate(process_version_id=pv.id, name="Approved Stage", code="APPR_DONE", stage_order=2, is_terminal=True),
    )
    await WorkflowService.create_transition(
        db_session,
        WorkflowTransitionCreate(
            process_version_id=pv.id,
            from_stage_id=stage_1.id,
            to_stage_id=stage_2.id,
            name="Grant Approval",
        ),
    )
    await ProcessService.publish_version(db_session, pv.id)

    case = await CaseService.create_case(
        db=db_session,
        organization_id=test_org.id,
        created_by_user_id=test_user.id,
        case_in=CaseCreate(title="Approval Case", process_version_id=pv.id),
    )

    # Request and decide approval
    approval = await ApprovalService.request_approval(
        db=db_session,
        approval_in=ApprovalCreate(
            case_id=case.id,
            approval_type="MANAGER_SIGN_OFF",
        ),
        organization_id=test_org.id,
        actor_id=test_user.id,
    )

    await ApprovalService.decide_approval(
        db=db_session,
        approval_id=approval.id,
        decided_by_user_id=test_user.id,
        decision_in=ApprovalDecisionRequest(
            decision=ApprovalDecision.APPROVED.value,
            comment="Looks good to go",
        ),
        organization_id=test_org.id,
    )

    # Emit & Dispatch APPROVAL_DECIDED
    appr_event = await EventService.emit_event(
        db=db_session,
        organization_id=test_org.id,
        case_id=case.id,
        event_type="APPROVAL_DECIDED",
        actor_type="USER",
        actor_id=test_user.id,
        payload={"approval_id": str(approval.id), "decision": ApprovalDecision.APPROVED.value},
    )

    result = await CaseOrchestrator.dispatch_event(
        db=db_session,
        event=appr_event,
        actor=test_user,
    )

    assert result.status == OrchestrationStatus.SUCCESS
    await db_session.refresh(case)
    assert case.current_stage_id == stage_2.id


@pytest.mark.asyncio
async def test_orchestrator_verification_completed_evaluates_workflow(
    db_session: AsyncSession, test_org: Organization, test_user: User
):
    """VERIFICATION_COMPLETED event triggers workflow evaluation and advances stage."""
    proc = await ProcessService.create_process(
        db=db_session,
        organization_id=test_org.id,
        process_in=ProcessCreate(name="Verif Flow", code="verif_flow"),
    )
    versions = await ProcessService.get_versions_by_process_id(db_session, proc.id)
    pv = versions[0]

    stage_1 = await WorkflowService.create_stage(
        db_session,
        WorkflowStageCreate(process_version_id=pv.id, name="Verify Stage", code="STAGE_VERIF", stage_order=1, is_initial=True),
    )
    stage_2 = await WorkflowService.create_stage(
        db_session,
        WorkflowStageCreate(process_version_id=pv.id, name="Verified Stage", code="STAGE_PASSED", stage_order=2, is_terminal=True),
    )
    await WorkflowService.create_transition(
        db_session,
        WorkflowTransitionCreate(
            process_version_id=pv.id,
            from_stage_id=stage_1.id,
            to_stage_id=stage_2.id,
            name="Passed Verification",
        ),
    )
    await ProcessService.publish_version(db_session, pv.id)

    case = await CaseService.create_case(
        db=db_session,
        organization_id=test_org.id,
        created_by_user_id=test_user.id,
        case_in=CaseCreate(title="Verif Case", process_version_id=pv.id),
    )

    verif_comp_event = await EventService.emit_event(
        db=db_session,
        organization_id=test_org.id,
        case_id=case.id,
        event_type="VERIFICATION_COMPLETED",
        actor_type="SYSTEM",
        payload={"case_id": str(case.id), "status": "PASSED"},
    )

    result = await CaseOrchestrator.dispatch_event(
        db=db_session,
        event=verif_comp_event,
        actor=test_user,
    )

    assert result.status == OrchestrationStatus.SUCCESS
    await db_session.refresh(case)
    assert case.current_stage_id == stage_2.id


@pytest.mark.asyncio
async def test_orchestrator_workflow_transition_terminal_stage(
    db_session: AsyncSession, test_org: Organization, test_user: User
):
    """WORKFLOW_TRANSITION event into a terminal stage updates actions taken and details."""
    proc = await ProcessService.create_process(
        db=db_session,
        organization_id=test_org.id,
        process_in=ProcessCreate(name="Terminal Flow", code="term_flow"),
    )
    versions = await ProcessService.get_versions_by_process_id(db_session, proc.id)
    pv = versions[0]

    terminal_stage = await WorkflowService.create_stage(
        db_session,
        WorkflowStageCreate(process_version_id=pv.id, name="Terminal Stage", code="TERMINAL", stage_order=1, is_initial=True, is_terminal=True),
    )
    await ProcessService.publish_version(db_session, pv.id)

    case = await CaseService.create_case(
        db=db_session,
        organization_id=test_org.id,
        created_by_user_id=test_user.id,
        case_in=CaseCreate(title="Terminal Case", process_version_id=pv.id),
    )

    trans_event = await EventService.emit_event(
        db=db_session,
        organization_id=test_org.id,
        case_id=case.id,
        event_type="WORKFLOW_TRANSITIONED",
        actor_type="SYSTEM",
        payload={"to_stage_id": str(terminal_stage.id)},
    )

    result = await CaseOrchestrator.dispatch_event(
        db=db_session,
        event=trans_event,
        actor=test_user,
    )

    assert result.status == OrchestrationStatus.SUCCESS
    assert any("TERMINAL_STAGE_ENTERED" in action for action in result.actions_taken)
    assert result.details.get("terminal") is True
