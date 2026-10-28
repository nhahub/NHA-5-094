import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.processes.models import Process, ProcessVersion
from app.domain.workflows.schemas import (
    TransitionRequest,
    TransitionResult,
    WorkflowStageCreate,
    WorkflowStageRead,
    WorkflowTransitionCreate,
    WorkflowTransitionRead,
)
from app.domain.workflows.service import WorkflowService
from app.infrastructure.database.session import get_db
from app.security.authorization import require_internal_user, require_manager
from app.security.models import User
from app.security.router import get_current_user

workflows_router = APIRouter(prefix="/workflows", tags=["Workflows"])


async def _require_organization_version(
    db: AsyncSession, version_id: uuid.UUID, current_user: User
) -> None:
    stmt = (
        select(ProcessVersion.id)
        .join(Process, Process.id == ProcessVersion.process_id)
        .where(
            ProcessVersion.id == version_id,
            Process.organization_id == current_user.organization_id,
        )
    )
    if await db.scalar(stmt) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Process version not found")


@workflows_router.post("/stages", response_model=WorkflowStageRead, status_code=status.HTTP_201_CREATED)
async def create_stage(
    stage_in: WorkflowStageCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> Any:
    require_manager(current_user)
    await _require_organization_version(db, stage_in.process_version_id, current_user)
    return await WorkflowService.create_stage(db, stage_in)


@workflows_router.get("/stages/version/{version_id}", response_model=list[WorkflowStageRead])
async def list_stages(
    version_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> Any:
    require_internal_user(current_user)
    await _require_organization_version(db, version_id, current_user)
    return await WorkflowService.get_stages_by_version(db, version_id)


@workflows_router.post("/transitions", response_model=WorkflowTransitionRead, status_code=status.HTTP_201_CREATED)
async def create_transition(
    transition_in: WorkflowTransitionCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> Any:
    require_manager(current_user)
    await _require_organization_version(db, transition_in.process_version_id, current_user)
    return await WorkflowService.create_transition(db, transition_in)


@workflows_router.get("/transitions/version/{version_id}", response_model=list[WorkflowTransitionRead])
async def list_transitions(
    version_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> Any:
    require_internal_user(current_user)
    await _require_organization_version(db, version_id, current_user)
    return await WorkflowService.get_transitions_by_version(db, version_id)


@workflows_router.post("/validate", response_model=TransitionResult)
async def validate_transition(
    request: TransitionRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> Any:
    require_internal_user(current_user)
    # Identity and authority come from authentication, never from the request body.
    request.actor_id = current_user.id
    request.actor_role = _authenticated_role(current_user)
    request.actor_type = "USER"
    return await WorkflowService.validate_transition(
        db, request, organization_id=current_user.organization_id
    )


@workflows_router.post("/transition", response_model=TransitionResult)
async def execute_transition(
    request: TransitionRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> Any:
    require_internal_user(current_user)
    # Identity and authority come from authentication, never from the request body.
    request.actor_id = current_user.id
    request.actor_role = _authenticated_role(current_user)
    request.actor_type = "USER"
    result = await WorkflowService.execute_transition(
        db, request, organization_id=current_user.organization_id
    )
    if not result.allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": result.reason,
                "violations": [v.model_dump(mode="json") for v in result.violations],
                "case_id": str(result.case_id),
            },
        )
    return result


def _authenticated_role(user: User) -> str:
    role = getattr(user, "role", None)
    return role.value if hasattr(role, "value") else str(role or "")
