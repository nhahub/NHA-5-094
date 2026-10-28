"""Load a declarative process definition through the domain services."""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.documents.intelligence import resolve_document_classes
from app.domain.processes.schemas import (
    BusinessRuleCreate,
    ProcessCreate,
    ProcessVersionCreate,
    RequirementCreate,
    WorkflowStageCreate,
    WorkflowTransitionCreate,
)
from app.domain.processes.service import ProcessService
from app.domain.rules.schemas import CalculationDefinitionCreate
from app.domain.rules.service import RuleService
from app.domain.verifications.schemas import (
    VerificationDefinitionCreate,
    VerificationRuleLink,
)
from app.domain.verifications.service import VerificationService


def validate_process_definition(definition: Any) -> dict[str, Any]:
    """Validate all process data and references before creating database records."""
    if not isinstance(definition, dict):
        raise TypeError("Process configuration must be a JSON object.")
    if definition.get("schema_version") != 1:
        raise ValueError("Unsupported process configuration schema_version.")

    process_data = definition.get("process")
    process = ProcessCreate.model_validate(process_data)
    configuration = definition.get("version_configuration", {})
    if not isinstance(configuration, dict):
        raise TypeError("version_configuration must be an object.")
    if "extraction_schemas" in configuration:
        schemas = configuration["extraction_schemas"]
        if not isinstance(schemas, dict):
            raise TypeError("extraction_schemas must be an object.")
        for schema in schemas.values():
            Draft202012Validator.check_schema(schema)
    resolve_document_classes(configuration)

    stages = definition.get("stages", [])
    stage_codes: set[str] = set()
    initial_count = 0
    for item in stages:
        stage = WorkflowStageCreate.model_validate(item)
        if stage.code in stage_codes:
            raise ValueError(f"Duplicate stage code: {stage.code}")
        stage_codes.add(stage.code)
        initial_count += int(stage.is_initial)
    if not stages:
        raise ValueError("Process configuration must define at least one stage.")
    if initial_count != 1:
        raise ValueError("Process configuration must define exactly one initial stage.")

    for item in definition.get("transitions", []):
        transition = dict(item)
        source = transition.pop("from", None)
        target = transition.pop("to", None)
        if source not in stage_codes or target not in stage_codes:
            raise ValueError("Transition references an unknown stage code.")
        condition_config = transition.get("condition_config") or {}
        if not isinstance(condition_config, dict):
            raise TypeError("Transition condition_config must be an object.")
        allowed_failed = condition_config.get("allow_failed_verifications", [])
        if not isinstance(allowed_failed, list) or any(
            not isinstance(code, str) or not code.strip() for code in allowed_failed
        ):
            raise ValueError("allow_failed_verifications must be a list of non-empty verification codes.")
        if allowed_failed:
            target_stage = next(stage for stage in stages if stage["code"] == target)
            if not (target_stage.get("config") or {}).get("review_stage"):
                raise ValueError("Failed-verification exceptions may target only a configured review_stage.")
        WorkflowTransitionCreate(
            from_stage_id=uuid.UUID(int=0), to_stage_id=uuid.UUID(int=0), **transition
        )

    for item in definition.get("requirements", []):
        requirement = dict(item)
        stage_code = requirement.pop("stage_code", None)
        if stage_code is not None and stage_code not in stage_codes:
            raise ValueError(f"Requirement references an unknown stage code: {stage_code}")
        RequirementCreate(
            stage_id=uuid.UUID(int=0) if stage_code else None, **requirement
        )

    rules = definition.get("rules", [])
    rule_codes: set[str] = set()
    for item in rules:
        rule = dict(item)
        code = rule.get("code")
        if code in rule_codes:
            raise ValueError(f"Duplicate rule code: {code}")
        rule_codes.add(code)
        BusinessRuleCreate(process_version_id=uuid.UUID(int=0), **rule)

    calculations = definition.get("calculations", [])
    calculation_codes: set[str] = set()
    for item in calculations:
        calculation = dict(item)
        code = calculation.get("code")
        if code in calculation_codes:
            raise ValueError(f"Duplicate calculation code: {code}")
        calculation_codes.add(code)
        CalculationDefinitionCreate(process_version_id=uuid.UUID(int=0), **calculation)

    verifications = definition.get("verifications", [])
    verification_codes: set[str] = set()
    for item in verifications:
        verification = dict(item)
        code = verification.get("code")
        if code in verification_codes:
            raise ValueError(f"Duplicate verification code: {code}")
        verification_codes.add(code)
        stage_code = verification.pop("stage_code", None)
        rule_links = verification.pop("rules", [])
        if stage_code is not None and stage_code not in stage_codes:
            raise ValueError(f"Verification references an unknown stage code: {stage_code}")
        for link in rule_links:
            rule_code = link.get("rule_code")
            if rule_code not in rule_codes:
                raise ValueError(f"Verification references an unknown rule code: {rule_code}")
            VerificationRuleLink(
                rule_id=uuid.UUID(int=0),
                execution_order=link.get("execution_order", 0),
                required=link.get("required", True),
            )
        VerificationDefinitionCreate(
            process_version_id=uuid.UUID(int=0),
            stage_id=uuid.UUID(int=0) if stage_code else None,
            rules=[],
            **verification,
        )

    for transition in definition.get("transitions", []):
        allowed_failed = (transition.get("condition_config") or {}).get(
            "allow_failed_verifications", []
        )
        unknown_codes = set(allowed_failed) - verification_codes
        if unknown_codes:
            raise ValueError(
                "Transition allows unknown failed-verification codes: "
                + ", ".join(sorted(unknown_codes))
            )

    return {"process": process, "configuration": configuration}


