"""Tests for Document Agent (Phase 10)."""
import uuid
import pymupdf
import pytest
from types import SimpleNamespace
from httpx import AsyncClient
from sqlalchemy import select

from app.agents.document_agent import DocumentAgent, DocumentAgentError
from app.agents.models import AgentExecution
from app.agents.schemas import DocumentAgentRunRequest, AgentRunRequest
from app.agents.service import AgentOrchestratorService
from app.core.config import settings
from app.domain.cases.models import Case
from app.domain.cases.schemas import CaseCreate
from app.domain.cases.service import CaseService
from app.domain.documents.models import (
    Document,
    DocumentProcessingRun,
    DocumentVersion,
    ExtractedField,
)
from app.domain.documents.processing import DocumentProcessingService
from app.domain.documents.service import DocumentService
from app.domain.knowledge.schemas import KnowledgeSourceCreate
from app.domain.knowledge.service import KnowledgeService
from app.domain.processes.schemas import ProcessCreate
from app.domain.processes.service import ProcessService
from app.domain.tasks.models import Task
from app.domain.workflows.schemas import WorkflowStageCreate
from app.infrastructure.llm.embedding import ErrorEmbeddingAdapter, FakeEmbeddingAdapter
from app.infrastructure.storage import LocalFileStorage
from app.security.models import Organization, User, Role, Permission, RolePermission
from app.tools.schemas import ToolExecutionRequest
from app.tools.service import ToolGatewayService, ToolPolicyError


class CleanInvoiceModel:
    """Simulates high confidence extraction with valid citations."""

    async def generate_json(self, *, system_prompt, user_prompt, response_schema):
        if "class_id" in response_schema.get("properties", {}):
            return {"class_id": "invoice", "confidence": 0.99, "rationale": "Clear invoice header"}, "mock-v1"
        return {
            "fields": {
                "invoice_number": {
                    "value": "INV-2026-001",
                    "confidence": 0.98,
                    "citations": [{"block_index": 0, "quote": "Invoice INV-2026-001"}],
                },
                "supplier": {
                    "value": "Acme Global Trading",
                    "confidence": 0.95,
                    "citations": [{"block_index": 1, "quote": "Supplier: Acme Global Trading"}],
                },
                "invoice_date": {
                    "value": "2026-10-01",
                    "confidence": 0.96,
                    "citations": [{"block_index": 2, "quote": "Date: 2026-10-01"}],
                },
                "currency": {
                    "value": "USD",
                    "confidence": 0.99,
                    "citations": [{"block_index": 3, "quote": "Currency: USD"}],
                },
                "items": {"value": [], "confidence": 0.92, "citations": [{"block_index": 4, "quote": "Total: 5000.00"}]},
                "total": {
                    "value": 5000.00,
                    "confidence": 0.95,
                    "citations": [{"block_index": 4, "quote": "Total: 5000.00"}],
                },
            }
        }, "mock-v1"


class LowConfidenceInvoiceModel:
    """Simulates low confidence on total field, triggering human review."""

    async def generate_json(self, *, system_prompt, user_prompt, response_schema):
        if "class_id" in response_schema.get("properties", {}):
            return {"class_id": "invoice", "confidence": 0.90, "rationale": "Header matches"}, "mock-v1"
        return {
            "fields": {
                "invoice_number": {
                    "value": "INV-2026-002",
                    "confidence": 0.95,
                    "citations": [{"block_index": 0, "quote": "Invoice INV-2026-001"}],
                },
                "supplier": {
                    "value": "Acme Global Trading",
                    "confidence": 0.95,
                    "citations": [{"block_index": 1, "quote": "Supplier: Acme Global Trading"}],
                },
                "invoice_date": {
                    "value": "2026-10-01",
                    "confidence": 0.95,
                    "citations": [{"block_index": 2, "quote": "Date: 2026-10-01"}],
                },
                "currency": {
                    "value": "USD",
                    "confidence": 0.95,
                    "citations": [{"block_index": 3, "quote": "Currency: USD"}],
                },
                "items": {"value": [], "confidence": 0.90, "citations": [{"block_index": 4, "quote": "Total: 5000.00"}]},
                "total": {
                    "value": 5000.00,
                    "confidence": 0.40,  # Below threshold
                    "citations": [{"block_index": 4, "quote": "Total: 5000.00"}],
                },
            }
        }, "mock-v1"


def _create_sample_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    lines = [
        "Invoice INV-2026-001",
        "Supplier: Acme Global Trading",
        "Date: 2026-10-01",
        "Currency: USD",
        "Total: 5000.00",
    ]
    for idx, text in enumerate(lines):
        page.insert_text((72, 72 + idx * 24), text)
    content = doc.tobytes()
    doc.close()
    return content


