"""
Unit tests for Phase 2: Database Models, Schema Registry, and Relationships.
"""
import uuid
from datetime import datetime, timezone
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, configure_mappers

from app.infrastructure.database.base import Base
import app.domain.organizations.models as org_models
import app.security.models as sec_models
import app.domain.processes.models as proc_models
import app.domain.workflows.models as wf_models
import app.domain.cases.models as case_models
import app.domain.documents.models as doc_models
import app.domain.rules.models as rule_models
import app.domain.verifications.models as verif_models
import app.domain.tasks.models as task_models
import app.domain.approvals.models as apprv_models
import app.tools.models as tool_models
import app.domain.knowledge.models as know_models
import app.agents.models as agent_models
import app.events.models as event_models
import app.domain.audit.models as audit_models


@pytest.fixture(scope="module", autouse=True)
def setup_mappers():
    """Ensure all SQLAlchemy mappers are compiled without error."""
    configure_mappers()


def test_all_tables_registered():
    """Verify that schema tables and the Phase 8 processing table are registered."""
    expected_tables = {
        "organizations",
        "departments",
        "department_members",
        "roles",
        "permissions",
        "role_permissions",
        "user_roles",
        "users",
        "processes",
        "process_versions",
        "workflow_stages",
        "workflow_transitions",
        "requirements",
        "business_rules",
        "calculation_definitions",
        "verification_definitions",
        "verification_rules",
        "cases",
        "case_participants",
        "case_data",
        "case_stage_history",
        "documents",
        "document_versions",
        "document_processing_runs",
        "extracted_fields",
        "evidence",
        "evidence_items",
        "verification_executions",
        "verification_results",
        "rule_executions",
        "calculation_executions",
        "tasks",
        "approvals",
        "tool_definitions",
        "tool_executions",
        "integrations",
        "integration_configs",
        "knowledge_sources",
        "knowledge_documents",
        "knowledge_chunks",
        "model_configs",
        "agent_definitions",
        "agent_executions",
        "events",
        "event_deliveries",
        "audit_logs",
        "notifications",
        "task_review_comments",
    }

    registered_tables = set(Base.metadata.tables.keys())
    missing_tables = expected_tables - registered_tables
    assert not missing_tables, f"Missing tables in Base.metadata: {missing_tables}"
    assert len(registered_tables) == 48


def test_organization_and_user_models():
    """Test instantiating Organization, Department, Role, User, and their mappings."""
    org_id = uuid.uuid4()
    org = org_models.Organization(
        id=org_id,
        name="Acme Global Logistics",
        slug="acme-global",
        status="active",
        settings={"timezone": "UTC", "currency": "USD"},
        is_active=True,
    )
    assert org.slug == "acme-global"

    user_id = uuid.uuid4()
    user = sec_models.User(
        id=user_id,
        organization_id=org_id,
        email="operator@acme.com",
        name="Alice Operator",
        hashed_password="hashed_secret_pw",
        role=sec_models.RoleEnum.EMPLOYEE,
        status="active",
        is_active=True,
    )
    assert user.role == sec_models.RoleEnum.EMPLOYEE

    dept_id = uuid.uuid4()
    dept = org_models.Department(
        id=dept_id,
        organization_id=org_id,
        name="Customs Verification",
        description="Handles customs inspection workflows",
    )
    assert dept.name == "Customs Verification"

    role_id = uuid.uuid4()
    role = sec_models.Role(
        id=role_id,
        organization_id=org_id,
        name="Customs Officer",
        description="Reviews import declarations",
    )
    assert role.name == "Customs Officer"

    perm_id = uuid.uuid4()
    perm = sec_models.Permission(
        id=perm_id,
        code="customs:review",
        description="Permission to review customs documents",
    )
    assert perm.code == "customs:review"


