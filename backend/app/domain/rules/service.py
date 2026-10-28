import uuid
from typing import Any, Dict, List, Optional, Union
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.rules.engine import CalculationEngine, RuleEngine
from app.domain.rules.models import BusinessRule, CalculationDefinition, RuleSeverity
from app.domain.rules.schemas import (
    BusinessRuleCreate,
    CalculationDefinitionCreate,
    CalculationResult,
    RuleEvaluationResult,
)


class RuleService:
    """Service evaluating declarative business rules and mathematical formulas deterministically."""

    @staticmethod
    async def create_rule(db: AsyncSession, rule_in: BusinessRuleCreate) -> BusinessRule:
        rule = BusinessRule(
            process_version_id=rule_in.process_version_id,
            name=rule_in.name,
            code=rule_in.code,
            description=rule_in.description,
            rule_type=rule_in.rule_type,
            expression=rule_in.expression,
            severity=rule_in.severity.value if hasattr(rule_in.severity, "value") else str(rule_in.severity),
        )
        db.add(rule)
        await db.commit()
        await db.refresh(rule)
        return rule

    @staticmethod
    async def get_rules_by_version(
        db: AsyncSession, process_version_id: uuid.UUID
    ) -> List[BusinessRule]:
        stmt = select(BusinessRule).where(
            BusinessRule.process_version_id == process_version_id,
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def create_calculation(
        db: AsyncSession, calc_in: CalculationDefinitionCreate
    ) -> CalculationDefinition:
        calc = CalculationDefinition(
            process_version_id=calc_in.process_version_id,
            name=calc_in.name,
            code=calc_in.code,
            description=calc_in.description,
            calculation_type=calc_in.calculation_type,
            configuration=calc_in.configuration,
        )
        db.add(calc)
        await db.commit()
        await db.refresh(calc)
        return calc

    @staticmethod
    async def get_calculations_by_version(
        db: AsyncSession, process_version_id: uuid.UUID
    ) -> List[CalculationDefinition]:
        stmt = select(CalculationDefinition).where(
            CalculationDefinition.process_version_id == process_version_id
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @classmethod
    async def evaluate_rule(
        cls,
        db: AsyncSession,
        rule_id: Optional[uuid.UUID] = None,
        expression: Optional[Dict[str, Any]] = None,
        context_data: Optional[Dict[str, Any]] = None,
    ) -> RuleEvaluationResult:
        context = context_data or {}
        severity = RuleSeverity.ERROR

        if rule_id is not None:
            stmt = select(BusinessRule).where(BusinessRule.id == rule_id)
            result = await db.execute(stmt)
            rule = result.scalars().first()
            if not rule:
                return RuleEvaluationResult(
                    rule_id=rule_id,
                    passed=False,
                    message=f"BusinessRule with ID '{rule_id}' not found.",
                    severity=RuleSeverity.ERROR,
                )
            expr = rule.expression
            severity = RuleSeverity(rule.severity) if hasattr(RuleSeverity, rule.severity) else RuleSeverity.ERROR
            name = rule.name
        else:
            expr = expression or {}
            name = "Ad-hoc Rule"

        passed, trace = RuleEngine.evaluate_expression(expr, context)
        msg = f"Rule '{name}' passed." if passed else f"Rule '{name}' failed assertion."

        return RuleEvaluationResult(
            rule_id=rule_id,
            passed=passed,
            message=msg,
            severity=severity,
            details=trace,
        )

    @classmethod
    async def evaluate_calculation(
        cls,
        db: AsyncSession,
        calculation_id: Optional[uuid.UUID] = None,
        formula: Optional[Union[Dict[str, Any], str]] = None,
        context_data: Optional[Dict[str, Any]] = None,
    ) -> CalculationResult:
        context = context_data or {}

        if calculation_id is not None:
            stmt = select(CalculationDefinition).where(CalculationDefinition.id == calculation_id)
            result = await db.execute(stmt)
            calc = result.scalars().first()
            if not calc:
                return CalculationResult(
                    calculation_id=calculation_id,
                    status="FAILED",
                    error=f"CalculationDefinition with ID '{calculation_id}' not found.",
                )
            target_formula = calc.configuration.get("formula", calc.configuration)
        else:
            target_formula = formula

        if target_formula is None:
            return CalculationResult(
                calculation_id=calculation_id,
                status="FAILED",
                error="No formula provided for calculation.",
            )

        calc_value = CalculationEngine.evaluate(target_formula, context)
        # Convert Decimal to float/str for serialization
        serializable_val = float(calc_value) if calc_value is not None else None

        return CalculationResult(
            calculation_id=calculation_id,
            value=serializable_val,
            status="SUCCESS" if calc_value is not None else "FAILED",
            error=None if calc_value is not None else "Evaluation produced null result (check inputs).",
        )