async def _setup_case_with_document(db_session, test_org, test_user, storage):
    # Setup permissions for the user role
    role = Role(organization_id=test_org.id, name="ADMIN")
    db_session.add(role)
    await db_session.flush()

    for p_code in [
        "tool.search_knowledge",
        "tool.check_required_documents",
        "tool.request_approval",
        "tool.create_task",
        "tool.calculate_order_total",
    ]:
        perm = Permission(code=p_code)
        db_session.add(perm)
        await db_session.flush()
        db_session.add(RolePermission(role_id=role.id, permission_id=perm.id))

    process = await ProcessService.create_process(
        db=db_session,
        organization_id=test_org.id,
        process_in=ProcessCreate(name="Import Operations", code=f"IMP_{uuid.uuid4().hex[:6]}"),
    )
    process_version = (await ProcessService.get_versions_by_process_id(db_session, process.id))[0]
    stage = await ProcessService.add_stage_to_version(
        db=db_session,
        version_id=process_version.id,
        stage_in=WorkflowStageCreate(
            process_version_id=process_version.id,
            name="Document Intake",
            code="INTAKE",
            stage_order=1,
            is_initial=True,
        ),
    )
    await ProcessService.publish_version(db_session, process_version.id)

    case = await CaseService.create_case(
        db=db_session,
        organization_id=test_org.id,
        created_by_user_id=test_user.id,
        case_in=CaseCreate(
            process_version_id=process_version.id,
            title="Import Shipment 2026",
            initial_data={},
        ),
    )

    pdf_bytes = _create_sample_pdf()
    document, _ = await DocumentService.upload_document(
        db=db_session,
        organization_id=test_org.id,
        case_id=case.id,
        uploaded_by=test_user.id,
        document_type="invoice",
        filename="commercial_invoice.pdf",
        declared_content_type="application/pdf",
        content=pdf_bytes,
        storage=storage,
    )
    version = document.versions[0]

    return case, document, version, process_version, stage


@pytest.mark.asyncio
async def test_document_agent_clean_extraction(db_session, test_org, test_user, tmp_path):
    storage = LocalFileStorage(root=str(tmp_path))
    case, doc, version, p_ver, stage = await _setup_case_with_document(
        db_session, test_org, test_user, storage
    )

    agent = DocumentAgent(model_adapter=CleanInvoiceModel())
    result = await agent.process_document(
        db=db_session,
        actor=test_user,
        case_id=case.id,
        document_id=doc.id,
        document_version_id=version.id,
        storage=storage,
    )

    assert result.predicted_document_type == "invoice"
    assert result.review_required is False
    assert len(result.extracted_fields) >= 4
    assert result.extracted_fields["invoice_number"]["value"] == "INV-2026-001"
    assert result.extracted_fields["total"]["value"] == 5000.00
    assert len(result.proposals) == 1
    assert result.proposals[0].proposed_action == "EXTRACTED_FIELDS_VALIDATED"
    assert result.execution_id is not None

    # Check AgentExecution trace in DB
    exec_stmt = select(AgentExecution).where(AgentExecution.id == result.execution_id)
    execution = (await db_session.execute(exec_stmt)).scalars().first()
    assert execution is not None
    assert execution.status == "SUCCESS"
    assert execution.case_id == case.id

    # Non-mutation guarantee: Case stage and status are unchanged
    case_db = (await db_session.execute(select(Case).where(Case.id == case.id))).scalars().first()
    assert case_db.current_stage_id == stage.id
    assert case_db.status == "OPEN"


@pytest.mark.asyncio
async def test_document_agent_refreshes_records_after_orchestration_rollback(
    db_session, test_org, test_user, tmp_path, monkeypatch
):
    storage = LocalFileStorage(root=str(tmp_path))
    case, doc, version, _p_ver, _stage = await _setup_case_with_document(
        db_session, test_org, test_user, storage
    )

    async def expire_after_dispatch(db, *_args, **_kwargs):
        # Downstream orchestration can expire the shared document records after a
        # rollback. Reproduce just those affected identities without touching the
        # broader fixture session.
        for instance in tuple(db.sync_session.identity_map.values()):
            if isinstance(instance, (Document, DocumentVersion, DocumentProcessingRun)):
                db.sync_session.expire(instance)

    monkeypatch.setattr(
        "app.domain.documents.processing.EventService.dispatch_persisted_event",
        expire_after_dispatch,
    )
    result = await DocumentAgent(model_adapter=CleanInvoiceModel()).process_document(
        db=db_session,
        actor=test_user,
        case_id=case.id,
        document_id=doc.id,
        document_version_id=version.id,
        storage=storage,
    )

    assert result.predicted_document_type == "invoice"
    assert result.extracted_fields["invoice_number"]["value"] == "INV-2026-001"
    assert result.execution_id is not None