def test_process_and_version_models():
    """Test Process, immutable ProcessVersion, Requirements, and Stages."""
    proc_id = uuid.uuid4()
    proc = proc_models.Process(
        id=proc_id,
        organization_id=uuid.uuid4(),
        name="Import Order Verification",
        code="import_order_v1",
        description="End-to-end customs and invoice verification",
        status=proc_models.ProcessStatus.ACTIVE.value,
    )
    assert proc.code == "import_order_v1"

    version_id = uuid.uuid4()
    version = proc_models.ProcessVersion(
        id=version_id,
        process_id=proc_id,
        version_number=1,
        status=proc_models.ProcessVersionStatus.PUBLISHED.value,
        configuration={"auto_transition": True},
        published_at=datetime.now(timezone.utc),
    )
    assert version.status == "PUBLISHED"

    req = proc_models.Requirement(
        process_version_id=version_id,
        name="Commercial Invoice Required",
        code="REQ_COMMERCIAL_INVOICE",
        type=proc_models.RequirementType.DOCUMENT.value,
        required=True,
        configuration={"document_type": "COMMERCIAL_INVOICE"},
    )
    assert req.required is True

    stage_1_id = uuid.uuid4()
    stage_1 = wf_models.WorkflowStage(
        id=stage_1_id,
        process_version_id=version_id,
        name="Document Collection",
        code="DOC_COLLECTION",
        stage_order=1,
        is_initial=True,
        is_terminal=False,
    )
    stage_2_id = uuid.uuid4()
    stage_2 = wf_models.WorkflowStage(
        id=stage_2_id,
        process_version_id=version_id,
        name="Verification",
        code="VERIFICATION",
        stage_order=2,
        is_initial=False,
        is_terminal=False,
    )
    trans = wf_models.WorkflowTransition(
        process_version_id=version_id,
        from_stage_id=stage_1_id,
        to_stage_id=stage_2_id,
        name="Start Verification",
        requires_approval=False,
    )
    assert trans.requires_approval is False


def test_case_and_runtime_models():
    """Test Case model binding to immutable ProcessVersion and its runtime state entities."""
    case_id = uuid.uuid4()
    org_id = uuid.uuid4()
    proc_id = uuid.uuid4()
    version_id = uuid.uuid4()
    user_id = uuid.uuid4()

    case = case_models.Case(
        id=case_id,
        organization_id=org_id,
        process_id=proc_id,
        process_version_id=version_id,
        case_number="CASE-2026-1042",
        title="Import Order Shipment #1042",
        status=case_models.CaseStatus.IN_PROGRESS.value,
        created_by=user_id,
        case_metadata={"shipment_origin": "Shanghai", "destination": "Rotterdam"},
    )
    assert case.case_number == "CASE-2026-1042"

    part = case_models.CaseParticipant(
        case_id=case_id,
        user_id=user_id,
        participant_type=case_models.ParticipantType.CUSTOMER.value,
        name="Importing Client Corp",
    )
    assert part.participant_type == "CUSTOMER"

    c_data = case_models.CaseData(
        case_id=case_id,
        field_name="declared_total_usd",
        field_value={"amount": 48500.00, "currency": "USD"},
        source_type="DOCUMENT",
        confidence=0.98,
    )
    assert c_data.field_name == "declared_total_usd"


def test_documents_and_evidence_models():
    """Test Document, DocumentVersion, ExtractedField, Evidence, and EvidenceItem."""
    case_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    doc = doc_models.Document(
        id=doc_id,
        case_id=case_id,
        document_type="COMMERCIAL_INVOICE",
        name="commercial_invoice_1042.pdf",
        status=doc_models.DocumentStatus.PROCESSED.value,
    )
    assert doc.document_type == "COMMERCIAL_INVOICE"

    doc_ver_id = uuid.uuid4()
    doc_ver = doc_models.DocumentVersion(
        id=doc_ver_id,
        document_id=doc_id,
        version_number=1,
        storage_reference="storage/cases/1042/invoice_v1.pdf",
        file_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        mime_type="application/pdf",
        file_size=204850,
    )
    assert doc_ver.version_number == 1

    extracted = doc_models.ExtractedField(
        document_version_id=doc_ver_id,
        field_name="total_amount",
        field_value={"value": 48500.00, "currency": "USD"},
        confidence=0.99,
        page_number=1,
        extraction_method="DocumentAgent_v1",
    )
    assert extracted.field_name == "total_amount"

    ev_id = uuid.uuid4()
    ev = doc_models.Evidence(
        id=ev_id,
        case_id=case_id,
        evidence_type="INVOICE_TOTAL_VERIFICATION",
        description="Evidence supporting PO vs Invoice total reconciliation",
    )
    ev_item = doc_models.EvidenceItem(
        evidence_id=ev_id,
        source_type="EXTRACTED_FIELD",
        field_reference="total_amount",
        value_snapshot={"amount": 48500.00},
        page_number=1,
    )
    assert ev_item.source_type == "EXTRACTED_FIELD"


