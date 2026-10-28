import json
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.cases.schemas import CaseCreate
from app.domain.cases.service import CaseService
from app.domain.processes.configuration_loader import load_process_definition
from app.domain.processes.configuration_loader import validate_process_definition
from app.domain.processes.models import Process, ProcessVersion, Requirement
from app.domain.processes.schemas import WorkflowStageCreate
from app.domain.processes.service import ProcessService
from app.domain.rules.models import BusinessRule, CalculationDefinition
from app.domain.verifications.models import VerificationDefinition, VerificationRule
from app.domain.workflows.models import WorkflowStage, WorkflowTransition


@pytest.mark.asyncio
async def test_import_export_process_definition_publishes_generic_configuration(
    db_session: AsyncSession, test_org,
):
    config_path = Path(__file__).resolve().parents[2] / "workflows" / "import_export" / "process.json"
    process, version = await load_process_definition(
        db_session, organization_id=test_org.id, path=config_path,
    )

    assert process.code == "import_order_verification"
    assert version.status == "PUBLISHED"
    assert version.configuration["tool_gateway"]["allowed_tools"]["check_inventory"]["enabled"] is True
    assert version.configuration["tool_gateway"]["allowed_tools"]["run_verification"]["enabled"] is True
    assert version.configuration["demo_external_integrations"]["payment"]["required"] is True
    stages = list((await db_session.execute(
        select(WorkflowStage).where(WorkflowStage.process_version_id == version.id)
    )).scalars())
    transitions = list((await db_session.execute(
        select(WorkflowTransition).where(WorkflowTransition.process_version_id == version.id)
    )).scalars())
    requirements = list((await db_session.execute(
        select(Requirement).where(Requirement.process_version_id == version.id)
    )).scalars())
    rules = list((await db_session.execute(
        select(BusinessRule).where(BusinessRule.process_version_id == version.id)
    )).scalars())
    calculations = list((await db_session.execute(
        select(CalculationDefinition).where(CalculationDefinition.process_version_id == version.id)
    )).scalars())
    verifications = list((await db_session.execute(
        select(VerificationDefinition).where(VerificationDefinition.process_version_id == version.id)
    )).scalars())
    verification_links = list((await db_session.execute(
        select(VerificationRule).where(VerificationRule.verification_id.in_([v.id for v in verifications]))
    )).scalars())
    assert len(stages) == 7
    assert len(transitions) == 6
    assert {item.code for item in stages} >= {"INTAKE", "MANAGER_APPROVAL", "COMPLETED"}
    assert {item.code for item in requirements} >= {
        "PURCHASE_ORDER", "COMMERCIAL_INVOICE", "PACKING_LIST", "MANAGER_SIGNOFF",
    }
    assert {item.code for item in rules} >= {
        "invoice_supplier_matches_po", "invoice_currency_matches_po",
        "invoice_total_matches_lines", "packing_quantity_matches_invoice",
        "inventory_is_sufficient", "invoice_payment_is_settled",
    }
    assert [item.code for item in calculations] == ["invoice_line_total"]
    assert [item.code for item in verifications] == ["order_consistency"]
    assert len(verification_links) == 7
    assert len(version.configuration["extraction_schemas"]) == 3
    case = await CaseService.create_case(
        db_session, test_org.id, None,
        CaseCreate(title="Phase 17 configuration binding", process_version_id=version.id),
    )
    assert case.process_version_id == version.id
    with pytest.raises(ValueError, match="cannot be modified"):
        await ProcessService.add_stage_to_version(
            db_session, version.id,
            WorkflowStageCreate(name="Mutation attempt", code="MUTATION_ATTEMPT"),
        )


@pytest.mark.asyncio
async def test_invalid_process_references_are_rejected_before_persistence(
    db_session: AsyncSession, test_org,
):
    config_path = Path(__file__).resolve().parents[2] / "workflows" / "import_export" / "process.json"
    definition = json.loads(config_path.read_text(encoding="utf-8"))
    definition["verifications"][0]["rules"][0]["rule_code"] = "does_not_exist"
    invalid_path = Path(__file__).with_name(".invalid_phase17_process.json")
    invalid_path.write_text(json.dumps(definition), encoding="utf-8")

    try:
        with pytest.raises(ValueError, match="unknown rule code"):
            await load_process_definition(
                db_session, organization_id=test_org.id, path=invalid_path,
            )

        assert not list((await db_session.execute(select(Process))).scalars())
        assert not list((await db_session.execute(select(ProcessVersion))).scalars())
    finally:
        invalid_path.unlink(missing_ok=True)


def test_import_export_configuration_declares_external_dependencies():
    config_path = Path(__file__).resolve().parents[2] / "workflows" / "import_export" / "process.json"
    configuration = json.loads(config_path.read_text(encoding="utf-8"))["version_configuration"]
    tools = configuration["tool_gateway"]["allowed_tools"]
    assert tools["check_inventory"]["integration_type"] == "ERP"
    assert tools["get_customer"]["integration_type"] == "ERP"
    assert tools["get_payment_status"]["integration_type"] == "FINANCE"
    assert tools["check_inventory"]["enabled"] is True
    assert tools["get_payment_status"]["enabled"] is True


def test_failed_verification_exception_is_limited_to_review_stage():
    config_path = Path(__file__).resolve().parents[2] / "workflows" / "import_export" / "process.json"
    definition = json.loads(config_path.read_text(encoding="utf-8"))
    validate_process_definition(definition)

    definition["transitions"][2]["condition_config"]["allow_failed_verifications"] = [
        "not_configured",
    ]
    with pytest.raises(ValueError, match="unknown failed-verification codes"):
        validate_process_definition(definition)

    definition = json.loads(config_path.read_text(encoding="utf-8"))
    definition["transitions"][2]["to"] = "MANAGER_APPROVAL"
    with pytest.raises(ValueError, match="only a configured review_stage"):
        validate_process_definition(definition)


@pytest.mark.asyncio
async def test_process_loader_publishes_new_immutable_version_for_existing_process(
    db_session: AsyncSession, test_org,
):
    config_path = Path(__file__).resolve().parents[2] / "workflows" / "import_export" / "process.json"
    process, first = await load_process_definition(
        db_session, organization_id=test_org.id, path=config_path,
    )

    same_process, second = await load_process_definition(
        db_session, organization_id=test_org.id, path=config_path, process_id=process.id,
    )

    assert same_process.id == process.id
    assert first.version_number == 1
    assert first.status == "PUBLISHED"
    assert second.version_number == 2
    assert second.status == "PUBLISHED"
    assert first.id != second.id
    assert second.configuration["tool_gateway"]["allowed_tools"]["run_verification"]["enabled"] is True
