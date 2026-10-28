import uuid
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.processes.schemas import (
    BusinessRuleCreate,
    BusinessRuleRead,
    CustomerProcessOptionRead,
    ProcessCreate,
    ProcessRead,
    ProcessVersionCreate,
    ProcessVersionDetailRead,
    ProcessVersionRead,
    RequirementCreate,
    RequirementRead,
    VerificationDefinitionCreate,
    VerificationDefinitionRead,
    WorkflowStageCreate,
    WorkflowStageRead,
    WorkflowTransitionCreate,
    WorkflowTransitionRead,
)
from app.domain.processes.service import ProcessService
from app.infrastructure.database.session import get_db
from app.security.authorization import (
    require_customer,
    require_internal_user,
    require_manager,
)
from app.security.models import User
from app.security.router import get_current_user

processes_router = APIRouter(prefix="/processes", tags=["Processes"])


@processes_router.post("", response_model=ProcessRead, status_code=status.HTTP_201_CREATED)
async def create_process(
    process_in: ProcessCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    require_manager(current_user)
    return await ProcessService.create_process(
        db,
        organization_id=current_user.organization_id,
        process_in=process_in,
        created_by=current_user.id,
    )


@processes_router.get("", response_model=List[ProcessRead])
async def list_processes(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    require_internal_user(current_user)
    return await ProcessService.get_processes(db, current_user.organization_id, skip=skip, limit=limit)


@processes_router.get("/customer-options", response_model=List[CustomerProcessOptionRead])
async def list_customer_process_options(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    require_customer(current_user)
    rows = await ProcessService.get_customer_options(db, current_user.organization_id, skip, limit)
    return [
        CustomerProcessOptionRead(
            process_id=process.id,
            process_version_id=version.id,
            name=process.name,
            description=process.description,
        )
        for process, version in rows
    ]


@processes_router.get("/{process_id}", response_model=ProcessRead)
async def get_process(
    process_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    require_internal_user(current_user)
    process = await ProcessService.get_process_by_id(db, process_id)
    if not process or process.organization_id != current_user.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Process not found")
    return process


@processes_router.get("/{process_id}/versions", response_model=List[ProcessVersionRead])
async def list_process_versions(
    process_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    require_internal_user(current_user)
    process = await ProcessService.get_process_by_id(db, process_id)
    if not process or process.organization_id != current_user.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Process not found")
    return await ProcessService.get_versions_by_process_id(db, process_id)


@processes_router.post("/{process_id}/versions", response_model=ProcessVersionRead, status_code=status.HTTP_201_CREATED)
async def create_process_version(
    process_id: uuid.UUID,
    version_in: ProcessVersionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    require_manager(current_user)
    process = await ProcessService.get_process_by_id(db, process_id)
    if not process or process.organization_id != current_user.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Process not found")
    return await ProcessService.create_new_version(db, process_id, version_in, created_by=current_user.id)


@processes_router.get("/versions/{version_id}", response_model=ProcessVersionDetailRead)
async def get_process_version_detail(
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    require_internal_user(current_user)
    version = await ProcessService.get_version_detail(db, version_id)
    process = await ProcessService.get_process_by_id(db, version.process_id) if version else None
    if not version or not process or process.organization_id != current_user.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Process version not found")
    return version


async def _require_organization_version(
    db: AsyncSession, version_id: uuid.UUID, current_user: User
) -> None:
    version = await ProcessService.get_version_by_id(db, version_id)
    process = await ProcessService.get_process_by_id(db, version.process_id) if version else None
    if not version or not process or process.organization_id != current_user.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Process version not found")


@processes_router.post("/versions/{version_id}/stages", response_model=WorkflowStageRead, status_code=status.HTTP_201_CREATED)
async def add_stage(
    version_id: uuid.UUID,
    stage_in: WorkflowStageCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    require_manager(current_user)
    await _require_organization_version(db, version_id, current_user)
    try:
        return await ProcessService.add_stage_to_version(db, version_id, stage_in)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@processes_router.post("/versions/{version_id}/transitions", response_model=WorkflowTransitionRead, status_code=status.HTTP_201_CREATED)
async def add_transition(
    version_id: uuid.UUID,
    transition_in: WorkflowTransitionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    require_manager(current_user)
    await _require_organization_version(db, version_id, current_user)
    try:
        return await ProcessService.add_transition_to_version(db, version_id, transition_in)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@processes_router.post("/versions/{version_id}/requirements", response_model=RequirementRead, status_code=status.HTTP_201_CREATED)
async def add_requirement(
    version_id: uuid.UUID,
    req_in: RequirementCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    require_manager(current_user)
    await _require_organization_version(db, version_id, current_user)
    try:
        return await ProcessService.add_requirement_to_version(db, version_id, req_in)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@processes_router.post("/versions/{version_id}/verifications", response_model=VerificationDefinitionRead, status_code=status.HTTP_201_CREATED)
async def add_verification(
    version_id: uuid.UUID,
    verif_in: VerificationDefinitionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    require_manager(current_user)
    await _require_organization_version(db, version_id, current_user)
    try:
        return await ProcessService.add_verification_to_version(db, version_id, verif_in)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@processes_router.post("/versions/{version_id}/rules", response_model=BusinessRuleRead, status_code=status.HTTP_201_CREATED)
async def add_business_rule(
    version_id: uuid.UUID,
    rule_in: BusinessRuleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    require_manager(current_user)
    await _require_organization_version(db, version_id, current_user)
    try:
        return await ProcessService.add_rule_to_version(db, version_id, rule_in)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@processes_router.post("/versions/{version_id}/publish", response_model=ProcessVersionRead)
async def publish_version(
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    require_manager(current_user)
    await _require_organization_version(db, version_id, current_user)
    try:
        return await ProcessService.publish_version(db, version_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@processes_router.post("/versions/{version_id}/archive", response_model=ProcessVersionRead)
async def archive_version(
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    require_manager(current_user)
    await _require_organization_version(db, version_id, current_user)
    try:
        return await ProcessService.archive_version(db, version_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
