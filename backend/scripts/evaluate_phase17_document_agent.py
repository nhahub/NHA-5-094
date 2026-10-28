"""Run the configured live Document Agent against the held-out synthetic pack."""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

import app.main  # noqa: F401 - initialize the application module graph before importing agents/documents
from app.core.config import settings
from app.domain.documents.intelligence import (
    classify_document,
    extract_document_fields,
    resolve_document_classes,
)
from app.domain.documents.ocr import apply_ocr
from app.domain.documents.parsing import parse_document_content
from app.infrastructure.llm.gateway import JsonModelAdapter, get_json_model_adapter

ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = ROOT / "data" / "phase17_evaluation"
PROCESS_PATH = ROOT / "workflows" / "import_export" / "process.json"


def _configure_provider() -> JsonModelAdapter:
    values = dotenv_values(ROOT / ".env")
    settings.GROQ_API_KEY = values.get("GROQ_API_KEY") or settings.GROQ_API_KEY
    settings.GROQ_API_KEY_FALLBACK_1 = values.get("GROQ_API_KEY_FALLBACK_1") or settings.GROQ_API_KEY_FALLBACK_1
    settings.GROQ_API_KEY_FALLBACK_2 = values.get("GROQ_API_KEY_FALLBACK_2") or settings.GROQ_API_KEY_FALLBACK_2
    settings.GROQ_DOCUMENT_MODEL = values.get("GROQ_DOCUMENT_MODEL") or settings.GROQ_DOCUMENT_MODEL
    settings.LLM7_API_KEY = values.get("LLM7_API_KEY") or settings.LLM7_API_KEY
    settings.LLM7_API_BASE_URL = values.get("LLM7_API_BASE_URL") or settings.LLM7_API_BASE_URL
    settings.LLM7_DOCUMENT_MODEL = values.get("LLM7_DOCUMENT_MODEL") or settings.LLM7_DOCUMENT_MODEL
    settings.KILO_API_KEY = values.get("KILO_API_KEY") or settings.KILO_API_KEY
    settings.KILO_API_BASE_URL = values.get("KILO_API_BASE_URL") or settings.KILO_API_BASE_URL
    settings.KILO_DOCUMENT_MODEL = values.get("KILO_DOCUMENT_MODEL") or settings.KILO_DOCUMENT_MODEL
    settings.DOCUMENT_MODEL_PROVIDER = values.get("DOCUMENT_MODEL_PROVIDER") or settings.DOCUMENT_MODEL_PROVIDER
    settings.TESSERACT_CMD = values.get("TESSERACT_CMD") or settings.TESSERACT_CMD
    provider = settings.DOCUMENT_MODEL_PROVIDER.strip().lower()
    if provider == "groq" and not any((
        settings.GROQ_API_KEY,
        settings.GROQ_API_KEY_FALLBACK_1,
        settings.GROQ_API_KEY_FALLBACK_2,
    )):
        raise RuntimeError("Set at least one GROQ_API_KEY field in the repository .env before evaluation.")
    if provider == "llm7" and not settings.LLM7_API_KEY:
        raise RuntimeError("Set LLM7_API_KEY in the repository .env before evaluation.")
    return get_json_model_adapter(provider=provider)


def _normalize(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value)).strip().casefold()
    try:
        return format(Decimal(text.replace(",", "")).normalize(), "f")
    except InvalidOperation:
        return text


def _predicted_value(fields: dict[str, Any], expected_key: str) -> Any:
    if expected_key in {"quantity", "sku", "amount"}:
        items_field = fields.get("items")
        items = getattr(items_field, "value", items_field)
        if not isinstance(items, list) or not items or not isinstance(items[0], dict):
            return None
        return items[0].get(expected_key)
    field = fields.get(expected_key)
    return getattr(field, "value", field)


def _citation_field(fields: dict[str, Any], expected_key: str) -> Any:
    if expected_key in {"quantity", "sku", "amount"}:
        return fields.get("items")
    return fields.get(expected_key)