@pytest.mark.asyncio
async def test_document_agent_low_confidence_triggers_review_task(db_session, test_org, test_user, tmp_path):
    storage = LocalFileStorage(root=str(tmp_path))
    case, doc, version, p_ver, stage = await _setup_case_with_document(
        db_session, test_org, test_user, storage
    )

    agent = DocumentAgent(model_adapter=LowConfidenceInvoiceModel())
    result = await agent.process_document(
        db=db_session,
        actor=test_user,
        case_id=case.id,
        document_id=doc.id,
        document_version_id=version.id,
        storage=storage,
    )

    assert result.review_required is True
    assert len(result.review_reasons) >= 1
    assert len(result.proposals) == 1
    assert result.proposals[0].proposed_action == "REQUEST_HUMAN_REVIEW"
    assert result.review_task_id is not None

    # Verify Task exists in DB
    task_stmt = select(Task).where(Task.id == result.review_task_id)
    task = (await db_session.execute(task_stmt)).scalars().first()
    assert task is not None
    assert task.task_type == "DOCUMENT_REVIEW"
    assert task.case_id == case.id


@pytest.mark.asyncio
async def test_search_knowledge_tool_gateway_integration(
    db_session, test_org, test_user, tmp_path, monkeypatch
):
    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER", "fake")
    storage = LocalFileStorage(root=str(tmp_path))
    case, doc, version, p_ver, stage = await _setup_case_with_document(
        db_session, test_org, test_user, storage
    )

    # Ingest a knowledge doc
    source = await KnowledgeService.create_source(
        db=db_session,
        org_id=test_org.id,
        source_in=KnowledgeSourceCreate(name="Customs Rules", source_type="REGULATORY"),
    )
    k_doc = await KnowledgeService.upload_document(
        db=db_session,
        source_id=source.id,
        org_id=test_org.id,
        file_bytes=b"Invoices over $2500 require declared export value certificates.",
        filename="customs.txt",
        title="Customs Declaration Policy",
        document_version="1.0",
        storage=storage,
    )
    await KnowledgeService.ingest_document(
        db=db_session,
        doc_id=k_doc.id,
        org_id=test_org.id,
        storage=storage,
        embedding_adapter=FakeEmbeddingAdapter(),
    )

    # Enable search_knowledge in process version tool_gateway configuration
    p_ver.configuration = {
        "tool_gateway": {
            "allowed_tools": {
                "search_knowledge": {"enabled": True, "allowed_agents": ["DOCUMENT", "SUPERVISOR"]},
                "check_required_documents": {"enabled": True, "allowed_agents": ["DOCUMENT"]},
            }
        }
    }
    db_session.add(p_ver)
    await db_session.commit()

    # The Tool Gateway permits a Document Agent identity to use scoped semantic search.
    agent = DocumentAgent(model_adapter=CleanInvoiceModel())
    agent_def = await agent._get_or_create_agent_definition(db_session, test_org.id)
    tool_res = await ToolGatewayService.execute_tool(
        db=db_session,
        request=ToolExecutionRequest(
            tool_name="search_knowledge",
            case_id=case.id,
            arguments={"query": "export value certificates", "top_k": 2},
        ),
        actor=test_user,
        agent_id=agent_def.id,
    )
    assert tool_res.error is None
    assert tool_res.status == "SUCCESS"
    assert "results" in tool_res.output
    assert len(tool_res.output["results"]) >= 1


@pytest.mark.asyncio
async def test_search_gateway_does_not_fake_results_when_embedding_fails(
    db_session, test_org, test_user, tmp_path, monkeypatch
):
    storage = LocalFileStorage(root=str(tmp_path))
    case, _doc, _version, process_version, _stage = await _setup_case_with_document(
        db_session, test_org, test_user, storage
    )
    process_version.configuration = {
        "tool_gateway": {
            "allowed_tools": {
                "search_knowledge": {"enabled": True, "allowed_agents": ["DOCUMENT"]},
            }
        }
    }
    db_session.add(process_version)
    await db_session.commit()

    monkeypatch.setattr(settings, "APP_ENV", "development")
    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER", "huggingface_api")
    monkeypatch.setattr(
        "app.infrastructure.llm.embedding.get_embedding_adapter",
        lambda: ErrorEmbeddingAdapter(),
    )
    agent_def = await DocumentAgent(model_adapter=CleanInvoiceModel())._get_or_create_agent_definition(
        db_session, test_org.id
    )
    result = await ToolGatewayService.execute_tool(
        db_session,
        ToolExecutionRequest(
            tool_name="search_knowledge",
            case_id=case.id,
            arguments={"query": "shipping policy"},
        ),
        actor=test_user,
        agent_id=agent_def.id,
    )

    assert result.success is False
    assert result.status == "FAILED"
    assert result.output is None
    assert result.error == "Tool execution failed (RuntimeError)."


