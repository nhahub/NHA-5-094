"""Score configured Import/Export business rules against synthetic gold fields."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.domain.rules.engine import CalculationEngine, RuleEngine

ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = ROOT / "data" / "phase17_evaluation"
PROCESS_PATH = ROOT / "workflows" / "import_export" / "process.json"


def _value(document_fields: dict[str, Any], name: str) -> Any:
    return document_fields.get(name)


def evaluate() -> dict[str, Any]:
    manifest = json.loads((DATA_ROOT / "manifest.json").read_text(encoding="utf-8"))
    process = json.loads(PROCESS_PATH.read_text(encoding="utf-8"))
    rules = process["rules"]
    calculation = process["calculations"][0]["configuration"]
    results: list[dict[str, Any]] = []

    for case in manifest["cases"]:
        expected_fields = case["expected_fields"]
        documents: dict[str, Any] = {}
        for document_type, fields in expected_fields.items():
            items = []
            if fields.get("quantity") is not None:
                items.append({
                    "quantity": fields["quantity"],
                    "sku": fields.get("sku"),
                    "amount": fields.get("amount"),
                })
            documents[document_type] = {
                "supplier": fields.get("supplier"),
                "currency": fields.get("currency"),
                "total": fields.get("total"),
                "items": items,
            }
        context: dict[str, Any] = {"documents": documents}
        requested_quantity = expected_fields["purchase_order"].get("quantity") or 0
        available_quantity = case["expected"]["inventory_available_quantity"]
        context["tools"] = {
            "check_inventory": {
                "found": True,
                "requested_quantity": requested_quantity,
                "available_quantity": available_quantity,
                "decision": "AVAILABLE" if available_quantity >= requested_quantity else "INSUFFICIENT",
            },
            "get_payment_status": {
                "found": True,
                "status": case["expected"]["payment_status"],
            },
        }
        calculated_total = CalculationEngine.evaluate(calculation["formula"], context)
        context["invoice_line_total"] = calculated_total

        rule_results = []
        for rule in rules:
            actual_passed, trace = RuleEngine.evaluate_expression(rule["expression"], context)
            code = rule["code"]
            if code == "invoice_supplier_matches_po":
                expected_passed = (
                    _value(expected_fields["invoice"], "supplier").casefold()
                    == _value(expected_fields["purchase_order"], "supplier").casefold()
                )
            elif code == "invoice_currency_matches_po":
                expected_passed = (
                    _value(expected_fields["invoice"], "currency").casefold()
                    == _value(expected_fields["purchase_order"], "currency").casefold()
                )
            elif code == "invoice_quantity_matches_po":
                expected_passed = (
                    _value(expected_fields["invoice"], "quantity")
                    == _value(expected_fields["purchase_order"], "quantity")
                )
            elif code == "invoice_total_matches_lines":
                invoice_total = Decimal(str(expected_fields["invoice"]["total"]))
                line_amount = expected_fields["invoice"].get("amount")
                line_total = Decimal(str(line_amount)) if line_amount is not None else Decimal(0)
                expected_passed = abs(invoice_total - line_total) <= Decimal(
                    str(rule["expression"].get("tolerance", 0))
                )
            elif code == "packing_quantity_matches_invoice":
                if "packing_list" not in expected_fields:
                    rule_results.append({
                        "rule_code": code,
                        "status": "not_applicable_missing_document",
                        "engine_passed": actual_passed,
                        "trace": trace,
                    })
                    continue
                expected_passed = (
                    _value(expected_fields["packing_list"], "quantity")
                    == _value(expected_fields["invoice"], "quantity")
                )
            elif code == "inventory_is_sufficient":
                expected_passed = available_quantity >= requested_quantity
            elif code == "invoice_payment_is_settled":
                expected_passed = case["expected"]["payment_status"] == "PAID"
            else:
                raise ValueError(f"Unscored configured rule: {code}")
            rule_results.append({
                "rule_code": code,
                "status": "scored",
                "expected_passed": expected_passed,
                "engine_passed": actual_passed,
                "match": actual_passed == expected_passed,
                "trace": trace,
            })
        scored = [item for item in rule_results if item["status"] == "scored"]
        results.append({
            "case_id": case["case_id"],
            "expected_workflow_outcome": case["expected"]["workflow_outcome"],
            "calculated_invoice_line_total": str(calculated_total),
            "scored_rule_count": len(scored),
            "matched_rule_count": sum(item["match"] for item in scored),
            "rule_accuracy": (
                sum(item["match"] for item in scored) / len(scored) if scored else None
            ),
            "rules": rule_results,
        })

    scored_count = sum(item["scored_rule_count"] for item in results)
    matched_count = sum(item["matched_rule_count"] for item in results)
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "evaluation": "Phase 17 configured deterministic rule diagnostics",
        "dataset": manifest["dataset_name"],
        "data_version": manifest["version"],
        "scenario_count": len(results),
        "rule_comparison_count": scored_count,
        "matched_rule_comparisons": matched_count,
        "rule_decision_accuracy": matched_count / scored_count if scored_count else None,
        "expected_workflow_outcomes_scored": False,
        "scenarios": results,
        "limitations": [
            "Rules run against labeled synthetic gold fields; this isolates the configured deterministic engine from extraction errors.",
            "This does not score live extraction, workflow transitions, external provider decisions, or the complete ten-case journey.",
            "Missing packing-list checks are reported as not applicable to business-rule accuracy and are handled by the document-requirement gate.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Optional JSON report path.")
    args = parser.parse_args()
    report = evaluate()
    reports = DATA_ROOT / "reports"
    reports.mkdir(exist_ok=True)
    output = args.output or reports / f"rule_diagnostics_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(
        f"Matched {report['matched_rule_comparisons']}/{report['rule_comparison_count']} "
        f"configured rule decisions across {report['scenario_count']} scenarios; "
        f"report: {output}"
    )


if __name__ == "__main__":
    main()
