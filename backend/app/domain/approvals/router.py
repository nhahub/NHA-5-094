import uuid
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.approvals.schemas import (
    ApprovalCreate,
    ApprovalDecisionRequest,
    ApprovalRead,
)
from app.domain.approvals.service import ApprovalService
from app.infrastructure.database.session import get_db
from app.security.authorization import (
    require_accessible_case,
    require_internal_user,
    require_manager,
)
from app.security.models import User
from app.security.router import get_current_user

approvals_router = APIRouter(prefix="/approvals", tags=["Approvals"])


def _role_value(user: User) -> str:
    return user.role.value if hasattr(user.role, "value") else str(user.role).upper()


@approvals_router.get("/pending", response_model=List[ApprovalRead])
async def list_pending_approvals(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    if _role_value(current_user) not in {"MANAGER", "ADMIN"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Manager approval role required")
    return await ApprovalService.get_pending_approvals(db, current_user.organization_id)


@approvals_router.post("", response_model=ApprovalRead, status_code=status.HTTP_201_CREATED)
async def request_approval(
    approval_in: ApprovalCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    require_internal_user(current_user)
    try:
        return await ApprovalService.request_approval(
            db,
            approval_in,
            organization_id=current_user.organization_id,
            actor_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@approvals_router.post("/{approval_id}/decide", response_model=ApprovalRead)
async def decide_approval(
    approval_id: uuid.UUID,
    decision_in: ApprovalDecisionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    try:
        require_manager(current_user)
        approval = await ApprovalService.decide_approval(
            db,
            approval_id=approval_id,
            decided_by_user_id=current_user.id,
            decision_in=decision_in,
            organization_id=current_user.organization_id,
            actor_role=_role_value(current_user),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if not approval:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval request not found")
    return approval


@approvals_router.get("/case/{case_id}", response_model=List[ApprovalRead])
async def list_approvals_for_case(
    case_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    require_internal_user(current_user)
    await require_accessible_case(db, case_id, current_user)
    return await ApprovalService.get_approvals_by_case(db, case_id)
