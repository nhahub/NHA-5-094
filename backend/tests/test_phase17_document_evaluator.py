from __future__ import annotations

from types import SimpleNamespace

from scripts.evaluate_phase17_document_agent import (
    _citation_field,
    _normalize,
    _predicted_value,
)


def test_evaluator_normalizes_numeric_formatting_and_text_spacing():
    assert _normalize(125.0) == _normalize("125.00")
    assert _normalize("  Northstar   Imports ") == _normalize("northstar imports")


def test_evaluator_reads_nested_item_values_and_uses_item_evidence():
    items = SimpleNamespace(
        value=[{"quantity": 10, "sku": "VALVE-100", "amount": 125.0}],
        citations=[SimpleNamespace(block_index=0, quote="Quantity: 10; Amount: 125.00")],
    )
    fields = {
        "items": items,
        "total": SimpleNamespace(value=125.0, citations=[]),
    }
    assert _predicted_value(fields, "quantity") == 10
    assert _predicted_value(fields, "sku") == "VALVE-100"
    assert _predicted_value(fields, "amount") == 125.0
    assert _predicted_value(fields, "total") == 125.0
    assert _citation_field(fields, "quantity") is items
