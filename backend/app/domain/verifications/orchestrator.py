"""Deterministic verification orchestration, independent of persistence.

The service prepares case facts and definitions. This module executes ordered
calculations and rules, preserving the mature recursive rule/calculation AST
supported by :mod:`app.domain.rules.engine`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Sequence, Tuple

from app.domain.rules.engine import CalculationEngine, RuleEngine
from app.domain.rules.models import BusinessRule, CalculationDefinition, RuleSeverity
from app.domain.verifications.models import VerificationStatus


@dataclass(frozen=True)
class CalculationTrace:
    calculation_id: str
    calculation_code: str
    input_context: Dict[str, Any]
    value: Any
    status: str
    error: str | None = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "calculation_id": self.calculation_id,
            "calculation_code": self.calculation_code,
            "input_context": self.input_context,
            "value": self.value,
            "status": self.status,
            "error": self.error,
        }


@dataclass(frozen=True)
class RuleTrace:
    rule_id: str
    rule_code: str
    passed: bool
    required: bool
    details: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "rule_code": self.rule_code,
            "passed": self.passed,
            "required": self.required,
            **self.details,
        }


@dataclass(frozen=True)
class VerificationEvaluation:
    context: Dict[str, Any]
    calculations: List[CalculationTrace]
    rules: List[RuleTrace]
    status: VerificationStatus
    summary: str
    passed_rules: int
    total_rules: int


class VerificationOrchestrator:
    """Runs deterministic calculations and verification rules in order."""

    @classmethod
    def evaluate(
        cls,
        calculations: Sequence[CalculationDefinition],
        rules: Sequence[Tuple[BusinessRule, bool]],
        context: Dict[str, Any],
    ) -> VerificationEvaluation:
        working_context = dict(context)
        calculation_traces: List[CalculationTrace] = []
        calculation_failed = False

        # Configured execution_order is optional for legacy records. Code gives
        # a stable fallback order so runs are reproducible across DB engines.
        ordered_calculations = sorted(
            calculations,
            key=lambda calc: (
                int((calc.configuration or {}).get("execution_order", 0)),
                calc.code,
            ),
        )
        for calculation in ordered_calculations:
            formula_spec = (calculation.configuration or {}).get("formula", calculation.configuration or {})
            before = dict(working_context)
            try:
                value = CalculationEngine.evaluate(formula_spec, working_context)
                if value is None:
                    raise ValueError("Calculation returned no value (check for missing or invalid operands).")
                # Keep Decimal internally for exact downstream comparisons;
                # AuditService sanitizes values when writing JSON to the DB.
                working_context[calculation.code] = value
                working_context[f"calc_{calculation.code}"] = value
                calculation_traces.append(CalculationTrace(
                    calculation_id=str(calculation.id),
                    calculation_code=calculation.code,
                    input_context=before,
                    value=value,
                    status="SUCCESS",
                ))
            except Exception as exc:  # calculation errors become explicit trace data
                calculation_failed = True
                calculation_traces.append(CalculationTrace(
                    calculation_id=str(calculation.id),
                    calculation_code=calculation.code,
                    input_context=before,
                    value=None,
                    status="FAILED",
                    error=str(exc),
                ))

        rule_traces: List[RuleTrace] = []
        for rule, required in rules:
            passed, details = RuleEngine.evaluate_expression(rule.expression or {}, working_context)
            rule_traces.append(RuleTrace(
                rule_id=str(rule.id),
                rule_code=rule.code,
                passed=passed,
                required=required,
                details=details,
            ))

        passed_count = sum(1 for trace in rule_traces if trace.passed)
        total = len(rule_traces)
        skipped = any(trace.details.get("skipped") for trace in rule_traces)
        severities = {str(rule.id): rule.severity for rule, _ in rules}
        critical_failure = any(
            not trace.passed and (
                trace.required or severities.get(trace.rule_id) in (
                    RuleSeverity.CRITICAL.value, RuleSeverity.ERROR.value,
                )
            )
            for trace in rule_traces
        )
        warning_failure = any(not trace.passed for trace in rule_traces)

        if calculation_failed or skipped:
            status = VerificationStatus.INCONCLUSIVE
            summary = "Verification is inconclusive because inputs or calculations are incomplete."
        elif total == 0:
            status = VerificationStatus.NOT_APPLICABLE
            summary = "No rules defined for this verification definition."
        elif passed_count == total:
            status = VerificationStatus.PASS
            summary = f"All {total} verification rules passed successfully."
        elif critical_failure:
            status = VerificationStatus.FAIL
            summary = f"Verification failed: {total - passed_count} of {total} rules failed."
        elif warning_failure:
            status = VerificationStatus.REVIEW
            summary = f"Verification requires review: {passed_count}/{total} rules passed."
        else:
            status = VerificationStatus.INCONCLUSIVE
            summary = "Verification evaluation produced inconclusive results."

        return VerificationEvaluation(
            context=working_context,
            calculations=calculation_traces,
            rules=rule_traces,
            status=status,
            summary=summary,
            passed_rules=passed_count,
            total_rules=total,
        )
