"""Phase 12 — Workflow Agent contract, security, gateway, and end-to-end tests.

Tests verify:
1. Structured action contract — allowlisted actions, unknown action rejection
2. Context scoping — actor organization, process version, current stage
3. Security — cross-tenant rejection, disabled agent, terminal case
4. Model validation — malformed plan, unknown IDs, stale stage ID
5. Tool Gateway integration — task creation, approval request, transition tool
6. Deterministic service authority — WorkflowService rejects bad transitions
7. Trace/audit — AgentExecution persisted on success and failure
8. API dispatch — proposal_state clearly distinguishes PROPOSED/EXECUTED/REJECTED
9. Prompt injection boundary — document content cannot alter action
10. Fail-closed — gateway denial produces REJECTED, not a successful transition
"""

import json
import uuid

import pytest
from app.agents.models import AgentExecution
from app.agents.schemas import AgentRunRequest
from app.agents.service import AgentOrchestratorService
from app.agents.workflow_agent import ALLOWED_ACTIONS, WorkflowAgent, WorkflowAgentError
from app.domain.approvals.models import Approval, ApprovalDecision
from app.domain.cases.models import CaseStatus
from app.domain.cases.schemas import CaseCreate
from app.domain.cases.service import CaseService
from app.domain.organizations.models import Organization
from app.domain.processes.schemas import ProcessCreate
from app.domain.processes.service import ProcessService
from app.domain.tasks.models import Task
from app.domain.workflows.schemas import WorkflowStageCreate, WorkflowTransitionCreate
from app.domain.workflows.service import WorkflowService
from app.security.models import Permission, Role, RoleEnum, RolePermission, User
from app.tools.models import ToolExecution
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Fake model adapters
# ---------------------------------------------------------------------------

class _ProposeTransitionModel:
    """Returns PROPOSE_TRANSITION (no tool call — pure proposal)."""

    def __init__(self, target_stage_id: str | None = None):
        self._target = target_stage_id

    async def generate_json(self, *, system_prompt, user_prompt, response_schema):
        ctx = json.loads(user_prompt)
        transitions = ctx.get("available_transitions", [])
        target = self._target or (transitions[0]["to_stage_id"] if transitions else str(uuid.uuid4()))
        return {
            "action_type": "PROPOSE_TRANSITION",
            "rationale": "All requirements look satisfied; proposing next stage.",
            "confidence": 0.85,
            "missing_information": [],
            "target_stage_id": target,
            "tool_call": None,
        }, "test-model"


class _RequestApprovalModel:
    """Returns REQUEST_APPROVAL with a create_task tool call."""

    async def generate_json(self, *, system_prompt, user_prompt, response_schema):
        return {
            "action_type": "REQUEST_APPROVAL",
            "rationale": "Pending approval required before transition.",
            "confidence": 0.9,
            "missing_information": [],
            "target_stage_id": None,
            "tool_call": {
                "tool_name": "request_approval",
                "arguments": {"approval_type": "MANAGER_APPROVAL"},
            },
        }, "test-model"


class _CreateTaskModel:
    """Returns CREATE_TASK with a create_task tool call."""

    async def generate_json(self, *, system_prompt, user_prompt, response_schema):
        return {
            "action_type": "CREATE_TASK",
            "rationale": "A document is missing; creating a task for the reviewer.",
            "confidence": 0.8,
            "missing_information": ["Commercial invoice not uploaded."],
            "target_stage_id": None,
            "tool_call": {
                "tool_name": "create_task",
                "arguments": {"title": "Upload commercial invoice", "priority": "HIGH"},
            },
        }, "test-model"


class _TransitionToolModel:
    """Returns PROPOSE_TRANSITION with a transition_workflow tool call."""

    def __init__(self, to_stage_id: str):
        self._to_stage_id = to_stage_id

    async def generate_json(self, *, system_prompt, user_prompt, response_schema):
        context = json.loads(user_prompt)
        current_stage_id = context["case"]["current_stage_id"]
        return {
            "action_type": "PROPOSE_TRANSITION",
            "rationale": "All requirements verified; executing transition.",
            "confidence": 0.95,
            "missing_information": [],
            "target_stage_id": self._to_stage_id,
            "tool_call": {
                "tool_name": "transition_workflow",
                "arguments": {
                    "to_stage_id": self._to_stage_id,
                    "from_stage_id": current_stage_id,
                    "reason": "Agent-initiated transition after verification.",
                },
            },
        }, "test-model"


