import uuid
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.tasks.schemas import (
    TaskAssignmentRequest,
    TaskCreate,
    TaskRead,
    TaskResolutionRequest,
    TaskReviewCommentCreate,
    TaskReviewCommentRead,
    TaskUpdate,
)
from app.domain.tasks.service import TaskService
from app.infrastructure.database.session import get_db
from app.security.authorization import require_internal_user, require_manager
from app.security.models import User
from app.security.router import get_current_user

tasks_router = APIRouter(prefix="/tasks", tags=["Tasks"])


def _require_internal_reviewer(user: User) -> None:
    require_internal_user(user)


def _require_manager(user: User) -> None:
    require_manager(user)


@tasks_router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(
    task_in: TaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    _require_internal_reviewer(current_user)
    if task_in.assigned_user_id or task_in.assigned_role_id or task_in.assigned_department_id:
        _require_manager(current_user)
    try:
        return await TaskService.create_task(
            db=db,
            task_in=task_in,
            created_by_id=current_user.id,
            created_by_type="USER",
            organization_id=current_user.organization_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@tasks_router.get("", response_model=List[TaskRead])
async def list_tasks(
    case_id: Optional[uuid.UUID] = Query(None),
    assigned_user_id: Optional[uuid.UUID] = Query(None),
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    _require_internal_reviewer(current_user)
    return await TaskService.get_tasks(
        db=db,
        organization_id=current_user.organization_id,
        case_id=case_id,
        assigned_user_id=assigned_user_id,
        status=status,
        priority=priority,
        skip=skip,
        limit=limit,
    )


@tasks_router.get("/my", response_model=List[TaskRead])
async def list_my_tasks(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    _require_internal_reviewer(current_user)
    return await TaskService.get_tasks_for_user(
        db=db,
        user_id=current_user.id,
        organization_id=current_user.organization_id,
    )


@tasks_router.get("/case/{case_id}", response_model=List[TaskRead])
async def list_tasks_for_case(
    case_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    _require_internal_reviewer(current_user)
    return await TaskService.get_tasks_by_case(
        db=db, case_id=case_id, organization_id=current_user.organization_id
    )


@tasks_router.get("/{task_id}", response_model=TaskRead)
async def get_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    _require_internal_reviewer(current_user)
    task = await TaskService.get_task_for_organization(
        db=db, task_id=task_id, organization_id=current_user.organization_id
    )
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


@tasks_router.patch("/{task_id}", response_model=TaskRead)
async def update_task(
    task_id: uuid.UUID,
    task_update: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    _require_internal_reviewer(current_user)
    if any((
        task_update.status is not None,
        task_update.assigned_user_id is not None,
        task_update.assigned_role_id is not None,
        task_update.assigned_department_id is not None,
        task_update.completion_metadata is not None,
    )):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use the task assignment or resolution endpoint for status and assignee changes.",
        )
    task = await TaskService.update_task(
        db=db,
        task_id=task_id,
        task_update=task_update,
        actor_id=current_user.id,
        actor_type="USER",
        organization_id=current_user.organization_id,
    )
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


@tasks_router.post("/{task_id}/assign", response_model=TaskRead)
async def assign_task(
    task_id: uuid.UUID,
    assignment: TaskAssignmentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    _require_manager(current_user)
    try:
        task = await TaskService.assign_task(
            db, task_id, assignment, organization_id=current_user.organization_id, actor=current_user
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


@tasks_router.post("/{task_id}/start", response_model=TaskRead)
async def start_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    _require_internal_reviewer(current_user)
    try:
        task = await TaskService.start_task(
            db, task_id, organization_id=current_user.organization_id, actor=current_user
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


@tasks_router.post("/{task_id}/comments", response_model=TaskReviewCommentRead, status_code=status.HTTP_201_CREATED)
async def add_task_review_comment(
    task_id: uuid.UUID,
    comment: TaskReviewCommentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    _require_internal_reviewer(current_user)
    try:
        record = await TaskService.add_review_comment(
            db, task_id, comment, organization_id=current_user.organization_id, actor=current_user
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return record


@tasks_router.get("/{task_id}/comments", response_model=list[TaskReviewCommentRead])
async def list_task_review_comments(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    _require_internal_reviewer(current_user)
    records = await TaskService.get_review_comments(db, task_id, current_user.organization_id)
    if records is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return records


@tasks_router.post("/{task_id}/resolve", response_model=TaskRead)
async def resolve_task(
    task_id: uuid.UUID,
    resolution: TaskResolutionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    _require_internal_reviewer(current_user)
    try:
        task = await TaskService.resolve_task(
            db, task_id, resolution, organization_id=current_user.organization_id, actor=current_user
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task