async def load_process_definition(
    db: AsyncSession, *, organization_id: uuid.UUID, path: str | Path,
    created_by: uuid.UUID | None = None, process_id: uuid.UUID | None = None,
) -> tuple[Any, Any]:
    """Create a process and publish a new version from a JSON configuration.

    This intentionally accepts only data. It does not load or execute Python
    handlers from the process definition.
    """
    definition = json.loads(Path(path).read_text(encoding="utf-8"))
    validated = validate_process_definition(definition)
    version_data = validated["configuration"]
    if process_id is None:
        process = await ProcessService.create_process(
            db, organization_id=organization_id,
            process_in=validated["process"], created_by=created_by,
        )
        version = (await ProcessService.get_versions_by_process_id(db, process.id))[0]
        version.configuration = version_data
        await db.commit()
    else:
        process = await ProcessService.get_process_by_id(db, process_id)
        if process is None or process.organization_id != organization_id:
            raise ValueError("Process was not found in the requested organization.")
        if process.code != validated["process"].code:
            raise ValueError("Process configuration code does not match the selected process.")
        version = await ProcessService.create_new_version(
            db, process.id, ProcessVersionCreate(configuration=version_data), created_by=created_by,
        )

    stage_by_code: dict[str, Any] = {}
    for stage_data in definition.get("stages", []):
        stage = await ProcessService.add_stage_to_version(
            db, version.id, WorkflowStageCreate(**stage_data),
        )
        stage_by_code[stage.code] = stage

    for transition_data in definition.get("transitions", []):
        transition = dict(transition_data)
        try:
            source = stage_by_code[transition["from"]]
            target = stage_by_code[transition["to"]]
        except KeyError as exc:
            raise ValueError(f"Transition references an unknown stage code: {exc.args[0]}") from exc
        await ProcessService.add_transition_to_version(
            db, version.id,
            WorkflowTransitionCreate(
                process_version_id=version.id,
                from_stage_id=source.id,
                to_stage_id=target.id,
                **{key: value for key, value in transition.items() if key not in {"from", "to"}},
            ),
        )

    for requirement_data in definition.get("requirements", []):
        requirement = dict(requirement_data)
        stage_code = requirement.pop("stage_code", None)
        if stage_code and stage_code not in stage_by_code:
            raise ValueError(f"Requirement references an unknown stage code: {stage_code}")
        await ProcessService.add_requirement_to_version(
            db, version.id,
            RequirementCreate(
                stage_id=stage_by_code[stage_code].id if stage_code else None,
                **requirement,
            ),
        )

    rule_by_code: dict[str, Any] = {}
    for rule_data in definition.get("rules", []):
        rule = await ProcessService.add_rule_to_version(
            db, version.id,
            BusinessRuleCreate(process_version_id=version.id, **rule_data),
        )
        rule_by_code[rule.code] = rule

    for calculation_data in definition.get("calculations", []):
        await RuleService.create_calculation(
            db,
            CalculationDefinitionCreate(
                process_version_id=version.id, **calculation_data
            ),
        )

    for verification_data in definition.get("verifications", []):
        verification = dict(verification_data)
        stage_code = verification.pop("stage_code", None)
        rule_links = verification.pop("rules", [])
        await VerificationService.create_definition(
            db,
            VerificationDefinitionCreate(
                process_version_id=version.id,
                stage_id=stage_by_code[stage_code].id if stage_code else None,
                rules=[
                    VerificationRuleLink(
                        rule_id=rule_by_code[link["rule_code"]].id,
                        execution_order=link.get("execution_order", 0),
                        required=link.get("required", True),
                    )
                    for link in rule_links
                ],
                **verification,
            ),
        )

    published = await ProcessService.publish_version(db, version.id)
    return process, published