class _UnknownActionModel:
    """Returns an action type not in ALLOWED_ACTIONS."""

    async def generate_json(self, *, system_prompt, user_prompt, response_schema):
        return {
            "action_type": "DELETE_CASE",
            "rationale": "Test injection.",
            "confidence": 1.0,
            "missing_information": [],
        }, "test-model"


class _MalformedModel:
    """Returns a non-dict response."""

    async def generate_json(self, *, system_prompt, user_prompt, response_schema):
        return "this is not json", "test-model"


class _UnknownStageModel:
    """Returns PROPOSE_TRANSITION with a made-up stage ID."""

    async def generate_json(self, *, system_prompt, user_prompt, response_schema):
        return {
            "action_type": "PROPOSE_TRANSITION",
            "rationale": "Test unknown stage.",
            "confidence": 0.9,
            "missing_information": [],
            "target_stage_id": str(uuid.uuid4()),  # not in context
            "tool_call": None,
        }, "test-model"


class _UnknownToolModel:
    """Returns a tool_call referencing a tool not in the gateway."""

    async def generate_json(self, *, system_prompt, user_prompt, response_schema):
        return {
            "action_type": "CREATE_TASK",
            "rationale": "Bypass attempt.",
            "confidence": 1.0,
            "missing_information": [],
            "target_stage_id": None,
            "tool_call": {
                "tool_name": "execute_arbitrary_sql",
                "arguments": {"query": "DROP TABLE cases"},
            },
        }, "test-model"


class _EscalateModel:
    """Returns ESCALATE (no tool call)."""

    async def generate_json(self, *, system_prompt, user_prompt, response_schema):
        return {
            "action_type": "ESCALATE",
            "rationale": "Too many missing documents; escalating to reviewer.",
            "confidence": 0.7,
            "missing_information": ["Commercial invoice", "Packing list"],
            "target_stage_id": None,
            "tool_call": None,
        }, "test-model"


# ---------------------------------------------------------------------------
# Test setup helper
# ---------------------------------------------------------------------------

async def _setup_workflow_case(
    db_session: AsyncSession,
    test_org: Organization,
    test_user: User,
    *,
    add_gateway_permissions: bool = True,
    configure_transition_tool: bool = False,
    configure_task_tools: bool = False,
):
    """Create a minimal process/case/workflow scenario for Workflow Agent tests."""
    # Permissions — use role name "ADMIN" to match test_user.role = RoleEnum.ADMIN
    # The gateway _authorize check matches Permission.code against
    # role names (case-insensitive) associated with the actor, so the role
    # name must be "ADMIN" to match the conftest test user.
    if add_gateway_permissions:
        for code in (
            "tool.transition_workflow",
            "tool.create_task",
            "tool.request_approval",
            "tool.run_verification",
        ):
            perm = Permission(code=code)
            db_session.add(perm)
        await db_session.flush()

        # Use name="ADMIN" to match RoleEnum.ADMIN on test_user
        role = Role(organization_id=test_org.id, name="ADMIN")
        db_session.add(role)
        await db_session.flush()

        perms = list(
            (
                await db_session.execute(select(Permission))
            )
            .scalars()
            .all()
        )
        for p in perms:
            db_session.add(RolePermission(role_id=role.id, permission_id=p.id))
        await db_session.flush()

    # Process
    process = await ProcessService.create_process(
        db=db_session,
        organization_id=test_org.id,
        process_in=ProcessCreate(
            name="Import Workflow Agent Test",
            code=f"IWA_{uuid.uuid4().hex[:6]}",
        ),
    )
    version = (await ProcessService.get_versions_by_process_id(db_session, process.id))[0]

    # Two stages: DOC_REVIEW -> APPROVAL
    s1 = await WorkflowService.create_stage(
        db_session,
        WorkflowStageCreate(
            process_version_id=version.id,
            name="Document Review",
            code="DOC_REVIEW",
            stage_order=1,
            is_initial=True,
        ),
    )
    s2 = await WorkflowService.create_stage(
        db_session,
        WorkflowStageCreate(
            process_version_id=version.id,
            name="Approval Stage",
            code="APPROVAL",
            stage_order=2,
        ),
    )
    await WorkflowService.create_transition(
        db_session,
        WorkflowTransitionCreate(
            process_version_id=version.id,
            from_stage_id=s1.id,
            to_stage_id=s2.id,
            name="To Approval",
            code="TO_APPROVAL",
        ),
    )

    await ProcessService.publish_version(db_session, version.id)

    # Tool gateway config
    allowed_tools: dict = {}
    if configure_transition_tool:
        allowed_tools["transition_workflow"] = {
            "enabled": True,
            "allowed_agents": ["WORKFLOW"],
        }
    if configure_task_tools:
        allowed_tools["create_task"] = {
            "enabled": True,
            "allowed_agents": ["WORKFLOW"],
        }
        allowed_tools["request_approval"] = {
            "enabled": True,
            "allowed_agents": ["WORKFLOW"],
        }
    if allowed_tools:
        version.configuration = {"tool_gateway": {"allowed_tools": allowed_tools}}
        await db_session.flush()

    case = await CaseService.create_case(
        db=db_session,
        organization_id=test_org.id,
        created_by_user_id=test_user.id,
        case_in=CaseCreate(
            process_version_id=version.id,
            title="Import/Export Case",
            initial_data={},
        ),
    )

    # Advance case to s1
    from app.domain.workflows.schemas import TransitionRequest
    await WorkflowService.execute_transition(
        db_session,
        TransitionRequest(
            case_id=case.id,
            to_stage_id=s1.id,
            actor_id=test_user.id,
            actor_role="ADMIN",
            actor_type="USER",
        ),
        organization_id=test_org.id,
    )
    await db_session.refresh(case)

    return case, s1, s2, version


