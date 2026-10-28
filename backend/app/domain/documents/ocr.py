"""Tesseract adapter that returns word-level text and source geometry."""
from __future__ import annotations

import io
import math
from collections import defaultdict
from typing import Any, Dict, List

import pymupdf
import pytesseract
from PIL import Image
from pytesseract import Output
from pytesseract.pytesseract import TesseractNotFoundError

from app.core.config import settings
from app.domain.documents.parsing import ContentBlock, DocumentParseError, ParsedDocument


class OCRUnavailable(RuntimeError):
    """The configured OCR engine is missing or cannot process the input."""


def ocr_image(content: bytes, *, page_number: int = 1) -> List[ContentBlock]:
    try:
        with Image.open(io.BytesIO(content)) as image:
            image.load()
            if image.width * image.height > 40_000_000:
                raise DocumentParseError("Image dimensions exceed the OCR processing limit.")
            return _recognize(image, page_number)
    except DocumentParseError:
        raise
    except (TesseractNotFoundError, RuntimeError) as exc:
        raise OCRUnavailable("Tesseract is unavailable or exceeded its processing timeout.") from exc
    except Exception as exc:
        if isinstance(exc, OCRUnavailable):
            raise
        raise OCRUnavailable("Image OCR failed.") from exc


def ocr_pdf_pages(content: bytes, pages: List[int]) -> Dict[int, List[ContentBlock]]:
    results: Dict[int, List[ContentBlock]] = {}
    try:
        with pymupdf.open(stream=content, filetype="pdf") as pdf:
            for page_number in pages:
                if page_number < 1 or page_number > pdf.page_count:
                    raise DocumentParseError("OCR page number is outside the PDF page range.")
                page = pdf[page_number - 1]
                scale = settings.OCR_DPI / 72.0
                estimated_pixels = (
                    math.ceil(page.rect.width * scale) * math.ceil(page.rect.height * scale)
                )
                if estimated_pixels > 40_000_000:
                    raise DocumentParseError("Rendered PDF page exceeds the OCR processing limit.")
                pixmap = page.get_pixmap(dpi=settings.OCR_DPI, alpha=False)
                image_bytes = pixmap.tobytes("png")
                with Image.open(io.BytesIO(image_bytes)) as image:
                    results[page_number] = _recognize(image, page_number)
    except DocumentParseError:
        raise
    except (TesseractNotFoundError, RuntimeError) as exc:
        raise OCRUnavailable("Tesseract is unavailable or exceeded its processing timeout.") from exc
    except Exception as exc:
        if isinstance(exc, OCRUnavailable):
            raise
        raise OCRUnavailable("PDF OCR failed.") from exc
    return results


def apply_ocr(filename: str, content: bytes, parsed: ParsedDocument) -> ParsedDocument:
    """Run OCR only on image content or PDF pages identified as scanned."""
    if not parsed.pages_requiring_ocr:
        return parsed
    if parsed.source_format == "pdf":
        by_page = ocr_pdf_pages(content, parsed.pages_requiring_ocr)
        ocr_blocks = [block for page_blocks in by_page.values() for block in page_blocks]
    elif parsed.source_format in {"png", "jpg", "jpeg"}:
        ocr_blocks = ocr_image(content)
    else:
        raise DocumentParseError(f"No OCR path is registered for {filename}.")
    parsed.blocks.extend(ocr_blocks)
    parsed.pages_requiring_ocr = []
    parsed.warnings = [
        warning for warning in parsed.warnings
        if warning != "OCR is required to extract text from this image."
    ]
    if not ocr_blocks:
        parsed.warnings.append("OCR completed but did not recognize readable text.")
    return parsed


def _recognize(image: Image.Image, page_number: int) -> List[ContentBlock]:
    if settings.TESSERACT_CMD:
        pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD
    try:
        data = pytesseract.image_to_data(
            image,
            lang=settings.OCR_LANGUAGE,
            output_type=Output.DICT,
            timeout=settings.OCR_TIMEOUT_SECONDS,
        )
    except (TesseractNotFoundError, RuntimeError):
        raise
    except Exception as exc:
        raise OCRUnavailable("Tesseract could not recognize this image.") from exc

    grouped: dict[tuple[int, int, int], list[dict[str, Any]]] = defaultdict(list)
    count = len(data.get("text", []))
    for index in range(count):
        text = str(data["text"][index]).strip()
        if not text:
            continue
        try:
            confidence = float(data["conf"][index])
        except (TypeError, ValueError):
            confidence = -1
        if confidence < 0:
            continue
        key = (
            int(data["block_num"][index]),
            int(data["par_num"][index]),
            int(data["line_num"][index]),
        )
        grouped[key].append({
            "text": text,
            "confidence": confidence / 100.0,
            "left": int(data["left"][index]),
            "top": int(data["top"][index]),
            "width": int(data["width"][index]),
            "height": int(data["height"][index]),
        })

    blocks: List[ContentBlock] = []
    for line_number, words in enumerate(grouped.values(), start=1):
        left = min(word["left"] for word in words)
        top = min(word["top"] for word in words)
        right = max(word["left"] + word["width"] for word in words)
        bottom = max(word["top"] + word["height"] for word in words)
        blocks.append(ContentBlock(
            kind="ocr_text",
            text=" ".join(word["text"] for word in words),
            source={
                "page": page_number,
                "line": line_number,
                "bbox": [left, top, right, bottom],
                "coordinate_system": "image-pixels-origin-top-left",
            },
            confidence=sum(word["confidence"] for word in words) / len(words),
        ))
    return blocks
