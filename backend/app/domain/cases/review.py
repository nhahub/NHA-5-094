from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.models import AgentDefinition, AgentExecution
from app.domain.approvals.models import Approval
from app.domain.approvals.schemas import ApprovalRead
from app.domain.cases.models import Case
from app.domain.cases.schemas import CaseRead
from app.domain.documents.models import (
    Document,
    DocumentProcessingRun,
    DocumentVersion,
    Evidence,
    EvidenceItem,
    ExtractedField,
)
from app.domain.tasks.models import Task, TaskReviewComment
from app.domain.tasks.schemas import TaskRead
from app.domain.verifications.models import VerificationExecution, VerificationResult


class CaseReviewService:
    """Build the bounded, read-only evidence packet needed for human review."""

    @staticmethod
    async def get_bundle(
        db: AsyncSession, case_id: uuid.UUID, organization_id: uuid.UUID
    ) -> dict[str, Any] | None:
        case = (await db.execute(select(Case).where(
            Case.id == case_id, Case.organization_id == organization_id
        ))).scalars().first()
        if case is None:
            return None

        tasks = list((await db.execute(
            select(Task).where(Task.case_id == case.id).order_by(Task.created_at.desc())
        )).scalars().all())
        task_ids = [task.id for task in tasks]
        comments = list((await db.execute(
            select(TaskReviewComment).where(TaskReviewComment.task_id.in_(task_ids))
            .order_by(TaskReviewComment.created_at.asc())
        )).scalars().all()) if task_ids else []
        comments_by_task: dict[uuid.UUID, list[dict[str, Any]]] = {}
        for comment in comments:
            comments_by_task.setdefault(comment.task_id, []).append({
                "id": str(comment.id),
                "author_id": str(comment.author_id),
                "comment": comment.comment,
                "evidence_ids": comment.evidence_ids or [],
                "created_at": comment.created_at,
            })

        documents = list((await db.execute(
            select(Document).where(Document.case_id == case.id).order_by(Document.created_at.desc())
        )).scalars().all())
        document_ids = [document.id for document in documents]
        versions = list((await db.execute(
            select(DocumentVersion).where(DocumentVersion.document_id.in_(document_ids))
            .order_by(DocumentVersion.version_number.desc())
        )).scalars().all()) if document_ids else []
        version_ids = [version.id for version in versions]
        fields = list((await db.execute(
            select(ExtractedField).where(ExtractedField.document_version_id.in_(version_ids))
        )).scalars().all()) if version_ids else []
        runs = list((await db.execute(
            select(DocumentProcessingRun).where(DocumentProcessingRun.document_version_id.in_(version_ids))
            .order_by(DocumentProcessingRun.run_number.desc())
        )).scalars().all()) if version_ids else []
        fields_by_version: dict[uuid.UUID, list[dict[str, Any]]] = {}
        for field in fields:
            fields_by_version.setdefault(field.document_version_id, []).append({
                "id": str(field.id), "field_name": field.field_name,
                "field_value": field.field_value, "confidence": field.confidence,
                "page_number": field.page_number, "bounding_box": field.bounding_box,
                "source_text": field.source_text, "source_locator": field.source_locator,
                "extraction_method": field.extraction_method,
                "processing_run_id": str(field.processing_run_id) if field.processing_run_id else None,
            })
        runs_by_version: dict[uuid.UUID, list[dict[str, Any]]] = {}
        for run in runs:
            runs_by_version.setdefault(run.document_version_id, []).append({
                "id": str(run.id), "run_number": run.run_number, "status": run.status,
                "predicted_document_type": run.predicted_document_type,
                "classification_confidence": run.classification_confidence,
                "review_required": run.review_required,
                "review_reasons": run.review_reasons,
                "safe_error": run.safe_error,
                "completed_at": run.completed_at,
            })
        discrepancies = [
            {"kind": "DOCUMENT_REVIEW", "document_version_id": str(run.document_version_id),
             "processing_run_id": str(run.id), "reasons": run.review_reasons or []}
            for run in runs if run.review_required
        ]
        versions_by_document: dict[uuid.UUID, list[dict[str, Any]]] = {}
        for version in versions:
            versions_by_document.setdefault(version.document_id, []).append({
                "id": str(version.id), "version_number": version.version_number,
                "mime_type": version.mime_type, "file_size": version.file_size,
                "file_hash": version.file_hash, "uploaded_by": str(version.uploaded_by) if version.uploaded_by else None,
                "extracted_fields": fields_by_version.get(version.id, []),
                "processing_runs": runs_by_version.get(version.id, []),
            })

        execution_rows = list((await db.execute(
            select(VerificationExecution).where(VerificationExecution.case_id == case.id)
            .order_by(VerificationExecution.started_at.desc())
        )).scalars().all())
        execution_ids = [execution.id for execution in execution_rows]
        verification_results = list((await db.execute(
            select(VerificationResult).where(VerificationResult.verification_execution_id.in_(execution_ids))
        )).scalars().all()) if execution_ids else []
        results_by_execution: dict[uuid.UUID, list[dict[str, Any]]] = {}
        for result in verification_results:
            results_by_execution.setdefault(result.verification_execution_id, []).append({
                "id": str(result.id), "result": result.result, "summary": result.summary,
                "confidence": result.confidence, "reason": result.reason,
            })
            if result.result.upper() in {"FAIL", "REVIEW", "INCONCLUSIVE"}:
                discrepancies.append({
                    "kind": "VERIFICATION_" + result.result.upper(),
                    "verification_execution_id": str(result.verification_execution_id),
                    "result_id": str(result.id), "summary": result.summary,
                    "reason": result.reason,
                })

        evidence_rows = list((await db.execute(
            select(Evidence).where(Evidence.case_id == case.id).order_by(Evidence.created_at.desc())
        )).scalars().all())
        evidence_ids = [item.id for item in evidence_rows]
        evidence_items = list((await db.execute(
            select(EvidenceItem).where(EvidenceItem.evidence_id.in_(evidence_ids))
        )).scalars().all()) if evidence_ids else []
        evidence_by_id: dict[uuid.UUID, list[dict[str, Any]]] = {}
        for item in evidence_items:
            evidence_by_id.setdefault(item.evidence_id, []).append({
                "id": str(item.id), "source_type": item.source_type,
                "source_id": str(item.source_id) if item.source_id else None,
                "field_reference": item.field_reference,
                "value_snapshot": item.value_snapshot, "page_number": item.page_number,
                "location": item.location,
            })

        approvals = list((await db.execute(
            select(Approval).where(Approval.case_id == case.id).order_by(Approval.created_at.desc())
        )).scalars().all())
        agent_rows = list((await db.execute(
            select(AgentExecution, AgentDefinition.agent_type)
            .join(AgentDefinition, AgentDefinition.id == AgentExecution.agent_id)
            .where(AgentExecution.case_id == case.id)
            .order_by(AgentExecution.started_at.desc()).limit(20)
        )).all())
        recommendations = []
        visible_fields = {
            "recommendation", "interpretation", "summary", "review_required",
            "review_reasons", "proposed_actions", "actions", "status", "reason",
        }
        for execution, agent_type in agent_rows:
            output = execution.output if isinstance(execution.output, dict) else {}
            recommendation = {key: output[key] for key in visible_fields if key in output}
            if recommendation:
                recommendations.append({
                    "execution_id": str(execution.id), "agent_type": agent_type,
                    "status": execution.status, "recommendation": recommendation,
                    "completed_at": execution.completed_at,
                })

        return {
            "case": CaseRead.model_validate(case).model_dump(mode="json"),
            "review_tasks": [
                {**TaskRead.model_validate(task).model_dump(mode="json"),
                 "comments": comments_by_task.get(task.id, [])}
                for task in tasks
            ],
            "approvals": [ApprovalRead.model_validate(approval).model_dump(mode="json") for approval in approvals],
            "documents": [
                {"id": str(document.id), "name": document.name,
                 "document_type": document.document_type, "status": document.status,
                 "versions": versions_by_document.get(document.id, [])}
                for document in documents
            ],
            "verifications": [
                {"id": str(execution.id), "verification_id": str(execution.verification_id),
                 "status": execution.status, "started_at": execution.started_at,
                 "completed_at": execution.completed_at, "results": results_by_execution.get(execution.id, [])}
                for execution in execution_rows
            ],
            "evidence": [
                {"id": str(item.id), "evidence_type": item.evidence_type,
                 "description": item.description,
                 "verification_execution_id": str(item.verification_execution_id) if item.verification_execution_id else None,
                 "items": evidence_by_id.get(item.id, [])}
                for item in evidence_rows
            ],
            "discrepancies": discrepancies,
            "recommendations": recommendations,
        }
