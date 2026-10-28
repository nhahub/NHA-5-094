import uuid
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.testclient import TestClient
from httpx import AsyncClient
from app.main import app
from app.domain.cases.models import Case
from app.domain.organizations.models import Organization
from app.domain.processes.models import Process, ProcessVersion
from app.security.models import Permission, Role, RoleEnum, RolePermission, User
from app.agents.models import AgentDefinition
from app.tools.models import ToolExecution
from app.tools.schemas import ToolExecutionRequest
from app.tools.service import ToolGatewayService


def test_api_routes_registered() -> None:
    """Verify that all domain routers are registered under /api/v1 in OpenAPI."""
    openapi_schema = app.openapi()
    paths = list(openapi_schema["paths"].keys())

    assert "/api/v1/auth/login" in paths
    assert "/api/v1/cases" in paths
    assert "/api/v1/processes" in paths
    assert "/api/v1/workflows/stages" in paths
    assert "/api/v1/documents" in paths
    assert "/api/v1/verifications/definitions" in paths
    assert "/api/v1/rules" in paths
    assert "/api/v1/tasks" in paths
    assert "/api/v1/approvals" in paths
    assert "/api/v1/tools" in paths
    assert "/api/v1/agents/run" in paths
    assert any(p.startswith("/api/v1/knowledge") for p in paths)
    assert "/api/v1/events" in paths
    assert "/api/v1/audit" in paths


@pytest.mark.asyncio
async def test_tool_gateway_calculation_is_scoped_authorized_and_audited(
    db_session: AsyncSession,
    test_org: Organization,
    test_user: User,
) -> None:
    """Tool execution applies process policy, validates contracts, and persists traces."""
    process = Process(organization_id=test_org.id, name="Gateway Test", code=f"GW_{uuid.uuid4().hex[:8]}")
    db_session.add(process)
    await db_session.flush()
    version = ProcessVersion(
        process_id=process.id,
        version_number=1,
        configuration={"tool_gateway": {"allowed_tools": {"calculate_order_total": {"enabled": True}}}},
    )
    db_session.add(version)
    await db_session.flush()
    case = Case(
        organization_id=test_org.id,
        process_id=process.id,
        process_version_id=version.id,
        case_number=f"CASE-{uuid.uuid4().hex[:12]}",
        title="Tool gateway case",
        status="OPEN",
        case_metadata={},
    )
    role = Role(organization_id=test_org.id, name="ADMIN")
    permission = Permission(code="tool.calculate_order_total")
    db_session.add_all([case, role, permission])
    await db_session.flush()
    db_session.add(RolePermission(role_id=role.id, permission_id=permission.id))
    await db_session.commit()

    req = ToolExecutionRequest(
        tool_name="calculate_order_total",
        case_id=case.id,
        arguments={"quantity": 10.0, "unit_price": 25.0, "tax_rate": 0.1},
    )
    result = await ToolGatewayService.execute_tool(db_session, req, test_user)
    assert result.success is True
    assert result.output["subtotal"] == "250.00"
    assert result.output["tax"] == "25.000"
    assert result.output["total"] == "275.000"
    assert result.execution_id is not None

    execution = await db_session.get(ToolExecution, result.execution_id)
    assert execution is not None
    assert execution.status == "SUCCESS"
    assert execution.case_id == case.id
    available_tools = await ToolGatewayService.list_tools(db_session, test_user, case.id)
    assert [tool.name for tool in available_tools] == ["calculate_order_total"]

    invalid = ToolExecutionRequest(
        tool_name="calculate_order_total",
        case_id=case.id,
        arguments={"quantity": 10.0},
    )
    invalid_result = await ToolGatewayService.execute_tool(db_session, invalid, test_user)
    assert invalid_result.success is False
    assert invalid_result.http_status_code == 422

    # Process policy rejection is also recorded as an execution attempt.
    version.configuration = {"tool_gateway": {"allowed_tools": {}}}
    await db_session.commit()
    rejected = await ToolGatewayService.execute_tool(db_session, req, test_user)
    assert rejected.success is False
    assert rejected.status == "REJECTED"
    assert rejected.http_status_code == 403
    rejected_execution = await db_session.get(ToolExecution, rejected.execution_id)
    assert rejected_execution is not None
    assert rejected_execution.status == "REJECTED"

    # An authenticated user still needs the specific tool permission.
    unauthorized_user = User(
        id=uuid.uuid4(),
        organization_id=test_org.id,
        email=f"unprivileged-{uuid.uuid4().hex[:8]}@verifia.ai",
        name="Unprivileged User",
        role=RoleEnum.EMPLOYEE,
        hashed_password="not-used",
        is_active=True,
    )
    version.configuration = {"tool_gateway": {"allowed_tools": {"calculate_order_total": {"enabled": True}}}}
    await db_session.commit()
    unauthorized = await ToolGatewayService.execute_tool(db_session, req, unauthorized_user)
    assert unauthorized.success is False
    assert unauthorized.http_status_code == 403

    # Agent access is an intersection of the built-in contract and process policy.
    agent = AgentDefinition(
        organization_id=test_org.id,
        name="Verification agent",
        agent_type="VERIFICATION",
        enabled=True,
    )
    db_session.add(agent)
    version.configuration = {"tool_gateway": {"allowed_tools": {
        "calculate_order_total": {"enabled": True, "allowed_agents": ["VERIFICATION"]},
    }}}
    await db_session.commit()
    agent_request = ToolExecutionRequest(
        tool_name="calculate_order_total",
        case_id=case.id,
        arguments={"quantity": 2, "unit_price": 3},
    )
    agent_result = await ToolGatewayService.execute_tool(
        db_session, agent_request, test_user, agent_id=agent.id
    )
    assert agent_result.success is True
    agent_execution = await db_session.get(ToolExecution, agent_result.execution_id)
    assert agent_execution is not None
    assert agent_execution.requested_by_type == "AGENT"

    version.configuration = {"tool_gateway": {"allowed_tools": {
        "calculate_order_total": {"enabled": True, "allowed_agents": []},
    }}}
    await db_session.commit()
    denied_agent = await ToolGatewayService.execute_tool(
        db_session, agent_request, test_user, agent_id=agent.id
    )
    assert denied_agent.success is False
    assert denied_agent.http_status_code == 403

    unknown = ToolExecutionRequest(
        tool_name="unregistered_capability", case_id=case.id, arguments={}
    )
    unknown_result = await ToolGatewayService.execute_tool(db_session, unknown, test_user)
    assert unknown_result.success is False
    assert unknown_result.http_status_code == 404

    other_org = Organization(
        id=uuid.uuid4(), name="Other organization", slug=f"other-{uuid.uuid4().hex[:8]}",
        status="active", settings={}, is_active=True,
    )
    db_session.add(other_org)
    await db_session.commit()
    other_user = User(
        id=uuid.uuid4(), organization_id=other_org.id,
        email=f"other-{uuid.uuid4().hex[:8]}@verifia.ai", name="Other User",
        role=test_user.role, hashed_password="not-used", is_active=True,
    )
    cross_org = await ToolGatewayService.execute_tool(db_session, req, other_user)
    assert cross_org.success is False
    assert cross_org.http_status_code == 403

    executions = list((await db_session.execute(select(ToolExecution))).scalars().all())
    assert len(executions) == 8


