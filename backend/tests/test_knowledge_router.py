"""Integration tests for Knowledge API router (Phase 9 RAG endpoints)."""
import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.domain.knowledge.schemas import KnowledgeSourceCreate
from app.domain.knowledge.service import KnowledgeService
from app.infrastructure.llm.embedding import FakeEmbeddingAdapter, get_embedding_adapter
from app.infrastructure.storage import LocalFileStorage, get_storage_backend
from app.main import app
from app.security.models import RoleEnum


@pytest.fixture(autouse=True)
def override_embedding():
    app.dependency_overrides[get_embedding_adapter] = lambda: FakeEmbeddingAdapter()
    yield
    app.dependency_overrides.pop(get_embedding_adapter, None)


@pytest.mark.asyncio
async def test_knowledge_sources_endpoints(async_client: AsyncClient):
    # Create source
    payload = {
        "name": "Router Test Policy",
        "source_type": "INTERNAL_POLICY",
        "description": "API Router test source",
    }
    resp = await async_client.post("/api/v1/knowledge/sources", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Router Test Policy"
    source_id = data["id"]

    # List sources
    resp = await async_client.get("/api/v1/knowledge/sources")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) >= 1

    # Get single source
    resp = await async_client.get(f"/api/v1/knowledge/sources/{source_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == source_id


@pytest.mark.asyncio
async def test_knowledge_search_endpoint(async_client: AsyncClient):
    search_payload = {
        "query": "verification requirements",
        "top_k": 3,
    }
    resp = await async_client.post("/api/v1/knowledge/search", json=search_payload)
    assert resp.status_code == 200
    results = resp.json()
    assert results["query"] == search_payload["query"]
    assert results["top_k"] == search_payload["top_k"]
    assert isinstance(results["results"], list)


@pytest.mark.asyncio
async def test_update_knowledge_source_route(async_client: AsyncClient):
    created = await async_client.post(
        "/api/v1/knowledge/sources",
        json={"name": "Before", "source_type": "POLICY"},
    )
    assert created.status_code == 201

    response = await async_client.patch(
        f"/api/v1/knowledge/sources/{created.json()['id']}",
        json={"name": "After"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "After"


@pytest.mark.asyncio
async def test_knowledge_write_routes_require_manager(
    async_client: AsyncClient, db_session, test_user
):
    source = await KnowledgeService.create_source(
        db_session,
        test_user.organization_id,
        KnowledgeSourceCreate(name="Restricted source", source_type="POLICY"),
    )
    test_user.role = RoleEnum.EMPLOYEE
    await db_session.commit()

    create = await async_client.post(
        "/api/v1/knowledge/sources",
        json={"name": "Unauthorized", "source_type": "POLICY"},
    )
    update = await async_client.patch(
        f"/api/v1/knowledge/sources/{source.id}", json={"name": "Unauthorized"}
    )
    upload = await async_client.post(
        f"/api/v1/knowledge/sources/{source.id}/documents",
        data={"title": "Unauthorized"},
        files={"file": ("policy.txt", b"policy content", "text/plain")},
    )

    assert create.status_code == 403
    assert update.status_code == 403
    assert upload.status_code == 403


@pytest.mark.asyncio
async def test_knowledge_document_upload_ingest_read_and_delete_routes(
    async_client: AsyncClient, test_org, tmp_path, monkeypatch
):
    storage = LocalFileStorage(root=str(tmp_path))
    monkeypatch.setitem(app.dependency_overrides, get_storage_backend, lambda: storage)
    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER", "fake")

    source_response = await async_client.post(
        "/api/v1/knowledge/sources",
        json={"name": "Lifecycle policy", "source_type": "POLICY"},
    )
    assert source_response.status_code == 201
    source_id = source_response.json()["id"]

    upload = await async_client.post(
        f"/api/v1/knowledge/sources/{source_id}/documents",
        data={"title": "Shipping policy", "document_version": "1"},
        files={
            "file": (
                "shipping.txt",
                b"All international shipments require a commercial invoice, a packing list, and a verified customs declaration before release.",
                "text/plain",
            )
        },
    )
    assert upload.status_code == 201
    document_id = upload.json()["id"]

    ingest = await async_client.post(f"/api/v1/knowledge/documents/{document_id}/ingest")
    assert ingest.status_code == 202, ingest.text
    assert ingest.json()["status"] == "INGESTED"

    read = await async_client.get(f"/api/v1/knowledge/documents/{document_id}")
    listing = await async_client.get(f"/api/v1/knowledge/sources/{source_id}/documents")
    assert read.status_code == 200
    assert read.json()["id"] == document_id
    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()] == [document_id]

    delete = await async_client.delete(f"/api/v1/knowledge/documents/{document_id}")
    assert delete.status_code == 204
