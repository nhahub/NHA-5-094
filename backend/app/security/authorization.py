"""Shared role and case access checks for authenticated API routes."""
from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.cases.models import Case, CaseParticipant, ParticipantType
from app.security.models import RoleEnum, User


def role_name(user: User) -> str:
    role = user.role
    return role.value if hasattr(role, "value") else str(role).upper()


def require_internal_user(user: User) -> None:
    if role_name(user) == RoleEnum.CUSTOMER.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Internal user access is required.",
        )


def require_manager(user: User) -> None:
    if role_name(user) not in {RoleEnum.MANAGER.value, RoleEnum.ADMIN.value}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Manager access is required.",
        )


def require_customer(user: User) -> None:
    if role_name(user) != RoleEnum.CUSTOMER.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Customer access is required.",
        )


async def get_accessible_case(
    db: AsyncSession, case_id: uuid.UUID, user: User
) -> Case | None:
    """Return an organization case only when a customer is its linked participant."""
    stmt = select(Case).where(
        Case.id == case_id,
        Case.organization_id == user.organization_id,
    )
    if role_name(user) == RoleEnum.CUSTOMER.value:
        stmt = stmt.join(CaseParticipant).where(
            CaseParticipant.case_id == Case.id,
            CaseParticipant.user_id == user.id,
            CaseParticipant.participant_type == ParticipantType.CUSTOMER.value,
        )
    return (await db.execute(stmt)).scalars().first()


async def require_accessible_case(
    db: AsyncSession, case_id: uuid.UUID, user: User
) -> Case:
    case = await get_accessible_case(db, case_id, user)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    return case
