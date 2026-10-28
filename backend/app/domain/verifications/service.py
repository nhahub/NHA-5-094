import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.audit.service import AuditService
from app.domain.cases.models import Case
from app.domain.documents.models import (
    Document,
    DocumentVersion,
    Evidence,
    EvidenceItem,
    ExtractedField,
)
from app.domain.rules.models import BusinessRule, CalculationDefinition
from app.domain.verifications.models import (
    CalculationExecution,
    RuleExecution,
    VerificationDefinition,
    VerificationExecution,
    VerificationResult,
    VerificationRule,
    VerificationStatus,
)
from app.domain.verifications.orchestrator import VerificationOrchestrator
from app.domain.verifications.schemas import (
    VerificationDefinitionCreate,
    VerificationRunRequest,
)
from app.events.service import EventService


class VerificationService:
    """Service managing verification definitions, deterministic execution orchestrations, and evidence trails."""

    @staticmethod
    async def create_definition(
        db: AsyncSession, def_in: VerificationDefinitionCreate
    ) -> VerificationDefinition:
        definition = VerificationDefinition(
            process_version_id=def_in.process_version_id,
            name=def_in.name,
            code=def_in.code,
            description=def_in.description,
            stage_id=def_in.stage_id,
            result_policy=def_in.result_policy or {},
        )
        db.add(definition)
        await db.flush()

        # Link rules if provided
        for rule_link in def_in.rules:
            vr = VerificationRule(
                verification_id=definition.id,
                rule_id=rule_link.rule_id,
                execution_order=rule_link.execution_order,
                required=rule_link.required,
            )
            db.add(vr)

        await db.commit()
        await db.refresh(definition)
        return definition

    @staticmethod
    async def get_definitions_by_version(
        db: AsyncSession, process_version_id: uuid.UUID
    ) -> list[VerificationDefinition]:
        stmt = (
            select(VerificationDefinition)
            .where(VerificationDefinition.process_version_id == process_version_id)
            .options(selectinload(VerificationDefinition.verification_rules))
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_definition_by_id(
        db: AsyncSession, definition_id: uuid.UUID
    ) -> VerificationDefinition | None:
        stmt = (
            select(VerificationDefinition)
            .where(VerificationDefinition.id == definition_id)
            .options(
                selectinload(VerificationDefinition.verification_rules).selectinload(VerificationRule.rule)
            )
        )
        result = await db.execute(stmt)
        return result.scalars().first()

    @classmethod
    async def run_verification(
        cls, db: AsyncSession, request: VerificationRunRequest
    ) -> VerificationExecution:
        """Run all associated calculations and rules for a VerificationDefinition against a Case."""
        started_at = datetime.now(timezone.utc)

        # 1. Fetch Case with CaseData, Documents, and ExtractedFields
        case_stmt = (
            select(Case)
            .where(Case.id == request.case_id)
            .options(
                selectinload(Case.case_data),
                selectinload(Case.documents).selectinload(Document.versions),
            )
        )
        case_res = await db.execute(case_stmt)
        case = case_res.scalars().first()
        if not case:
            raise ValueError(f"Case '{request.case_id}' does not exist.")

        # 2. Fetch VerificationDefinition with rules
        definition = await cls.get_definition_by_id(db, request.verification_id)
        if not definition:
            raise ValueError(f"VerificationDefinition '{request.verification_id}' does not exist.")
        if definition.process_version_id != case.process_version_id:
            raise ValueError("Verification definition does not belong to the case's process version.")

        tool_executions: list[Any] = []
        tool_outputs: dict[str, dict[str, Any]] = {}
        requested_tool_ids = set(request.tool_execution_ids)
        if requested_tool_ids:
            # Import locally because the Tool Gateway also invokes this service.
            from app.tools.models import ToolDefinition as ToolDefinitionRecord
            from app.tools.models import ToolExecution

            # Select both the persisted execution and its registered, trusted
            # tool code; never derive rule paths from model-supplied labels.
            rows = list((await db.execute(
                select(ToolExecution, ToolDefinitionRecord.code)
                .join(ToolDefinitionRecord, ToolDefinitionRecord.id == ToolExecution.tool_id)
                .where(
                    ToolExecution.id.in_(requested_tool_ids),
                    ToolExecution.case_id == case.id,
                    ToolExecution.status == "SUCCESS",
                    (ToolExecution.organization_id == case.organization_id)
                    | ToolExecution.organization_id.is_(None),
                )
                .order_by(ToolExecution.started_at, ToolExecution.id)
            )).all())
            if {item.id for item, _code in rows} != requested_tool_ids:
                raise ValueError(
                    "Every referenced tool execution must be successful and belong to this case."
                )
            tool_executions = [item for item, _code in rows]
            for item, tool_code in rows:
                if isinstance(item.output_data, dict):
                    tool_outputs[tool_code] = item.output_data

        # 3. Assemble Evaluation Context
        context: dict[str, Any] = {
            "case": {
                "id": str(case.id),
                "case_number": case.case_number,
                "title": case.title,
                "status": case.status,
                "metadata": case.case_metadata or {},
            },
            "case_data": {},
            "documents": {},
            "tools": {},
        }
        # Merge explicit inputs
        if request.inputs:
            context.update(request.inputs)
        # Tool facts are loaded only from successful, case-scoped Tool Gateway
        # executions. Caller-provided inputs must not be able to forge them.
        context["tools"] = tool_outputs

        # Populate case_data
        for cd in (case.case_data or []):
            val = cd.field_value if cd.field_value is not None else cd.field_name
            context["case_data"][cd.field_name] = val
            # Also expose at top-level for convenience
            if cd.field_name not in context:
                context[cd.field_name] = val

        # Populate document extracted fields
        for doc in (case.documents or []):
            doc_key = doc.document_type.lower()
            context["documents"][doc_key] = {
                "id": str(doc.id),
                "name": doc.name,
                "document_type": doc.document_type,
                "status": doc.status,
            }

        # Query extracted fields for case documents
        doc_ids = [d.id for d in (case.documents or [])]
        evidence_items: list[EvidenceItem] = []
        for document in case.documents or []:
            latest_version = max(
                document.versions or [], key=lambda version: version.version_number, default=None
            )
            evidence_items.append(EvidenceItem(
                source_type="DOCUMENT",
                source_id=document.id,
                field_reference=document.document_type,
                value_snapshot=AuditService._sanitize_json({
                    "name": document.name,
                    "document_type": document.document_type,
                    "status": document.status,
                    "version_id": latest_version.id if latest_version else None,
                    "version_number": latest_version.version_number if latest_version else None,
                    "file_hash": latest_version.file_hash if latest_version else None,
                }),
            ))
        if doc_ids:
            # Scope evidence to this case's documents. Without the predicate,
            # fields from other cases sharing a document type could leak in.
            ef_stmt = (
                select(ExtractedField)
                .join(ExtractedField.document_version)
                .where(DocumentVersion.document_id.in_(doc_ids))
                .options(
                    selectinload(ExtractedField.document_version)
                    .selectinload(DocumentVersion.document)
                )
            )
            ef_res = await db.execute(ef_stmt)
            for ef in ef_res.scalars().all():
                if ef.document_version and ef.document_version.document:
                    d_key = ef.document_version.document.document_type.lower()
                    if d_key in context["documents"]:
                        raw_value = ef.field_value
                        extracted_value = (
                            raw_value.get("value")
                            if isinstance(raw_value, dict) and "value" in raw_value
                            else raw_value
                        )
                        context["documents"][d_key][ef.field_name] = extracted_value
                        evidence_items.append(EvidenceItem(
                            source_type="EXTRACTED_FIELD",
                            source_id=ef.id,
                            field_reference=ef.field_name,
                            value_snapshot=AuditService._sanitize_json({
                                "value": raw_value,
                                "document_id": ef.document_version.document.id,
                                "document_version_id": ef.document_version.id,
                                "document_type": ef.document_version.document.document_type,
                                "confidence": ef.confidence,
                                "extraction_method": ef.extraction_method,
                            }),
                            page_number=ef.page_number,
                            location=AuditService._sanitize_json(ef.bounding_box),
                        ))

        for tool_execution in tool_executions:
            evidence_items.append(EvidenceItem(
                source_type="TOOL_EXECUTION",
                source_id=tool_execution.id,
                field_reference=str(tool_execution.tool_id),
                value_snapshot=AuditService._sanitize_json({
                    "status": tool_execution.status,
                    "output": tool_execution.output_data,
                }),
            ))

        # 4. Create VerificationExecution instance
        execution = VerificationExecution(
            case_id=case.id,
            verification_id=definition.id,
            status=VerificationStatus.INCONCLUSIVE.value,
            started_at=started_at,
            executed_by_type=request.actor_type,
            executed_by_id=request.actor_id,
            inputs=AuditService._sanitize_json(context),
        )
        db.add(execution)
        await db.flush()
        # Preserve the scalar key across the later commit. AsyncSession expires
        # ORM attributes at commit, and synchronous access during audit/event
        # creation would otherwise attempt IO outside greenlet_spawn.
        execution_id = execution.id
        case_id = case.id
        organization_id = case.organization_id
        verification_id = definition.id
        verification_code = definition.code
        verification_name = definition.name

        # Record the beginning as its own committed history boundary. If the
        # deterministic evaluation fails later, the started execution remains visible.
        await EventService.emit_event(
            db=db,
            event_type="VERIFICATION_STARTED",
            organization_id=organization_id,
            actor_type=request.actor_type,
            actor_id=request.actor_id,
            case_id=case_id,
            payload={
                "execution_id": str(execution_id),
                "verification_code": verification_code,
                "verification_name": verification_name,
            },
        )

        # 5. Run Calculations (if any defined in process version)
        calc_stmt = select(CalculationDefinition).where(
            CalculationDefinition.process_version_id == case.process_version_id
        )
        calc_res = await db.execute(calc_stmt)
        calculations = list(calc_res.scalars().all())

        # 6. Run Rules
        # Load rules from VerificationRule link, or fall back to process version rules
        rules_to_run: list[tuple[BusinessRule, bool]] = []
        if definition.verification_rules:
            for vr in sorted(definition.verification_rules, key=lambda r: r.execution_order):
                if vr.rule:
                    rules_to_run.append((vr.rule, vr.required))
        else:
            p_rules_stmt = select(BusinessRule).where(
                BusinessRule.process_version_id == case.process_version_id
            )
            p_rules = list((await db.execute(p_rules_stmt)).scalars().all())
            for r in p_rules:
                rules_to_run.append((r, True))

        evaluation = VerificationOrchestrator.evaluate(calculations, rules_to_run, context)
        context = evaluation.context
        for calc, trace in zip(
            sorted(calculations, key=lambda item: (int((item.configuration or {}).get("execution_order", 0)), item.code)),
            evaluation.calculations,
        ):
            c_exec = CalculationExecution(
                verification_execution_id=execution_id,
                calculation_id=calc.id,
                input_data=AuditService._sanitize_json(trace.input_context),
                output_data=AuditService._sanitize_json({
                    "value": float(trace.value) if trace.value is not None else None,
                    "trace": trace.to_dict(),
                }),
                status=trace.status,
                executed_at=datetime.now(timezone.utc),
            )
            db.add(c_exec)
            await db.flush()
            evidence_items.append(EvidenceItem(
                source_type="CALCULATION_EXECUTION",
                source_id=c_exec.id,
                field_reference=calc.code,
                value_snapshot=AuditService._sanitize_json({
                    "status": trace.status,
                    "output": trace.to_dict(),
                }),
            ))

        for rule_trace in evaluation.rules:
            r_exec = RuleExecution(
                verification_execution_id=execution_id,
                rule_id=uuid.UUID(rule_trace.rule_id),
                input_data=AuditService._sanitize_json(context),
                result="PASS" if rule_trace.passed else "FAIL",
                output_data=AuditService._sanitize_json(rule_trace.to_dict()),
                executed_at=datetime.now(timezone.utc),
            )
            db.add(r_exec)
            await db.flush()
            evidence_items.append(EvidenceItem(
                source_type="RULE_EXECUTION",
                source_id=r_exec.id,
                field_reference=rule_trace.rule_code,
                value_snapshot=AuditService._sanitize_json(r_exec.output_data),
            ))

        # 7. Persist the aggregate result selected by the orchestrator.
        final_status = evaluation.status.value
        summary = evaluation.summary
        total_rules = evaluation.total_rules
        passed_rules_count = evaluation.passed_rules

        execution.status = final_status
        execution.completed_at = datetime.now(timezone.utc)

        # 8. Create VerificationResult summary
        confidence = float(passed_rules_count / total_rules) if total_rules > 0 else 1.0
        v_result = VerificationResult(
            verification_execution_id=execution_id,
            result=final_status,
            summary=summary,
            confidence=confidence,
            reason=f"Executed {total_rules} rules with {passed_rules_count} passes.",
        )
        db.add(v_result)

        evidence = Evidence(
            case_id=case_id,
            verification_execution_id=execution_id,
            evidence_type="VERIFICATION",
            description=f"Evidence supporting verification {verification_code} ({execution_id}).",
            items=evidence_items,
        )
        db.add(evidence)

        # 9. Emit Event
        await EventService.emit_event(
            db=db,
            event_type="VERIFICATION_COMPLETED",
            organization_id=organization_id,
            actor_type=request.actor_type,
            actor_id=request.actor_id,
            case_id=case_id,
            payload={
                "execution_id": str(execution_id),
                "verification_code": verification_code,
                "verification_name": verification_name,
                "status": final_status,
                "passed_rules": passed_rules_count,
                "total_rules": total_rules,
                "tool_execution_ids": [str(item.id) for item in tool_executions],
            },
            dispatch_orchestration=True,
        )

        # 10. Audit Log
        await AuditService.log_action(
            db=db,
            organization_id=organization_id,
            action="VERIFICATION_EXECUTED",
            resource_type="VERIFICATION",
            resource_id=execution_id,
            actor_type=request.actor_type,
            actor_id=request.actor_id,
            after_state={"status": final_status, "case_id": str(case_id)},
            audit_metadata={
                "verification_id": str(verification_id),
                "verification_code": verification_code,
                "passed_count": passed_rules_count,
                "total_count": total_rules,
            },
        )

        await db.commit()

        # Reload full execution with relations
        return await cls.get_execution_by_id(db, execution_id)

    @staticmethod
    async def get_execution_by_id(
        db: AsyncSession, execution_id: uuid.UUID
    ) -> VerificationExecution | None:
        stmt = (
            select(VerificationExecution)
            .where(VerificationExecution.id == execution_id)
            .options(
                selectinload(VerificationExecution.results),
                selectinload(VerificationExecution.rule_executions),
                selectinload(VerificationExecution.calculation_executions),
                selectinload(VerificationExecution.evidence).selectinload(Evidence.items),
            )
        )
        result = await db.execute(stmt)
        return result.scalars().first()

    @staticmethod
    async def get_executions_by_case(
        db: AsyncSession, case_id: uuid.UUID
    ) -> list[VerificationExecution]:
        stmt = (
            select(VerificationExecution)
            .where(VerificationExecution.case_id == case_id)
            .options(
                selectinload(VerificationExecution.results),
                selectinload(VerificationExecution.rule_executions),
                selectinload(VerificationExecution.calculation_executions),
                selectinload(VerificationExecution.evidence).selectinload(Evidence.items),
            )
            .order_by(VerificationExecution.created_at.desc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())
