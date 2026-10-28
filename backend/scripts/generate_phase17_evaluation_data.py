"""Generate a deterministic fictional Import/Export evaluation pack.

The generated records are synthetic. They do not represent a real company,
supplier, jurisdiction, or legal/customs policy.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "data" / "phase17_evaluation"
COMPANY = {
    "name": "Northstar Demo Imports Ltd",
    "currency": "USD",
    "jurisdiction": None,
    "roles": ["employee", "manager", "administrator"],
    "supplier": {"name": "Meridian Components Ltd", "supplier_id": "SUP-MER-001"},
    "items": [
        {"sku": "VALVE-100", "description": "Industrial valve assembly", "warehouse": "Main Warehouse - NDI"},
        {"sku": "GLOVE-200", "description": "Protective work gloves", "warehouse": "Main Warehouse - NDI"},
    ],
    "assumptions": [
        "All records and policies are invented for controlled evaluation.",
        "The fixture uses USD and does not evaluate jurisdiction-specific compliance.",
        "Inventory uses the live synthetic VALVE-100 ERPNext stock fixture; payment labels map to three reusable synthetic ERPNext invoice fixtures.",
    ],
}

SCENARIOS: list[dict[str, Any]] = [
    {"id": "clean_paid", "qty_po": 10, "qty_invoice": 10, "qty_packing": 10,
     "unit_price": "12.50", "invoice_total": "125.00", "packing": True,
     "inventory": 20, "payment": "PAID", "expected": "complete", "approval": "APPROVE"},
    {"id": "invoice_quantity_mismatch", "qty_po": 10, "qty_invoice": 8, "qty_packing": 8,
     "unit_price": "12.50", "invoice_total": "100.00", "packing": True,
     "inventory": 20, "payment": "UNPAID", "expected": "human_review", "approval": "REJECT"},
    {"id": "invoice_total_mismatch", "qty_po": 10, "qty_invoice": 10, "qty_packing": 10,
     "unit_price": "12.50", "invoice_total": "130.00", "packing": True,
     "inventory": 20, "payment": "PARTIALLY_PAID", "expected": "human_review", "approval": "REJECT"},
    {"id": "missing_packing_list", "qty_po": 10, "qty_invoice": 10, "qty_packing": 10,
     "unit_price": "12.50", "invoice_total": "125.00", "packing": False,
     "inventory": 20, "payment": "PAID", "expected": "document_review", "approval": "NOT_REACHED"},
    {"id": "inventory_shortage", "qty_po": 25, "qty_invoice": 25, "qty_packing": 25,
     "unit_price": "12.50", "invoice_total": "312.50", "packing": True,
     "inventory": 20, "payment": "PAID", "expected": "human_review", "approval": "REJECT"},
    {"id": "low_quality_scan", "qty_po": 2, "qty_invoice": 2, "qty_packing": 2,
     "unit_price": "12.50", "invoice_total": "25.00", "packing": True,
     "inventory": 20, "payment": "PAID", "expected": "document_review", "approval": "NOT_REACHED",
     "low_quality": True},
    {"id": "supplier_mismatch", "qty_po": 10, "qty_invoice": 10, "qty_packing": 10,
     "unit_price": "12.50", "invoice_total": "125.00", "packing": True,
     "invoice_supplier": "Other Fictional Supplier Ltd", "inventory": 20, "payment": "PAID",
     "expected": "human_review", "approval": "REJECT"},
    {"id": "currency_mismatch", "qty_po": 10, "qty_invoice": 10, "qty_packing": 10,
     "unit_price": "12.50", "invoice_total": "125.00", "packing": True,
     "invoice_currency": "EUR", "inventory": 20, "payment": "PAID",
     "expected": "human_review", "approval": "REJECT"},
    {"id": "unpaid_invoice", "qty_po": 10, "qty_invoice": 10, "qty_packing": 10,
     "unit_price": "12.50", "invoice_total": "125.00", "packing": True,
     "inventory": 20, "payment": "UNPAID", "expected": "human_review", "approval": "REJECT"},
    {"id": "approval_rejected", "qty_po": 10, "qty_invoice": 10, "qty_packing": 10,
     "unit_price": "12.50", "invoice_total": "125.00", "packing": True,
     "inventory": 20, "payment": "PAID", "expected": "approval_rejected", "approval": "REJECT"},
]

POLICIES = {
    "document_intake.txt": (
        "FICTIONAL POLICY: Each import order requires a purchase order, a supplier commercial invoice, "
        "and a packing list before automated verification can finish. Missing or unreadable documents "
        "must remain in document review and be requested from the employee."
    ),
    "discrepancy_review.txt": (
        "FICTIONAL POLICY: A difference in supplier identity, currency, ordered quantity, shipped quantity, "
        "or invoice arithmetic creates a discrepancy. Preserve the source evidence and route the case to "
        "employee review; do not silently alter extracted values."
    ),
    "inventory_and_payment.txt": (
        "FICTIONAL POLICY: Shipment readiness requires sufficient available stock and a paid supplier invoice. "
        "A shortage, unpaid balance, unknown provider result, or unavailable provider blocks the case and "
        "requires human review."
    ),
    "approval_and_audit.txt": (
        "FICTIONAL POLICY: Only a manager may approve a reviewed import order. A rejection keeps the case "
        "on hold. Record the decision, actor, time, reason, supporting evidence, and resulting workflow event."
    ),
}

RETRIEVAL_QUESTIONS = [
    {"query": "Which documents must be present before import verification finishes?", "expected_source": "document_intake.txt"},
    {"query": "What should happen when the shipped quantity differs from the order?", "expected_source": "discrepancy_review.txt"},
    {"query": "Can shipment continue if stock is insufficient or the supplier invoice is unpaid?", "expected_source": "inventory_and_payment.txt"},
    {"query": "Who can approve a reviewed import case?", "expected_source": "approval_and_audit.txt"},
    {"query": "What must be preserved when an extraction or verification finds an issue?", "expected_source": "discrepancy_review.txt"},
    {"query": "What does a manager rejection do to the workflow?", "expected_source": "approval_and_audit.txt"},
    {"query": "List the required paperwork for an import order.", "expected_source": "document_intake.txt"},
    {"query": "What is the review path for an invoice total that does not add up?", "expected_source": "discrepancy_review.txt"},
    {"query": "What blocks dispatch when ERP inventory or payment information is missing?", "expected_source": "inventory_and_payment.txt"},
    {"query": "Which role has authority to sign off after employee review?", "expected_source": "approval_and_audit.txt"},
    {"query": "Should the system correct a mismatch in extracted source values automatically?", "expected_source": "discrepancy_review.txt"},
    {"query": "How is an approval refusal represented in the case history?", "expected_source": "approval_and_audit.txt"},
]


def _document_text(kind: str, scenario: dict[str, Any]) -> str:
    suffix = scenario["id"].upper().replace("_", "-")
    qty = {"purchase_order": scenario["qty_po"], "invoice": scenario["qty_invoice"],
           "packing_list": scenario["qty_packing"]}[kind]
    amount = f"{qty * float(scenario['unit_price']):.2f}"
    payment_reference = {
        "PAID": "INV-CLEAN-PAID",
        "PARTIALLY_PAID": "INV-INVOICE-TOTAL-MISMATCH",
        "UNPAID": "INV-UNPAID-INVOICE",
    }[scenario["payment"]]
    if kind == "purchase_order":
        lines = ["PURCHASE ORDER", f"Order Number: PO-{suffix}", "Buyer: Northstar Demo Imports Ltd",
                 "Supplier: Meridian Components Ltd", "Order Date: 2026-09-15", "Currency: USD",
                 "Item SKU: VALVE-100", "Item Description: Industrial valve assembly",
                 f"Quantity: {qty}", f"Unit Price: USD {scenario['unit_price']}", f"Line Amount: USD {amount}",
                 f"Order Total: USD {amount}"]
    elif kind == "invoice":
        lines = ["COMMERCIAL INVOICE", f"Invoice Number: INV-{suffix}",
                 f"Supplier: {scenario.get('invoice_supplier', 'Meridian Components Ltd')}",
                 "Invoice Date: 2026-09-18", f"Currency: {scenario.get('invoice_currency', 'USD')}", "Item SKU: VALVE-100",
                 "Item Description: Industrial valve assembly", f"Quantity: {qty}",
                 f"Unit Price: USD {scenario['unit_price']}", f"Line Amount: USD {amount}",
                 f"Invoice Total: USD {scenario['invoice_total']}", f"Payment Reference: {payment_reference}"]
    else:
        lines = ["PACKING LIST", f"Shipment Reference: SHP-{suffix}", "Shipper: Meridian Components Ltd",
                 "Consignee: Northstar Demo Imports Ltd", "Package Count: 2", "Gross Weight: 24.0 kg",
                 "Net Weight: 22.0 kg", "Item SKU: VALVE-100", "Item Description: Industrial valve assembly",
                 f"Quantity Packed: {qty}"]
    return "\n".join(lines) + "\n"


def _write_low_quality_scan(path: Path, text: str) -> None:
    image = Image.new("RGB", (1500, 900), "#e9e9e9")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=23)
    for index, line in enumerate(text.splitlines()):
        draw.text((54, 52 + index * 45), line, fill="#686868", font=font)
    image = image.filter(ImageFilter.GaussianBlur(radius=0.55))
    image.save(path, format="PNG", optimize=True)


def _write_ocr_scan(path: Path, text: str, quality: str) -> None:
    settings = {
        "clean": {"font_size": 25, "fill": "#202020", "blur": 0.0, "rotation": 0.0},
        "low_contrast": {"font_size": 25, "fill": "#777777", "blur": 0.0, "rotation": 0.0},
        "small_font": {"font_size": 18, "fill": "#202020", "blur": 0.0, "rotation": 0.0},
        "mild_blur": {"font_size": 24, "fill": "#303030", "blur": 0.45, "rotation": 0.0},
        "slight_skew": {"font_size": 23, "fill": "#303030", "blur": 0.15, "rotation": 0.35},
    }[quality]
    image = Image.new("RGB", (1700, 1150), "#fafafa")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=settings["font_size"])
    for index, line in enumerate(text.splitlines()):
        draw.text((72, 60 + index * 62), line, fill=settings["fill"], font=font)
    if settings["blur"]:
        image = image.filter(ImageFilter.GaussianBlur(radius=settings["blur"]))
    if settings["rotation"]:
        image = image.rotate(settings["rotation"], resample=Image.Resampling.BICUBIC, fillcolor="#fafafa")
    image.save(path, format="PNG", optimize=True)


def generate(output: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    policies_dir = output / "policies"
    policies_dir.mkdir(exist_ok=True)
    for name, content in POLICIES.items():
        (policies_dir / name).write_text(content + "\n", encoding="utf-8")

    ocr_dir = output / "ocr_pages"
    ocr_dir.mkdir(exist_ok=True)
    ocr_samples = []
    qualities = ["clean", "low_contrast", "small_font", "mild_blur", "slight_skew"]
    for index, quality in enumerate(qualities):
        scenario = SCENARIOS[index]
        expected_text = _document_text("invoice", scenario)
        relative_path = Path("ocr_pages") / f"invoice_{quality}.png"
        _write_ocr_scan(output / relative_path, expected_text, quality)
        ocr_samples.append({
            "file": relative_path.as_posix(), "quality": quality,
            "expected_text": expected_text,
        })

    cases = []
    for scenario in SCENARIOS:
        case_dir = output / "cases" / scenario["id"]
        case_dir.mkdir(parents=True, exist_ok=True)
        document_paths: dict[str, str] = {}
        expected_fields: dict[str, dict[str, Any]] = {}
        for kind in ("purchase_order", "invoice", "packing_list"):
            if kind == "packing_list" and not scenario["packing"]:
                continue
            content = _document_text(kind, scenario)
            file_name = f"{kind}.txt"
            if kind == "invoice" and scenario.get("low_quality"):
                file_name = "invoice_low_quality.png"
                _write_low_quality_scan(case_dir / file_name, content)
            else:
                (case_dir / file_name).write_text(content, encoding="utf-8")
            document_paths[kind] = str((Path("cases") / scenario["id"] / file_name).as_posix())
            quantity = {"purchase_order": scenario["qty_po"], "invoice": scenario["qty_invoice"],
                        "packing_list": scenario["qty_packing"]}[kind]
            expected_fields[kind] = {
                "supplier": scenario.get("invoice_supplier", "Meridian Components Ltd") if kind == "invoice" else "Meridian Components Ltd" if kind == "purchase_order" else None,
                "currency": scenario.get("invoice_currency", "USD") if kind == "invoice" else "USD" if kind == "purchase_order" else None,
                "quantity": quantity,
                "sku": "VALVE-100",
                "amount": f"{quantity * float(scenario['unit_price']):.2f}" if kind != "packing_list" else None,
                "total": scenario["invoice_total"] if kind == "invoice" else f"{quantity * float(scenario['unit_price']):.2f}" if kind == "purchase_order" else None,
            }
        cases.append({
            "case_id": scenario["id"], "split": "evaluation", "documents": document_paths,
            "expected_fields": expected_fields,
            "expected": {"workflow_outcome": scenario["expected"], "manager_decision": scenario["approval"],
                         "inventory_available_quantity": scenario["inventory"], "payment_status": scenario["payment"],
                         "discrepancy": scenario["expected"] == "human_review"},
        })

    manifest = {
        "dataset_name": "Verifia Phase 17 synthetic Import/Export evaluation pack",
        "version": "1.0.0", "generator": "backend/scripts/generate_phase17_evaluation_data.py",
        "data_kind": "synthetic", "company_profile": COMPANY,
        "cases": cases,
        "ocr_samples": ocr_samples,
        "policies": [{"file": str((Path("policies") / name).as_posix()), "fictional": True} for name in POLICIES],
        "retrieval_questions": RETRIEVAL_QUESTIONS,
        "leakage_controls": {"split": "evaluation", "prompt_examples_included": False, "tuning_examples_included": False},
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    manifest = generate(args.output)
    print(f"Generated {len(manifest['cases'])} synthetic evaluation cases in {args.output}")


if __name__ == "__main__":
    main()