async def _evaluate(limit: int | None) -> dict[str, Any]:
    adapter = _configure_provider()
    manifest = json.loads((DATA_ROOT / "manifest.json").read_text(encoding="utf-8"))
    configuration = json.loads(PROCESS_PATH.read_text(encoding="utf-8"))["version_configuration"]
    catalog = resolve_document_classes(configuration)
    records: list[dict[str, Any]] = []
    for case in manifest["cases"]:
        for document_type, relative_path in case["documents"].items():
            if limit is not None and len(records) >= limit:
                break
            content_path = DATA_ROOT / relative_path
            content = content_path.read_bytes()
            parsed = parse_document_content(content_path.name, content)
            if parsed.pages_requiring_ocr:
                parsed = apply_ocr(content_path.name, content, parsed)
            started = time.perf_counter()
            record: dict[str, Any] = {
                "case_id": case["case_id"], "document_type": document_type,
                "asset": relative_path, "status": "evaluated",
            }
            try:
                classification = await classify_document(
                    parsed, catalog=catalog, declared_type=document_type, adapter=adapter,
                )
                extraction = await extract_document_fields(
                    parsed, document_class=document_type,
                    configuration=configuration, adapter=adapter,
                )
                expected = case["expected_fields"][document_type]
                fields = extraction.fields
                comparisons = []
                cited = valid_citations = 0
                for key, expected_value in expected.items():
                    if expected_value is None:
                        continue
                    predicted = _predicted_value(fields, key)
                    comparisons.append(_normalize(predicted) == _normalize(expected_value))
                    extracted = _citation_field(fields, key)
                    citations = getattr(extracted, "citations", []) if extracted is not None else []
                    for citation in citations:
                        cited += 1
                        if 0 <= citation.block_index < len(parsed.blocks):
                            source = _normalize(parsed.blocks[citation.block_index].text)
                            quote = _normalize(citation.quote)
                            valid_citations += int(bool(quote) and quote in source)
                record.update({
                    "classification_correct": classification.class_id == document_type,
                    "field_count": len(comparisons),
                    "field_matches": sum(comparisons),
                    "citation_count": cited,
                    "valid_citations": valid_citations,
                    "model": extraction.model,
                    "review_required": extraction.review_required,
                })
            except Exception as exc:  # noqa: BLE001 - continue scoring; report only the safe error type
                record.update({"status": "error", "error_type": type(exc).__name__})
            record["latency_seconds"] = round(time.perf_counter() - started, 3)
            records.append(record)
            await asyncio.sleep(1.5)
        if limit is not None and len(records) >= limit:
            break

    scored = [record for record in records if record["status"] == "evaluated"]
    total_fields = sum(record["field_count"] for record in scored)
    total_matches = sum(record["field_matches"] for record in scored)
    total_citations = sum(record["citation_count"] for record in scored)
    total_valid = sum(record["valid_citations"] for record in scored)
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "provider": adapter.provider_name, "model_configured": adapter.model,
        "dataset": manifest["dataset_name"], "data_version": manifest["version"],
        "document_count": len(records), "successful_documents": len(scored),
        "classification_accuracy": (
            sum(bool(record.get("classification_correct")) for record in scored) / len(scored)
            if scored else None
        ),
        "required_field_exact_match": total_matches / total_fields if total_fields else None,
        "citation_support_validity": total_valid / total_citations if total_citations else None,
        "field_count": total_fields, "citation_count": total_citations,
        "average_latency_seconds": (
            round(sum(record["latency_seconds"] for record in records) / len(records), 3)
            if records else None
        ),
        "records": records,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, help="Evaluate only the first N labeled documents.")
    parser.add_argument("--output", type=Path, help="Optional report path; defaults to a UTC-dated JSON file.")
    args = parser.parse_args()
    result = asyncio.run(_evaluate(args.limit))
    reports = DATA_ROOT / "reports"
    reports.mkdir(exist_ok=True)
    output = args.output or reports / f"document_agent_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Evaluated {result['document_count']} documents; report: {output}")
    print(
        "Classification accuracy: {classification_accuracy}; field exact match: "
        "{required_field_exact_match}; citation validity: {citation_support_validity}".format(**result)
    )


if __name__ == "__main__":
    main()
