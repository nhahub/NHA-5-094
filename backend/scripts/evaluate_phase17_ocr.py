"""Score Tesseract token recall on the labeled synthetic Phase 17 scan set."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

import app.main  # noqa: F401 - initialize application settings and document modules
from app.core.config import settings
from app.domain.documents.ocr import apply_ocr
from app.domain.documents.parsing import parse_document_content
from scripts.phase17_thresholds import load_phase17_thresholds

ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = ROOT / "data" / "phase17_evaluation"
THRESHOLDS_PATH = DATA_ROOT / "acceptance_thresholds.json"


def _tokens(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", value.casefold())


def _token_recall(expected: str, recognized: str) -> tuple[int, int, float]:
    expected_tokens = Counter(_tokens(expected))
    recognized_tokens = Counter(_tokens(recognized))
    total = sum(expected_tokens.values())
    matched = sum((expected_tokens & recognized_tokens).values())
    return matched, total, matched / total if total else 1.0


def evaluate() -> dict[str, Any]:
    env = dotenv_values(ROOT / ".env")
    if env.get("TESSERACT_CMD"):
        settings.TESSERACT_CMD = env["TESSERACT_CMD"]
    manifest = json.loads((DATA_ROOT / "manifest.json").read_text(encoding="utf-8"))
    thresholds = load_phase17_thresholds(THRESHOLDS_PATH)["targets"]["ocr_normalized_token_recall"]
    results = []
    for sample in manifest.get("ocr_samples", []):
        path = DATA_ROOT / sample["file"]
        content = path.read_bytes()
        parsed = parse_document_content(path.name, content)
        parsed = apply_ocr(path.name, content, parsed)
        recognized = "\n".join(block.text for block in parsed.blocks)
        matched, total, recall = _token_recall(sample["expected_text"], recognized)
        results.append({
            "file": sample["file"], "quality": sample["quality"],
            "matched_tokens": matched, "expected_tokens": total,
            "normalized_token_recall": round(recall, 4),
        })

    page_count = len(results)
    expected_count = sum(item["expected_tokens"] for item in results)
    matched_count = sum(item["matched_tokens"] for item in results)
    recall = matched_count / expected_count if expected_count else None
    enough_pages = page_count >= thresholds["minimum_pages"]
    passed = enough_pages and recall is not None and recall >= thresholds["minimum"]
    return {
        "created_at": datetime.now(UTC).isoformat(),
        "evaluation": "Phase 17 synthetic scan OCR baseline",
        "engine": "Tesseract",
        "dataset": manifest["dataset_name"], "data_version": manifest["version"],
        "page_count": page_count, "matched_tokens": matched_count,
        "expected_tokens": expected_count,
        "normalized_token_recall": round(recall, 4) if recall is not None else None,
        "minimum_pages": thresholds["minimum_pages"],
        "minimum_recall": thresholds["minimum"],
        "threshold_result": "pass" if passed else "fail_or_insufficient_sample",
        "samples": results,
        "limitations": [
            "Generated scans validate the OCR path on controlled layouts and degradation only.",
            "This does not represent real-world document diversity or replace licensed benchmark data.",
        ],
    }


def evaluate_doclaynet(source_zip: Path) -> dict[str, Any]:
    """Score OCR against the publisher's paired text-cell references in the 20-page set."""
    env = dotenv_values(ROOT / ".env")
    if env.get("TESSERACT_CMD"):
        settings.TESSERACT_CMD = env["TESSERACT_CMD"]
    thresholds = load_phase17_thresholds(THRESHOLDS_PATH)["targets"]["ocr_normalized_token_recall"]
    digest = hashlib.sha256(source_zip.read_bytes()).hexdigest()
    results = []
    with zipfile.ZipFile(source_zip) as archive:
        names = set(archive.namelist())
        if "LICENSE" not in names:
            raise ValueError("DocLayNet archive is missing its bundled license.")
        license_text = archive.read("LICENSE").decode("utf-8", errors="replace")
        if "Apache License" not in license_text or "Version 2.0" not in license_text:
            raise ValueError("DocLayNet development archive license could not be verified as Apache-2.0.")
        json_paths = sorted(name for name in names if name.startswith("JSON/") and name.endswith(".json"))
        if len(json_paths) != 20:
            raise ValueError(f"Expected the official 20-page development set; found {len(json_paths)} paired text references.")
        for json_path in json_paths:
            reference = json.loads(archive.read(json_path))
            page_hash = reference.get("metadata", {}).get("page_hash")
            if not isinstance(page_hash, str) or len(page_hash) != 64:
                raise ValueError(f"Invalid page hash in {json_path}.")
            image_path = f"PNG/{page_hash}.png"
            if image_path not in names:
                raise ValueError(f"Image paired with {json_path} is missing.")
            expected = "\n".join(
                cell.get("text", "") for cell in reference.get("cells", [])
                if isinstance(cell, dict) and isinstance(cell.get("text", ""), str)
            )
            content = archive.read(image_path)
            image_name = Path(image_path).name
            parsed = parse_document_content(image_name, content)
            parsed = apply_ocr(image_name, content, parsed)
            recognized = "\n".join(block.text for block in parsed.blocks)
            matched, total, recall = _token_recall(expected, recognized)
            results.append({
                "page_hash": page_hash,
                "document_category": reference.get("metadata", {}).get("doc_category"),
                "matched_tokens": matched,
                "expected_tokens": total,
                "normalized_token_recall": round(recall, 4),
            })

    page_count = len(results)
    expected_count = sum(item["expected_tokens"] for item in results)
    matched_count = sum(item["matched_tokens"] for item in results)
    recall = matched_count / expected_count if expected_count else None
    passed = page_count >= thresholds["minimum_pages"] and recall is not None and recall >= thresholds["minimum"]
    return {
        "created_at": datetime.now(UTC).isoformat(),
        "evaluation": "Phase 17 external OCR/layout sample",
        "engine": "Tesseract",
        "dataset": "Official DocLayNet ICDAR 2023 20-page development set",
        "dataset_source": "https://ds4sd.github.io/icdar23-doclaynet/task/",
        "license": "Apache-2.0 (bundled archive LICENSE verified)",
        "source_archive_sha256": digest,
        "page_count": page_count,
        "matched_tokens": matched_count,
        "expected_tokens": expected_count,
        "normalized_token_recall": round(recall, 4) if recall is not None else None,
        "minimum_pages": thresholds["minimum_pages"],
        "minimum_recall": thresholds["minimum"],
        "threshold_result": "pass" if passed else "fail_or_insufficient_sample",
        "samples": results,
        "limitations": [
            "DocLayNet tests general document OCR/layout inputs, not trade-document field extraction or Verifia case outcomes.",
            "Reference text is paired digital-PDF cell text, not an independent human transcription; token recall is a diagnostic baseline.",
            "The 20-page development subset is small and does not represent production document diversity.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Optional JSON report path.")
    parser.add_argument("--doclaynet-zip", type=Path, help="Evaluate the official 20-page DocLayNet development archive.")
    args = parser.parse_args()
    report = evaluate_doclaynet(args.doclaynet_zip) if args.doclaynet_zip else evaluate()
    reports_dir = DATA_ROOT / "reports"
    reports_dir.mkdir(exist_ok=True)
    output = args.output or reports_dir / f"ocr_{datetime.now(UTC):%Y%m%dT%H%M%SZ}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        f"Tesseract normalized token recall: {report['normalized_token_recall']} "
        f"over {report['page_count']} pages ({report['threshold_result']}); report: {output}"
    )


if __name__ == "__main__":
    main()
