"""Policy-enforcing, auditable Tool Gateway.

Handlers are registered in trusted application code. A process version enables
and parameterizes those handlers through ``configuration.tool_gateway``; the
configuration never supplies executable code.
"""
from __future__ import annotations

import asyncio
import inspect
import logging
import math
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.models import AgentDefinition
from app.domain.approvals.schemas import ApprovalCreate
from app.domain.approvals.service import ApprovalService
from app.domain.cases.models import Case, CaseData
from app.domain.documents.models import Document, DocumentVersion, ExtractedField
from app.domain.organizations.models import Department
from app.domain.processes.models import Process, ProcessVersion, Requirement
from app.domain.tasks.models import Task
from app.domain.tasks.schemas import TaskCreate
from app.domain.tasks.service import TaskService
from app.domain.verifications.schemas import VerificationRunRequest
from app.domain.verifications.service import VerificationService
from app.domain.workflows.models import WorkflowStage
from app.security.models import Permission, Role, RolePermission, User, UserRole
from app.tools.erpnext import erpnext_integration_adapter
from app.tools.models import Integration, ToolExecution
from app.tools.models import ToolDefinition as ToolDefinitionRecord
from app.tools.schemas import ToolDefinition, ToolExecutionRequest, ToolExecutionResult

ToolHandler = Callable[["ToolContext", Dict[str, Any]], Any | Awaitable[Any]]


@dataclass(frozen=True)
class ToolContext:
    db: AsyncSession
    actor: User
    case: Case
    process_version: ProcessVersion
    tool_configuration: Dict[str, Any]
    agent: Optional[AgentDefinition] = None


@dataclass(frozen=True)
class _ToolSpec:
    name: str
    description: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    permission_code: str
    allowed_agents: tuple[str, ...]
    handler: ToolHandler

    def public_definition(self, allowed_agents: Optional[List[str]] = None) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            input_schema=self.input_schema,
            output_schema=self.output_schema,
            required_permission=self.permission_code,
            allowed_agents=allowed_agents if allowed_agents is not None else list(self.allowed_agents),
        )


class ToolPolicyError(Exception):
    def __init__(self, message: str, status_code: int = 403) -> None:
        super().__init__(message)
        self.status_code = status_code


class ToolValidationError(ValueError):
    pass


