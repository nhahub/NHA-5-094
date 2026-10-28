import uuid
import io
import zipfile

import pytest
from httpx import AsyncClient
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.cases.schemas import CaseCreate
from app.domain.cases.service import CaseService
from app.domain.documents.router import get_document_storage
from app.domain.documents.models import Document, DocumentVersion
from app.domain.processes.schemas import ProcessCreate, WorkflowStageCreate
from app.domain.processes.service import ProcessService
from app.events.models import EventRecord
from app.infrastructure.storage import LocalFileStorage
from app.security.models import User
from app.domain.organizations.models import Organization
from app.main import app
from app.domain.documents.upload import UploadValidationError, validate_upload
from app.infrastructure.storage import StorageError


def _minimal_docx(content: bytes = b"Sample document") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr(
            "[Content_Types].xml",
            '<Types><Override PartName="/word/document.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.'
            'wordprocessingml.document.main+xml"/></Types>',
        )
        package.writestr("word/document.xml", content)
    return buffer.getvalue()


@pytest.mark.asyncio
async def test_local_storage_round_trip_and_idempotent_delete(tmp_path):
    storage = LocalFileStorage(tmp_path)
    reference = "organizations/org/cases/case/document/v1/file.pdf"
    content = b"%PDF-1.7\nminimal test document"

    assert await storage.upload(reference, content, "application/pdf") == reference
    assert await storage.exists(reference)
    assert await storage.download(reference) == content
    await storage.delete(reference)
    await storage.delete(reference)
    assert not await storage.exists(reference)


@pytest.mark.asyncio
async def test_local_storage_rejects_traversal_and_absolute_references(tmp_path):
    storage = LocalFileStorage(tmp_path)
    for reference in ("../outside.txt", "/outside.txt", r"folder\outside.txt"):
        with pytest.raises(StorageError):
            await storage.exists(reference)


@pytest.mark.parametrize(
    ("filename", "content", "content_type", "expected_status"),
    [
        ("invoice.exe", b"anything", "application/octet-stream", 415),
        ("invoice.pdf", b"not a pdf", "application/pdf", 415),
        ("invoice.pdf", b"%PDF-1.7 test", "image/png", 415),
        ("invoice.pdf", b"%PDF-1.7 test", "application/pdf", 200),
    ],
)
def test_upload_validation_checks_extension_signature_and_mime(
    filename, content, content_type, expected_status
):
    if expected_status == 200:
        assert validate_upload(filename, content, content_type, 1024) == (
            filename,
            "application/pdf",
            ".pdf",
        )
    else:
        with pytest.raises(UploadValidationError) as error:
            validate_upload(filename, content, content_type, 1024)
        assert error.value.status_code == expected_status


def test_upload_validation_rejects_oversized_and_unsafe_filename():
    with pytest.raises(UploadValidationError) as oversized:
        validate_upload("large.pdf", b"%PDF-1.7", "application/pdf", 4)
    assert oversized.value.status_code == 413

    with pytest.raises(UploadValidationError):
        validate_upload("../invoice.pdf", b"%PDF-1.7", "application/pdf", 1024)


