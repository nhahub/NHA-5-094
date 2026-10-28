import uuid
from typing import Any, List

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.schemas import EventRecordCreate, EventRecordRead
from app.events.service import EventService
from app.infrastructure.database.session import get_db
from app.security.authorization import (
    require_accessible_case,
    require_internal_user,
    require_manager,
)
from app.security.models import User
from app.security.router import get_current_user

events_router = APIRouter(prefix="/events", tags=["Events"])


@events_router.post("", response_model=EventRecordRead, status_code=status.HTTP_201_CREATED)
async def create_event(
    event_in: EventRecordCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    require_manager(current_user)
    if event_in.case_id is not None:
        await require_accessible_case(db, event_in.case_id, current_user)
    return await EventService.emit_event(
        db=db,
        organization_id=current_user.organization_id,
        event_type=event_in.event_type,
        actor_type="USER",
        actor_id=current_user.id,
        case_id=event_in.case_id,
        payload=event_in.payload,
    )


@events_router.get("/case/{case_id}", response_model=List[EventRecordRead])
async def list_events_for_case(
    case_id: uuid.UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    require_internal_user(current_user)
    await require_accessible_case(db, case_id, current_user)
    return await EventService.get_events_for_case(db, case_id=case_id, skip=skip, limit=limit)
