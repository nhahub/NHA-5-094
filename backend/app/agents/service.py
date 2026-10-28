"""Agent orchestration and dispatch service — Phases 10, 11, and 12."""

from __future__ import annotations

import logging
import uuid
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.agents.document_agent import DocumentAgent
from app.agents.schemas import (
    AgentProposal,
    AgentRunRequest,
    AgentRunResponse,
    DocumentAgentResult,
    DocumentAgentRunRequest,
)
from app.agents.verification_agent import VerificationAgent
from app.agents.workflow_agent import WorkflowAgent
from app.agents.supervisor_agent import SupervisorAgent
from app.agents.models import AgentDefinition, AgentExecution
from app.domain.documents.intelligence import JsonModelAdapter
from app.infrastructure.storage import StorageBackend
from app.security.models import User

logger = logging.getLogger(__name__)


class AgentOrchestratorService:
    """Service coordinating specialized AI agents."""

    @staticmethod
    async def process_document(
        db: AsyncSession,
        actor: User,
        request: DocumentAgentRunRequest,
        storage: Optional[StorageBackend] = None,
        model_adapter: Optional[JsonModelAdapter] = None,
        parent_execution_id: Optional[uuid.UUID] = None,
    ) -> DocumentAgentResult:
        """Directly invoke the Document Agent on a case document."""
        agent = DocumentAgent(model_adapter=model_adapter)
        return await agent.process_document(
            db=db,
            actor=actor,
            case_id=request.case_id,
            document_id=request.document_id,
            document_version_id=request.document_version_id,
            storage=storage,
            user_guidance=request.user_guidance,
            parent_execution_id=parent_execution_id,
        )

    @staticmethod
    async def run_agent(
        db: AsyncSession,
        actor: User,
        request: AgentRunRequest,
        storage: Optional[StorageBackend] = None,
        model_adapter: Optional[JsonModelAdapter] = None,
        parent_execution_id: Optional[uuid.UUID] = None,
    ) -> AgentRunResponse:
        """Generic agent entrypoint dispatching to specialized agents."""
        agent_type_upper = request.agent_type.strip().upper()

        if parent_execution_id is not None:
            if agent_type_upper == "SUPERVISOR":
                raise ValueError("Recursive Supervisor delegation is not allowed.")
            await AgentOrchestratorService._validate_parent_execution(
                db=db,
                actor=actor,
                case_id=request.case_id,
                agent_type=agent_type_upper,
                parent_execution_id=parent_execution_id,
            )

        if agent_type_upper == "SUPERVISOR":
            return await SupervisorAgent(model_adapter=model_adapter).run(
                db=db,
                actor=actor,
                request=request,
                storage=storage,
            )

        if agent_type_upper == "DOCUMENT":
            if not request.document_id:
                raise ValueError(
                    "document_id is required when agent_type is 'DOCUMENT'."
                )

            doc_result = await AgentOrchestratorService.process_document(
                db=db,
                actor=actor,
                request=DocumentAgentRunRequest(
                    case_id=request.case_id,
                    document_id=request.document_id,
                    document_version_id=request.document_version_id,
                    user_guidance=request.user_prompt,
                ),
                storage=storage,
                model_adapter=model_adapter,
                parent_execution_id=parent_execution_id,
            )

            summary = (
                f"DocumentAgent processed document (classified as '{doc_result.predicted_document_type}', "
                f"review_required={doc_result.review_required})."
            )
            return AgentRunResponse(
                case_id=request.case_id,
                agent_type="DOCUMENT",
                success=True,
                summary=summary,
                proposals=doc_result.proposals,
                result_data=doc_result.model_dump(mode="json"),
                execution_id=doc_result.execution_id,
            )

        # Phase 11 adds the Verification Agent; Phase 12 adds the Workflow Agent.
        proposals: List[AgentProposal] = []
        if agent_type_upper == "VERIFICATION":
            result = await VerificationAgent(model_adapter=model_adapter).run(
                db=db,
                actor=actor,
                case_id=request.case_id,
                user_prompt=request.user_prompt,
                parent_execution_id=parent_execution_id,
            )
            proposals = [
                AgentProposal.model_validate(item) for item in result["proposals"]
            ]
            return AgentRunResponse(
                case_id=request.case_id,
                agent_type="VERIFICATION",
                success=True,
                summary=result["summary"],
                proposals=proposals,
                result_data=result,
                execution_id=uuid.UUID(result["execution_id"]),
            )
        elif agent_type_upper == "WORKFLOW":
            result = await WorkflowAgent(model_adapter=model_adapter).run(
                db=db,
                actor=actor,
                case_id=request.case_id,
                user_prompt=request.user_prompt,
                parent_execution_id=parent_execution_id,
            )
            proposals = [
                AgentProposal.model_validate(item) for item in result["proposals"]
            ]
            proposal_state = result.get("proposal_state", "PROPOSED")
            summary = result.get("summary", f"WorkflowAgent {proposal_state.lower()}.")
            return AgentRunResponse(
                case_id=request.case_id,
                agent_type="WORKFLOW",
                success=True,
                summary=summary,
                proposals=proposals,
                result_data=result,
                execution_id=uuid.UUID(result["execution_id"]),
            )
        else:
            raise ValueError(
                f"Unknown or unsupported agent_type: '{request.agent_type}'."
            )

    @staticmethod
    async def _validate_parent_execution(
        *,
        db: AsyncSession,
        actor: User,
        case_id: uuid.UUID,
        agent_type: str,
        parent_execution_id: uuid.UUID,
    ) -> None:
        """Allow only one-level child calls from a Supervisor in the same tenant/case."""
        if agent_type not in {"DOCUMENT", "VERIFICATION", "WORKFLOW"}:
            raise ValueError("Unsupported child agent type.")
        parent = (
            await db.execute(
                select(AgentExecution)
                .join(AgentDefinition, AgentDefinition.id == AgentExecution.agent_id)
                .where(
                    AgentExecution.id == parent_execution_id,
                    AgentExecution.case_id == case_id,
                    AgentExecution.parent_execution_id.is_(None),
                    AgentExecution.status == "RUNNING",
                    AgentDefinition.agent_type == "SUPERVISOR",
                )
            )
        ).scalars().first()
        if parent is None:
            raise ValueError("Parent execution is invalid for this case or agent.")

        from app.domain.cases.models import Case

        case = (
            await db.execute(
                select(Case).where(
                    Case.id == case_id,
                    Case.organization_id == actor.organization_id,
                )
            )
        ).scalars().first()
        if case is None:
            raise ValueError("Case not found or outside actor's organization scope.")
