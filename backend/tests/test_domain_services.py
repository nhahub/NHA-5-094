"""
Unit tests for Phase 3: Domain Services (ProcessService, CaseService, TaskService, EventService).
Validates business logic, state transitions, event emissions, and immutability invariants.
"""
import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.organizations.models import Organization
from app.security.models import User
from app.domain.processes.service import ProcessService
from app.domain.processes.schemas import (
    ProcessCreate,
    ProcessVersionCreate,
    WorkflowStageCreate,
    WorkflowTransitionCreate,
    RequirementCreate,
    BusinessRuleCreate,
    VerificationDefinitionCreate,
)
from app.domain.cases.service import CaseService
from app.domain.cases.schemas import (
    CaseCreate,
    CaseUpdate,
    CaseCloseRequest,
    CaseParticipantCreate,
)
from app.domain.tasks.service import TaskService
from app.domain.tasks.schemas import TaskCreate, TaskUpdate
from app.domain.tasks.models import TaskPriority, TaskStatus
from app.events.service import EventService


@pytest.mark.asyncio
async def test_case_requires_published_process_version_in_same_organization(
    db_session: AsyncSession, test_org: Organization, test_user: User
):
    draft_process = await ProcessService.create_process(
        db_session,
        test_org.id,
        ProcessCreate(name="Draft Process", code="DRAFT_CASE_GUARD"),
    )
    draft_version = (await ProcessService.get_versions_by_process_id(db_session, draft_process.id))[0]
    with pytest.raises(ValueError, match="published process version"):
        await CaseService.create_case(
            db_session,
            organization_id=test_org.id,
            created_by_user_id=test_user.id,
            case_in=CaseCreate(process_version_id=draft_version.id, title="Draft case"),
        )

    other_org = Organization(
        name="Other Tenant",
        slug=f"other-{uuid.uuid4().hex[:8]}",
        status="active",
        settings={},
        is_active=True,
    )
    db_session.add(other_org)
    await db_session.commit()
    foreign_process = await ProcessService.create_process(
        db_session,
        other_org.id,
        ProcessCreate(name="Foreign Process", code="FOREIGN_CASE_GUARD"),
    )
    foreign_version = (await ProcessService.get_versions_by_process_id(db_session, foreign_process.id))[0]
    await ProcessService.add_stage_to_version(
        db_session,
        foreign_version.id,
        WorkflowStageCreate(name="Intake", code="FOREIGN_INTAKE", stage_order=1, is_initial=True),
    )
    await ProcessService.publish_version(db_session, foreign_version.id)
    with pytest.raises(ValueError, match="same organization"):
        await CaseService.create_case(
            db_session,
            organization_id=test_org.id,
            created_by_user_id=test_user.id,
            case_in=CaseCreate(process_version_id=foreign_version.id, title="Cross-tenant case"),
        )