@pytest.mark.asyncio
async def test_document_agent_records_failed_execution(
    db_session, test_org, test_user, tmp_path, monkeypatch
):
    storage = LocalFileStorage(root=str(tmp_path))
    case, doc, version, _process_version, _stage = await _setup_case_with_document(
        db_session, test_org, test_user, storage
    )

    async def fail_processing(**_kwargs):
        raise RuntimeError("model backend unavailable")

    monkeypatch.setattr(DocumentProcessingService, "process_version", fail_processing)
    agent = DocumentAgent(model_adapter=CleanInvoiceModel())

    with pytest.raises(DocumentAgentError, match="model backend unavailable"):
        await agent.process_document(
            db_session,
            test_user,
            case.id,
            doc.id,
            version.id,
            storage,
        )

    failed = (
        await db_session.execute(
            select(AgentExecution).where(
                AgentExecution.case_id == case.id,
                AgentExecution.status == "FAILED",
            )
        )
    ).scalars().all()
    assert len(failed) == 1
    assert "model backend unavailable" in failed[0].error


@pytest.mark.asyncio
async def test_zero_classification_confidence_is_not_inflated(
    db_session, test_org, test_user, tmp_path, monkeypatch
):
    storage = LocalFileStorage(root=str(tmp_path))
    case, doc, version, _process_version, _stage = await _setup_case_with_document(
        db_session, test_org, test_user, storage
    )

    async def zero_confidence(**_kwargs):
        return SimpleNamespace(
            id=uuid.uuid4(),
            review_required=True,
            review_reasons=["Classification requires review."],
            classification_confidence=0.0,
            predicted_document_type="invoice",
            review_task_id=None,
        )

    monkeypatch.setattr(DocumentProcessingService, "process_version", zero_confidence)
    result = await DocumentAgent(model_adapter=CleanInvoiceModel()).process_document(
        db_session,
        test_user,
        case.id,
        doc.id,
        version.id,
        storage,
    )

    assert result.classification_confidence == 0.0
    assert result.proposals[0].confidence == 0.0


@pytest.mark.asyncio
async def test_document_agent_prohibited_tools(db_session, test_org, test_user, tmp_path):
    storage = LocalFileStorage(root=str(tmp_path))
    case, doc, version, p_ver, stage = await _setup_case_with_document(
        db_session, test_org, test_user, storage
    )

    agent = DocumentAgent(model_adapter=CleanInvoiceModel())
    agent_def = await agent._get_or_create_agent_definition(db_session, test_org.id)

    # Document Agent is not in allowed_agents for request_approval
    p_ver.configuration = {
        "tool_gateway": {
            "allowed_tools": {
                "request_approval": {"enabled": True, "allowed_agents": ["WORKFLOW"]},
            }
        }
    }
    db_session.add(p_ver)
    await db_session.commit()

    tool_res = await ToolGatewayService.execute_tool(
        db=db_session,
        request=ToolExecutionRequest(
            tool_name="request_approval",
            case_id=case.id,
            arguments={"approval_type": "FINAL_DISCHARGE"},
        ),
        actor=test_user,
        agent_id=agent_def.id,
    )
    assert tool_res.status == "REJECTED"
    assert tool_res.success is False
    assert tool_res.http_status_code == 403


@pytest.mark.asyncio
async def test_agent_orchestrator_service_run_agent(db_session, test_org, test_user, tmp_path):
    storage = LocalFileStorage(root=str(tmp_path))
    case, doc, version, p_ver, stage = await _setup_case_with_document(
        db_session, test_org, test_user, storage
    )

    # Run generic agent dispatcher with agent_type="DOCUMENT"
    response = await AgentOrchestratorService.run_agent(
        db=db_session,
        actor=test_user,
        request=AgentRunRequest(
            case_id=case.id,
            agent_type="DOCUMENT",
            document_id=doc.id,
            document_version_id=version.id,
        ),
        storage=storage,
        model_adapter=CleanInvoiceModel(),
    )

    assert response.success is True
    assert response.agent_type == "DOCUMENT"
    assert len(response.proposals) >= 1
    assert response.execution_id is not None
