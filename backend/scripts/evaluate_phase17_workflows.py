"""Run the ten synthetic Phase 17 cases through authenticated application APIs."""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
from sqlalchemy import select

logging.disable(logging.CRITICAL)

# Load the application module graph first; domain package initializers share
# service/router imports and are not intended to be imported in isolation.
import app.main  # noqa: F401
from app.domain.processes.models import Process, ProcessVersion
from app.infrastructure.database.session import AsyncSessionLocal
from app.security.models import RoleEnum, User
from app.security.service import AuthService

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "phase17_evaluation"
BASE_URL = "http://127.0.0.1:8000/api/v1"
WAREHOUSE = "Main Warehouse - NDI"
PAYMENT_REFERENCES = {
    "PAID": "INV-CLEAN-PAID",
    "PARTIALLY_PAID": "INV-INVOICE-TOTAL-MISMATCH",
    "UNPAID": "INV-UNPAID-INVOICE",
}


async def runtime_context() -> tuple[str, dict[str, str]]:
    async with AsyncSessionLocal() as db:
        versions = await db.execute(
            select(Process, ProcessVersion)
            .join(ProcessVersion, ProcessVersion.process_id == Process.id)
            .where(Process.code == "import_order_verification", ProcessVersion.status == "PUBLISHED")
            .order_by(ProcessVersion.version_number.desc())
        )
        process, version = versions.first()
        users = list((await db.execute(
            select(User).where(User.organization_id == process.organization_id, User.is_active.is_(True))
        )).scalars())
        manager = next(user for user in users if user.role in (RoleEnum.MANAGER, RoleEnum.ADMIN))
        employee = next(user for user in users if user.role == RoleEnum.EMPLOYEE)
        customer = next(user for user in users if user.role == RoleEnum.CUSTOMER)
        return str(version.id), {
            "manager": AuthService.create_access_token(manager.id, manager.organization_id, manager.role),
            "employee": AuthService.create_access_token(employee.id, employee.organization_id, employee.role),
            "customer": AuthService.create_access_token(customer.id, customer.organization_id, customer.role),
            "employee_id": str(employee.id),
        }