@pytest.mark.parametrize(
    ("filename", "content", "content_type", "expected"),
    [
        (
            "contract.docx",
            _minimal_docx(),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        ("notes.txt", "UTF-8 text\nwith tabs\tallowed".encode(), "text/plain", "text/plain"),
    ],
    ids=["docx", "utf8-text"],
)
def test_upload_validation_accepts_docx_and_utf8_text(
    filename, content, content_type, expected
):
    assert validate_upload(filename, content, content_type, 1024 * 1024) == (
        filename,
        expected,
        f".{filename.rsplit('.', 1)[1]}",
    )


@pytest.mark.parametrize(
    ("filename", "content"),
    [
        ("contract.docx", b"PK\x03\x04not-an-ooxml-document"),
        ("contract.docx", b"PK\x03\x04"),
        ("notes.txt", b"not utf-8: \xff\xfe"),
        ("notes.txt", b"binary\x00payload"),
        ("macro.docm", _minimal_docx()),
    ],
    ids=["malformed-ooxml", "truncated-zip", "invalid-utf8", "binary-text", "macro-enabled-docm"],
)
def test_upload_validation_rejects_malformed_docx_and_unsupported_text(
    filename, content
):
    with pytest.raises(UploadValidationError) as error:
        validate_upload(filename, content, "application/octet-stream", 1024 * 1024)
    assert error.value.status_code == 415


def test_docx_validation_enforces_archive_entry_and_expansion_limits(monkeypatch):
    monkeypatch.setattr(
        "app.domain.documents.upload.settings.DOCUMENT_MAX_ARCHIVE_ENTRIES", 1
    )
    with pytest.raises(UploadValidationError) as too_many_entries:
        validate_upload("contract.docx", _minimal_docx(), None, 1024 * 1024)
    assert too_many_entries.value.status_code == 413

    monkeypatch.setattr(
        "app.domain.documents.upload.settings.DOCUMENT_MAX_ARCHIVE_ENTRIES", 2048
    )
    monkeypatch.setattr(
        "app.domain.documents.upload.settings.DOCUMENT_MAX_ARCHIVE_EXPANDED_SIZE_BYTES", 16
    )
    with pytest.raises(UploadValidationError) as expanded_too_large:
        validate_upload("contract.docx", _minimal_docx(), None, 1024 * 1024)
    assert expanded_too_large.value.status_code == 413


@pytest.mark.asyncio
async def test_document_upload_returns_503_when_storage_is_unavailable(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_org: Organization,
    test_user: User,
):
    process = await ProcessService.create_process(
        db=db_session,
        organization_id=test_org.id,
        process_in=ProcessCreate(
            name="Storage Failure Intake",
            code=f"STORAGE_FAILURE_{uuid.uuid4().hex[:8]}",
        ),
    )
    process_version = (await ProcessService.get_versions_by_process_id(
        db_session, process.id
    ))[0]
    await ProcessService.add_stage_to_version(
        db_session,
        process_version.id,
        WorkflowStageCreate(name="Intake", code="INTAKE", stage_order=1, is_initial=True),
    )
    await ProcessService.publish_version(db_session, process_version.id)
    case = await CaseService.create_case(
        db=db_session,
        organization_id=test_org.id,
        created_by_user_id=test_user.id,
        case_in=CaseCreate(process_version_id=process_version.id, title="Storage outage"),
    )

    class UnavailableStorage:
        async def upload(self, key: str, data: bytes, content_type: str) -> str:
            del key, data, content_type
            raise StorageError("storage service unavailable")

    app.dependency_overrides[get_document_storage] = lambda: UnavailableStorage()
    response = await async_client.post(
        "/api/v1/documents",
        data={"case_id": str(case.id), "document_type": "invoice"},
        files={"file": ("invoice.pdf", b"%PDF-1.7\nstorage failure", "application/pdf")},
    )

    assert response.status_code == 503
    assert "storage service unavailable" in response.json()["detail"]
    assert await db_session.scalar(select(func.count()).select_from(Document)) == 0


@pytest.mark.asyncio
async def test_document_upload_duplicate_version_and_download(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_org: Organization,
    test_user: User,
    tmp_path,
):
    process = await ProcessService.create_process(
        db=db_session,
        organization_id=test_org.id,
        process_in=ProcessCreate(name="Document Intake", code="DOCUMENT_INTAKE"),
    )
    process_version = (await ProcessService.get_versions_by_process_id(
        db_session, process.id
    ))[0]
    await ProcessService.add_stage_to_version(
        db_session,
        process_version.id,
        WorkflowStageCreate(name="Intake", code="INTAKE", stage_order=1, is_initial=True),
    )
    await ProcessService.publish_version(db_session, process_version.id)
    case = await CaseService.create_case(
        db=db_session,
        organization_id=test_org.id,
        created_by_user_id=test_user.id,
        case_in=CaseCreate(process_version_id=process_version.id, title="Upload test"),
    )

    storage = LocalFileStorage(tmp_path)
    app.dependency_overrides[get_document_storage] = lambda: storage
    v1 = b"%PDF-1.7\nversion one"
    v2 = b"%PDF-1.7\nversion two"

    uploaded = await async_client.post(
        "/api/v1/documents",
        data={"case_id": str(case.id), "document_type": "invoice"},
        files={"file": ("invoice.pdf", v1, "application/pdf")},
    )
    assert uploaded.status_code == 201, uploaded.text
    first = uploaded.json()
    assert first["duplicate"] is False
    document = first["document"]
    assert document["document_type"] == "INVOICE"
    assert len(document["versions"]) == 1
    version1 = document["versions"][0]
    assert version1["file_size"] == len(v1)
    version1_row = await db_session.get(DocumentVersion, uuid.UUID(version1["id"]))
    assert await storage.download(version1_row.storage_reference) == v1

    duplicate = await async_client.post(
        "/api/v1/documents",
        data={"case_id": str(case.id), "document_type": "invoice"},
        files={"file": ("invoice-copy.pdf", v1, "application/pdf")},
    )
    assert duplicate.status_code == 200, duplicate.text
    assert duplicate.json()["duplicate"] is True
    assert duplicate.json()["document"]["id"] == document["id"]

    second = await async_client.post(
        f"/api/v1/documents/{document['id']}/versions",
        files={"file": ("invoice.pdf", v2, "application/pdf")},
    )
    assert second.status_code == 201, second.text
    versions = second.json()["document"]["versions"]
    assert [version["version_number"] for version in versions] == [1, 2]
    version2 = next(version for version in versions if version["version_number"] == 2)
    version2_row = await db_session.get(DocumentVersion, uuid.UUID(version2["id"]))
    assert await storage.download(version2_row.storage_reference) == v2

    for version, expected in ((version1, v1), (version2, v2)):
        response = await async_client.get(
            f"/api/v1/documents/{document['id']}/versions/{version['id']}/content"
        )
        assert response.status_code == 200
        assert response.content == expected

    for name, content_type, file_content, semantic_type in (
        (
            "contract.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            _minimal_docx(b"<document>Contract text</document>"),
            "CONTRACT",
        ),
        ("notes.txt", "text/plain", b"Case notes\nUTF-8 text", "NOTES"),
    ):
        format_upload = await async_client.post(
            "/api/v1/documents",
            data={"case_id": str(case.id), "document_type": semantic_type},
            files={"file": (name, file_content, content_type)},
        )
        assert format_upload.status_code == 201, format_upload.text
        uploaded_version = format_upload.json()["document"]["versions"][0]
        downloaded = await async_client.get(
            f"/api/v1/documents/{format_upload.json()['document']['id']}"
            f"/versions/{uploaded_version['id']}/content"
        )
        assert downloaded.status_code == 200
        assert downloaded.content == file_content

    event_count = await db_session.scalar(
        select(func.count()).select_from(EventRecord).where(
            EventRecord.case_id == case.id,
            EventRecord.event_type == "DOCUMENT_UPLOADED",
        )
    )
    assert event_count == 4

    inaccessible = await async_client.post(
        "/api/v1/documents",
        data={"case_id": str(uuid.uuid4()), "document_type": "invoice"},
        files={"file": ("invoice.pdf", v1, "application/pdf")},
    )
    assert inaccessible.status_code == 404
