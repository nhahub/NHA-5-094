import uuid
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.cases.models import Case
from app.domain.processes.models import Process, ProcessVersion
from app.domain.rules.models import BusinessRule
from app.domain.verifications.models import VerificationExecution
from app.domain.verifications.schemas import (
    VerificationDefinitionCreate,
    VerificationDefinitionRead,
    VerificationExecutionRead,
    VerificationRunRequest,
)
from app.domain.verifications.service import VerificationService
from app.infrastructure.database.session import get_db
from app.security.authorization import (
    require_accessible_case,
    require_internal_user,
    require_manager,
)
from app.security.models import User
from app.security.router import get_current_user

verifications_router = APIRouter(prefix="/verifications", tags=["Verifications"])
verification_router = verifications_router


async def _require_owned_version(
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


@verifications_router.post("/definitions", response_model=VerificationDefinitionRead, status_code=status.HTTP_201_CREATED)
async def create_verification_definition(
    def_in: VerificationDefinitionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    require_manager(current_user)
    await _require_owned_version(db, def_in.process_version_id, current_user)
    for rule_link in def_in.rules:
        rule_id = getattr(rule_link, "rule_id", None)
        if rule_id is not None:
            rule = await db.scalar(
                select(BusinessRule.id).where(
                    BusinessRule.id == rule_id,
                    BusinessRule.process_version_id == def_in.process_version_id,
                )
            )
            if rule is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found in this process version")
    return await VerificationService.create_definition(db, def_in)


@verifications_router.get("/definitions/version/{version_id}", response_model=List[VerificationDefinitionRead])
async def list_definitions_for_version(
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    require_internal_user(current_user)
    await _require_owned_version(db, version_id, current_user)
    return await VerificationService.get_definitions_by_version(db, version_id)


@verifications_router.post("/execute", response_model=VerificationExecutionRead)
async def execute_verification(
    request: VerificationRunRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    require_internal_user(current_user)
    await require_accessible_case(db, request.case_id, current_user)
    request.actor_id = current_user.id
    request.actor_type = "USER"
    try:
        execution = await VerificationService.run_verification(db, request)
        if not execution:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Verification execution failed to initialize.")
        return execution
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@verifications_router.get("/case/{case_id}", response_model=List[VerificationExecutionRead])
async def list_executions_for_case(
    case_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    require_internal_user(current_user)
    await require_accessible_case(db, case_id, current_user)
    return await VerificationService.get_executions_by_case(db, case_id)


@verifications_router.get("/{execution_id}", response_model=VerificationExecutionRead)
async def get_execution_detail(
    execution_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    require_internal_user(current_user)
    scoped_case_id = await db.scalar(
        select(Case.id)
        .join(VerificationExecution, VerificationExecution.case_id == Case.id)
        .where(
            VerificationExecution.id == execution_id,
            Case.organization_id == current_user.organization_id,
        )
    )
    if scoped_case_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Verification execution not found.")
    execution = await VerificationService.get_execution_by_id(db, execution_id)
    if not execution:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Verification execution not found.")
    return execution
