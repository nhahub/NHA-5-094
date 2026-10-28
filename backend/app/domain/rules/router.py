import uuid
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.processes.models import Process, ProcessVersion
from app.domain.rules.models import BusinessRule, CalculationDefinition
from app.domain.rules.schemas import (
    BusinessRuleCreate,
    BusinessRuleRead,
    CalculationDefinitionCreate,
    CalculationDefinitionRead,
    CalculationRequest,
    CalculationResult,
    RuleEvaluationRequest,
    RuleEvaluationResult,
)
from app.domain.rules.service import RuleService
from app.infrastructure.database.session import get_db
from app.security.authorization import require_internal_user, require_manager
from app.security.models import User
from app.security.router import get_current_user

rules_router = APIRouter(prefix="/rules", tags=["Rules & Calculations"])


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


async def _require_owned_definition(
    db: AsyncSession, model: type[BusinessRule] | type[CalculationDefinition],
    definition_id: uuid.UUID, current_user: User,
) -> None:
    stmt = (
        select(model.id)
        .join(ProcessVersion, ProcessVersion.id == model.process_version_id)
        .join(Process, Process.id == ProcessVersion.process_id)
        .where(model.id == definition_id, Process.organization_id == current_user.organization_id)
    )
    if await db.scalar(stmt) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Definition not found")


@rules_router.post("", response_model=BusinessRuleRead, status_code=status.HTTP_201_CREATED)
async def create_rule(
    rule_in: BusinessRuleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    require_manager(current_user)
    await _require_owned_version(db, rule_in.process_version_id, current_user)
    return await RuleService.create_rule(db, rule_in)


@rules_router.get("/version/{version_id}", response_model=List[BusinessRuleRead])
async def list_rules_for_version(
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    require_internal_user(current_user)
    await _require_owned_version(db, version_id, current_user)
    return await RuleService.get_rules_by_version(db, version_id)


@rules_router.post("/calculations", response_model=CalculationDefinitionRead, status_code=status.HTTP_201_CREATED)
async def create_calculation(
    calc_in: CalculationDefinitionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    require_manager(current_user)
    await _require_owned_version(db, calc_in.process_version_id, current_user)
    return await RuleService.create_calculation(db, calc_in)


@rules_router.get("/calculations/version/{version_id}", response_model=List[CalculationDefinitionRead])
async def list_calculations_for_version(
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    require_internal_user(current_user)
    await _require_owned_version(db, version_id, current_user)
    return await RuleService.get_calculations_by_version(db, version_id)


@rules_router.post("/evaluate", response_model=RuleEvaluationResult)
async def evaluate_rule(
    req: RuleEvaluationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    require_internal_user(current_user)
    if req.rule_id is not None:
        await _require_owned_definition(db, BusinessRule, req.rule_id, current_user)
    return await RuleService.evaluate_rule(
        db, rule_id=req.rule_id, expression=req.expression, context_data=req.context_data
    )


@rules_router.post("/calculate", response_model=CalculationResult)
async def calculate_formula(
    req: CalculationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    require_internal_user(current_user)
    if req.calculation_id is not None:
        await _require_owned_definition(db, CalculationDefinition, req.calculation_id, current_user)
    return await RuleService.evaluate_calculation(
        db, calculation_id=req.calculation_id, formula=req.formula, context_data=req.context_data
    )