# ---------------------------------------------------------------------------
# Test 1: Contract — PROPOSE_TRANSITION (no tool call = PROPOSED state)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_workflow_agent_propose_transition_no_tool_call(
    db_session: AsyncSession,
    test_org: Organization,
    test_user: User,
):
    """Agent returns PROPOSED when action is PROPOSE_TRANSITION with no tool call."""
    case, _s1, s2, _version = await _setup_workflow_case(
        db_session, test_org, test_user
    )
    response = await AgentOrchestratorService.run_agent(
        db=db_session,
        actor=test_user,
        request=AgentRunRequest(case_id=case.id, agent_type="WORKFLOW"),
        model_adapter=_ProposeTransitionModel(target_stage_id=str(s2.id)),
    )

    assert response.success is True
    assert response.execution_id is not None
    assert len(response.proposals) == 1
    assert response.proposals[0].proposed_action == "PROPOSE_TRANSITION"
    assert response.result_data["proposal_state"] == "PROPOSED"
    assert response.result_data["action_type"] == "PROPOSE_TRANSITION"

    # AgentExecution persisted
    exec_record = await db_session.get(AgentExecution, response.execution_id)
    assert exec_record is not None
    assert exec_record.status == "SUCCESS"
    assert exec_record.case_id == case.id


# ---------------------------------------------------------------------------
# Test 2: ESCALATE action (no tool call)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_workflow_agent_escalate_returns_proposal(
    db_session: AsyncSession,
    test_org: Organization,
    test_user: User,
):
    case, _s1, _s2, _ = await _setup_workflow_case(db_session, test_org, test_user)
    response = await AgentOrchestratorService.run_agent(
        db=db_session,
        actor=test_user,
        request=AgentRunRequest(case_id=case.id, agent_type="WORKFLOW"),
        model_adapter=_EscalateModel(),
    )

    assert response.success is True
    assert response.proposals[0].proposed_action == "ESCALATE"
    assert response.result_data["proposal_state"] == "PROPOSED"
    assert "Commercial invoice" in str(response.result_data["missing_information"])


