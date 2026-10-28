"""Phase 11 Verification Agent contract tests."""

import json
import uuid

import pytest
from sqlalchemy import select

from app.agents.models import AgentExecution
from app.agents.schemas import AgentRunRequest
from app.agents.service import AgentOrchestratorService
from app.domain.cases.schemas import CaseCreate
from app.domain.cases.service import CaseService
from app.domain.processes.schemas import ProcessCreate
from app.domain.processes.service import ProcessService
from app.domain.verifications.models import (
    VerificationDefinition,
    VerificationExecution,
)
from app.domain.workflows.schemas import WorkflowStageCreate
from app.security.models import Permission, Role, RolePermission
from app.tools.models import ToolExecution


class VerificationModel:
    async def generate_json(self, *, system_prompt, user_prompt, response_schema):
        context = json.loads(user_prompt)
        if "tool_calls" in str(response_schema):
            definition = context["verification_definitions"][0]
            return {
                "selected_verification_ids": [definition["id"]],
                "missing_information": [],
                "tool_calls": [
                    {
                        "tool_name": "run_verification",
                        "arguments": {"verification_id": definition["id"]},
                        "rationale": "Run the configured deterministic verification.",
                    }
                ],
            }, "test-model"
        result = context["deterministic_results"][0]
        return {
            "summary": "The configured check returned its deterministic status.",
            "findings": [
                {
                    "execution_id": "model-generated-invalid-id",
                    "explanation": "Reported the gateway result.",
                }
            ],
            "discrepancies": [
                "The deterministic check requires reviewer confirmation."
            ],
            "review_required": False,
            "review_reasons": [],
        }, "test-model"


async def _setup_verification_case(db_session, test_org, test_user):
    role = Role(organization_id=test_org.id, name="ADMIN")
    db_session.add(role)
    await db_session.flush()
    permission = Permission(code="tool.run_verification")
    db_session.add(permission)
    await db_session.flush()
    db_session.add(RolePermission(role_id=role.id, permission_id=permission.id))

    process = await ProcessService.create_process(
        db=db_session,
        organization_id=test_org.id,
        process_in=ProcessCreate(
            name="Verification test", code=f"VER_{uuid.uuid4().hex[:6]}"
        ),
    )
    version = (await ProcessService.get_versions_by_process_id(db_session, process.id))[
        0
    ]
    stage = await ProcessService.add_stage_to_version(
        db=db_session,
        version_id=version.id,
        stage_in=WorkflowStageCreate(
            process_version_id=version.id,
            name="Review",
            code="REVIEW",
            stage_order=1,
            is_initial=True,
        ),
    )
    await ProcessService.publish_version(db_session, version.id)
    version.configuration = {
        "tool_gateway": {
            "allowed_tools": {
                "run_verification": {
                    "enabled": True,
                    "allowed_agents": ["VERIFICATION"],
                },
            }
        }
    }
    case = await CaseService.create_case(
        db=db_session,
        organization_id=test_org.id,
        created_by_user_id=test_user.id,
        case_in=CaseCreate(
            process_version_id=version.id, title="Verification case", initial_data={}
        ),
    )
    definition = VerificationDefinition(
        process_version_id=version.id,
        stage_id=stage.id,
        name="Configured check",
        code=f"CHECK_{uuid.uuid4().hex[:6]}",
        description="Test deterministic check.",
    )
    db_session.add(definition)
    await db_session.commit()
    await db_session.refresh(definition)
    return case, definition


@pytest.mark.asyncio
async def test_verification_agent_runs_gateway_check_and_preserves_deterministic_result(
    db_session,
    test_org,
    test_user,
):
    case, definition = await _setup_verification_case(db_session, test_org, test_user)
    response = await AgentOrchestratorService.run_agent(
        db=db_session,
        actor=test_user,
        request=AgentRunRequest(case_id=case.id, agent_type="VERIFICATION"),
        model_adapter=VerificationModel(),
    )

    assert response.success is True
    assert response.execution_id is not None
    deterministic = response.result_data["deterministic_results"]
    assert len(deterministic) == 1
    assert deterministic[0]["status"] == "NOT_APPLICABLE"
    assert response.result_data["interpretation"]["discrepancies"]
    assert response.result_data["interpretation"]["findings"] == [
        {"explanation": "Reported the gateway result."}
    ]
    assert response.result_data["review_required"] is True
    assert response.proposals[0].proposed_action == "REQUEST_HUMAN_REVIEW"

    gateway_call = (
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
    assert gateway_call is not None
    assert gateway_call.requested_by_type == "AGENT"
    verification_run = (
        (
            await db_session.execute(
                select(VerificationExecution).where(
                    VerificationExecution.case_id == case.id,
                    VerificationExecution.verification_id == definition.id,
                )
            )
        )
        .scalars()
        .first()
    )
    assert verification_run is not None
    agent_run = await db_session.get(AgentExecution, response.execution_id)
    assert agent_run is not None and agent_run.status == "SUCCESS"


@pytest.mark.asyncio
async def test_verification_agent_rejects_unconfigured_or_unauthorized_tool(
    db_session,
    test_org,
    test_user,
):
    case, _definition = await _setup_verification_case(db_session, test_org, test_user)

    class UnauthorizedToolModel(VerificationModel):
        async def generate_json(self, *, system_prompt, user_prompt, response_schema):
            if "tool_calls" in str(response_schema):
                return {
                    "selected_verification_ids": [],
                    "missing_information": [],
                    "tool_calls": [
                        {
                            "tool_name": "create_task",
                            "arguments": {"title": "Bypass"},
                            "rationale": "Not allowed.",
                        }
                    ],
                }, "test-model"
            raise AssertionError("Interpretation must not run after an invalid plan")

    with pytest.raises(ValueError, match="not available to this agent"):
        await AgentOrchestratorService.run_agent(
            db=db_session,
            actor=test_user,
            request=AgentRunRequest(case_id=case.id, agent_type="VERIFICATION"),
            model_adapter=UnauthorizedToolModel(),
        )

    assert (
        await db_session.execute(
            select(ToolExecution).where(
                ToolExecution.case_id == case.id,
            )
        )
    ).scalars().all() == []
