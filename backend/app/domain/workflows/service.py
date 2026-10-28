import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.approvals.models import Approval, ApprovalDecision
from app.domain.audit.service import AuditService
from app.domain.cases.models import Case, CaseData, CaseStageHistory, CaseStatus
from app.domain.documents.models import Document
from app.domain.processes.models import Requirement, RequirementType
from app.domain.verifications.models import (
    VerificationDefinition,
    VerificationExecution,
    VerificationStatus,
)
from app.domain.workflows.models import WorkflowStage, WorkflowTransition
from app.domain.workflows.schemas import (
    TransitionRequest,
    TransitionResult,
    TransitionViolation,
    WorkflowStageCreate,
    WorkflowTransitionCreate,
)
from app.events.service import EventService


class WorkflowService:
    """Deterministic Workflow Engine managing stages, transitions, prerequisite validations, and audit logs."""

    @staticmethod
    async def create_stage(db: AsyncSession, stage_in: WorkflowStageCreate) -> WorkflowStage:
        stage = WorkflowStage(
            process_version_id=stage_in.process_version_id,
            name=stage_in.name,
            code=stage_in.code,
            description=stage_in.description,
            stage_order=stage_in.stage_order,
            is_initial=stage_in.is_initial,
            is_terminal=stage_in.is_terminal,
            config=stage_in.config or {},
        )
        db.add(stage)
        await db.commit()
        await db.refresh(stage)
        return stage

    @staticmethod
    async def get_stages_by_version(
        db: AsyncSession, process_version_id: uuid.UUID
    ) -> list[WorkflowStage]:
        stmt = (
            select(WorkflowStage)
            .where(WorkflowStage.process_version_id == process_version_id)
            .order_by(WorkflowStage.stage_order)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_stage_by_id(db: AsyncSession, stage_id: uuid.UUID) -> WorkflowStage | None:
        stmt = select(WorkflowStage).where(WorkflowStage.id == stage_id)
        result = await db.execute(stmt)
        return result.scalars().first()

    @staticmethod
    async def create_transition(
        db: AsyncSession, transition_in: WorkflowTransitionCreate
    ) -> WorkflowTransition:
        transition = WorkflowTransition(
            process_version_id=transition_in.process_version_id,
            from_stage_id=transition_in.from_stage_id,
            to_stage_id=transition_in.to_stage_id,
            name=transition_in.name,
            code=transition_in.code,
            condition_config=transition_in.condition_config or {},
            requires_approval=transition_in.requires_approval,
            required_role=transition_in.required_role,
        )
        db.add(transition)
        await db.commit()
        await db.refresh(transition)
        return transition

    @staticmethod
    async def get_transitions_from_stage(
        db: AsyncSession, stage_id: uuid.UUID
    ) -> list[WorkflowTransition]:
        stmt = select(WorkflowTransition).where(WorkflowTransition.from_stage_id == stage_id)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_transitions_by_version(
        db: AsyncSession, process_version_id: uuid.UUID
    ) -> list[WorkflowTransition]:
        stmt = select(WorkflowTransition).where(
            WorkflowTransition.process_version_id == process_version_id
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @classmethod
    async def validate_transition(
        cls,
        db: AsyncSession,
        request: TransitionRequest,
        organization_id: uuid.UUID | None = None,
    ) -> TransitionResult:
        """Deterministically validate if a Case can legally transition to a target stage."""
        violations: list[TransitionViolation] = []

        # 1. Fetch Case with relationships (organization-scoped when org_id provided)
        stmt = (
            select(Case)
            .where(Case.id == request.case_id)
            .options(
                selectinload(Case.documents),
                selectinload(Case.approvals),
                selectinload(Case.verifications),
                selectinload(Case.case_data),
            )
        )
        if organization_id is not None:
            stmt = stmt.where(Case.organization_id == organization_id)
        result = await db.execute(stmt)
        case = result.scalars().first()

        if not case:
            # Return non-disclosing 404-style message regardless of whether the case
            # doesn't exist or belongs to a different organization.
            return TransitionResult(
                allowed=False,
                reason=f"Case with ID '{request.case_id}' does not exist or is outside the authorized organization scope.",
                case_id=request.case_id,
            )

        previous_stage_id = case.current_stage_id

        # 2. Check if case is already completed or cancelled
        if case.status in [CaseStatus.COMPLETED.value, CaseStatus.CANCELLED.value, CaseStatus.REJECTED.value]:
            return TransitionResult(
                allowed=False,
                reason=f"Cannot transition case in terminal status '{case.status}'.",
                case_id=case.id,
                previous_stage_id=previous_stage_id,
                current_stage_id=previous_stage_id,
                case_status=case.status,
            )

        # 3. Check target stage exists in the same process version
        target_stage = await cls.get_stage_by_id(db, request.to_stage_id)
        if not target_stage or target_stage.process_version_id != case.process_version_id:
            return TransitionResult(
                allowed=False,
                reason="Target stage does not exist or belongs to a different process version.",
                case_id=case.id,
                previous_stage_id=previous_stage_id,
                current_stage_id=previous_stage_id,
                case_status=case.status,
            )

        # 4. Check for repeated transition (already at target stage)
        if case.current_stage_id == request.to_stage_id:
            return TransitionResult(
                allowed=False,
                reason=f"Case is already in stage '{target_stage.name}' ({target_stage.code}).",
                case_id=case.id,
                previous_stage_id=previous_stage_id,
                current_stage_id=previous_stage_id,
                case_status=case.status,
            )

        # 5. Check source stage match if specified
        if request.from_stage_id is not None and request.from_stage_id != case.current_stage_id:
            return TransitionResult(
                allowed=False,
                reason=f"Current stage mismatch: expected '{case.current_stage_id}', request specified '{request.from_stage_id}'.",
                case_id=case.id,
                previous_stage_id=previous_stage_id,
                current_stage_id=previous_stage_id,
                case_status=case.status,
            )

        # 6. Find valid Transition Definition
        transition: WorkflowTransition | None = None
        if case.current_stage_id is None:
            # Entry into initial stage
            if not target_stage.is_initial:
                return TransitionResult(
                    allowed=False,
                    reason=f"Target stage '{target_stage.name}' is not configured as an initial stage.",
                    case_id=case.id,
                    previous_stage_id=previous_stage_id,
                    current_stage_id=previous_stage_id,
                    case_status=case.status,
                )
        else:
            stmt = select(WorkflowTransition).where(
                WorkflowTransition.process_version_id == case.process_version_id,
                WorkflowTransition.from_stage_id == case.current_stage_id,
                WorkflowTransition.to_stage_id == request.to_stage_id,
            )
            res = await db.execute(stmt)
            transition = res.scalars().first()

            if not transition:
                current_stage = await cls.get_stage_by_id(db, case.current_stage_id)
                current_name = current_stage.name if current_stage else str(case.current_stage_id)
                return TransitionResult(
                    allowed=False,
                    reason=f"No configured transition exists from '{current_name}' to '{target_stage.name}'.",
                    case_id=case.id,
                    previous_stage_id=previous_stage_id,
                    current_stage_id=previous_stage_id,
                    case_status=case.status,
                )

        # 7. Check Actor Role Permissions
        if transition and transition.required_role:
            actor_role = request.actor_role
            if actor_role != "ADMIN" and actor_role != transition.required_role:
                violations.append(
                    TransitionViolation(
                        code="UNAUTHORIZED_ROLE",
                        message=f"Transition '{transition.name}' requires role '{transition.required_role}', but actor has '{actor_role}'.",
                    )
                )

        # 8. Check Required Transition Approval
        if transition and transition.requires_approval:
            appr_stmt = select(Approval).where(
                Approval.case_id == case.id,
                Approval.decision == ApprovalDecision.APPROVED.value,
            )
            appr_res = await db.execute(appr_stmt)
            has_approval = appr_res.scalars().first() is not None
            if not has_approval:
                violations.append(
                    TransitionViolation(
                        code="MISSING_APPROVAL",
                        message=f"Transition '{transition.name}' requires an approved human authorization.",
                    )
                )

        # 9. Check Stage Prerequisites / Requirements
        req_stmt = select(Requirement).where(
            Requirement.process_version_id == case.process_version_id,
            Requirement.required == True,
        )
        if case.current_stage_id:
            req_stmt = req_stmt.where(
                (Requirement.stage_id == case.current_stage_id) | (Requirement.stage_id.is_(None))
            )
        req_res = await db.execute(req_stmt)
        requirements = list(req_res.scalars().all())
        review_stage = bool((target_stage.config or {}).get("review_stage"))
        condition_config = transition.condition_config if transition else {}
        allowed_failed_verifications = set(
            condition_config.get("allow_failed_verifications", [])
            if isinstance(condition_config, dict) else []
        )

        for req in requirements:
            if req.type == RequirementType.DOCUMENT.value:
                doc_type = req.configuration.get("document_type", req.code)
                doc_stmt = select(Document).where(
                    Document.case_id == case.id,
                    (Document.document_type == doc_type) | (Document.document_type == req.code),
                )
                doc_res = await db.execute(doc_stmt)
                has_doc = doc_res.scalars().first() is not None
                if not has_doc:
                    violations.append(
                        TransitionViolation(
                            code="MISSING_DOCUMENT",
                            message=f"Required document '{req.name}' ({req.code}) has not been uploaded.",
                            requirement_id=req.id,
                            requirement_type=req.type,
                        )
                    )

            elif req.type == RequirementType.APPROVAL.value:
                appr_stmt = select(Approval).where(
                    Approval.case_id == case.id,
                    Approval.decision == ApprovalDecision.APPROVED.value,
                )
                appr_res = await db.execute(appr_stmt)
                has_app = appr_res.scalars().first() is not None
                if not has_app:
                    violations.append(
                        TransitionViolation(
                            code="MISSING_APPROVAL",
                            message=f"Required approval '{req.name}' has not been granted.",
                            requirement_id=req.id,
                            requirement_type=req.type,
                        )
                    )

            elif req.type == RequirementType.VERIFICATION.value:
                target_verif_code = req.configuration.get("verification_code", req.code)
                if review_stage and target_verif_code in allowed_failed_verifications:
                    failed_stmt = (
                        select(VerificationExecution.id)
                        .join(
                            VerificationDefinition,
                            VerificationDefinition.id == VerificationExecution.verification_id,
                        )
                        .where(
                            VerificationExecution.case_id == case.id,
                            VerificationDefinition.code == target_verif_code,
                            VerificationExecution.status.in_([
                                VerificationStatus.FAIL.value,
                                VerificationStatus.REVIEW.value,
                                VerificationStatus.INCONCLUSIVE.value,
                            ]),
                        )
                    )
                    failed_execution = (await db.execute(failed_stmt)).scalars().first()
                    if failed_execution is not None:
                        # Only an actual non-passing result for the explicitly
                        # named check can route into a configured review stage.
                        continue
                verif_stmt = select(VerificationExecution).where(
                    VerificationExecution.case_id == case.id,
                    VerificationExecution.status == VerificationStatus.PASS.value,
                )
                verif_res = await db.execute(verif_stmt)
                has_passed_verif = verif_res.scalars().first() is not None
                if not has_passed_verif:
                    violations.append(
                        TransitionViolation(
                            code="FAILED_OR_MISSING_VERIFICATION",
                            message=f"Required verification '{req.name}' ({target_verif_code}) has not passed.",
                            requirement_id=req.id,
                            requirement_type=req.type,
                        )
                    )

            elif req.type == RequirementType.DATA.value or req.type == "FIELD":
                target_field = req.configuration.get("field_name", req.code)
                data_stmt = select(CaseData).where(
                    CaseData.case_id == case.id,
                    CaseData.field_name == target_field,
                )
                data_res = await db.execute(data_stmt)
                has_data = data_res.scalars().first() is not None
                if not has_data:
                    violations.append(
                        TransitionViolation(
                            code="MISSING_REQUIRED_DATA",
                            message=f"Required field '{req.name}' ({target_field}) is not present.",
                            requirement_id=req.id,
                            requirement_type=req.type,
                        )
                    )

        if violations:
            return TransitionResult(
                allowed=False,
                reason="Transition preconditions not satisfied.",
                case_id=case.id,
                previous_stage_id=previous_stage_id,
                current_stage_id=previous_stage_id,
                case_status=case.status,
                transition_id=transition.id if transition else None,
                violations=violations,
            )

        return TransitionResult(
            allowed=True,
            reason="Transition preconditions satisfied.",
            case_id=case.id,
            previous_stage_id=previous_stage_id,
            current_stage_id=request.to_stage_id,
            case_status=CaseStatus.COMPLETED.value if target_stage.is_terminal else CaseStatus.IN_PROGRESS.value,
            transition_id=transition.id if transition else None,
            violations=[],
        )

    @classmethod
    async def execute_transition(
        cls,
        db: AsyncSession,
        request: TransitionRequest,
        organization_id: uuid.UUID | None = None,
    ) -> TransitionResult:
        """Validate and execute a workflow stage transition with event emission and audit records.

        When ``organization_id`` is supplied (e.g. from an agent or API route) the
        case load is organization-scoped so cross-tenant writes are rejected at the
        service layer regardless of caller context.
        """
        # 1. Deterministic Validation (organization-scoped)
        validation = await cls.validate_transition(db, request, organization_id=organization_id)
        if not validation.allowed:
            # Audit rejected attempt
            stmt = select(Case).where(Case.id == request.case_id)
            if organization_id is not None:
                stmt = stmt.where(Case.organization_id == organization_id)
            res = await db.execute(stmt)
            case_obj = res.scalars().first()
            if case_obj:
                await AuditService.log_action(
                    db=db,
                    organization_id=case_obj.organization_id,
                    action="WORKFLOW_TRANSITION_REJECTED",
                    resource_type="CASE",
                    resource_id=case_obj.id,
                    actor_type=request.actor_type,
                    actor_id=request.actor_id,
                    before_state={"stage_id": str(case_obj.current_stage_id)},
                    after_state={"stage_id": str(case_obj.current_stage_id), "status": case_obj.status},
                    audit_metadata={
                        "attempted_target_stage_id": str(request.to_stage_id),
                        "reason": validation.reason,
                        "violations": [v.model_dump(mode="json") for v in validation.violations],
                    },
                )
            return validation

        # 2. Fetch Case & Target Stage to apply updates
        stmt = select(Case).where(Case.id == request.case_id)
        if organization_id is not None:
            stmt = stmt.where(Case.organization_id == organization_id)
        res = await db.execute(stmt)
        case = res.scalars().first()
        assert case is not None

        target_stage = await cls.get_stage_by_id(db, request.to_stage_id)
        assert target_stage is not None

        previous_stage_id = case.current_stage_id
        case.current_stage_id = target_stage.id

        if case.status == CaseStatus.OPEN.value:
            case.status = CaseStatus.IN_PROGRESS.value

        if target_stage.is_terminal:
            case.status = CaseStatus.COMPLETED.value
            case.completed_at = datetime.now(timezone.utc)

        # 3. Insert Stage History
        history = CaseStageHistory(
            case_id=case.id,
            from_stage_id=previous_stage_id,
            to_stage_id=target_stage.id,
            transition_id=validation.transition_id,
            triggered_by_type=request.actor_type,
            triggered_by_id=request.actor_id,
            reason=request.reason,
        )
        db.add(history)
        await db.flush()
        await db.refresh(history)

        # 4. Emit Events
        await EventService.emit_event(
            db=db,
            event_type="WORKFLOW_TRANSITIONED",
            organization_id=case.organization_id,
            actor_type=request.actor_type,
            actor_id=request.actor_id,
            case_id=case.id,
            payload={
                "from_stage_id": str(previous_stage_id) if previous_stage_id else None,
                "to_stage_id": str(target_stage.id),
                "target_stage_code": target_stage.code,
                "target_stage_name": target_stage.name,
                "reason": request.reason,
            },
            dispatch_orchestration=True,
        )

        if target_stage.is_terminal:
            await EventService.emit_event(
                db=db,
                event_type="CASE_COMPLETED",
                organization_id=case.organization_id,
                actor_type=request.actor_type,
                actor_id=request.actor_id,
                case_id=case.id,
                payload={
                    "completed_at": case.completed_at.isoformat() if case.completed_at else None,
                    "terminal_stage": target_stage.code,
                },
                dispatch_orchestration=True,
            )

        # 5. Write Audit Log
        await AuditService.log_action(
            db=db,
            organization_id=case.organization_id,
            action="WORKFLOW_TRANSITION_EXECUTED",
            resource_type="CASE",
            resource_id=case.id,
            actor_type=request.actor_type,
            actor_id=request.actor_id,
            before_state={"stage_id": str(previous_stage_id) if previous_stage_id else None},
            after_state={"stage_id": str(target_stage.id), "status": case.status},
            audit_metadata={
                "history_id": str(history.id),
                "reason": request.reason,
                "metadata": request.metadata,
            },
        )

        await db.commit()
        await db.refresh(case)

        return TransitionResult(
            allowed=True,
            reason=f"Transition to stage '{target_stage.name}' executed successfully.",
            case_id=case.id,
            previous_stage_id=previous_stage_id,
            current_stage_id=case.current_stage_id,
            case_status=case.status,
            transition_id=validation.transition_id,
            history_id=history.id,
            violations=[],
        )