# ---------------------------------------------------------------------------
# Test 3: CREATE_TASK tool call through Gateway
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_workflow_agent_create_task_through_gateway(
    db_session: AsyncSession,
    test_org: Organization,
    test_user: User,
):
    """Agent CREATE_TASK action creates a task via Tool Gateway; state = EXECUTED."""
    case, _s1, _s2, _ = await _setup_workflow_case(
        db_session, test_org, test_user, configure_task_tools=True
    )
    response = await AgentOrchestratorService.run_agent(
        db=db_session,
        actor=test_user,
        request=AgentRunRequest(case_id=case.id, agent_type="WORKFLOW"),
        model_adapter=_CreateTaskModel(),
    )

    assert response.success is True
    assert response.result_data["proposal_state"] == "EXECUTED"
    tool_results = response.result_data["tool_results"]
    assert len(tool_results) == 1
    assert tool_results[0]["tool_name"] == "create_task"
    assert tool_results[0]["success"] is True

    # Task persisted in DB
    tasks = list(
        (
            await db_session.execute(
                select(Task).where(Task.case_id == case.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(tasks) == 1
    assert tasks[0].title == "Upload commercial invoice"

    # ToolExecution persisted
    tool_exec = (
        (
            await db_session.execute(
                select(ToolExecution).where(
                    ToolExecution.case_id == case.id,
                    ToolExecution.status == "SUCCESS",
                )
            )
        )
        .scalars()
        .first()
    )
    assert tool_exec is not None
    assert tool_exec.requested_by_type == "AGENT"

    # AgentExecution links
    agent_exec = await db_session.get(AgentExecution, response.execution_id)
    assert agent_exec is not None
    assert agent_exec.status == "SUCCESS"


# ---------------------------------------------------------------------------
# Test 4: REQUEST_APPROVAL tool call
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_workflow_agent_request_approval_through_gateway(
    db_session: AsyncSession,
    test_org: Organization,
    test_user: User,
):
    case, _s1, _s2, _ = await _setup_workflow_case(
        db_session, test_org, test_user, configure_task_tools=True
    )
    response = await AgentOrchestratorService.run_agent(
        db=db_session,
        actor=test_user,
        request=AgentRunRequest(case_id=case.id, agent_type="WORKFLOW"),
        model_adapter=_RequestApprovalModel(),
    )

    assert response.success is True
    assert response.result_data["proposal_state"] == "EXECUTED"

    # Approval persisted
    approvals = list(
        (
            await db_session.execute(
                select(Approval).where(Approval.case_id == case.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(approvals) == 1
    assert approvals[0].decision == ApprovalDecision.PENDING.value


# ---------------------------------------------------------------------------
# Test 5: transition_workflow tool executes actual stage transition
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_workflow_agent_transition_tool_executes_real_transition(
    db_session: AsyncSession,
    test_org: Organization,
    test_user: User,
):
    """transition_workflow tool causes actual deterministic state change."""
    case, s1, s2, _ = await _setup_workflow_case(
        db_session, test_org, test_user,
        configure_transition_tool=True,
    )
    assert case.current_stage_id == s1.id

    response = await AgentOrchestratorService.run_agent(
        db=db_session,
        actor=test_user,
        request=AgentRunRequest(case_id=case.id, agent_type="WORKFLOW"),
        model_adapter=_TransitionToolModel(to_stage_id=str(s2.id)),
    )

    assert response.success is True
    assert response.result_data["proposal_state"] == "EXECUTED"
    tool_results = response.result_data["tool_results"]
    assert tool_results[0]["success"] is True
    assert tool_results[0]["output"]["transition_allowed"] is True

    # Case stage actually changed in DB
    await db_session.refresh(case)
    assert case.current_stage_id == s2.id


# ---------------------------------------------------------------------------
# Test 6: Security — cross-tenant case rejected
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cross_tenant_rejection_does_not_write_into_case_owner_audit_log(
    db_session: AsyncSession,
    test_org: Organization,
    test_user: User,
):
    from app.domain.audit.models import AuditLog
    from app.domain.workflows.schemas import TransitionRequest

    case, _s1, s2, _ = await _setup_workflow_case(db_session, test_org, test_user)
    audit_query = select(AuditLog).where(
        AuditLog.action == "WORKFLOW_TRANSITION_REJECTED",
        AuditLog.resource_id == case.id,
    )
    before_count = len((await db_session.execute(audit_query)).scalars().all())
    result = await WorkflowService.execute_transition(
        db_session,
        TransitionRequest(
            case_id=case.id,
            to_stage_id=s2.id,
            actor_id=test_user.id,
            actor_role="ADMIN",
            actor_type="USER",
        ),
        organization_id=uuid.uuid4(),
    )
    assert result.allowed is False
    after_count = len((await db_session.execute(audit_query)).scalars().all())
    assert after_count == before_count


async def test_workflow_agent_rejects_cross_tenant_case(
    db_session: AsyncSession,
    test_org: Organization,
    test_user: User,
):
    """Agent must reject a case from a different organization."""
    # Create a second org and case
    other_org = Organization(
        id=uuid.uuid4(),
        name="Other Org",
        slug="other-org",
        status="active",
        settings={},
        is_active=True,
    )
    db_session.add(other_org)
    await db_session.flush()

    other_user = User(
        id=uuid.uuid4(),
        organization_id=other_org.id,
        email="other@other.ai",
        name="Other",
        role=RoleEnum.ADMIN,
        hashed_password="x",
        status="active",
        is_active=True,
    )
    db_session.add(other_user)
    await db_session.flush()

    process = await ProcessService.create_process(
        db=db_session,
        organization_id=other_org.id,
        process_in=ProcessCreate(name="Other Process", code=f"OP_{uuid.uuid4().hex[:6]}"),
    )
    version = (await ProcessService.get_versions_by_process_id(db_session, process.id))[0]

    # publish_version requires at least one WorkflowStage
    await WorkflowService.create_stage(
        db_session,
        WorkflowStageCreate(
            process_version_id=version.id,
            name="Initial",
            code="INITIAL",
            stage_order=1,
            is_initial=True,
        ),
    )
    await ProcessService.publish_version(db_session, version.id)
    other_case = await CaseService.create_case(
        db=db_session,
        organization_id=other_org.id,
        created_by_user_id=other_user.id,
        case_in=CaseCreate(
            process_version_id=version.id, title="Other Case", initial_data={}
        ),
    )

    # test_user (org A) tries to access other_case (org B)
    with pytest.raises(WorkflowAgentError, match="organization scope"):
        await WorkflowAgent().run(
            db=db_session,
            actor=test_user,
            case_id=other_case.id,
        )


# ---------------------------------------------------------------------------
# Test 7: Security — terminal case rejected
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_workflow_agent_rejects_terminal_case(
    db_session: AsyncSession,
    test_org: Organization,
    test_user: User,
):
    case, _s1, _s2, _ = await _setup_workflow_case(db_session, test_org, test_user)
    # Force case into terminal state
    case.status = CaseStatus.COMPLETED.value
    await db_session.flush()

    with pytest.raises(WorkflowAgentError, match="terminal status"):
        await WorkflowAgent(model_adapter=_EscalateModel()).run(
            db=db_session,
            actor=test_user,
            case_id=case.id,
        )


# ---------------------------------------------------------------------------
# Test 8: Unknown action type — fail closed, trace persisted
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_workflow_agent_rejects_unknown_action_and_traces_failure(
    db_session: AsyncSession,
    test_org: Organization,
    test_user: User,
):
    case, _s1, _s2, _ = await _setup_workflow_case(db_session, test_org, test_user)

    with pytest.raises(WorkflowAgentError, match="unknown action"):
        await WorkflowAgent(model_adapter=_UnknownActionModel()).run(
            db=db_session,
            actor=test_user,
            case_id=case.id,
        )

    # Failure trace persisted
    failure = (
        (
            await db_session.execute(
                select(AgentExecution).where(
                    AgentExecution.case_id == case.id,
                    AgentExecution.status == "FAILED",
                )
            )
        )
        .scalars()
        .first()
    )
    assert failure is not None


# ---------------------------------------------------------------------------
# Test 9: Malformed model response — fail closed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_workflow_agent_rejects_malformed_response(
    db_session: AsyncSession,
    test_org: Organization,
    test_user: User,
):
    case, s1, _s2, _ = await _setup_workflow_case(db_session, test_org, test_user)

    with pytest.raises(WorkflowAgentError):
        await WorkflowAgent(model_adapter=_MalformedModel()).run(
            db=db_session,
            actor=test_user,
            case_id=case.id,
        )

    # Case stage unchanged
    await db_session.refresh(case)
    assert case.current_stage_id == s1.id


# ---------------------------------------------------------------------------
# Test 10: Unknown stage ID — fail closed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_workflow_agent_rejects_unknown_stage_id(
    db_session: AsyncSession,
    test_org: Organization,
    test_user: User,
):
    """Model proposing a stage ID not in the context must be rejected."""
    case, s1, _s2, _ = await _setup_workflow_case(db_session, test_org, test_user)

    with pytest.raises(WorkflowAgentError, match="available transitions"):
        await WorkflowAgent(model_adapter=_UnknownStageModel()).run(
            db=db_session,
            actor=test_user,
            case_id=case.id,
        )

    # No state change
    await db_session.refresh(case)
    assert case.current_stage_id == s1.id


# ---------------------------------------------------------------------------
# Test 11: Unknown tool name — fail closed
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "action_type,tool_name,arguments,overrides,expected_error",
    [
        ("ESCALATE", "transition_workflow", {"to_stage_id": "00000000-0000-0000-0000-000000000002"}, {}, "cannot execute tool"),
        ("PROPOSE_TRANSITION", "transition_workflow", {"to_stage_id": "00000000-0000-0000-0000-000000000003", "from_stage_id": "00000000-0000-0000-0000-000000000001"}, {}, "target must match"),
        ("PROPOSE_TRANSITION", "transition_workflow", {"to_stage_id": "00000000-0000-0000-0000-000000000002", "from_stage_id": "00000000-0000-0000-0000-000000000004"}, {}, "from_stage_id must match"),
        ("CREATE_TASK", "create_task", {"title": "Task"}, {"untrusted": True}, "unknown fields"),
        ("RUN_VERIFICATION", "run_verification", {"verification_id": "00000000-0000-0000-0000-000000000005"}, {}, "requires verification_id"),
    ],
)
def test_workflow_agent_rejects_action_tool_or_contract_mismatch(
    action_type, tool_name, arguments, overrides, expected_error
):
    plan = {
        "action_type": action_type,
        "rationale": "Test plan.",
        "confidence": 0.8,
        "missing_information": [],
        "target_stage_id": "00000000-0000-0000-0000-000000000002" if action_type == "PROPOSE_TRANSITION" else None,
        "tool_call": {"tool_name": tool_name, "arguments": arguments},
        **overrides,
    }
    context = {
        "case": {"current_stage_id": "00000000-0000-0000-0000-000000000001"},
        "current_stage_id": "00000000-0000-0000-0000-000000000001",
        "available_transitions": [{"to_stage_id": "00000000-0000-0000-0000-000000000002"}],
        "verification_definitions": [],
    }
    with pytest.raises(WorkflowAgentError, match=expected_error):
        WorkflowAgent()._validate_plan(plan, context, {tool_name: {}})


@pytest.mark.asyncio
async def test_workflow_agent_rejects_unknown_tool_name(
    db_session: AsyncSession,
    test_org: Organization,
    test_user: User,
):
    """Agent cannot call a tool not in the gateway allowlist."""
    case, _s1, _s2, _ = await _setup_workflow_case(db_session, test_org, test_user)

    with pytest.raises(WorkflowAgentError, match="not available to this agent"):
        await WorkflowAgent(model_adapter=_UnknownToolModel()).run(
            db=db_session,
            actor=test_user,
            case_id=case.id,
        )

    # No tasks or tool executions created
    tasks = (await db_session.execute(select(Task).where(Task.case_id == case.id))).scalars().all()
    assert len(tasks) == 0


# ---------------------------------------------------------------------------
# Test 12: Gateway denial → REJECTED state (not a successful transition)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_workflow_agent_gateway_denial_yields_rejected(
    db_session: AsyncSession,
    test_org: Organization,
    test_user: User,
):
    """When the transition tool is allowed but the engine rejects, state=REJECTED.

    Strategy: create 3 stages s1→s2→s3. Advance case to s2. The model proposes
    PROPOSE_TRANSITION with target_stage_id=s3 (valid in context at s2) and a
    transition_workflow tool call to s3. We then forcibly break the precondition
    by advancing the case to s3 before the agent executes — the engine sees the
    case is already at s3, so the s2→s3 transition is rejected deterministically.

    This proves model proposals can be stale and that the deterministic service
    is the final authority, not the model's claim.
    """
    # Build 3-stage process
    process = await ProcessService.create_process(
        db=db_session,
        organization_id=test_org.id,
        process_in=ProcessCreate(
            name="Denial Test Process",
            code=f"DEN_{uuid.uuid4().hex[:6]}",
        ),
    )
    version = (await ProcessService.get_versions_by_process_id(db_session, process.id))[0]

    s1 = await WorkflowService.create_stage(
        db_session,
        WorkflowStageCreate(
            process_version_id=version.id, name="Stage 1", code="S1",
            stage_order=1, is_initial=True,
        ),
    )
    s2 = await WorkflowService.create_stage(
        db_session,
        WorkflowStageCreate(
            process_version_id=version.id, name="Stage 2", code="S2", stage_order=2,
        ),
    )
    s3 = await WorkflowService.create_stage(
        db_session,
        WorkflowStageCreate(
            process_version_id=version.id, name="Stage 3", code="S3",
            stage_order=3, is_terminal=True,
        ),
    )
    await WorkflowService.create_transition(
        db_session,
        WorkflowTransitionCreate(
            process_version_id=version.id,
            from_stage_id=s1.id, to_stage_id=s2.id, name="To S2", code="TO_S2",
        ),
    )
    await WorkflowService.create_transition(
        db_session,
        WorkflowTransitionCreate(
            process_version_id=version.id,
            from_stage_id=s2.id, to_stage_id=s3.id, name="To S3", code="TO_S3",
        ),
    )
    await ProcessService.publish_version(db_session, version.id)

    # Grant permissions
    perm = Permission(code="tool.transition_workflow")
    db_session.add(perm)
    await db_session.flush()
    role = Role(organization_id=test_org.id, name="ADMIN")
    db_session.add(role)
    await db_session.flush()
    db_session.add(RolePermission(role_id=role.id, permission_id=perm.id))
    await db_session.flush()

    version.configuration = {
        "tool_gateway": {
            "allowed_tools": {
                "transition_workflow": {"enabled": True, "allowed_agents": ["WORKFLOW"]},
            }
        }
    }
    await db_session.flush()

    case = await CaseService.create_case(
        db=db_session,
        organization_id=test_org.id,
        created_by_user_id=test_user.id,
        case_in=CaseCreate(
            process_version_id=version.id, title="Denial Test", initial_data={},
        ),
    )

    # Advance to s1
    from app.domain.workflows.schemas import TransitionRequest
    await WorkflowService.execute_transition(
        db_session,
        TransitionRequest(
            case_id=case.id, to_stage_id=s1.id,
            actor_id=test_user.id, actor_role="ADMIN", actor_type="USER",
        ),
        organization_id=test_org.id,
    )
    # Advance to s2 — now the agent sees s2→s3 as the only available transition
    await WorkflowService.execute_transition(
        db_session,
        TransitionRequest(
            case_id=case.id, to_stage_id=s2.id,
            actor_id=test_user.id, actor_role="ADMIN", actor_type="USER",
        ),
        organization_id=test_org.id,
    )
    await db_session.refresh(case)
    assert case.current_stage_id == s2.id

    class _StaleTransitionModel:
        async def generate_json(self, *, system_prompt, user_prompt, response_schema):
            context = json.loads(user_prompt)
            planned_from_stage = context["case"]["current_stage_id"]
            assert planned_from_stage == str(s2.id)
            # Simulate another actor moving the case while the model is planning.
            case.current_stage_id = s3.id
            await db_session.flush()
            return {
                "action_type": "PROPOSE_TRANSITION",
                "rationale": "All requirements verified; execute the planned transition.",
                "confidence": 0.9,
                "missing_information": [],
                "target_stage_id": str(s3.id),
                "tool_call": {
                    "tool_name": "transition_workflow",
                    "arguments": {
                        "to_stage_id": str(s3.id),
                        "from_stage_id": planned_from_stage,
                        "reason": "Stale proposal test.",
                    },
                },
            }, "test-model"

    response = await AgentOrchestratorService.run_agent(
        db=db_session,
        actor=test_user,
        request=AgentRunRequest(case_id=case.id, agent_type="WORKFLOW"),
        model_adapter=_StaleTransitionModel(),
    )

    assert response.success is True
    assert response.result_data["proposal_state"] == "REJECTED"
    assert response.result_data["tool_results"][0]["success"] is False
    await db_session.refresh(case)
    assert case.current_stage_id == s3.id
    agent_exec = await db_session.get(AgentExecution, response.execution_id)
    assert agent_exec is not None and agent_exec.status == "SUCCESS"


# ---------------------------------------------------------------------------
# Test 13: Disabled agent → rejected
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_workflow_agent_disabled_raises_error(
    db_session: AsyncSession,
    test_org: Organization,
    test_user: User,
):
    case, _s1, _s2, _ = await _setup_workflow_case(db_session, test_org, test_user)

    # Disable the agent definition
    from app.agents.models import AgentDefinition
    from sqlalchemy import or_
    select(AgentDefinition).where(
        AgentDefinition.agent_type == "WORKFLOW",
        or_(
            AgentDefinition.organization_id == test_org.id,
            AgentDefinition.organization_id.is_(None),
        ),
    )
    # Create one explicitly disabled
    defn = AgentDefinition(
        organization_id=test_org.id,
        name="WorkflowAgent",
        agent_type="WORKFLOW",
        description="Disabled.",
        enabled=False,
    )
    db_session.add(defn)
    await db_session.commit()

    with pytest.raises(WorkflowAgentError, match="disabled"):
        await WorkflowAgent(model_adapter=_EscalateModel()).run(
            db=db_session,
            actor=test_user,
            case_id=case.id,
        )


# ---------------------------------------------------------------------------
# Test 14: Cross-tenant workflow service — validate_transition with org_id
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_workflow_service_validate_transition_rejects_cross_tenant(
    db_session: AsyncSession,
    test_org: Organization,
    test_user: User,
):
    """WorkflowService.validate_transition with wrong org_id must return not-allowed."""
    from app.domain.workflows.schemas import TransitionRequest

    case, _s1, s2, _ = await _setup_workflow_case(
        db_session, test_org, test_user, add_gateway_permissions=False
    )

    wrong_org_id = uuid.uuid4()
    result = await WorkflowService.validate_transition(
        db=db_session,
        request=TransitionRequest(
            case_id=case.id,
            to_stage_id=s2.id,
            actor_id=test_user.id,
            actor_role="ADMIN",
            actor_type="USER",
        ),
        organization_id=wrong_org_id,
    )

    assert result.allowed is False
    assert "organization scope" in result.reason.lower() or "does not exist" in result.reason.lower()


# ---------------------------------------------------------------------------
# Test 15: Workflow Agent context — non-terminal, correct version, correct stage
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_workflow_agent_context_scoped_to_case_stage(
    db_session: AsyncSession,
    test_org: Organization,
    test_user: User,
):
    """Verify the built context contains the correct stage and transitions."""
    case, s1, s2, version = await _setup_workflow_case(
        db_session, test_org, test_user
    )

    agent = WorkflowAgent(model_adapter=_EscalateModel())
    ctx = await agent._build_context(db_session, test_user, case)

    assert ctx["case"]["current_stage_id"] == str(s1.id)
    assert ctx["case"]["current_stage_code"] == "DOC_REVIEW"
    assert ctx["case"]["process_version_id"] == str(version.id)
    assert ctx["case"]["is_terminal_stage"] is False

    transition_ids = [t["to_stage_id"] for t in ctx["available_transitions"]]
    assert str(s2.id) in transition_ids


# ---------------------------------------------------------------------------
# Test 16: ALLOWED_ACTIONS set is finite and contains expected entries
# ---------------------------------------------------------------------------

def test_allowed_actions_are_finite_and_not_extensible():
    assert "PROPOSE_TRANSITION" in ALLOWED_ACTIONS
    assert "REQUEST_DOCUMENT" in ALLOWED_ACTIONS
    assert "RUN_VERIFICATION" in ALLOWED_ACTIONS
    assert "CREATE_TASK" in ALLOWED_ACTIONS
    assert "REQUEST_APPROVAL" in ALLOWED_ACTIONS
    assert "ESCALATE" in ALLOWED_ACTIONS
    # Must be a frozenset — immutable; model cannot extend at runtime
    assert isinstance(ALLOWED_ACTIONS, frozenset)
    # Should not contain dangerous/arbitrary operations
    assert "EXECUTE_SQL" not in ALLOWED_ACTIONS
    assert "DELETE_CASE" not in ALLOWED_ACTIONS


# ---------------------------------------------------------------------------
# Test 17: API dispatch — WORKFLOW agent_type routed to WorkflowAgent
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_agent_orchestrator_dispatches_workflow(
    db_session: AsyncSession,
    test_org: Organization,
    test_user: User,
):
    case, _s1, _s2, _ = await _setup_workflow_case(db_session, test_org, test_user)

    response = await AgentOrchestratorService.run_agent(
        db=db_session,
        actor=test_user,
        request=AgentRunRequest(case_id=case.id, agent_type="WORKFLOW"),
        model_adapter=_EscalateModel(),
    )

    assert response.agent_type == "WORKFLOW"
    assert response.success is True
    assert response.execution_id is not None
    # result_data must distinguish proposal state
    assert "proposal_state" in response.result_data
    assert response.result_data["proposal_state"] in ("PROPOSED", "EXECUTED", "REJECTED")


# ---------------------------------------------------------------------------
# Test 18: transition_workflow tool registered and WORKFLOW in allowed_agents
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_transition_workflow_tool_registered_for_workflow_agent(
    db_session: AsyncSession,
    test_org: Organization,
    test_user: User,
):
    """transition_workflow must be in the gateway registry and allow WORKFLOW agents."""
    case, _s1, _s2, _version = await _setup_workflow_case(
        db_session, test_org, test_user, configure_transition_tool=True
    )
    from app.tools.service import ToolGatewayService

    tools = await ToolGatewayService.list_tools(db=db_session, actor=test_user, case_id=case.id)
    tool_names = {t.name for t in tools}
    assert "transition_workflow" in tool_names

    transition_tool = next(t for t in tools if t.name == "transition_workflow")
    assert "WORKFLOW" in transition_tool.allowed_agents