def test_verification_and_rules_models():
    """Test VerificationDefinition, BusinessRule, CalculationDefinition, and Executions."""
    proc_ver_id = uuid.uuid4()

    rule_id = uuid.uuid4()
    rule = rule_models.BusinessRule(
        id=rule_id,
        process_version_id=proc_ver_id,
        name="Invoice Total Matches Purchase Order",
        code="RULE_INVOICE_PO_MATCH",
        rule_type="EQUALITY",
        expression={"left": "invoice.total", "op": "==", "right": "po.total"},
        severity=rule_models.RuleSeverity.ERROR.value,
    )
    assert rule.rule_type == "EQUALITY"

    calc = rule_models.CalculationDefinition(
        process_version_id=proc_ver_id,
        name="Order Item Total Formula",
        code="CALC_ITEM_TOTAL",
        calculation_type="FORMULA",
        configuration={"formula": "quantity * unit_price"},
    )
    assert calc.calculation_type == "FORMULA"

    v_def_id = uuid.uuid4()
    v_def = verif_models.VerificationDefinition(
        id=v_def_id,
        process_version_id=proc_ver_id,
        name="Financial Reconciliation Check",
        code="VERIF_FINANCIAL_RECON",
        description="Validates that invoice line items sum to the declared total",
        result_policy={"fail_on_error": True},
    )
    assert v_def.code == "VERIF_FINANCIAL_RECON"

    v_rule = verif_models.VerificationRule(
        verification_id=v_def_id,
        rule_id=rule_id,
        execution_order=1,
        required=True,
    )
    assert v_rule.execution_order == 1

    case_id = uuid.uuid4()
    v_exec_id = uuid.uuid4()
    v_exec = verif_models.VerificationExecution(
        id=v_exec_id,
        case_id=case_id,
        verification_id=v_def_id,
        status=verif_models.VerificationStatus.PASS.value,
        executed_by_type="SYSTEM",
        inputs={"invoice_total": 48500.0, "po_total": 48500.0},
    )
    assert v_exec.status == "PASS"

    v_res = verif_models.VerificationResult(
        verification_execution_id=v_exec_id,
        result="PASS",
        summary="All figures reconciled with 0 discrepancy.",
        confidence=1.0,
    )
    assert v_res.result == "PASS"


def test_tasks_and_approvals_models():
    """Test Task and Approval models."""
    case_id = uuid.uuid4()
    task_id = uuid.uuid4()
    task = task_models.Task(
        id=task_id,
        case_id=case_id,
        task_type="DISCREPANCY_REVIEW",
        title="Review Quantity Discrepancy",
        description="PO indicates 500 units, Invoice shows 480 units.",
        status=task_models.TaskStatus.PENDING.value,
        priority=task_models.TaskPriority.HIGH.value,
    )
    assert task.status == "PENDING"

    apprv = apprv_models.Approval(
        case_id=case_id,
        task_id=task_id,
        requested_at=datetime.now(timezone.utc),
        decision=apprv_models.ApprovalDecision.PENDING.value,
    )
    assert apprv.decision == "PENDING"


def test_tools_agents_knowledge_events_audit():
    """Test ToolGateway, Agent, Knowledge RAG (pgvector), EventBus, and AuditLog models."""
    org_id = uuid.uuid4()

    tool = tool_models.ToolDefinition(
        organization_id=org_id,
        name="Compare Documents Tool",
        code="compare_documents",
        tool_type="DETERMINISTIC",
        input_schema={"doc_a": "string", "doc_b": "string"},
        output_schema={"match": "boolean"},
        enabled=True,
    )
    assert tool.code == "compare_documents"

    model_cfg = agent_models.ModelConfig(
        provider="Gemini",
        model_name="gemini-1.5-pro",
        configuration={"temperature": 0.0},
    )
    assert model_cfg.provider == "Gemini"

    agent_def = agent_models.AgentDefinition(
        organization_id=org_id,
        name="Verification Agent",
        agent_type="VERIFICATION_AGENT",
        enabled=True,
    )
    assert agent_def.agent_type == "VERIFICATION_AGENT"

    k_source = know_models.KnowledgeSource(
        organization_id=org_id,
        name="Import Compliance Policy 2026",
        source_type="POLICY",
    )
    assert k_source.name == "Import Compliance Policy 2026"

    ev = event_models.EventRecord(
        organization_id=org_id,
        case_id=uuid.uuid4(),
        event_type="CASE_CREATED",
        actor_type="USER",
        payload={"case_number": "CASE-1042"},
    )
    assert ev.event_type == "CASE_CREATED"

    audit = audit_models.AuditLog(
        organization_id=org_id,
        actor_type="USER",
        action="APPROVAL_GRANTED",
        resource_type="CASE",
        resource_id=uuid.uuid4(),
        audit_metadata={"reason": "Manual sign-off complete"},
    )
    assert audit.action == "APPROVAL_GRANTED"