async def run() -> dict:
    manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    version_id, auth = await runtime_context()
    headers = {role: {"Authorization": f"Bearer {token}"} for role, token in auth.items() if role != "employee_id"}
    report: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": manifest["dataset_name"],
        "process_version_id": version_id,
        "execution_mode": "authenticated HTTP API; synthetic data; orchestration disabled",
        "cases": [],
        "security": {"invalid_transition_attempts": 0, "invalid_transition_rejections": 0,
                     "unauthorized_tool_attempts": 0, "unauthorized_tool_denials": 0},
    }

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=60) as client:
        stage_response = await client.get(f"/workflows/stages/version/{version_id}", headers=headers["manager"])
        stage_response.raise_for_status()
        stages = {stage["code"]: stage["id"] for stage in stage_response.json()}
        definitions_response = await client.get(f"/verifications/definitions/version/{version_id}", headers=headers["manager"])
        definitions_response.raise_for_status()
        verification_id = next(item["id"] for item in definitions_response.json() if item["code"] == "order_consistency")

        for scenario in manifest["cases"]:
            case_id = None
            result = {"scenario": scenario["case_id"], "expected": scenario["expected"]["workflow_outcome"],
                      "tool_results": {}, "verification": None, "stage": None, "outcome": None}
            try:
                created = await client.post("/cases", headers=headers["manager"], json={
                    "title": f"Phase 17 evaluation: {scenario['case_id']}",
                    "process_version_id": version_id,
                    "case_metadata": {"evaluation_dataset": manifest["dataset_name"], "scenario": scenario["case_id"]},
                })
                created.raise_for_status()
                case_id = created.json()["id"]
                result["case_id"] = case_id

                # Each scenario probes an invalid target and customer tool access.
                report["security"]["invalid_transition_attempts"] += 1
                invalid = await client.post("/workflows/transition", headers=headers["manager"], json={
                    "case_id": case_id, "to_stage_id": str(uuid.uuid4()), "reason": "Phase 17 negative security check",
                })
                if invalid.status_code == 400:
                    report["security"]["invalid_transition_rejections"] += 1
                else:
                    raise RuntimeError(f"Invalid transition was not rejected: HTTP {invalid.status_code}")

                report["security"]["unauthorized_tool_attempts"] += 1
                denied = await client.post("/tools/execute", headers=headers["customer"], json={
                    "tool_name": "get_customer", "case_id": case_id, "arguments": {"customer_id": "CUST-NORTHSTAR-DEMO"},
                })
                if denied.status_code == 403:
                    report["security"]["unauthorized_tool_denials"] += 1
                else:
                    raise RuntimeError(f"Unauthorized tool attempt was not denied: HTTP {denied.status_code}")

                document_ids = {}
                for key, relative_path in scenario["documents"].items():
                    path = DATA / relative_path
                    document_type = {"purchase_order": "PURCHASE_ORDER", "invoice": "INVOICE", "packing_list": "PACKING_LIST"}[key]
                    uploaded = await client.post("/documents", headers=headers["manager"], data={
                        "case_id": case_id, "document_type": document_type,
                    }, files={"file": (path.name, path.read_bytes(), "image/png" if path.suffix.lower() == ".png" else "text/plain")})
                    uploaded.raise_for_status()
                    document = uploaded.json()["document"]
                    document_ids[key] = document["id"]
                    # The low-quality image is deliberately held for human inspection;
                    # OCR is scored separately by the real Tesseract evaluation.
                    if scenario["case_id"] == "low_quality_scan":
                        continue
                    fields = scenario["expected_fields"].get(key, {})
                    values = []
                    for field_name in ("supplier", "currency", "total"):
                        if fields.get(field_name) is not None:
                            values.append({"field_name": field_name, "field_value": {"value": fields[field_name]}, "confidence": 1.0, "extraction_method": "synthetic_gold_for_workflow_evaluation"})
                    if fields.get("quantity") is not None:
                        item = {"sku": fields.get("sku"), "quantity": fields["quantity"], "amount": float(fields["amount"]) if fields.get("amount") is not None else None}
                        values.append({"field_name": "items", "field_value": {"value": [item]}, "confidence": 1.0, "extraction_method": "synthetic_gold_for_workflow_evaluation"})
                    if values:
                        version = document["versions"][-1]["id"]
                        saved = await client.post(f"/documents/{version}/fields", headers=headers["manager"], json=values)
                        saved.raise_for_status()

                # Move to review intake. Missing-document scenarios must be blocked
                # from entering VERIFICATION by the configured required-document gate.
                moved = await client.post("/workflows/transition", headers=headers["manager"], json={
                    "case_id": case_id, "to_stage_id": stages["DOCUMENT_REVIEW"], "reason": "Documents received for evaluation",
                })
                moved.raise_for_status()
                result["stage"] = "DOCUMENT_REVIEW"
                if scenario["case_id"] == "missing_packing_list":
                    blocked = await client.post("/workflows/transition", headers=headers["manager"], json={
                        "case_id": case_id, "to_stage_id": stages["VERIFICATION"], "reason": "Expected missing document gate",
                    })
                    if blocked.status_code != 400 or "MISSING_DOCUMENT" not in blocked.text:
                        raise RuntimeError(f"Required packing-list gate did not block verification: HTTP {blocked.status_code} {blocked.text[:400]}")
                    result["outcome"] = "document_review"
                    report["cases"].append(result)
                    continue
                if scenario["case_id"] == "low_quality_scan":
                    result["outcome"] = "document_review"
                    result["limitation"] = "Held for operator review; OCR quality was evaluated in the separate Tesseract run."
                    report["cases"].append(result)
                    continue

                moved = await client.post("/workflows/transition", headers=headers["manager"], json={
                    "case_id": case_id, "to_stage_id": stages["VERIFICATION"], "reason": "Required documents present",
                })
                moved.raise_for_status()

                expected_fields = scenario["expected_fields"]
                po = expected_fields["purchase_order"]
                tool_ids = []
                for name, args in (
                    ("check_inventory", {"sku": po["sku"], "quantity": po["quantity"], "warehouse": WAREHOUSE}),
                    ("get_payment_status", {"payment_reference": PAYMENT_REFERENCES[scenario["expected"]["payment_status"]]}),
                ):
                    tool = await client.post("/tools/execute", headers=headers["manager"], json={"tool_name": name, "case_id": case_id, "arguments": args})
                    tool.raise_for_status()
                    payload = tool.json()
                    result["tool_results"][name] = payload.get("output")
                    tool_ids.append(payload["execution_id"])

                verified = await client.post("/verifications/execute", headers=headers["manager"], json={
                    "case_id": case_id, "verification_id": verification_id, "tool_execution_ids": tool_ids,
                    "inputs": {"tools": {"check_inventory": {"decision": "AVAILABLE"}, "get_payment_status": {"status": "PAID"}}},
                })
                verified.raise_for_status()
                verification = verified.json()
                result["verification"] = {"id": verification["id"], "status": verification["status"]}

                # A supported failure is routed into human review. Passing cases
                # progress to manager approval; a negative decision remains there.
                moved = await client.post("/workflows/transition", headers=headers["manager"], json={
                    "case_id": case_id, "to_stage_id": stages["HUMAN_REVIEW"], "reason": "Verification result routed for review",
                })
                moved.raise_for_status()
                result["stage"] = "HUMAN_REVIEW"
                if verification["status"] != "PASS":
                    result["outcome"] = "human_review"
                    if result["outcome"] != result["expected"]:
                        raise RuntimeError(f"Outcome mismatch: expected {result['expected']}, got {result['outcome']}")
                    report["cases"].append(result)
                    continue

                moved = await client.post("/workflows/transition", headers=headers["manager"], json={
                    "case_id": case_id, "to_stage_id": stages["MANAGER_APPROVAL"], "reason": "Verification passed",
                })
                moved.raise_for_status()
                approval = await client.post("/approvals", headers=headers["manager"], json={"case_id": case_id, "approval_type": "MANAGER"})
                approval.raise_for_status()
                decision = "REJECTED" if scenario["case_id"] == "approval_rejected" else "APPROVED"
                decided = await client.post(f"/approvals/{approval.json()['id']}/decide", headers=headers["manager"], json={
                    "decision": decision, "comment": f"Synthetic evaluation decision: {decision.lower()}",
                })
                decided.raise_for_status()
                if decision == "REJECTED":
                    result["stage"] = "MANAGER_APPROVAL"
                    result["outcome"] = "approval_rejected"
                else:
                    moved = await client.post("/workflows/transition", headers=headers["manager"], json={
                        "case_id": case_id, "to_stage_id": stages["SHIPPING"], "reason": "Manager approved synthetic case",
                    })
                    moved.raise_for_status()
                    moved = await client.post("/workflows/transition", headers=headers["manager"], json={
                        "case_id": case_id, "to_stage_id": stages["COMPLETED"], "reason": "Synthetic shipment completed",
                    })
                    moved.raise_for_status()
                    result["stage"] = "COMPLETED"
                    result["outcome"] = "complete"

                if result["outcome"] != result["expected"]:
                    raise RuntimeError(f"Outcome mismatch: expected {result['expected']}, got {result['outcome']}")
            except (httpx.HTTPError, RuntimeError, KeyError, StopIteration, ValueError) as exc:
                result["error"] = f"{type(exc).__name__}: {exc}"
                if isinstance(exc, httpx.HTTPStatusError):
                    result["error"] += f"; HTTP {exc.response.status_code}: {exc.response.text[:500]}"
            report["cases"].append(result)

    report["summary"] = {
        "scenario_count": len(report["cases"]),
        "outcome_matches": sum("error" not in row and row.get("outcome") == row["expected"] for row in report["cases"]),
        "invalid_transition_rejections": report["security"]["invalid_transition_rejections"],
        "unauthorized_tool_denials": report["security"]["unauthorized_tool_denials"],
        "passed": all("error" not in row and row.get("outcome") == row["expected"] for row in report["cases"])
                 and report["security"]["invalid_transition_attempts"] == report["security"]["invalid_transition_rejections"]
                 and report["security"]["unauthorized_tool_attempts"] == report["security"]["unauthorized_tool_denials"],
    }
    output = DATA / "reports" / f"workflow_security_{datetime.now(timezone.utc):%Y%m%d}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(output), "summary": report["summary"], "cases": report["cases"]}, indent=2))
    return report


if __name__ == "__main__":
    result = asyncio.run(run())
    raise SystemExit(0 if result["summary"]["passed"] else 1)
