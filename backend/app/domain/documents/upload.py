"""Validation helpers for safe document upload before bytes reach storage."""
from __future__ import annotations

import csv
import io
import stat
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Optional

from app.core.config import settings


@dataclass
class UploadValidationError(ValueError):
    message: str
    status_code: int = 400

    def __str__(self) -> str:
        return self.message


def ensure_uploads_allowed() -> None:
    """Apply the explicit unscanned-upload policy before buffering file bytes."""
    if not settings.allow_unscanned_uploads:
        raise UploadValidationError(
            "Uploads are disabled because no malware-scanning policy is configured.",
            status_code=503,
        )


_TYPES = {
    ".pdf": ("application/pdf", {"application/pdf"}),
    ".png": ("image/png", {"image/png"}),
    ".jpg": ("image/jpeg", {"image/jpeg"}),
    ".jpeg": ("image/jpeg", {"image/jpeg"}),
    ".xls": ("application/vnd.ms-excel", {"application/vnd.ms-excel", "application/octet-stream"}),
    ".xlsx": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/octet-stream"},
    ),
    ".csv": ("text/csv", {"text/csv", "text/plain", "application/octet-stream"}),
    ".docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        {
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/octet-stream",
        },
    ),
    ".txt": ("text/plain", {"text/plain", "application/octet-stream"}),
}


def validate_filename(filename: Optional[str]) -> tuple[str, str]:
    if not filename or filename != filename.strip():
        raise UploadValidationError("A filename is required.")
    if any(ord(char) < 32 or ord(char) == 127 for char in filename):
        raise UploadValidationError("Filename cannot contain control characters.")
    if "/" in filename or "\\" in filename or filename in (".", ".."):
        raise UploadValidationError("Filename must be a single safe file name.")
    if len(filename) > 255:
        raise UploadValidationError("Filename cannot exceed 255 characters.")
    extension = filename.rpartition(".")[2].lower()
    extension = f".{extension}" if extension else ""
    if extension not in _TYPES:
        raise UploadValidationError("Unsupported document file type.", status_code=415)
    return filename, extension


def validate_upload(
    filename: Optional[str],
    content: bytes,
    declared_content_type: Optional[str],
    max_size_bytes: int,
) -> tuple[str, str, str]:
    safe_name, extension = validate_filename(filename)
    if not content:
        raise UploadValidationError("Empty files cannot be uploaded.")
    if len(content) > max_size_bytes:
        raise UploadValidationError(
            f"File exceeds the maximum size of {max_size_bytes} bytes.", status_code=413
        )

    detected_type = _detect_content_type(extension, content)
    canonical_type, accepted_declared_types = _TYPES[extension]
    if detected_type != canonical_type:
        raise UploadValidationError("File content does not match its filename extension.", status_code=415)
    declared = (declared_content_type or "").split(";", 1)[0].strip().lower()
    if declared and declared not in accepted_declared_types:
        raise UploadValidationError("Declared content type does not match the file type.", status_code=415)
    return safe_name, detected_type, extension


def _detect_content_type(extension: str, content: bytes) -> Optional[str]:
    if extension == ".pdf" and content.startswith(b"%PDF-"):
        return "application/pdf"
    if extension == ".png" and content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if extension in (".jpg", ".jpeg") and content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if extension == ".xls" and content.startswith(bytes.fromhex("D0CF11E0A1B11AE1")):
        return "application/vnd.ms-excel"
    if extension == ".xlsx" and content.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as workbook:
                if {"[Content_Types].xml", "xl/workbook.xml"} <= set(workbook.namelist()):
                    return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        except (OSError, zipfile.BadZipFile):
            pass
    if extension == ".docx" and content.startswith(b"PK\x03\x04"):
        if _is_valid_docx(content):
            return _TYPES[extension][0]
    if extension == ".txt":
        try:
            text = content.decode("utf-8-sig")
            # Allow normal text whitespace while rejecting binary/control payloads.
            if "\x00" not in text and not any(
                ord(char) < 32 and char not in "\t\n\r\f" for char in text
            ):
                return "text/plain"
        except UnicodeDecodeError:
            pass
    if extension == ".csv":
        try:
            text = content.decode("utf-8-sig")
            if "\x00" not in text and any(row for row in csv.reader(io.StringIO(text))):
                return "text/csv"
        except (UnicodeDecodeError, csv.Error):
            pass
    return None


def _is_valid_docx(content: bytes) -> bool:
    """Check DOCX package markers and bound archive expansion before accepting it."""
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entries = archive.infolist()
            if not entries or len(entries) > settings.DOCUMENT_MAX_ARCHIVE_ENTRIES:
                raise UploadValidationError(
                    "DOCX archive contains too many entries.", status_code=413
                )

            names: set[str] = set()
            expanded_size = 0
            for entry in entries:
                name = entry.filename
                path = PurePosixPath(name)
                raw_parts = name.rstrip("/").split("/")
                if (
                    not name
                    or "\\" in name
                    or path.is_absolute()
                    or any(part in ("", ".", "..") for part in raw_parts)
                    or name in names
                    or entry.flag_bits & 0x1
                    or stat.S_ISLNK(entry.external_attr >> 16)
                ):
                    return False
                names.add(name)
                expanded_size += entry.file_size
                if entry.file_size > settings.DOCUMENT_MAX_ARCHIVE_ENTRY_SIZE_BYTES:
                    raise UploadValidationError(
                        "DOCX archive entry exceeds the permitted expanded size.",
                        status_code=413,
                    )
                if expanded_size > settings.DOCUMENT_MAX_ARCHIVE_EXPANDED_SIZE_BYTES:
                    raise UploadValidationError(
                        "DOCX archive exceeds the permitted expanded size.",
                        status_code=413,
                    )

            required = {"[Content_Types].xml", "word/document.xml"}
            if not required.issubset(names):
                return False
            content_types = archive.read("[Content_Types].xml").lower()
            main_document_type = b"wordprocessingml.document.main+xml"
            if main_document_type not in content_types:
                return False
            if b"macroenabled" in content_types or "word/vbaproject.bin" in names:
                return False
            # Reading the core part also verifies its compressed stream/CRC.
            archive.read("word/document.xml")
            return True
    except (OSError, zipfile.BadZipFile, RuntimeError, KeyError):
        return False
