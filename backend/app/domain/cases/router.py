import uuid
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.cases.review import CaseReviewService
from app.domain.cases.review_schemas import CaseReviewBundle
from app.domain.cases.schemas import (
    CaseCloseRequest,
    CaseCreate,
    CaseParticipantCreate,
    CaseParticipantRead,
    CaseRead,
    CaseStateRead,
    CaseUpdate,
    CustomerCaseRead,
)
from app.domain.cases.service import CaseService
from app.events.schemas import EventRecordRead
from app.events.service import EventService
from app.infrastructure.database.session import get_db
from app.security.authorization import (
    require_customer,
    require_internal_user,
    require_manager,
)
from app.security.models import User
from app.security.router import get_current_user

cases_router = APIRouter(prefix="/cases", tags=["Cases"])


@cases_router.get("/{case_id}/review", response_model=CaseReviewBundle)
async def get_case_review_bundle(
    case_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    require_internal_user(current_user)
    bundle = await CaseReviewService.get_bundle(db, case_id, current_user.organization_id)
    if bundle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    return bundle


@cases_router.post("", response_model=CaseRead, status_code=status.HTTP_201_CREATED)
async def create_case(
    case_in: CaseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    require_internal_user(current_user)
    try:
        return await CaseService.create_case(
            db,
            organization_id=current_user.organization_id,
            created_by_user_id=current_user.id,
            case_in=case_in,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@cases_router.post("/mine", response_model=CustomerCaseRead, status_code=status.HTTP_201_CREATED)
async def create_customer_case(
    case_in: CaseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    require_customer(current_user)
    try:
        case = await CaseService.create_case(
            db,
            organization_id=current_user.organization_id,
            created_by_user_id=current_user.id,
            case_in=case_in,
            customer_user_id=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return await CaseService.get_customer_case(
        db,
        case_id=case.id,
        organization_id=current_user.organization_id,
        customer_user_id=current_user.id,
    )


@cases_router.get("/mine", response_model=List[CustomerCaseRead])
async def list_customer_cases(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    require_customer(current_user)
    return await CaseService.get_customer_cases(
        db,
        organization_id=current_user.organization_id,
        customer_user_id=current_user.id,
        skip=skip,
        limit=limit,
    )


@cases_router.get("/mine/{case_id}", response_model=CustomerCaseRead)
async def get_customer_case(
    case_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    require_customer(current_user)
    case = await CaseService.get_customer_case(
        db,
        case_id=case_id,
        organization_id=current_user.organization_id,
        customer_user_id=current_user.id,
    )
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    return case


@cases_router.get("", response_model=List[CaseRead])
async def list_cases(
    status_filter: Optional[str] = Query(None, alias="status"),
    current_stage_id: Optional[uuid.UUID] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    require_internal_user(current_user)
    return await CaseService.get_cases(
        db,
        organization_id=current_user.organization_id,
        status=status_filter,
        current_stage_id=current_stage_id,
        skip=skip,
        limit=limit,
    )


@cases_router.get("/{case_id}", response_model=CaseRead)
async def get_case(
    case_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    require_internal_user(current_user)
    case = await CaseService.get_case_by_id(db, case_id)
    if not case or case.organization_id != current_user.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    return case


@cases_router.get("/{case_id}/state", response_model=CaseStateRead)
async def get_case_state(
    case_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    require_internal_user(current_user)
    state = await CaseService.get_case_state(db, case_id)
    if not state or state.case.organization_id != current_user.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    return state


@cases_router.get("/{case_id}/events", response_model=List[EventRecordRead])
async def list_case_events(
    case_id: uuid.UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    require_internal_user(current_user)
    case = await CaseService.get_case_by_id(db, case_id)
    if not case or case.organization_id != current_user.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    return await EventService.get_events_for_case(db, case_id, skip=skip, limit=limit)


@cases_router.patch("/{case_id}", response_model=CaseRead)
async def update_case(
    case_id: uuid.UUID,
    case_update: CaseUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    require_manager(current_user)
    case = await CaseService.get_case_by_id(db, case_id)
    if not case or case.organization_id != current_user.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    try:
        updated = await CaseService.update_case(db, case_id, case_update)
        return updated
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@cases_router.post("/{case_id}/close", response_model=CaseRead)
async def close_case(
    case_id: uuid.UUID,
    close_req: CaseCloseRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    require_manager(current_user)
    case = await CaseService.get_case_by_id(db, case_id)
    if not case or case.organization_id != current_user.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    try:
        return await CaseService.close_case(db, case_id, close_req, actor_id=current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@cases_router.post("/{case_id}/participants", response_model=CaseParticipantRead, status_code=status.HTTP_201_CREATED)
async def add_participant(
    case_id: uuid.UUID,
    participant_in: CaseParticipantCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    require_manager(current_user)
    case = await CaseService.get_case_by_id(db, case_id)
    if not case or case.organization_id != current_user.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    if participant_in.user_id is not None:
        participant = await db.get(User, participant_in.user_id)
        if participant is None or participant.organization_id != current_user.organization_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return await CaseService.add_participant(db, case_id, participant_in)