class ToolGatewayService:
    """Registry and invocation boundary for trusted built-ins and adapters."""

    _registry: Dict[str, _ToolSpec] = {}
    _integration_adapters: Dict[str, ToolHandler] = {}
    _failure_tool_code = "__gateway_rejected__"
    _execution_timeout_seconds = 30

    @classmethod
    def register_tool(
        cls,
        name: str,
        description: str,
        func: ToolHandler,
        input_schema: Optional[Dict[str, Any]] = None,
        output_schema: Optional[Dict[str, Any]] = None,
        required_role: Optional[str] = None,
        *,
        permission_code: Optional[str] = None,
        allowed_agents: Optional[List[str]] = None,
    ) -> None:
        """Register a trusted handler; process configuration controls availability."""
        normalized = name.strip()
        if not re.fullmatch(r"[a-z][a-z0-9_]{1,99}", normalized):
            raise ValueError("Tool names must use lowercase letters, digits, and underscores.")
        if normalized in cls._registry:
            raise ValueError(f"Tool '{normalized}' is already registered.")
        if not inspect.iscoroutinefunction(func):
            raise TypeError("Tool handlers must be async so the gateway can enforce execution timeouts.")
        cls._registry[normalized] = _ToolSpec(
            name=normalized,
            description=description,
            input_schema=input_schema or {"type": "object", "properties": {}, "additionalProperties": False},
            output_schema=output_schema or {"type": "object"},
            permission_code=permission_code or required_role or f"tool.{normalized}",
            allowed_agents=tuple(allowed_agents or ()),
            handler=func,
        )

    @classmethod
    def register_integration_adapter(cls, integration_type: str, handler: ToolHandler) -> None:
        """Attach trusted code to an organization integration type."""
        if not inspect.iscoroutinefunction(handler):
            raise TypeError("Integration adapters must be async so the gateway can enforce execution timeouts.")
        cls._integration_adapters[integration_type.strip().upper()] = handler

    @classmethod
    async def list_tools(
        cls, db: AsyncSession, actor: User, case_id: uuid.UUID
    ) -> List[ToolDefinition]:
        case, process_version = await cls._load_case_context(db, actor, case_id)
        definitions: List[ToolDefinition] = []
        for spec in cls._registry.values():
            try:
                configured = cls._tool_configuration(process_version, spec.name)
                enabled = (await db.execute(select(ToolDefinitionRecord.enabled).where(
                    ToolDefinitionRecord.code == spec.name,
                ))).scalar_one_or_none()
                if enabled is False:
                    continue
                if spec.handler is _call_organization_system and not await cls._integration_ready(
                    db, actor, configured
                ):
                    continue
                await cls._authorize(db, actor, case, spec, configured, None)
                definitions.append(spec.public_definition(configured.get("allowed_agents")))
            except ToolPolicyError:
                continue
        return definitions

    @classmethod
    async def execute_tool(
        cls,
        db: AsyncSession,
        request: ToolExecutionRequest,
        actor: User,
        agent_id: Optional[uuid.UUID] = None,
    ) -> ToolExecutionResult:
        started_at = datetime.now(timezone.utc)
        spec = cls._registry.get(request.tool_name)
        definition = await cls._ensure_tool_record(db, spec)
        execution = ToolExecution(
            organization_id=actor.organization_id,
            case_id=None,
            tool_id=definition.id,
            requested_by_type="AGENT" if agent_id else "USER",
            requested_by_id=agent_id or actor.id,
            input_data=jsonable_encoder({
                "requested_case_id": request.case_id,
                "arguments": request.arguments,
                "agent_id": agent_id,
            }),
            output_data={},
            status="RUNNING",
            error=None,
            started_at=started_at,
        )
        db.add(execution)
        await db.commit()
        await db.refresh(execution)
        case: Optional[Case] = None
        result: ToolExecutionResult

        try:
            if spec is None:
                raise ToolPolicyError(f"Tool '{request.tool_name}' is not registered.", 404)
            if not definition.enabled:
                raise ToolPolicyError(f"Tool '{spec.name}' is disabled in the registry.", 403)
            case, process_version = await cls._load_case_context(db, actor, request.case_id)
            execution.case_id = case.id
            configured = dict(cls._tool_configuration(process_version, spec.name))
            configured["_tool_name"] = spec.name
            agent = await cls._load_agent(db, actor, agent_id) if agent_id else None
            await cls._authorize(db, actor, case, spec, configured, agent)
            if spec.handler is _call_organization_system and not await cls._integration_ready(
                db, actor, configured
            ):
                raise ToolPolicyError("No active integration and trusted adapter are configured for this tool.", 503)
            cls._validate_schema(request.arguments, spec.input_schema)
            context = ToolContext(db, actor, case, process_version, configured, agent)
            output = await asyncio.wait_for(
                spec.handler(context, request.arguments), timeout=cls._execution_timeout_seconds
            )
            if not isinstance(output, dict):
                raise TypeError("Tool handlers must return an object matching the output schema.")
            cls._validate_schema(output, spec.output_schema)
            result = ToolExecutionResult(
                tool_name=spec.name,
                case_id=request.case_id,
                success=True,
                output=jsonable_encoder(output),
                status="SUCCESS",
            )
        except ToolPolicyError as exc:
            result = ToolExecutionResult(
                tool_name=request.tool_name, case_id=request.case_id, success=False,
                error=str(exc), status="REJECTED", http_status_code=exc.status_code,
            )
        except ToolValidationError as exc:
            result = ToolExecutionResult(
                tool_name=request.tool_name, case_id=request.case_id, success=False,
                error=str(exc), status="REJECTED", http_status_code=422,
            )
        except asyncio.TimeoutError:
            result = ToolExecutionResult(
                tool_name=request.tool_name, case_id=request.case_id, success=False,
                error="Tool execution timed out.", status="FAILED", http_status_code=504,
            )
        except Exception as exc:  # errors are returned and recorded; never bypass the gateway
            logger.exception("Tool execution unhandled error: %s", exc)
            result = ToolExecutionResult(
                tool_name=request.tool_name, case_id=request.case_id, success=False,
                error=f"Tool execution failed ({type(exc).__name__}).", status="FAILED", http_status_code=500,
            )

        execution.output_data = jsonable_encoder(result.output or {})
        execution.status = result.status
        execution.error = result.error
        execution.completed_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(execution)
        result.execution_id = execution.id
        return result

    @classmethod
    async def _load_case_context(
        cls, db: AsyncSession, actor: User, case_id: uuid.UUID
    ) -> tuple[Case, ProcessVersion]:
        stmt = (
            select(Case, ProcessVersion, Process)
            .join(ProcessVersion, Case.process_version_id == ProcessVersion.id)
            .join(Process, ProcessVersion.process_id == Process.id)
            .where(Case.id == case_id)
        )
        row = (await db.execute(stmt)).first()
        if row is None:
            raise ToolPolicyError("Case not found.", 404)
        case, process_version, process = row
        if case.organization_id != actor.organization_id:
            raise ToolPolicyError("Case is outside the actor's organization scope.", 403)
        if process.organization_id != actor.organization_id:
            raise ToolPolicyError("Case process is outside the actor's organization scope.", 403)
        return case, process_version

    @classmethod
    async def _load_agent(
        cls, db: AsyncSession, actor: User, agent_id: uuid.UUID
    ) -> AgentDefinition:
        stmt = select(AgentDefinition).where(
            AgentDefinition.id == agent_id,
            AgentDefinition.enabled.is_(True),
            or_(
                AgentDefinition.organization_id == actor.organization_id,
                AgentDefinition.organization_id.is_(None),
            ),
        )
        agent = (await db.execute(stmt)).scalars().first()
        if agent is None:
            raise ToolPolicyError("Agent is missing, disabled, or outside the organization scope.", 403)
        return agent

    @classmethod
    def _tool_configuration(cls, process_version: ProcessVersion, tool_name: str) -> Dict[str, Any]:
        gateway = (process_version.configuration or {}).get("tool_gateway", {})
        allowed = gateway.get("allowed_tools", {}) if isinstance(gateway, dict) else {}
        if isinstance(allowed, list):
            enabled = tool_name in allowed
            config: Dict[str, Any] = {}
        elif isinstance(allowed, dict):
            if tool_name not in allowed:
                enabled = False
                config = {}
            else:
                config = allowed[tool_name] or {}
                enabled = bool(config.get("enabled", False)) if isinstance(config, dict) else bool(config)
        else:
            raise ToolPolicyError("Process tool configuration is invalid.", 403)
        if not enabled:
            raise ToolPolicyError(f"Tool '{tool_name}' is not enabled for this process.", 403)
        if not isinstance(config, dict):
            config = {}
        allowed_agents = config.get("allowed_agents")
        if allowed_agents is not None and (
            not isinstance(allowed_agents, list)
            or any(not isinstance(agent_name, str) for agent_name in allowed_agents)
        ):
            raise ToolPolicyError(f"Process configuration for '{tool_name}' has an invalid allowed_agents list.", 403)
        return config

    @classmethod
    async def _authorize(
        cls,
        db: AsyncSession,
        actor: User,
        case: Case,
        spec: _ToolSpec,
        configuration: Dict[str, Any],
        agent: Optional[AgentDefinition],
    ) -> None:
        if case.organization_id != actor.organization_id:
            raise ToolPolicyError("Case is outside the actor's organization scope.", 403)
        if agent is not None:
            process_agents = configuration.get("allowed_agents")
            allowed_agents = set(process_agents if process_agents is not None else spec.allowed_agents)
            if not allowed_agents or agent.agent_type not in allowed_agents or (
                spec.allowed_agents and agent.agent_type not in spec.allowed_agents
            ):
                raise ToolPolicyError("Agent is not allowed to use this tool for the process.", 403)

        stmt = (
            select(Permission.id)
            .select_from(Permission)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(Role, Role.id == RolePermission.role_id)
            .outerjoin(UserRole, UserRole.role_id == Role.id)
            .where(
                Permission.code == spec.permission_code,
                or_(Role.organization_id == actor.organization_id, Role.organization_id.is_(None)),
                or_(
                    UserRole.user_id == actor.id,
                    func.upper(Role.name) == str(getattr(actor.role, "value", actor.role)).upper(),
                ),
            )
        )
        if (await db.execute(stmt)).first() is None:
            raise ToolPolicyError(f"Missing permission '{spec.permission_code}'.", 403)

    @classmethod
    async def _integration_ready(
        cls, db: AsyncSession, actor: User, configuration: Dict[str, Any]
    ) -> bool:
        integration_type = configuration.get("integration_type")
        if not integration_type or str(integration_type).upper() not in cls._integration_adapters:
            return False
        stmt = select(Integration.id).where(
            Integration.organization_id == actor.organization_id,
            Integration.status == "ACTIVE",
            func.upper(Integration.integration_type) == str(integration_type).upper(),
        )
        integration_id = configuration.get("integration_id")
        if integration_id:
            try:
                stmt = stmt.where(Integration.id == uuid.UUID(str(integration_id)))
            except ValueError:
                return False
        return (await db.execute(stmt)).first() is not None

    @classmethod
    async def _ensure_tool_record(
        cls, db: AsyncSession, spec: Optional[_ToolSpec]
    ) -> ToolDefinitionRecord:
        code = spec.name if spec else cls._failure_tool_code
        record = (await db.execute(
            select(ToolDefinitionRecord).where(ToolDefinitionRecord.code == code)
        )).scalars().first()
        if record is None:
            record = ToolDefinitionRecord(
                organization_id=None,
                name=spec.name if spec else "Rejected gateway request",
                code=code,
                description=spec.description if spec else "Audit record for an unregistered tool request.",
                tool_type="DETERMINISTIC" if spec else "GATEWAY",
                input_schema=spec.input_schema if spec else {"type": "object"},
                output_schema=spec.output_schema if spec else {"type": "object"},
                permission_code=spec.permission_code if spec else None,
                enabled=True,
            )
            db.add(record)
            await db.flush()
        return record

    @classmethod
    def _validate_schema(cls, data: Any, schema: Dict[str, Any], path: str = "arguments") -> None:
        """Validate the JSON Schema subset used by built-in tool contracts."""
        expected_type = schema.get("type")
        type_checks = {
            "object": lambda value: isinstance(value, dict),
            "array": lambda value: isinstance(value, list),
            "null": lambda value: value is None,
            "string": lambda value: isinstance(value, str),
            "boolean": lambda value: isinstance(value, bool),
            "integer": lambda value: isinstance(value, int) and not isinstance(value, bool),
            "number": lambda value: isinstance(value, (int, float, Decimal)) and not isinstance(value, bool),
        }
        if isinstance(expected_type, list):
            if not any(type_checks.get(item, lambda _value: True)(data) for item in expected_type):
                raise ToolValidationError(f"{path} must match one of the allowed types: {', '.join(expected_type)}.")
        elif expected_type in type_checks and not type_checks[expected_type](data):
            raise ToolValidationError(f"{path} must be {expected_type}.")
        if "enum" in schema and data not in schema["enum"]:
            raise ToolValidationError(f"{path} must be one of {schema['enum']}.")
        if data is not None and schema.get("format") == "uuid":
            try:
                uuid.UUID(str(data))
            except (TypeError, ValueError, AttributeError) as exc:
                raise ToolValidationError(f"{path} must be a valid UUID.") from exc
        if data is not None and schema.get("format") == "date-time":
            try:
                datetime.fromisoformat(str(data).replace("Z", "+00:00"))
            except ValueError as exc:
                raise ToolValidationError(f"{path} must be an ISO 8601 date-time.") from exc
        if expected_type == "object":
            properties = schema.get("properties", {})
            missing = [key for key in schema.get("required", []) if key not in data]
            if missing:
                raise ToolValidationError(f"{path} is missing required field(s): {', '.join(missing)}.")
            if schema.get("additionalProperties") is False:
                extra = set(data) - set(properties)
                if extra:
                    raise ToolValidationError(f"{path} contains unsupported field(s): {', '.join(sorted(extra))}.")
            for key, value in data.items():
                if key in properties:
                    cls._validate_schema(value, properties[key], f"{path}.{key}")
        if expected_type == "array":
            for index, value in enumerate(data):
                cls._validate_schema(value, schema.get("items", {}), f"{path}[{index}]")
        if isinstance(data, (int, float, Decimal)) and not isinstance(data, bool):
            if (isinstance(data, float) and not math.isfinite(data)) or (
                isinstance(data, Decimal) and not data.is_finite()
            ):
                raise ToolValidationError(f"{path} must be finite.")
            if "minimum" in schema and data < schema["minimum"]:
                raise ToolValidationError(f"{path} must be at least {schema['minimum']}.")
            if "maximum" in schema and data > schema["maximum"]:
                raise ToolValidationError(f"{path} must be at most {schema['maximum']}.")
        if isinstance(data, str):
            if "minLength" in schema and len(data) < schema["minLength"]:
                raise ToolValidationError(f"{path} must contain at least {schema['minLength']} characters.")
            if "maxLength" in schema and len(data) > schema["maxLength"]:
                raise ToolValidationError(f"{path} must contain at most {schema['maxLength']} characters.")
        if isinstance(data, list) and "minItems" in schema and len(data) < schema["minItems"]:
            raise ToolValidationError(f"{path} must contain at least {schema['minItems']} items.")


