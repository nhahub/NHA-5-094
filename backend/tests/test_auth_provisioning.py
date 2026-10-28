from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.domain.audit.models import AuditLog
from app.domain.organizations.models import Organization
from app.infrastructure.database.session import get_db
from app.main import app
from app.security.models import RoleEnum, User
from app.security.schemas import ProvisionedUserCreate
from app.security.service import AuthService


@pytest_asyncio.fixture
async def identity_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Exercise the actual bearer authentication dependency against an isolated database."""
    app.dependency_overrides.clear()

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
    app.dependency_overrides.clear()


def bearer(user: User) -> dict[str, str]:
    token = AuthService.create_access_token(user.id, user.organization_id, user.role)
    return {"Authorization": f"Bearer {token}"}


def provision_payload(**overrides: object) -> dict[str, object]:
    return {
        "email": "reviewer@example.com",
        "full_name": "Case Reviewer",
        "password": "long-password-for-local-tests",
        "role": "EMPLOYEE",
        **overrides,
    }


@pytest.mark.asyncio
async def test_anonymous_registration_is_retired_and_admin_routes_require_auth(
    identity_client: AsyncClient,
):
    response = await identity_client.post(
        "/api/v1/auth/register",
        json={
            "email": "attacker@example.com",
            "full_name": "Attacker",
            "password": "long-password-for-local-tests",
            "organization_id": str(uuid.uuid4()),
            "role": "ADMIN",
            "is_active": True,
        },
    )
    assert response.status_code == 404
    assert (await identity_client.get("/api/v1/auth/users")).status_code == 401
    assert (await identity_client.post("/api/v1/auth/users", json=provision_payload())).status_code == 401


@pytest.mark.asyncio
async def test_non_admin_cannot_list_or_provision_users(
    identity_client: AsyncClient, test_user: User
):
    test_user.role = RoleEnum.EMPLOYEE
    headers = bearer(test_user)

    listed = await identity_client.get("/api/v1/auth/users", headers=headers)
    created = await identity_client.post(
        "/api/v1/auth/users", headers=headers, json=provision_payload()
    )

    assert listed.status_code == 403
    assert created.status_code == 403


@pytest.mark.asyncio
async def test_admin_provisions_same_tenant_non_admin_user_and_safe_audit(
    identity_client: AsyncClient, db_session: AsyncSession, test_user: User
):
    response = await identity_client.post(
        "/api/v1/auth/users", headers=bearer(test_user), json=provision_payload(role="MANAGER")
    )

    assert response.status_code == 201, response.text
    created = response.json()
    assert created["organization_id"] == str(test_user.organization_id)
    assert created["email"] == "reviewer@example.com"
    assert created["role"] == "MANAGER"
    assert created["is_active"] is True
    assert "password" not in created

    audit = await db_session.scalar(
        select(AuditLog).where(AuditLog.resource_id == uuid.UUID(created["id"]))
    )
    assert audit is not None
    assert audit.organization_id == test_user.organization_id
    assert audit.actor_id == test_user.id
    assert audit.action == "USER_PROVISIONED"
    assert audit.after_state == {
        "email": "reviewer@example.com",
        "role": "MANAGER",
        "is_active": True,
    }
    assert "password" not in str(audit.after_state).casefold()
    assert "hash" not in str(audit.after_state).casefold()


@pytest.mark.asyncio
async def test_failed_audit_commit_rolls_back_provisioned_user(
    db_session: AsyncSession, test_user: User, monkeypatch
):
    async def fail_commit():
        raise IntegrityError("forced audit commit failure", {}, RuntimeError("test"))

    monkeypatch.setattr(db_session, "commit", fail_commit)

    with pytest.raises(ValueError, match="Unable to provision"):
        await AuthService.provision_user(
            db_session,
            organization_id=test_user.organization_id,
            actor_id=test_user.id,
            user_in=ProvisionedUserCreate(**provision_payload(email="rollback@example.com")),
        )

    assert await db_session.scalar(
        select(User).where(User.email == "rollback@example.com")
    ) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "extra_fields",
    [
        {"organization_id": str(uuid.uuid4())},
        {"is_active": False},
        {"role": "ADMIN"},
    ],
)
async def test_provisioning_rejects_tenant_activation_and_admin_role_overrides(
    identity_client: AsyncClient,
    test_user: User,
    extra_fields: dict[str, object],
):
    response = await identity_client.post(
        "/api/v1/auth/users",
        headers=bearer(test_user),
        json=provision_payload(**extra_fields),
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_admin_user_list_is_scoped_to_actor_organization(
    identity_client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
):
    other_org = Organization(
        id=uuid.uuid4(),
        name="Other Tenant",
        slug=f"other-{uuid.uuid4().hex[:8]}",
        status="active",
        settings={},
        is_active=True,
    )
    db_session.add(other_org)
    await db_session.flush()
    db_session.add(
        User(
            organization_id=other_org.id,
            email="other@example.com",
            name="Other Tenant User",
            hashed_password="unused",
            role=RoleEnum.EMPLOYEE,
            is_active=True,
        )
    )
    await db_session.commit()

    response = await identity_client.get("/api/v1/auth/users", headers=bearer(test_user))

    assert response.status_code == 200
    assert {item["email"] for item in response.json()} == {"testuser@verifia.ai"}


@pytest.mark.asyncio
async def test_provisioning_email_is_case_insensitive_and_duplicate_is_generic(
    identity_client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
):
    first = await identity_client.post(
        "/api/v1/auth/users", headers=bearer(test_user), json=provision_payload()
    )
    second = await identity_client.post(
        "/api/v1/auth/users",
        headers=bearer(test_user),
        json=provision_payload(email="REVIEWER@EXAMPLE.COM"),
    )

    assert first.status_code == 201
    assert second.status_code == 409
    assert "reviewer@example.com" not in second.text
    audits = list((await db_session.scalars(select(AuditLog))).all())
    assert len(audits) == 1


@pytest.mark.asyncio
async def test_global_email_index_rejects_same_identity_in_another_tenant(
    db_session: AsyncSession, test_user: User
):
    other_org = Organization(
        id=uuid.uuid4(),
        name="Second Tenant",
        slug=f"second-{uuid.uuid4().hex[:8]}",
        status="active",
        settings={},
        is_active=True,
    )
    db_session.add(other_org)
    await db_session.flush()
    db_session.add(
        User(
            organization_id=other_org.id,
            email=test_user.email.upper(),
            name="Duplicate Identity",
            hashed_password="unused",
            role=RoleEnum.EMPLOYEE,
            is_active=True,
        )
    )

    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_login_fails_closed_for_legacy_ambiguous_email(monkeypatch, db_session: AsyncSession):
    monkeypatch.setattr(
        AuthService,
        "get_users_by_email",
        AsyncMock(return_value=[object(), object()]),
    )

    assert await AuthService.authenticate_user(db_session, "shared@example.com", "password") is None


@pytest.mark.asyncio
async def test_inactive_user_cannot_login(
    identity_client: AsyncClient,
    db_session: AsyncSession,
    test_org: Organization,
):
    user = User(
        organization_id=test_org.id,
        email="inactive@example.com",
        name="Inactive User",
        hashed_password=AuthService.get_password_hash("long-password-for-local-tests"),
        role=RoleEnum.EMPLOYEE,
        is_active=False,
    )
    db_session.add(user)
    await db_session.commit()

    response = await identity_client.post(
        "/api/v1/auth/login",
        json={"email": "inactive@example.com", "password": "long-password-for-local-tests"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("claim", ["org", "role", "subject"])
async def test_me_rejects_malformed_or_stale_identity_claims(
    identity_client: AsyncClient,
    test_user: User,
    claim: str,
):
    subject = str(test_user.id)
    organization_id = test_user.organization_id
    role = test_user.role
    if claim == "org":
        organization_id = uuid.uuid4()
    elif claim == "role":
        role = RoleEnum.EMPLOYEE
    else:
        subject = "not-a-uuid"
    token = jwt.encode(
        {
            "sub": subject,
            "org_id": str(organization_id),
            "role": role.value,
            "exp": 4_102_444_800,
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )

    response = await identity_client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_inactive_organization_invalidates_existing_token(
    identity_client: AsyncClient,
    test_user: User,
    test_org: Organization,
):
    test_org.is_active = False
    response = await identity_client.get("/api/v1/auth/me", headers=bearer(test_user))
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_inactive_organization_cannot_issue_new_login_token(
    identity_client: AsyncClient,
    db_session: AsyncSession,
    test_org: Organization,
):
    password = "a-long-local-test-password"
    user = User(
        organization_id=test_org.id,
        email="inactive-tenant@example.com",
        name="Inactive Tenant User",
        hashed_password=AuthService.get_password_hash(password),
        role=RoleEnum.EMPLOYEE,
        is_active=True,
    )
    test_org.is_active = False
    db_session.add(user)
    await db_session.commit()

    response = await identity_client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": password},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_existing_bearer_token(
    identity_client: AsyncClient, db_session: AsyncSession, test_user: User
):
    headers = bearer(test_user)

    assert (await identity_client.get("/api/v1/auth/me", headers=headers)).status_code == 200
    logged_out = await identity_client.post("/api/v1/auth/logout", headers=headers)

    assert logged_out.status_code == 204
    assert (await identity_client.get("/api/v1/auth/me", headers=headers)).status_code == 401

    audit = await db_session.scalar(
        select(AuditLog).where(
            AuditLog.action == "USER_SESSIONS_REVOKED",
            AuditLog.resource_id == test_user.id,
        )
    )
    assert audit is not None
    assert audit.actor_id == test_user.id
    assert audit.after_state == {"token_version": 1}
    assert audit.audit_metadata == {"reason": "logout"}


@pytest.mark.asyncio
async def test_password_change_revokes_old_session_and_keeps_audit_secret_free(
    identity_client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
):
    old_password = "original-password-long-enough"
    new_password = "new-password-long-enough-2026"
    test_user.hashed_password = AuthService.get_password_hash(old_password)
    headers = bearer(test_user)

    response = await identity_client.post(
        "/api/v1/auth/me/password",
        headers=headers,
        json={"current_password": old_password, "new_password": new_password},
    )

    assert response.status_code == 204
    assert (await identity_client.get("/api/v1/auth/me", headers=headers)).status_code == 401
    assert (await identity_client.post(
        "/api/v1/auth/login", json={"email": test_user.email, "password": old_password}
    )).status_code == 401
    login = await identity_client.post(
        "/api/v1/auth/login", json={"email": test_user.email, "password": new_password}
    )
    assert login.status_code == 200

    audit = await db_session.scalar(
        select(AuditLog).where(AuditLog.action == "USER_PASSWORD_CHANGED")
    )
    assert audit is not None
    assert audit.after_state == {"email": test_user.email, "token_version": 1}
    assert old_password not in str(audit.after_state) + str(audit.audit_metadata)
    assert new_password not in str(audit.after_state) + str(audit.audit_metadata)


@pytest.mark.asyncio
async def test_admin_password_reset_revokes_the_target_user_session(
    identity_client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
    test_org: Organization,
):
    old_password = "first-password-long-enough"
    new_password = "reset-password-long-enough-2026"
    target = User(
        organization_id=test_org.id,
        email="reset-target@example.com",
        name="Reset Target",
        hashed_password=AuthService.get_password_hash(old_password),
        role=RoleEnum.EMPLOYEE,
        is_active=True,
    )
    db_session.add(target)
    await db_session.commit()
    old_token = bearer(target)

    response = await identity_client.post(
        f"/api/v1/auth/users/{target.id}/password",
        headers=bearer(test_user),
        json={"new_password": new_password},
    )

    assert response.status_code == 204
    assert (await identity_client.get("/api/v1/auth/me", headers=old_token)).status_code == 401
    assert (await identity_client.post(
        "/api/v1/auth/login", json={"email": target.email, "password": new_password}
    )).status_code == 200
