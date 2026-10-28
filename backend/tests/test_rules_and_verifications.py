"""
Integration & Unit tests for Phase 5: Deterministic Rule & Calculation Engine & Verification Service.
Tests all logical/arithmetic primitives, tolerance deltas, cross-document checks,
safe formula evaluations, trace logging, and REST APIs without AI.
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.cases.models import CaseData
from app.domain.cases.schemas import CaseCreate
from app.domain.cases.service import CaseService
from app.domain.documents.models import Document, DocumentVersion, ExtractedField
from app.domain.organizations.models import Organization
from app.domain.processes.schemas import ProcessCreate, WorkflowStageCreate
from app.domain.processes.service import ProcessService
from app.domain.rules.engine import CalculationEngine, RuleEngine
from app.domain.rules.models import RuleSeverity
from app.domain.rules.schemas import BusinessRuleCreate, CalculationDefinitionCreate
from app.domain.rules.service import RuleService
from app.domain.verifications.models import VerificationStatus
from app.domain.verifications.schemas import (
    VerificationDefinitionCreate,
    VerificationRuleLink,
    VerificationRunRequest,
)
from app.domain.verifications.service import VerificationService
from app.events.service import EventService
from app.security.models import User
from app.tools.models import ToolDefinition, ToolExecution


def test_rule_engine_primitive_operators():
    """Unit tests for RuleEngine comparison and logical operators."""
    context = {
        "invoice": {"quantity": 500, "unit_price": "12.50", "currency": "USD", "code": "INV-2026-001"},
        "po": {"quantity": 500, "total_cost": 6250.00, "buyer": "Acme Corp"},
        "shipping": {"bl_date": "2026-09-01", "lc_expiry": "2026-09-25", "weight_kg": 1002.5},
        "declared_weight": 1000.0,
    }

    # 1. EQUAL
    passed, trace = RuleEngine.evaluate_expression(
        {"operator": "EQUAL", "left_field": "invoice.quantity", "right_field": "po.quantity"},
        context,
    )
    assert passed is True
    assert trace["left_value"] == 500
    assert trace["right_value"] == 500

    # 2. String Case-Insensitive Equality
    passed, _ = RuleEngine.evaluate_expression(
        {"operator": "EQUAL", "left_field": "invoice.currency", "expected_value": "usd"},
        context,
    )
    assert passed is True

    # 3. Numerical Comparison (GREATER_THAN)
    passed, _ = RuleEngine.evaluate_expression(
        {"operator": "GREATER_THAN", "left_field": "po.total_cost", "expected_value": 5000},
        context,
    )
    assert passed is True

    # 4. EXISTS / REQUIRED
    passed, _ = RuleEngine.evaluate_expression(
        {"operator": "EXISTS", "left_field": "po.buyer"},
        context,
    )
    assert passed is True

    passed_missing, _ = RuleEngine.evaluate_expression(
        {"operator": "EXISTS", "left_field": "po.non_existent_field"},
        context,
    )
    assert passed_missing is False

    # 5. REGEX_MATCH
    passed, _ = RuleEngine.evaluate_expression(
        {"operator": "REGEX_MATCH", "left_field": "invoice.code", "expected_value": r"^INV-\d{4}-\d{3}$"},
        context,
    )
    assert passed is True

    # 6. WITHIN_TOLERANCE (Absolute: ±5.0 kg)
    passed, trace = RuleEngine.evaluate_expression(
        {
            "operator": "WITHIN_TOLERANCE",
            "left_field": "shipping.weight_kg",
            "right_field": "declared_weight",
            "tolerance": 5.0,
            "tolerance_type": "ABSOLUTE",
        },
        context,
    )
    assert passed is True
    assert Decimal(trace["actual_delta"]) == Decimal("2.5")

    # 7. WITHIN_TOLERANCE (Percentage: ±0.1% fails since 2.5/1000 is 0.25%)
    passed_pct_fail, _trace_pct = RuleEngine.evaluate_expression(
        {
            "operator": "WITHIN_TOLERANCE",
            "left_field": "shipping.weight_kg",
            "right_field": "declared_weight",
            "tolerance": 0.1,
            "tolerance_type": "PERCENTAGE",
        },
        context,
    )
    assert passed_pct_fail is False

    # 8. DATE_DIFF_DAYS_LTE
    passed, trace = RuleEngine.evaluate_expression(
        {
            "operator": "DATE_DIFF_DAYS_LTE",
            "left_field": "shipping.bl_date",
            "right_field": "shipping.lc_expiry",
            "max_days": 30,
        },
        context,
    )
    assert passed is True
    assert trace["days_diff"] == 24

    # 9. Logical AND / OR
    passed_and, _ = RuleEngine.evaluate_expression(
        {
            "operator": "AND",
            "conditions": [
                {"operator": "EQUAL", "left_field": "invoice.currency", "expected_value": "USD"},
                {"operator": "GREATER_THAN", "left_field": "invoice.quantity", "expected_value": 100},
            ],
        },
        context,
    )
    assert passed_and is True


def test_rule_engine_between_and_missing_value_policies():
    """Range boundaries and missing inputs follow their configured policy."""
    context = {"amount": 10}

    passed, trace = RuleEngine.evaluate_expression(
        {
            "operator": "BETWEEN",
            "left_field": "amount",
            "between_low": 10,
            "between_high": 20,
        },
        context,
    )
    assert passed is True
    assert trace["between_low"] == "10"
    assert trace["between_high"] == "20"

    passed, trace = RuleEngine.evaluate_expression(
        {
            "operator": "GREATER_THAN",
            "left_field": "missing_amount",
            "expected_value": 0,
            "missing_policy": "skip",
        },
        context,
    )
    assert passed is False
    assert trace["skipped"] is True

    passed, trace = RuleEngine.evaluate_expression(
        {
            "operator": "EQUAL",
            "left_field": "missing_amount",
            "expected_value": 0,
            "missing_policy": "default_zero",
        },
        context,
    )
    assert passed is True

    passed, trace = RuleEngine.evaluate_expression(
        {
            "operator": "EQUAL",
            "left_field": "missing_amount",
            "expected_value": 0,
            "missing_policy": "raise",
        },
        context,
    )
    assert passed is False
    assert "Missing left operand" in trace["error"]


def test_calculation_engine_formulas():
    """Unit tests for CalculationEngine multi-field arithmetic and infix evaluation."""
    context = {
        "qty": 20,
        "unit_price": 150.50,
        "tax": 50.00,
        "discount": 100.00,
        "items": [
            {"amount": 50.0},
            {"amount": 150.0},
            {"amount": 25.0},
        ],
    }

    # 1. Structured MULTIPLY & ADD: (qty * unit_price) + tax - discount
    res_mult = CalculationEngine.evaluate(
        {
            "operator": "SUBTRACT",
            "operands": [
                {
                    "operator": "ADD",
                    "operands": [
                        {"operator": "MULTIPLY", "operands": [{"type": "FIELD", "path": "qty"}, {"type": "FIELD", "path": "unit_price"}]},
                        {"type": "FIELD", "path": "tax"},
                    ],
                },
                {"type": "FIELD", "path": "discount"},
            ],
        },
        context,
    )
    # 20 * 150.50 = 3010.00 + 50 - 100 = 2960.00
    assert res_mult == Decimal("2960.00")

    # 2. Infix String Arithmetic without eval()
    res_infix = CalculationEngine.evaluate("qty * unit_price + tax - discount", context)
    assert res_infix == Decimal("2960.00")

    # 3. Aggregation (SUM of list)
    res_sum = RuleEngine._resolve_operand(
        {"type": "AGGREGATE", "path": "items", "aggregate_op": "SUM", "item_field": "amount"},
        context,
    )
    assert res_sum == Decimal("225.0")

    # 4. Division by Zero Safety
    res_div_zero = CalculationEngine.evaluate({"operator": "DIVIDE", "left": 100, "right": 0}, context)
    assert res_div_zero is None

    # 5. Missing Field Handling
    res_missing = CalculationEngine.evaluate("qty * non_existent_price", context)
    assert res_missing is None
async def test_verification_service_full_lifecycle(
    db_session: AsyncSession,
    test_org: Organization,
    test_user: User,
):
    """Integration test executing a complete multi-rule VerificationDefinition against a Case."""
    # 1. Setup Process & ProcessVersion
    proc = await ProcessService.create_process(
        db=db_session,
        organization_id=test_org.id,
        process_in=ProcessCreate(name="Trade Finance Verification", code="TF_VERIF"),
    )
    versions = await ProcessService.get_versions_by_process_id(db=db_session, process_id=proc.id)
    ver = versions[0]

    # 2. Add Calculation: total_amount = qty * unit_price + shipping
    await RuleService.create_calculation(
        db=db_session,
        calc_in=CalculationDefinitionCreate(
            process_version_id=ver.id,
            name="Calculate Expected Invoice Total",
            code="expected_total",
            configuration={"formula": "invoice_qty * unit_price + shipping_fee"},
        ),
    )

    # 3. Add Rule 1: Invoice Qty == PO Qty (Critical)
    r1 = await RuleService.create_rule(
        db=db_session,
        rule_in=BusinessRuleCreate(
            process_version_id=ver.id,
            name="Quantity Reconciliation",
            code="R_QTY_MATCH",
            rule_type="EQUALITY",
            severity=RuleSeverity.CRITICAL,
            expression={"operator": "EQUAL", "left_field": "invoice_qty", "right_field": "po_qty"},
        ),
    )

    # 4. Add Rule 2: Actual Total matches Calculated Total within $0.10 tolerance (Error)
    r2 = await RuleService.create_rule(
        db=db_session,
        rule_in=BusinessRuleCreate(
            process_version_id=ver.id,
            name="Invoice Total Calculation Check",
            code="R_TOTAL_MATCH",
            rule_type="TOLERANCE",
            severity=RuleSeverity.ERROR,
            expression={
                "operator": "WITHIN_TOLERANCE",
                "left_field": "actual_invoice_total",
                "right_field": "expected_total",
                "tolerance": 0.10,
                "tolerance_type": "ABSOLUTE",
            },
        ),
    )

    # 5. Create VerificationDefinition linking both rules
    v_def = await VerificationService.create_definition(
        db=db_session,
        def_in=VerificationDefinitionCreate(
            process_version_id=ver.id,
            name="Commercial Invoice & PO Cross-Check",
            code="V_INV_PO_CHECK",
            rules=[
                VerificationRuleLink(rule_id=r1.id, execution_order=1, required=True),
                VerificationRuleLink(rule_id=r2.id, execution_order=2, required=True),
            ],
        ),
    )

    # Add Stage
    await ProcessService.add_stage_to_version(
        db=db_session,
        version_id=ver.id,
        stage_in=WorkflowStageCreate(name="Verification", code="VERIF_STAGE", stage_order=1, is_initial=True),
    )

    # Publish version
    await ProcessService.publish_version(db_session, ver.id)

    # 6. Create Case with CaseData facts (Matching scenario -> should PASS)
    case = await CaseService.create_case(
        db=db_session,
        organization_id=test_org.id,
        created_by_user_id=test_user.id,
        case_in=CaseCreate(
            process_version_id=ver.id,
            title="Consignment #4412",
        ),
    )

    # Add case facts
    facts = [
        CaseData(case_id=case.id, field_name="invoice_qty", field_value=100),
        CaseData(case_id=case.id, field_name="po_qty", field_value=100),
        CaseData(case_id=case.id, field_name="unit_price", field_value=25.00),
        CaseData(case_id=case.id, field_name="shipping_fee", field_value=150.00),
        CaseData(case_id=case.id, field_name="actual_invoice_total", field_value=2650.00),  # (100 * 25) + 150 = 2650
    ]
    db_session.add_all(facts)
    document = Document(
        case_id=case.id,
        document_type="INVOICE",
        name="invoice.pdf",
        status="PROCESSED",
    )
    db_session.add(document)
    await db_session.flush()
    document_version = DocumentVersion(
        document_id=document.id,
        version_number=1,
        storage_reference="cases/invoice.pdf",
        file_hash="sha256:invoice",
        mime_type="application/pdf",
        file_size=128,
    )
    tool_definition = ToolDefinition(
        name="Inventory lookup",
        code=f"inventory_{uuid.uuid4().hex[:8]}",
        tool_type="INTEGRATION",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        enabled=True,
    )
    db_session.add_all([document_version, tool_definition])
    await db_session.flush()
    extracted_field = ExtractedField(
        document_version_id=document_version.id,
        field_name="invoice_qty",
        field_value={"value": 100},
        confidence=0.99,
        page_number=1,
        bounding_box={"x": 10, "y": 20, "width": 30, "height": 12},
        extraction_method="TEST",
    )
    tool_execution = ToolExecution(
        organization_id=test_org.id,
        case_id=case.id,
        tool_id=tool_definition.id,
        requested_by_type="USER",
        requested_by_id=test_user.id,
        input_data={"sku": "SKU-1"},
        output_data={"available": True, "quantity": 100},
        status="SUCCESS",
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    db_session.add_all([extracted_field, tool_execution])
    await db_session.commit()

    # 7. Run Verification Execution
    execution = await VerificationService.run_verification(
        db=db_session,
        request=VerificationRunRequest(
            case_id=case.id,
            verification_id=v_def.id,
            actor_type="USER",
            actor_id=test_user.id,
            tool_execution_ids=[tool_execution.id],
        ),
    )

    # Assert Verification Passed
    assert execution is not None
    assert execution.status == VerificationStatus.PASS.value
    assert len(execution.results) == 1
    assert execution.results[0].result == "PASS"
    assert execution.results[0].confidence == 1.0

    # Assert Rule Execution logs
    assert len(execution.rule_executions) == 2
    assert all(r.result == "PASS" for r in execution.rule_executions)

    # Assert Calculation Execution logs
    assert len(execution.calculation_executions) == 1
    assert execution.calculation_executions[0].status == "SUCCESS"
    assert execution.calculation_executions[0].output_data["value"] == 2650.00

    assert len(execution.evidence) == 1
    evidence = execution.evidence[0]
    assert evidence.case_id == case.id
    assert evidence.verification_execution_id == execution.id
    source_types = {item.source_type for item in evidence.items}
    assert {
        "DOCUMENT", "EXTRACTED_FIELD", "TOOL_EXECUTION",
        "RULE_EXECUTION", "CALCULATION_EXECUTION",
    } <= source_types
    extracted_evidence = next(item for item in evidence.items if item.source_type == "EXTRACTED_FIELD")
    assert extracted_evidence.source_id == extracted_field.id
    assert extracted_evidence.page_number == 1
    assert extracted_evidence.location["x"] == 10
    tool_evidence = next(item for item in evidence.items if item.source_type == "TOOL_EXECUTION")
    assert tool_evidence.source_id == tool_execution.id
    assert tool_evidence.value_snapshot["output"]["available"] is True

    # Tool results can only be attached when they belong to this exact case.
    foreign_case = await CaseService.create_case(
        db=db_session,
        organization_id=test_org.id,
        created_by_user_id=test_user.id,
        case_in=CaseCreate(process_version_id=ver.id, title="Other case"),
    )
    foreign_tool = ToolExecution(
        organization_id=test_org.id,
        case_id=foreign_case.id,
        tool_id=tool_definition.id,
        requested_by_type="USER",
        requested_by_id=test_user.id,
        input_data={},
        output_data={"secret": "other case"},
        status="SUCCESS",
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    db_session.add(foreign_tool)
    await db_session.commit()
    with pytest.raises(ValueError, match="belong to this case"):
        await VerificationService.run_verification(
            db=db_session,
            request=VerificationRunRequest(
                case_id=case.id,
                verification_id=v_def.id,
                tool_execution_ids=[foreign_tool.id],
            ),
        )

    # Verify Event Emitted
    events = await EventService.get_events_for_case(db=db_session, case_id=case.id)
    assert any(e.event_type == "VERIFICATION_COMPLETED" for e in events)


@pytest.mark.asyncio
async def test_rules_and_verifications_api_endpoints(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_org: Organization,
    test_user: User,
):
    """Test REST API endpoints for rules evaluation and verification runs."""
    # 1. POST /api/v1/rules/evaluate (ad-hoc direct evaluation)
    res = await async_client.post(
        "/api/v1/rules/evaluate",
        json={
            "expression": {
                "operator": "GREATER_THAN",
                "left_field": "net_weight",
                "expected_value": 500,
            },
            "context_data": {"net_weight": 750},
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["passed"] is True

    # 2. POST /api/v1/rules/calculate (ad-hoc formula evaluation)
    res = await async_client.post(
        "/api/v1/rules/calculate",
        json={
            "formula": "items_count * price_per_item",
            "context_data": {"items_count": 12, "price_per_item": 9.99},
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["value"] == 119.88

    # 3. Create Process and Definition via API
    proc = await ProcessService.create_process(
        db=db_session,
        organization_id=test_org.id,
        process_in=ProcessCreate(name="API Verif Process", code="API_VERIF_P"),
    )
    versions = await ProcessService.get_versions_by_process_id(db=db_session, process_id=proc.id)
    ver = versions[0]

    # POST /api/v1/verifications/definitions
    res_def = await async_client.post(
        "/api/v1/verifications/definitions",
        json={
            "process_version_id": str(ver.id),
            "name": "Cargo Sanity Check",
            "code": "CARGO_SANITY",
        },
    )
    assert res_def.status_code == 201, res_def.text
    def_id = res_def.json()["id"]

    await ProcessService.add_stage_to_version(
        db=db_session,
        version_id=ver.id,
        stage_in=WorkflowStageCreate(name="Sanity Stage", code="SANITY_STG", stage_order=1, is_initial=True),
    )
    await ProcessService.publish_version(db_session, ver.id)

    case = await CaseService.create_case(
        db=db_session,
        organization_id=test_org.id,
        created_by_user_id=test_user.id,
        case_in=CaseCreate(process_version_id=ver.id, title="Cargo Case #909"),
    )

    # POST /api/v1/verifications/execute
    res_exec = await async_client.post(
        "/api/v1/verifications/execute",
        json={
            "case_id": str(case.id),
            "verification_id": def_id,
            "inputs": {"ambient_temp": 4.5},
        },
    )
    assert res_exec.status_code == 200, res_exec.text
    exec_data = res_exec.json()
    assert exec_data["case_id"] == str(case.id)
    assert exec_data["verification_id"] == def_id
    assert len(exec_data["evidence"]) == 1
    assert exec_data["evidence"][0]["verification_execution_id"] == exec_data["id"]
    assert exec_data["evidence"][0]["items"] == []

    # GET /api/v1/verifications/case/{id}
    res_list = await async_client.get(f"/api/v1/verifications/case/{case.id}")
    assert res_list.status_code == 200
    assert len(res_list.json()) >= 1


@pytest.mark.asyncio
async def test_verification_rules_consume_only_successful_case_scoped_tool_outputs(
    db_session: AsyncSession, test_org: Organization, test_user: User,
):
    process = await ProcessService.create_process(
        db_session, test_org.id,
        ProcessCreate(name="Tool-backed verification", code="TOOL_BACKED_VERIFICATION"),
    )
    version = (await ProcessService.get_versions_by_process_id(db_session, process.id))[0]
    await ProcessService.add_stage_to_version(
        db_session, version.id,
        WorkflowStageCreate(name="Verification", code="VERIFY", stage_order=1, is_initial=True),
    )
    tool = ToolDefinition(
        name="Inventory check", code="check_inventory", tool_type="INTEGRATION",
        input_schema={"type": "object"}, output_schema={"type": "object"}, enabled=True,
    )
    db_session.add(tool)
    await db_session.flush()
    rule = await RuleService.create_rule(
        db_session,
        BusinessRuleCreate(
            process_version_id=version.id,
            name="Inventory is sufficient",
            code="inventory_sufficient",
            rule_type="EQUALITY",
            severity=RuleSeverity.CRITICAL,
            expression={
                "operator": "EQUAL",
                "left_field": "tools.check_inventory.decision",
                "expected_value": "AVAILABLE",
                "missing_policy": "raise",
            },
        ),
    )
    definition = await VerificationService.create_definition(
        db_session,
        VerificationDefinitionCreate(
            process_version_id=version.id,
            name="Inventory sufficiency",
            code="inventory_sufficiency",
            rules=[VerificationRuleLink(rule_id=rule.id, required=True)],
        ),
    )
    await ProcessService.publish_version(db_session, version.id)
    case = await CaseService.create_case(
        db_session, test_org.id, test_user.id,
        CaseCreate(title="Tool evidence verification", process_version_id=version.id),
    )
    execution_record = ToolExecution(
        organization_id=test_org.id, case_id=case.id, tool_id=tool.id,
        requested_by_type="USER", requested_by_id=test_user.id,
        input_data={"sku": "VALVE-100"}, output_data={"decision": "INSUFFICIENT"},
        status="SUCCESS", started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    db_session.add(execution_record)
    await db_session.commit()

    result = await VerificationService.run_verification(
        db_session,
        VerificationRunRequest(
            case_id=case.id, verification_id=definition.id,
            tool_execution_ids=[execution_record.id],
            # Explicit inputs cannot override a persisted, trusted tool result.
            inputs={"tools": {"check_inventory": {"decision": "AVAILABLE"}}},
        ),
    )

    assert result.status == VerificationStatus.FAIL.value
    assert result.inputs["tools"]["check_inventory"]["decision"] == "INSUFFICIENT"
    assert any(item.source_type == "TOOL_EXECUTION" for item in result.evidence[0].items)