@pytest.mark.asyncio
async def test_tool_gateway_api_filters_discovery_and_rejects_agent_spoofing(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_org: Organization,
    test_user: User,
) -> None:
    process = Process(organization_id=test_org.id, name="API Gateway Test", code=f"GW_API_{uuid.uuid4().hex[:8]}")
    db_session.add(process)
    await db_session.flush()
    version = ProcessVersion(
        process_id=process.id,
        version_number=1,
        configuration={"tool_gateway": {"allowed_tools": {
            "calculate_order_total": {"enabled": True, "allowed_agents": []},
        }}},
    )
    db_session.add(version)
    await db_session.flush()
    case = Case(
        organization_id=test_org.id,
        process_id=process.id,
        process_version_id=version.id,
        case_number=f"CASE-{uuid.uuid4().hex[:12]}",
        title="Tool gateway API case",
        status="OPEN",
        case_metadata={},
    )
    role = Role(organization_id=test_org.id, name="ADMIN")
    permission = Permission(code="tool.calculate_order_total")
    db_session.add_all([case, role, permission])
    await db_session.flush()
    db_session.add(RolePermission(role_id=role.id, permission_id=permission.id))
    await db_session.commit()

    listed = await async_client.get(f"/api/v1/tools?case_id={case.id}")
    assert listed.status_code == 200
    assert [tool["name"] for tool in listed.json()] == ["calculate_order_total"]

    response = await async_client.post("/api/v1/tools/execute", json={
        "tool_name": "calculate_order_total",
        "case_id": str(case.id),
        "arguments": {"quantity": 2, "unit_price": 3},
    })
    assert response.status_code == 200, response.text
    execution_id = response.json()["execution_id"]
    execution = await db_session.get(ToolExecution, uuid.UUID(execution_id))
    assert execution is not None
    assert execution.requested_by_type == "USER"
    assert execution.requested_by_id == test_user.id

    spoofed = await async_client.post("/api/v1/tools/execute", json={
        "tool_name": "calculate_order_total",
        "case_id": str(case.id),
        "agent_id": str(uuid.uuid4()),
        "arguments": {"quantity": 2, "unit_price": 3},
    })
    assert spoofed.status_code == 422

    invalid = await async_client.post("/api/v1/tools/execute", json={
        "tool_name": "calculate_order_total",
        "case_id": str(case.id),
        "arguments": {"quantity": 2},
    })
    assert invalid.status_code == 422
    assert "execution_id" in invalid.json()["detail"]
