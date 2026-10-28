"""Authenticated identity must override caller-supplied workflow authority."""

import uuid

import pytest

from app.domain.workflows import router
from app.domain.workflows.schemas import TransitionRequest, TransitionResult
from app.security.models import RoleEnum


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint_name", ["validate_transition", "execute_transition"])
async def test_workflow_route_uses_authenticated_identity_and_role(
    endpoint_name, monkeypatch, db_session, test_user
):
    test_user.role = RoleEnum.EMPLOYEE
    request = TransitionRequest(
        case_id=uuid.uuid4(),
        to_stage_id=uuid.uuid4(),
        actor_id=uuid.uuid4(),
        actor_role="ADMIN",
        actor_type="AGENT",
    )
    captured = {}

    async def fake_service(db, received_request, organization_id=None):
        captured.update(
            actor_id=received_request.actor_id,
            actor_role=received_request.actor_role,
            actor_type=received_request.actor_type,
            organization_id=organization_id,
        )
        return TransitionResult(
            allowed=True, reason="ok", case_id=received_request.case_id
        )

    method = "validate_transition" if endpoint_name == "validate_transition" else "execute_transition"
    monkeypatch.setattr(router.WorkflowService, method, fake_service)
    await getattr(router, endpoint_name)(request, db_session, test_user)

    assert captured == {
        "actor_id": test_user.id,
        "actor_role": RoleEnum.EMPLOYEE.value,
        "actor_type": "USER",
        "organization_id": test_user.organization_id,
    }
