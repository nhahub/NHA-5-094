from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.cases.models import CaseParticipant
from app.domain.cases.schemas import CaseCreate
from app.domain.cases.service import CaseService
from app.domain.organizations.models import Organization
from app.domain.processes.schemas import ProcessCreate, WorkflowStageCreate
from app.domain.processes.service import ProcessService
from app.security.models import RoleEnum, User


async def _published_version(db: AsyncSession, org_id: uuid.UUID) -> uuid.UUID:
    process = await ProcessService.create_process(
        db,
        organization_id=org_id,
        process_in=ProcessCreate(name="Customer Intake", code=f"CUSTOMER_{uuid.uuid4().hex[:8]}"),
    )
    versions = await ProcessService.get_versions_by_process_id(db, process.id)
    version = versions[0]
    await ProcessService.add_stage_to_version(
        db,
        version.id,
        WorkflowStageCreate(name="Customer intake", code="CUSTOMER_INTAKE", is_initial=True),
    )
    await ProcessService.publish_version(db, version.id)
    return version.id


@pytest.mark.asyncio
async def test_customer_cases_are_participant_scoped_and_minimized(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_org: Organization,
    test_user: User,
):
    test_user.role = RoleEnum.CUSTOMER
    other_customer = User(
        organization_id=test_org.id,
        email="second-customer@example.com",
        name="Other Customer",
        hashed_password="unused",
        role=RoleEnum.CUSTOMER,
        is_active=True,
    )
    db_session.add(other_customer)
    await db_session.flush()
    version_id = await _published_version(db_session, test_org.id)

    own_case = await CaseService.create_case(
        db_session,
        organization_id=test_org.id,
        created_by_user_id=test_user.id,
        case_in=CaseCreate(
            process_version_id=version_id,
            title="My request",
            case_metadata={"private_internal_note": "must not be returned"},
        ),
        customer_user_id=test_user.id,
    )
    other_case = await CaseService.create_case(
        db_session,
        organization_id=test_org.id,
        created_by_user_id=other_customer.id,
        case_in=CaseCreate(process_version_id=version_id, title="Another customer's request"),
        customer_user_id=other_customer.id,
    )

    listed = await async_client.get("/api/v1/cases/mine")
    assert listed.status_code == 200, listed.text
    assert [row["id"] for row in listed.json()] == [str(own_case.id)]
    assert "case_metadata" not in listed.json()[0]
    assert "organization_id" not in listed.json()[0]
    assert "private_internal_note" not in listed.text

    own_detail = await async_client.get(f"/api/v1/cases/mine/{own_case.id}")
    other_detail = await async_client.get(f"/api/v1/cases/mine/{other_case.id}")
    assert own_detail.status_code == 200
    assert other_detail.status_code == 404

    assert (await async_client.get("/api/v1/cases")).status_code == 403
    assert (await async_client.get(f"/api/v1/cases/{own_case.id}/review")).status_code == 403
    assert (await async_client.get(f"/api/v1/documents/case/{own_case.id}")).status_code == 403
    assert (await async_client.post(
        f"/api/v1/cases/{own_case.id}/close",
        json={"status": "COMPLETED", "reason": "customer should not close cases"},
    )).status_code == 403


@pytest.mark.asyncio
async def test_customer_case_creation_links_the_authenticated_customer(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_org: Organization,
    test_user: User,
):
    test_user.role = RoleEnum.CUSTOMER
    version_id = await _published_version(db_session, test_org.id)

    response = await async_client.post(
        "/api/v1/cases/mine",
        json={
            "process_version_id": str(version_id),
            "title": "New customer request",
            "case_metadata": {"customer_supplied": "value"},
        },
    )

    assert response.status_code == 201, response.text
    created = response.json()
    assert created["title"] == "New customer request"
    assert "case_metadata" not in created
    participant = await db_session.scalar(
        select(CaseParticipant).where(
            CaseParticipant.case_id == uuid.UUID(created["id"]),
            CaseParticipant.user_id == test_user.id,
            CaseParticipant.participant_type == "CUSTOMER",
        )
    )
    assert participant is not None
    assert (await async_client.get("/api/v1/cases/mine")).json()[0]["id"] == created["id"]