async def _calculate_order_total(_context: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    try:
        quantity = Decimal(str(args["quantity"]))
        unit_price = Decimal(str(args["unit_price"]))
        tax_rate = Decimal(str(args.get("tax_rate", 0)))
    except (InvalidOperation, ValueError) as exc:
        raise ToolValidationError("Quantity, unit price, and tax rate must be valid decimals.") from exc
    if quantity < 0 or unit_price < 0 or tax_rate < 0:
        raise ToolValidationError("Quantity, unit price, and tax rate must not be negative.")
    subtotal = quantity * unit_price
    tax = subtotal * tax_rate
    return {
        "quantity": str(quantity),
        "unit_price": str(unit_price),
        "subtotal": str(subtotal),
        "tax": str(tax),
        "total": str(subtotal + tax),
    }


async def _check_required_documents(context: ToolContext, _args: Dict[str, Any]) -> Dict[str, Any]:
    requirements = list((await context.db.execute(select(Requirement).where(
        Requirement.process_version_id == context.process_version.id,
        Requirement.required.is_(True),
    ))).scalars().all())
    def normalize(value: Any) -> str:
        return re.sub(r"[^a-z0-9]", "", str(value).casefold())
    required_types = {
        normalize((requirement.configuration or {}).get("document_type") or requirement.code)
        for requirement in requirements
        if str(requirement.type).upper().endswith("DOCUMENT")
    }
    documents = list((await context.db.execute(select(Document).where(
        Document.case_id == context.case.id,
    ))).scalars().all())
    available_types = {normalize(document.document_type) for document in documents}
    missing = sorted(required_types - available_types)
    return {"complete": not missing, "required_document_types": sorted(required_types), "missing_document_types": missing}


async def _search_knowledge(context: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    from app.core.config import settings
    from app.domain.knowledge.schemas import KnowledgeSearchRequest
    from app.domain.knowledge.service import KnowledgeService
    from app.infrastructure.llm.embedding import (
        FakeEmbeddingAdapter,
        get_embedding_adapter,
    )

    query = args["query"]
    top_k = args.get("top_k", 5)
    source_type = args.get("source_type")
    source_ids = [uuid.UUID(str(s)) for s in args.get("source_ids", [])] if args.get("source_ids") else None

    provider = getattr(settings, "EMBEDDING_PROVIDER", "huggingface_api").lower()
    if provider == "fake" or getattr(settings, "APP_ENV", "").lower() in ("test", "testing"):
        adapter = FakeEmbeddingAdapter()
    else:
        # A configured production provider must fail visibly when unavailable.
        # Returning zero-vector search results would look successful but not be semantic.
        adapter = get_embedding_adapter()

    search_req = KnowledgeSearchRequest(
        query=query,
        top_k=top_k,
        source_type=source_type,
        source_ids=source_ids,
    )
    search_res = await KnowledgeService.search_knowledge(
        db=context.db,
        org_id=context.actor.organization_id,
        request=search_req,
        embedding_adapter=adapter,
    )
    return {
        "query": query,
        "results": [
            {
                "chunk_id": str(r.chunk_id),
                "document_title": r.document_title,
                "source_name": r.source_name,
                "source_type": r.source_type,
                "content": r.content,
                "similarity_score": r.similarity_score,
            }
            for r in search_res.results
        ],
    }


async def _compare_documents(context: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    async def resolve(field_name: str, document_type: Optional[str]) -> tuple[Any, Optional[Dict[str, Any]]]:
        if document_type:
            stmt = (
                select(ExtractedField)
                .join(DocumentVersion, ExtractedField.document_version_id == DocumentVersion.id)
                .join(Document, DocumentVersion.document_id == Document.id)
                .where(
                    Document.case_id == context.case.id,
                    func.upper(Document.document_type) == document_type.upper(),
                    ExtractedField.field_name == field_name,
                )
                .order_by(DocumentVersion.version_number.desc(), ExtractedField.created_at.desc())
                .limit(1)
            )
            field = (await context.db.execute(stmt)).scalars().first()
            if field is None:
                return None, None
            value = field.field_value
            value = value.get("value") if isinstance(value, dict) and "value" in value else value
            return value, {"document_type": document_type, "field_id": str(field.id), "page": field.page_number}

        rows = list((await context.db.execute(select(CaseData).where(
            CaseData.case_id == context.case.id,
            CaseData.field_name == field_name,
        ))).scalars().all())
        if len(rows) != 1:
            return None, None
        value = rows[0].field_value
        value = value.get("value") if isinstance(value, dict) and "value" in value else value
        return value, {"source_type": rows[0].source_type, "source_reference": rows[0].source_reference}

    left, left_evidence = await resolve(args["left_field"], args.get("left_document_type"))
    right, right_evidence = await resolve(args["right_field"], args.get("right_document_type"))
    if left is None or right is None:
        return {
            "status": "INCONCLUSIVE", "left_field": args["left_field"],
            "right_field": args["right_field"], "difference": None,
            "left_evidence": left_evidence, "right_evidence": right_evidence,
        }
    tolerance = Decimal(str(args.get("tolerance", 0)))
    try:
        decimal_left = Decimal(str(left))
        decimal_right = Decimal(str(right))
        if not decimal_left.is_finite() or not decimal_right.is_finite() or not tolerance.is_finite():
            raise InvalidOperation
        difference = abs(decimal_left - decimal_right)
        matched = difference <= tolerance
        difference_value: Any = str(difference)
    except InvalidOperation:
        if tolerance != 0:
            return {
                "status": "INCONCLUSIVE", "left_field": args["left_field"],
                "right_field": args["right_field"], "difference": None,
                "left_evidence": left_evidence, "right_evidence": right_evidence,
            }
        matched = str(left).strip().casefold() == str(right).strip().casefold()
        difference_value = None
    return {
        "status": "MATCH" if matched else "MISMATCH",
        "left_field": args["left_field"],
        "right_field": args["right_field"],
        "left_value": jsonable_encoder(left),
        "right_value": jsonable_encoder(right),
        "difference": difference_value,
        "left_evidence": left_evidence,
        "right_evidence": right_evidence,
    }


async def _run_verification(context: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    report = await VerificationService.run_verification(
        db=context.db,
        request=VerificationRunRequest(
            case_id=context.case.id,
            verification_id=uuid.UUID(args["verification_id"]),
            inputs=args.get("inputs", {}),
            tool_execution_ids=[uuid.UUID(str(item)) for item in args.get("tool_execution_ids", [])],
            actor_type="AGENT" if context.agent else "USER",
            actor_id=context.agent.id if context.agent else context.actor.id,
        ),
    )
    return {
        "execution_id": str(report.id),
        "status": report.status,
        "evidence_ids": [str(item.id) for item in report.evidence],
    }


async def _transition_workflow(context: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic workflow transition handler for the Tool Gateway.

    This is the ONLY path through which an agent can request a stage
    transition.  Every request is re-validated by WorkflowService at
    execution time — stale model proposals are rejected deterministically.
    The actor's organization_id is enforced at the service layer.
    """
    from app.domain.workflows.schemas import TransitionRequest
    from app.domain.workflows.service import WorkflowService

    to_stage_id_raw = args.get("to_stage_id")
    try:
        to_stage_id = uuid.UUID(str(to_stage_id_raw))
    except (TypeError, ValueError) as exc:
        raise ToolValidationError("to_stage_id must be a valid UUID.") from exc

    from_stage_id_raw = args.get("from_stage_id")
    from_stage_id: Optional[uuid.UUID] = None
    if from_stage_id_raw:
        try:
            from_stage_id = uuid.UUID(str(from_stage_id_raw))
        except (TypeError, ValueError) as exc:
            raise ToolValidationError("from_stage_id must be a valid UUID.") from exc

    actor_role_str: Optional[str] = None
    if hasattr(context.actor, "role"):
        actor_role_str = (
            context.actor.role.value
            if hasattr(context.actor.role, "value")
            else str(context.actor.role)
        )

    request = TransitionRequest(
        case_id=context.case.id,
        to_stage_id=to_stage_id,
        from_stage_id=from_stage_id,
        actor_id=context.agent.id if context.agent else context.actor.id,
        actor_role=actor_role_str,
        actor_type="AGENT" if context.agent else "USER",
        reason=str(args.get("reason", ""))[:500] or None,
    )

    result = await WorkflowService.execute_transition(
        db=context.db,
        request=request,
        # Organization scope enforced at service layer — prevents cross-tenant writes
        organization_id=context.actor.organization_id,
    )

    if not result.allowed:
        # Surface as ToolValidationError so the Gateway records a REJECTED status
        violations_summary = "; ".join(
            v.message for v in result.violations[:3]
        ) if result.violations else result.reason
        raise ToolValidationError(
            f"Workflow transition rejected: {violations_summary}"
        )

    return {
        "transition_allowed": True,
        "from_stage_id": str(result.previous_stage_id) if result.previous_stage_id else None,
        "to_stage_id": str(result.current_stage_id) if result.current_stage_id else None,
        "case_status": result.case_status,
        "history_id": str(result.history_id) if result.history_id else None,
        "reason": result.reason,
    }


async def _create_task(context: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    stage_id = args.get("stage_id")
    if stage_id:
        stage = (await context.db.execute(select(WorkflowStage).where(
            WorkflowStage.id == uuid.UUID(str(stage_id)),
            WorkflowStage.process_version_id == context.process_version.id,
        ))).scalars().first()
        if stage is None:
            raise ToolValidationError("stage_id must identify a stage in the case's process version.")
    assigned_user_id = args.get("assigned_user_id")
    if assigned_user_id:
        assignee = (await context.db.execute(select(User).where(
            User.id == uuid.UUID(str(assigned_user_id)),
            User.organization_id == context.case.organization_id,
        ))).scalars().first()
        if assignee is None:
            raise ToolValidationError("assigned_user_id must belong to the case's organization.")
    assigned_role_id = args.get("assigned_role_id")
    if assigned_role_id:
        role = (await context.db.execute(select(Role).where(
            Role.id == uuid.UUID(str(assigned_role_id)),
            or_(Role.organization_id == context.case.organization_id, Role.organization_id.is_(None)),
        ))).scalars().first()
        if role is None:
            raise ToolValidationError("assigned_role_id must be a role in the case's organization.")
    assigned_department_id = args.get("assigned_department_id")
    if assigned_department_id:
        department = (await context.db.execute(select(Department).where(
            Department.id == uuid.UUID(str(assigned_department_id)),
            Department.organization_id == context.case.organization_id,
        ))).scalars().first()
        if department is None:
            raise ToolValidationError("assigned_department_id must belong to the case's organization.")
    task = await TaskService.create_task(
        context.db,
        TaskCreate(case_id=context.case.id, **args),
        created_by_id=context.actor.id,
        created_by_type="AGENT" if context.agent else "USER",
    )
    return {"task_id": str(task.id), "status": task.status, "title": task.title}


async def _request_approval(context: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    task_id = args.get("task_id")
    if task_id and (await context.db.execute(select(Task.id).where(
        Task.id == uuid.UUID(str(task_id)), Task.case_id == context.case.id,
    ))).first() is None:
        raise ToolValidationError("task_id must identify a task belonging to the current case.")
    approval = await ApprovalService.request_approval(
        context.db,
        ApprovalCreate(case_id=context.case.id, **args),
        organization_id=context.case.organization_id,
        actor_id=context.agent.id if context.agent else context.actor.id,
        actor_type="AGENT" if context.agent else "USER",
    )
    return {"approval_id": str(approval.id), "decision": str(approval.decision)}


async def _call_organization_system(context: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    tool_type = context.tool_configuration.get("integration_type")
    integration_id = context.tool_configuration.get("integration_id")
    stmt = select(Integration).where(
        Integration.organization_id == context.actor.organization_id,
        Integration.status == "ACTIVE",
    )
    if integration_id:
        stmt = stmt.where(Integration.id == uuid.UUID(str(integration_id)))
    elif tool_type:
        stmt = stmt.where(func.upper(Integration.integration_type) == str(tool_type).upper())
    else:
        raise RuntimeError("The process does not configure an organization integration for this tool.")
    integration = (await context.db.execute(stmt)).scalars().first()
    if integration is None:
        raise RuntimeError("No active organization integration is configured for this tool.")
    if tool_type and integration.integration_type.upper() != str(tool_type).upper():
        raise RuntimeError("Configured integration type does not match the selected integration.")
    adapter = ToolGatewayService._integration_adapters.get(integration.integration_type.upper())
    if adapter is None:
        raise RuntimeError(f"No trusted adapter is registered for integration type '{tool_type}'.")
    output = adapter(context, args)
    return await output if inspect.isawaitable(output) else output


ToolGatewayService.register_tool(
    "calculate_order_total",
    "Calculate a deterministic order subtotal, tax, and total using decimal arithmetic.",
    _calculate_order_total,
    input_schema={
        "type": "object", "required": ["quantity", "unit_price"], "additionalProperties": False,
        "properties": {
            "quantity": {"type": "number", "minimum": 0},
            "unit_price": {"type": "number", "minimum": 0},
            "tax_rate": {"type": "number", "minimum": 0},
        },
    },
    output_schema={
        "type": "object", "required": ["quantity", "unit_price", "subtotal", "tax", "total"],
        "properties": {key: {"type": "string"} for key in ("quantity", "unit_price", "subtotal", "tax", "total")},
    },
    permission_code="tool.calculate_order_total",
    allowed_agents=["VERIFICATION", "WORKFLOW", "SUPERVISOR"],
)
ToolGatewayService.register_tool(
    "check_required_documents", "Check case documents against required document configuration.",
    _check_required_documents,
    input_schema={"type": "object", "properties": {}, "additionalProperties": False},
    output_schema={"type": "object", "required": ["complete", "required_document_types", "missing_document_types"], "properties": {
        "complete": {"type": "boolean"}, "required_document_types": {"type": "array", "items": {"type": "string"}},
        "missing_document_types": {"type": "array", "items": {"type": "string"}},
    }},
    permission_code="tool.check_required_documents", allowed_agents=["DOCUMENT", "VERIFICATION", "SUPERVISOR"],
)
ToolGatewayService.register_tool(
    "search_knowledge",
    "Retrieve relevant organization policies, SOPs, and compliance guidelines via semantic search.",
    _search_knowledge,
    input_schema={
        "type": "object",
        "required": ["query"],
        "additionalProperties": False,
        "properties": {
            "query": {"type": "string", "minLength": 1, "maxLength": 1000},
            "top_k": {"type": "integer", "minimum": 1, "maximum": 10},
            "source_type": {"type": ["string", "null"]},
            "source_ids": {"type": "array", "items": {"type": "string", "format": "uuid"}},
        },
    },
    output_schema={
        "type": "object",
        "required": ["query", "results"],
        "properties": {
            "query": {"type": "string"},
            "results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "chunk_id": {"type": "string"},
                        "document_title": {"type": "string"},
                        "source_name": {"type": "string"},
                        "source_type": {"type": "string"},
                        "content": {"type": "string"},
                        "similarity_score": {"type": "number"},
                    },
                },
            },
        },
    },
    permission_code="tool.search_knowledge",
    allowed_agents=["DOCUMENT", "VERIFICATION", "SUPERVISOR"],
)
ToolGatewayService.register_tool(
    "compare_documents", "Compare two extracted case fields, optionally using a numeric tolerance.",
    _compare_documents,
    input_schema={"type": "object", "required": ["left_field", "right_field"], "additionalProperties": False,
                  "properties": {"left_field": {"type": "string", "minLength": 1}, "right_field": {"type": "string", "minLength": 1},
                                 "left_document_type": {"type": ["string", "null"]}, "right_document_type": {"type": ["string", "null"]},
                                 "tolerance": {"type": "number", "minimum": 0}}},
    output_schema={"type": "object", "required": ["status"], "properties": {"status": {"type": "string"}}},
    permission_code="tool.compare_documents", allowed_agents=["VERIFICATION", "SUPERVISOR"],
)
ToolGatewayService.register_tool(
    "run_verification", "Run a configured deterministic verification for this case.",
    _run_verification,
    input_schema={"type": "object", "required": ["verification_id"], "additionalProperties": False,
                  "properties": {"verification_id": {"type": "string", "format": "uuid"}, "inputs": {"type": "object"},
                                 "tool_execution_ids": {"type": "array", "items": {"type": "string", "format": "uuid"}}}},
    output_schema={"type": "object", "required": ["execution_id", "status", "evidence_ids"], "properties": {
        "execution_id": {"type": "string"}, "status": {"type": "string"},
        "evidence_ids": {"type": "array", "items": {"type": "string"}},
    }},
    permission_code="tool.run_verification", allowed_agents=["VERIFICATION", "WORKFLOW", "SUPERVISOR"],
)
ToolGatewayService.register_tool(
    "transition_workflow",
    "Execute a deterministic workflow stage transition through the Workflow Engine. "
    "All preconditions, role checks, approvals, and requirements are enforced by the "
    "service regardless of model input. Re-validates case state at execution time.",
    _transition_workflow,
    input_schema={
        "type": "object",
        "required": ["to_stage_id"],
        "additionalProperties": False,
        "properties": {
            "to_stage_id": {"type": "string", "format": "uuid"},
            "from_stage_id": {"type": ["string", "null"], "format": "uuid"},
            "reason": {"type": ["string", "null"], "maxLength": 500},
        },
    },
    output_schema={
        "type": "object",
        "required": ["transition_allowed", "case_status", "reason"],
        "properties": {
            "transition_allowed": {"type": "boolean"},
            "from_stage_id": {"type": ["string", "null"]},
            "to_stage_id": {"type": ["string", "null"]},
            "case_status": {"type": ["string", "null"]},
            "history_id": {"type": ["string", "null"]},
            "reason": {"type": "string"},
        },
    },
    permission_code="tool.transition_workflow",
    allowed_agents=["WORKFLOW", "SUPERVISOR"],
)
ToolGatewayService.register_tool(
    "create_task", "Create an auditable human task for the current case.", _create_task,
    input_schema={"type": "object", "required": ["title"], "additionalProperties": False,
                  "properties": {"title": {"type": "string"}, "description": {"type": ["string", "null"]},
                                 "task_type": {"type": "string"}, "priority": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH", "URGENT"]},
                                 "stage_id": {"type": ["string", "null"], "format": "uuid"}, "assigned_user_id": {"type": ["string", "null"], "format": "uuid"},
                                 "assigned_role_id": {"type": ["string", "null"], "format": "uuid"}, "assigned_department_id": {"type": ["string", "null"], "format": "uuid"},
                                 "due_at": {"type": ["string", "null"], "format": "date-time"}}},
    output_schema={"type": "object", "required": ["task_id", "status", "title"], "properties": {"task_id": {"type": "string"}, "status": {"type": "string"}, "title": {"type": "string"}}},
    permission_code="tool.create_task", allowed_agents=["DOCUMENT", "WORKFLOW", "SUPERVISOR"],
)
ToolGatewayService.register_tool(
    "request_approval", "Create a pending approval request for the current case.", _request_approval,
    input_schema={"type": "object", "required": ["approval_type"], "additionalProperties": False,
                  "properties": {"approval_type": {"type": "string", "minLength": 1}, "task_id": {"type": ["string", "null"], "format": "uuid"}}},
    output_schema={"type": "object", "required": ["approval_id", "decision"], "properties": {"approval_id": {"type": "string"}, "decision": {"type": "string"}}},
    permission_code="tool.request_approval", allowed_agents=["WORKFLOW", "SUPERVISOR"],
)
for _name, _description, _fields, _agents in (
    ("check_inventory", "Look up available inventory through a configured organization integration.", {"sku": {"type": "string"}, "quantity": {"type": "number", "exclusiveMinimum": 0}, "warehouse": {"type": "string", "minLength": 1}}, ["VERIFICATION", "WORKFLOW"]),
    ("get_customer", "Look up a customer through a configured organization integration.", {"customer_id": {"type": "string"}}, ["VERIFICATION", "WORKFLOW"]),
    ("get_payment_status", "Look up payment status through a configured organization integration.", {"payment_reference": {"type": "string"}}, ["VERIFICATION", "WORKFLOW"]),
):
    _output_schema = {"type": "object"}
    if _name == "check_inventory":
        _fields = dict(_fields, quantity={"type": "number", "exclusiveMinimum": 0}, warehouse={"type": "string", "minLength": 1})
        _output_schema = {
            "type": "object", "required": ["found", "sku", "warehouse", "requested_quantity", "available_quantity", "reserved_quantity", "decision"],
            "properties": {
                "found": {"type": "boolean"}, "sku": {"type": "string"}, "warehouse": {"type": "string"},
                "requested_quantity": {"type": "number"}, "available_quantity": {"type": "number"},
                "reserved_quantity": {"type": "number"}, "decision": {"type": "string", "enum": ["AVAILABLE", "INSUFFICIENT"]},
            }, "additionalProperties": False,
        }
    elif _name == "get_payment_status":
        _output_schema = {
            "type": "object", "required": ["found", "payment_reference", "status", "outstanding_amount", "currency"],
            "properties": {
                "found": {"type": "boolean"}, "payment_reference": {"type": "string"},
                "status": {"type": "string", "enum": ["PAID", "PARTIALLY_PAID", "UNPAID", "UNKNOWN"]},
                "outstanding_amount": {"type": ["number", "null"]}, "currency": {"type": ["string", "null"]},
            }, "additionalProperties": False,
        }
    elif _name == "get_customer":
        _output_schema = {
            "type": "object", "required": [
                "found", "customer_id", "customer_name", "customer_group", "territory", "customer_type",
            ],
            "properties": {
                "found": {"type": "boolean"}, "customer_id": {"type": "string"},
                "customer_name": {"type": ["string", "null"]},
                "customer_group": {"type": ["string", "null"]},
                "territory": {"type": ["string", "null"]},
                "customer_type": {"type": ["string", "null"]},
            }, "additionalProperties": False,
        }
    ToolGatewayService.register_tool(
        _name, _description, _call_organization_system,
        input_schema={"type": "object", "required": list(_fields), "additionalProperties": False, "properties": _fields},
        output_schema=_output_schema, permission_code=f"tool.{_name}", allowed_agents=_agents,
    )


ToolGatewayService.register_integration_adapter("ERP", erpnext_integration_adapter)
ToolGatewayService.register_integration_adapter("FINANCE", erpnext_integration_adapter)