@pytest.mark.asyncio
async def test_process_lifecycle_and_immutability(
    db_session: AsyncSession, test_org: Organization, test_user: User
):
    """Test full process lifecycle: creation -> version draft -> stage/rule addition -> publish -> immutability check -> archive."""
    # 1. Create Process (which initializes draft v1 automatically)
    proc_in = ProcessCreate(
        name="Mortgage Application Process",
        code="MORTGAGE_APP",
        description="End-to-end mortgage onboarding and verification",
    )
    process = await ProcessService.create_process(
        db=db_session,
        organization_id=test_org.id,
        process_in=proc_in,
        created_by=test_user.id,
    )
    assert process.id is not None
    assert process.name == "Mortgage Application Process"
    assert process.code == "MORTGAGE_APP"

    # 2. Query Initial Version (v1 is in DRAFT)
    versions = await ProcessService.get_versions_by_process_id(db=db_session, process_id=process.id)
    assert len(versions) == 1
    version = versions[0]
    assert version.version_number == 1
    assert version.status == "DRAFT"

    # 3. Add Workflow Stages to DRAFT Version
    stage1 = await ProcessService.add_stage_to_version(
        db=db_session,
        version_id=version.id,
        stage_in=WorkflowStageCreate(
            name="Document Intake",
            code="DOC_INTAKE",
            stage_order=1,
            is_initial=True,
        ),
    )
    assert stage1.name == "Document Intake"
    assert stage1.stage_order == 1
    assert stage1.is_initial is True

    stage2 = await ProcessService.add_stage_to_version(
        db=db_session,
        version_id=version.id,
        stage_in=WorkflowStageCreate(
            name="Income Verification",
            code="INCOME_VERIF",
            stage_order=2,
            is_initial=False,
        ),
    )
    assert stage2.name == "Income Verification"

    # 4. Add Transition
    transition = await ProcessService.add_transition_to_version(
        db=db_session,
        version_id=version.id,
        transition_in=WorkflowTransitionCreate(
            from_stage_id=stage1.id,
            to_stage_id=stage2.id,
            name="Proceed to Verification",
            code="PROCEED_TO_VERIF",
            condition_config={"all_docs_verified": True},
        ),
    )
    assert transition.name == "Proceed to Verification"

    # 5. Add Requirement, Business Rule, Verification Definition
    req = await ProcessService.add_requirement_to_version(
        db=db_session,
        version_id=version.id,
        req_in=RequirementCreate(
            name="W2 Tax Form",
            code="REQ_W2",
            type="DOCUMENT",
            required=True,
            stage_id=stage1.id,
        ),
    )
    assert req.name == "W2 Tax Form"

    rule = await ProcessService.add_rule_to_version(
        db=db_session,
        version_id=version.id,
        rule_in=BusinessRuleCreate(
            name="Minimum Credit Score 650",
            code="RULE_MIN_CREDIT_SCORE",
            rule_type="DECISION_TABLE",
            expression={"credit_score": {">=": 650}},
            severity="ERROR",
        ),
    )
    assert rule.code == "RULE_MIN_CREDIT_SCORE"

    verif = await ProcessService.add_verification_to_version(
        db=db_session,
        version_id=version.id,
        verif_in=VerificationDefinitionCreate(
            name="Payslip Integrity and Tamper Check",
            code="VERIF_PAYSLIP_INTEGRITY",
            result_policy={"allow_override": True},
        ),
    )
    assert verif.code == "VERIF_PAYSLIP_INTEGRITY"

    # 6. Publish Version
    published_ver = await ProcessService.publish_version(db=db_session, version_id=version.id)
    assert published_ver.status == "PUBLISHED"
    assert published_ver.published_at is not None

    # 7. Immutability Enforcement Check: modifications on PUBLISHED version must fail
    with pytest.raises(ValueError, match="cannot be modified"):
        await ProcessService.add_stage_to_version(
            db=db_session,
            version_id=version.id,
            stage_in=WorkflowStageCreate(name="Late Stage", code="LATE_STAGE", stage_order=3),
        )

    with pytest.raises(ValueError, match="cannot be modified"):
        await ProcessService.add_requirement_to_version(
            db=db_session,
            version_id=version.id,
            req_in=RequirementCreate(name="Extra Doc", code="REQ_EXTRA", type="DOCUMENT"),
        )

    with pytest.raises(ValueError, match="cannot be modified"):
        await ProcessService.add_rule_to_version(
            db=db_session,
            version_id=version.id,
            rule_in=BusinessRuleCreate(
                name="Late Rule",
                code="RULE_LATE",
                expression={},
            ),
        )

    # 8. Archive Version
    archived_ver = await ProcessService.archive_version(db=db_session, version_id=version.id)
    assert archived_ver.status == "ARCHIVED"


