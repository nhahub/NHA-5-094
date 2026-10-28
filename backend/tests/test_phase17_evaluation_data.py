"""Integrity checks for the generated Phase 17 evaluation corpus."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.phase17_thresholds import (
    Phase17ThresholdConfigurationUnavailable,
    load_phase17_thresholds,
)

DATA_ROOT = Path(__file__).resolve().parents[2] / "data" / "phase17_evaluation"


def _ensure_evaluation_data():
    """Generate the small synthetic fixture pack when it is not checked out."""
    if not (DATA_ROOT / "manifest.json").is_file():
        from scripts.generate_phase17_evaluation_data import generate

        generate(DATA_ROOT)


def test_configured_rules_match_labeled_gold_fields_across_scenarios():
    _ensure_evaluation_data()
    from scripts.evaluate_phase17_rules import evaluate

    report = evaluate()

    assert report["scenario_count"] == 10
    assert report["rule_comparison_count"] == 69
    assert report["matched_rule_comparisons"] == 69
    assert report["rule_decision_accuracy"] == 1.0
    assert report["expected_workflow_outcomes_scored"] is False


def test_phase17_data_manifest_assets_and_scenario_coverage():
    _ensure_evaluation_data()
    manifest = json.loads((DATA_ROOT / "manifest.json").read_text(encoding="utf-8"))
    cases = {case["case_id"]: case for case in manifest["cases"]}

    assert len(cases) == 10
    assert all(case["split"] == "evaluation" for case in manifest["cases"])
    assert {"clean_paid", "invoice_quantity_mismatch", "invoice_total_mismatch",
            "missing_packing_list", "inventory_shortage", "low_quality_scan",
            "supplier_mismatch", "currency_mismatch", "unpaid_invoice",
            "approval_rejected"} <= set(cases)
    assert set(cases["clean_paid"]["documents"]) == {
        "purchase_order", "invoice", "packing_list",
    }
    assert "packing_list" not in cases["missing_packing_list"]["documents"]
    assert cases["invoice_quantity_mismatch"]["expected"]["discrepancy"] is True
    assert cases["inventory_shortage"]["expected"]["inventory_available_quantity"] < cases[
        "inventory_shortage"
    ]["expected_fields"]["purchase_order"]["quantity"]
    assert cases["low_quality_scan"]["documents"]["invoice"].endswith(".png")
    assert len(manifest["ocr_samples"]) == 5
    assert all(sample["expected_text"] for sample in manifest["ocr_samples"])
    assert all((DATA_ROOT / sample["file"]).is_file() for sample in manifest["ocr_samples"])

    for case in cases.values():
        for relative_path in case["documents"].values():
            assert (DATA_ROOT / relative_path).is_file()


def test_fictional_policy_questions_have_labeled_sources_and_threshold_gates():
    _ensure_evaluation_data()
    manifest = json.loads((DATA_ROOT / "manifest.json").read_text(encoding="utf-8"))
    policy_files = {Path(item["file"]).name for item in manifest["policies"]}
    assert len(manifest["retrieval_questions"]) == 12
    assert all(item["expected_source"] in policy_files for item in manifest["retrieval_questions"])
    assert all((DATA_ROOT / "policies" / policy).is_file() for policy in policy_files)

    try:
        targets = load_phase17_thresholds(DATA_ROOT / "acceptance_thresholds.json")
    except Phase17ThresholdConfigurationUnavailable as exc:
        pytest.skip(str(exc))
    assert "Phase 23" in targets["evaluation_stage"]
    assert targets["targets"]["unauthorized_tool_executions"]["maximum"] == 0
    assert targets["targets"]["invalid_workflow_transitions"]["maximum"] == 0
    assert all(targets["targets"][metric]["minimum"] < 1 for metric in (
        "document_classification_accuracy", "required_field_exact_match",
        "ocr_normalized_token_recall", "policy_retrieval_recall_at_3",
    ))


def test_missing_phase17_thresholds_produce_an_explicit_blocker():
    with pytest.raises(
        Phase17ThresholdConfigurationUnavailable,
        match="BLOCKED: Phase 17 acceptance thresholds are unavailable",
    ):
        load_phase17_thresholds(Path(__file__).with_name(".missing_acceptance_thresholds.json"))
