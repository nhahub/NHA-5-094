"""Tenant isolation and document lifecycle checks for Phase 9 Knowledge / RAG."""
import uuid

import pytest
from sqlalchemy import select

from app.domain.knowledge.models import KnowledgeDocument
from app.domain.knowledge.schemas import (
    KnowledgeSearchRequest,
    KnowledgeSourceCreate,
    KnowledgeSourceUpdate,
)
from app.domain.knowledge.service import KnowledgeService
from app.infrastructure.llm.embedding import FakeEmbeddingAdapter
from app.infrastructure.storage import LocalFileStorage
from app.security.models import Organization


async def _other_org(db_session) -> Organization:
    org = Organization(
        id=uuid.uuid4(),
        name="Other Knowledge Tenant",
        slug=f"other-knowledge-{uuid.uuid4().hex[:10]}",
        status="active",
        settings={},
        is_active=True,
    )
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


async def _source(db_session, org_id, name="Policy"):
    return await KnowledgeService.create_source(
        db=db_session,
        org_id=org_id,
        source_in=KnowledgeSourceCreate(name=name, source_type="POLICY"),
    )


@pytest.mark.asyncio
async def test_cross_organization_source_is_hidden_from_read_and_update(
    db_session, test_org
):
    other = await _other_org(db_session)
    source = await _source(db_session, test_org.id)

    assert await KnowledgeService.get_source_by_id(db_session, source.id, other.id) is None
    assert await KnowledgeService.update_source(
        db_session,
        source.id,
        other.id,
        KnowledgeSourceUpdate(name="Unauthorized rename"),
    ) is None
    unchanged = await KnowledgeService.get_source_by_id(db_session, source.id, test_org.id)
    assert unchanged.name == "Policy"


@pytest.mark.asyncio
async def test_upload_rejects_source_from_another_organization(
    db_session, test_org, tmp_path
):
    other = await _other_org(db_session)
    source = await _source(db_session, test_org.id)
    storage = LocalFileStorage(root=str(tmp_path))

    with pytest.raises(ValueError, match="not found"):
        await KnowledgeService.upload_document(
            db_session,
            source.id,
            other.id,
            b"tenant-private policy",
            "policy.txt",
            "Policy",
            "1",
            storage,
        )


@pytest.mark.asyncio
async def test_cross_organization_document_read_and_delete_are_blocked(
    db_session, test_org, tmp_path
):
    other = await _other_org(db_session)
    source = await _source(db_session, test_org.id)
    storage = LocalFileStorage(root=str(tmp_path))
    doc = await KnowledgeService.upload_document(
        db_session,
        source.id,
        test_org.id,
        b"tenant-private policy",
        "policy.txt",
        "Policy",
        "1",
        storage,
    )

    assert await KnowledgeService.get_document_by_id(db_session, doc.id, other.id) is None
    assert await KnowledgeService.delete_document(db_session, doc.id, other.id, storage) is False
    assert await KnowledgeService.get_document_by_id(db_session, doc.id, test_org.id) is not None


@pytest.mark.asyncio
async def test_duplicate_upload_in_same_source_returns_existing_document(
    db_session, test_org, tmp_path
):
    source = await _source(db_session, test_org.id)
    storage = LocalFileStorage(root=str(tmp_path))
    content = b"same bytes are the same source document"
    first = await KnowledgeService.upload_document(
        db_session, source.id, test_org.id, content, "policy.txt", "Original", "1", storage
    )
    duplicate = await KnowledgeService.upload_document(
        db_session, source.id, test_org.id, content, "renamed.txt", "Duplicate", "2", storage
    )

    assert duplicate.id == first.id
    docs = (
        await db_session.execute(
            select(KnowledgeDocument).where(KnowledgeDocument.knowledge_source_id == source.id)
        )
    ).scalars().all()
    assert len(docs) == 1


@pytest.mark.asyncio
async def test_identical_content_in_different_sources_is_not_deduplicated(
    db_session, test_org, tmp_path
):
    first_source = await _source(db_session, test_org.id, "Policy A")
    second_source = await _source(db_session, test_org.id, "Policy B")
    storage = LocalFileStorage(root=str(tmp_path))
    content = b"same content, distinct knowledge sources"

    first = await KnowledgeService.upload_document(
        db_session, first_source.id, test_org.id, content, "a.txt", "A", "1", storage
    )
    second = await KnowledgeService.upload_document(
        db_session, second_source.id, test_org.id, content, "b.txt", "B", "1", storage
    )

    assert first.id != second.id
    assert first.knowledge_source_id != second.knowledge_source_id


@pytest.mark.asyncio
async def test_semantic_search_is_scoped_to_the_requesting_organization(
    db_session, test_org, tmp_path
):
    other = await _other_org(db_session)
    source_a = await _source(db_session, test_org.id, "Tenant A")
    source_b = await _source(db_session, other.id, "Tenant B")
    storage = LocalFileStorage(root=str(tmp_path))
    adapter = FakeEmbeddingAdapter()
    doc_a = await KnowledgeService.upload_document(
        db_session,
        source_a.id,
        test_org.id,
        b"Tenant A shipping policy requires a verified invoice and packing list before customs release.",
        "a.txt",
        "A",
        "1",
        storage,
    )
    doc_b = await KnowledgeService.upload_document(
        db_session,
        source_b.id,
        other.id,
        b"Tenant B payment policy requires an approved payment instruction before funds are released.",
        "b.txt",
        "B",
        "1",
        storage,
    )
    await KnowledgeService.ingest_document(db_session, doc_a.id, test_org.id, storage, adapter)
    await KnowledgeService.ingest_document(db_session, doc_b.id, other.id, storage, adapter)

    result = await KnowledgeService.search_knowledge(
        db_session,
        test_org.id,
        KnowledgeSearchRequest(query="policy", top_k=10),
        adapter,
    )

    assert result.results
    assert {item.knowledge_document_id for item in result.results} == {doc_a.id}