@pytest.mark.asyncio
async def test_case_lifecycle_state_and_events(
    db_session: AsyncSession, test_org: Organization, test_user: User
):
    """Test case creation, event emission, state snapshot retrieval, metadata update, and closing."""
    # 1. Setup Process & Version with an initial stage
    proc = await ProcessService.create_process(
        db=db_session,
        organization_id=test_org.id,
        process_in=ProcessCreate(name="KYC Onboarding", code="KYC_ONBOARD"),
    )
    versions = await ProcessService.get_versions_by_process_id(db=db_session, process_id=proc.id)
    ver = versions[0]
    stage = await ProcessService.add_stage_to_version(
        db=db_session,
        version_id=ver.id,
        stage_in=WorkflowStageCreate(name="Identity Check", code="ID_CHECK", stage_order=1, is_initial=True),
    )
    await ProcessService.publish_version(db=db_session, version_id=ver.id)

    # 2. Create Case
    case_in = CaseCreate(
        process_version_id=ver.id,
        title="John Doe KYC Case",
        case_metadata={"applicant_name": "John Doe", "country": "US"},
    )
    case = await CaseService.create_case(
        db=db_session,
        organization_id=test_org.id,
        created_by_user_id=test_user.id,
        case_in=case_in,
    )
    assert case.id is not None
    assert case.case_number.startswith("CASE-")
    assert case.current_stage_id == stage.id
    assert case.status == "OPEN"

    # 3. Verify CASE_CREATED event was emitted
    events = await EventService.get_events_for_case(db=db_session, case_id=case.id)
    assert len(events) >= 1
    assert any(e.event_type == "CASE_CREATED" for e in events)

    # 4. Add Participant
    participant = await CaseService.add_participant(
        db=db_session,
        case_id=case.id,
        participant_in=CaseParticipantCreate(
            user_id=test_user.id,
            participant_type="REVIEWER",
            name="Compliance Reviewer",
        ),
    )
    assert participant.participant_type == "REVIEWER"

    # 5. Get Comprehensive Case State
    state = await CaseService.get_case_state(db=db_session, case_id=case.id)
    assert state.case.id == case.id
    assert state.case.case_number == case.case_number
    assert len(state.participants) == 1
    assert state.participants[0].participant_type == "REVIEWER"

    # 6. Update Case Metadata
    updated_case = await CaseService.update_case(
        db=db_session,
        case_id=case.id,
        case_update=CaseUpdate(title="John Doe KYC Case (Verified VIP)"),
    )
    assert updated_case.title == "John Doe KYC Case (Verified VIP)"

    # 7. Close Case
    closed_case = await CaseService.close_case(
        db=db_session,
        case_id=case.id,
        close_req=CaseCloseRequest(
            status="COMPLETED",
            reason="All identity requirements verified successfully",
        ),
        actor_id=test_user.id,
    )
    assert closed_case.status == "COMPLETED"
    assert closed_case.completed_at is not None

    # 8. Check CASE_COMPLETED event
    events_after_close = await EventService.get_events_for_case(db=db_session, case_id=case.id)
    assert any(e.event_type == "CASE_COMPLETED" for e in events_after_close)

    # 9. Verify Closed Case State Protection Invariant
    with pytest.raises(ValueError, match="Cannot modify case in 'COMPLETED' status"):
        await CaseService.update_case(
            db=db_session,
            case_id=case.id,
            case_update=CaseUpdate(title="Attempting edit on closed case"),
        )


@pytest.mark.asyncio
async def test_task_lifecycle_and_events(
    db_session: AsyncSession, test_org: Organization, test_user: User
):
    """Test task creation, querying by user/case, completion transition, and event emission."""
    # 1. Setup Process & Case
    proc = await ProcessService.create_process(
        db=db_session,
        organization_id=test_org.id,
        process_in=ProcessCreate(name="Claim Review", code="CLAIM_REV"),
    )
    versions = await ProcessService.get_versions_by_process_id(db=db_session, process_id=proc.id)
    ver = versions[0]
    await ProcessService.add_stage_to_version(
        db_session,
        ver.id,
        WorkflowStageCreate(name="Intake", code="CLAIM_INTAKE", stage_order=1, is_initial=True),
    )
    await ProcessService.publish_version(db_session, ver.id)
    case = await CaseService.create_case(
        db=db_session,
        organization_id=test_org.id,
        created_by_user_id=test_user.id,
        case_in=CaseCreate(process_version_id=ver.id, title="Auto Claim #8891"),
    )

    # 2. Create Task
    task_in = TaskCreate(
        case_id=case.id,
        task_type="MANUAL_REVIEW",
        title="Inspect Police Report",
        description="Verify date and timestamp matches collision timeline",
        priority=TaskPriority.HIGH,
        assigned_user_id=test_user.id,
    )
    task = await TaskService.create_task(
        db=db_session,
        task_in=task_in,
        created_by_id=test_user.id,
        created_by_type="USER",
    )
    assert task.id is not None
    assert task.status == "ASSIGNED"
    assert task.priority == "HIGH"

    # 3. Check TASK_CREATED event
    events = await EventService.get_events_for_case(db=db_session, case_id=case.id)
    assert any(e.event_type == "TASK_CREATED" for e in events)

    # 4. Query Tasks
    user_tasks = await TaskService.get_tasks_for_user(
        db=db_session, user_id=test_user.id, organization_id=test_org.id
    )
    assert len(user_tasks) >= 1
    assert user_tasks[0].id == task.id

    case_tasks = await TaskService.get_tasks_by_case(db=db_session, case_id=case.id)
    assert len(case_tasks) == 1

    # 5. Complete Task
    updated_task = await TaskService.update_task(
        db=db_session,
        task_id=task.id,
        task_update=TaskUpdate(
            status=TaskStatus.COMPLETED,
            completion_metadata={"notes": "Police report verified and valid"},
        ),
        actor_id=test_user.id,
    )
    assert updated_task.status == "COMPLETED"
    assert updated_task.completed_at is not None
    assert updated_task.completion_metadata["notes"] == "Police report verified and valid"
