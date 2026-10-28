"""Document Agent — Phase 10.

Responsible for document understanding, classification, extraction, schema validation,
grounding/citations, and proposing structured outcomes without mutating authoritative
business or workflow state directly.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.models import AgentDefinition, AgentExecution
from app.agents.schemas import AgentProposal, DocumentAgentResult
from app.domain.cases.models import Case
from app.domain.documents.models import (
    Document,
    DocumentProcessingRun,
    DocumentRunStatus,
    DocumentVersion,
    ExtractedField,
)
from app.domain.documents.processing import DocumentProcessingService
from app.domain.documents.intelligence import JsonModelAdapter, get_agent_json_model_adapter
from app.infrastructure.storage import StorageBackend, get_storage_backend
from app.security.models import User
from app.tools.schemas import ToolExecutionRequest

logger = logging.getLogger(__name__)


class DocumentAgentError(Exception):
    """Raised when document agent execution fails."""
    pass


class DocumentAgent:
    """Specialized Agent for document understanding, classification, and structured extraction."""

    AGENT_TYPE = "DOCUMENT"
    AGENT_NAME = "DocumentAgent"

    def __init__(
        self,
        model_adapter: Optional[JsonModelAdapter] = None,
        confidence_threshold: float = 0.75,
    ) -> None:
        self.model_adapter = model_adapter or get_agent_json_model_adapter(self.AGENT_TYPE)
        self.confidence_threshold = confidence_threshold

    async def _get_or_create_agent_definition(
        self, db: AsyncSession, organization_id: uuid.UUID
    ) -> AgentDefinition:
        """Find or create the system AgentDefinition for DocumentAgent."""
        stmt = select(AgentDefinition).where(
            AgentDefinition.agent_type == self.AGENT_TYPE,
            or_(
                AgentDefinition.organization_id == organization_id,
                AgentDefinition.organization_id.is_(None),
            ),
        )
        agent_def = (await db.execute(stmt)).scalars().first()
        if agent_def is None:
            agent_def = AgentDefinition(
                organization_id=organization_id,
                name=self.AGENT_NAME,
                agent_type=self.AGENT_TYPE,
                description="Specialized agent for document understanding, classification, and extraction.",
                enabled=True,
            )
            db.add(agent_def)
            await db.commit()
            await db.refresh(agent_def)
        return agent_def

    async def process_document(
        self,
        db: AsyncSession,
        actor: User,
        case_id: uuid.UUID,
        document_id: uuid.UUID,
        document_version_id: Optional[uuid.UUID] = None,
        storage: Optional[StorageBackend] = None,
        user_guidance: Optional[str] = None,
        parent_execution_id: Optional[uuid.UUID] = None,
    ) -> DocumentAgentResult:
        """Execute the Document Agent pipeline on a case document."""
        from app.tools.service import ToolGatewayService

        started_at = datetime.now(timezone.utc)
        input_context = {
            "case_id": str(case_id),
            "document_id": str(document_id),
            "document_version_id": str(document_version_id) if document_version_id else None,
            "user_guidance": user_guidance,
            "agent_type": self.AGENT_TYPE,
            "parent_execution_id": str(parent_execution_id) if parent_execution_id else None,
        }

        # 1. Verify case and tenant scope
        case_stmt = select(Case).where(
            Case.id == case_id,
            Case.organization_id == actor.organization_id,
        )
        case = (await db.execute(case_stmt)).scalars().first()
        if case is None:
            raise DocumentAgentError(f"Case {case_id} not found or outside actor's organization scope.")

        # 2. Verify document belongs to case
        doc_stmt = select(Document).where(
            Document.id == document_id,
            Document.case_id == case_id,
        )
        doc = (await db.execute(doc_stmt)).scalars().first()
        if doc is None:
            raise DocumentAgentError(f"Document {document_id} not found for case {case_id}.")

        # 3. Resolve target version
        if document_version_id:
            ver_stmt = select(DocumentVersion).where(
                DocumentVersion.id == document_version_id,
                DocumentVersion.document_id == document_id,
            )
            version = (await db.execute(ver_stmt)).scalars().first()
            if version is None:
                raise DocumentAgentError(f"DocumentVersion {document_version_id} not found.")
        else:
            ver_stmt = (
                select(DocumentVersion)
                .where(DocumentVersion.document_id == document_id)
                .order_by(DocumentVersion.version_number.desc())
            )
            version = (await db.execute(ver_stmt)).scalars().first()
            if version is None:
                raise DocumentAgentError(f"No document version found for document {document_id}.")

        # Resolve storage backend
        if storage is None:
            storage = get_storage_backend()

        # Resolve agent definition for execution logging
        agent_def = await self._get_or_create_agent_definition(db, actor.organization_id)
        agent_definition_id = agent_def.id

        try:
            # 4. Run document processing & extraction pipeline
            run_record = await DocumentProcessingService.process_version(
                db=db,
                organization_id=actor.organization_id,
                document_id=doc.id,
                version_id=version.id,
                storage=storage,
                adapter=self.model_adapter,
            )
            # Downstream event handling can roll back the shared session. Explicitly
            # reload these scalar records before using them after that orchestration.
            await db.refresh(doc)
            await db.refresh(version)
            if isinstance(run_record, DocumentProcessingRun):
                await db.refresh(run_record)
            if getattr(run_record, "status", None) == DocumentRunStatus.FAILED.value:
                raise DocumentAgentError("Document processing failed safely.")

            # 5. Query persisted Extracted fields
            fields_stmt = select(ExtractedField).where(
                ExtractedField.processing_run_id == run_record.id
            )
            extracted_fields = (await db.execute(fields_stmt)).scalars().all()

            extracted_dict: Dict[str, Any] = {}
            for field in extracted_fields:
                val = field.field_value
                if isinstance(val, dict) and "value" in val:
                    val_content = val["value"]
                else:
                    val_content = val
                extracted_dict[field.field_name] = {
                    "value": val_content,
                    "confidence": float(field.confidence) if field.confidence is not None else 1.0,
                    "page_number": field.page_number,
                    "bounding_box": field.bounding_box,
                    "source_text": field.source_text,
                    "source_locator": field.source_locator,
                }

            # 6. Check required documents via Tool Gateway (optional policy context)
            required_docs_check: Optional[Dict[str, Any]] = None
            try:
                tool_res = await ToolGatewayService.execute_tool(
                    db=db,
                    request=ToolExecutionRequest(
                        tool_name="check_required_documents",
                        case_id=case_id,
                        arguments={},
                    ),
                    actor=actor,
                    agent_id=agent_def.id,
                )
                if tool_res.status == "SUCCESS":
                    required_docs_check = tool_res.output
            except Exception as tool_err:
                logger.debug("Tool check_required_documents failed or was disabled: %s", tool_err)

            # 7. Formulate proposals
            proposals: List[AgentProposal] = []
            review_required = bool(run_record.review_required)
            review_reasons = list(run_record.review_reasons or [])
            classification_confidence = (
                float(run_record.classification_confidence)
                if run_record.classification_confidence is not None
                else None
            )

            if review_required:
                reasons_str = "; ".join(review_reasons)
                proposals.append(
                    AgentProposal(
                        agent_name=self.AGENT_NAME,
                        case_id=case_id,
                        proposed_action="REQUEST_HUMAN_REVIEW",
                        confidence=(
                            classification_confidence
                            if classification_confidence is not None
                            else 0.5
                        ),
                        rationale=f"Document '{doc.name or doc.document_type}' (v{version.version_number}) flagged for review: {reasons_str}",
                        evidence_references=[
                            f"Document:{doc.id}:v{version.version_number}",
                            f"ProcessingRun:{run_record.id}",
                        ],
                        payload={
                            "document_id": str(doc.id),
                            "document_version_id": str(version.id),
                            "predicted_type": run_record.predicted_document_type,
                            "review_task_id": str(run_record.review_task_id) if run_record.review_task_id else None,
                            "review_reasons": review_reasons,
                        },
                    )
                )
            else:
                proposals.append(
                    AgentProposal(
                        agent_name=self.AGENT_NAME,
                        case_id=case_id,
                        proposed_action="EXTRACTED_FIELDS_VALIDATED",
                        confidence=(
                            classification_confidence
                            if classification_confidence is not None
                            else 1.0
                        ),
                        rationale=f"Document '{doc.name or doc.document_type}' successfully classified as '{run_record.predicted_document_type}' with {len(extracted_dict)} validated fields.",
                        evidence_references=[
                            f"Document:{doc.id}:v{version.version_number}",
                            f"ProcessingRun:{run_record.id}",
                        ] + [f"Field:{k}" for k in list(extracted_dict.keys())[:5]],
                        payload={
                            "document_id": str(doc.id),
                            "document_version_id": str(version.id),
                            "predicted_type": run_record.predicted_document_type,
                            "extracted_field_count": len(extracted_dict),
                            "required_docs_status": required_docs_check,
                        },
                    )
                )

            result = DocumentAgentResult(
                case_id=case_id,
                document_id=doc.id,
                document_version_id=version.id,
                predicted_document_type=run_record.predicted_document_type or "unknown",
                classification_confidence=(
                    classification_confidence
                    if classification_confidence is not None
                    else 0.0
                ),
                extracted_fields=extracted_dict,
                review_required=review_required,
                review_reasons=review_reasons,
                review_task_id=run_record.review_task_id,
                proposals=proposals,
            )

            # 8. Record AgentExecution trace
            completed_at = datetime.now(timezone.utc)
            execution = AgentExecution(
                case_id=case_id,
                agent_id=agent_definition_id,
                parent_execution_id=parent_execution_id,
                input_context=input_context,
                output=result.model_dump(mode="json"),
                status="SUCCESS",
                started_at=started_at,
                completed_at=completed_at,
                token_usage={"model": str(getattr(self.model_adapter, "model", "default"))},
            )
            db.add(execution)
            await db.commit()
            await db.refresh(execution)
            result.execution_id = execution.id

            logger.info(
                "DocumentAgent completed for case=%s doc=%s (review_required=%s, execution_id=%s)",
                case_id, doc.id, review_required, execution.id
            )
            return result

        except Exception as exc:
            logger.error("DocumentAgent failed for case=%s doc=%s: %s", case_id, document_id, exc)
            completed_at = datetime.now(timezone.utc)
            execution = AgentExecution(
                case_id=case_id,
                agent_id=agent_definition_id,
                parent_execution_id=parent_execution_id,
                input_context=input_context,
                output={"error": str(exc)},
                status="FAILED",
                started_at=started_at,
                completed_at=completed_at,
                error=str(exc),
            )
            db.add(execution)
            await db.commit()
            raise DocumentAgentError(f"Document agent failed: {exc}") from exc
