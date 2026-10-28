"""Integration tests for KnowledgeService (Phase 9 RAG ingestion & retrieval)."""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.knowledge.service import KnowledgeService
from app.domain.knowledge.schemas import KnowledgeSourceCreate, KnowledgeSearchRequest
from app.domain.knowledge.models import KnowledgeDocumentStatus
from app.infrastructure.llm.embedding import FakeEmbeddingAdapter
from app.infrastructure.storage import LocalFileStorage
from app.security.models import Organization


@pytest.mark.asyncio
async def test_knowledge_source_crud(db_session: AsyncSession, test_org: Organization):
    org_id = test_org.id

    # Create source
    source = await KnowledgeService.create_source(
        db=db_session,
        org_id=org_id,
        source_in=KnowledgeSourceCreate(
            name="Policy Handbook",
            source_type="INTERNAL_POLICY",
            description="Company SOPs and guidelines",
        ),
    )
    assert source.id is not None
    assert source.organization_id == org_id
    assert source.name == "Policy Handbook"

    # Get source
    fetched = await KnowledgeService.get_source_by_id(db_session, source.id, org_id)
    assert fetched is not None
    assert fetched.id == source.id

    # List sources
    sources = await KnowledgeService.get_sources(db_session, org_id)
    assert len(sources) >= 1
    assert any(s.id == source.id for s in sources)


@pytest.mark.asyncio
async def test_knowledge_document_ingestion_and_search(
    db_session: AsyncSession,
    test_org: Organization,
    tmp_path,
):
    fake_adapter = FakeEmbeddingAdapter()
    storage = LocalFileStorage(root=str(tmp_path))
    org_id = test_org.id

    source = await KnowledgeService.create_source(
        db=db_session,
        org_id=org_id,
        source_in=KnowledgeSourceCreate(name="Compliance Docs", source_type="REGULATORY"),
    )

    content_bytes = b"KYC requires full identity verification including government issued photo ID and proof of address."
    doc = await KnowledgeService.upload_document(
        db=db_session,
        source_id=source.id,
        org_id=org_id,
        file_bytes=content_bytes,
        filename="kyc_2026.txt",
        title="KYC Compliance Guideline 2026",
        document_version="1.0",
        storage=storage,
    )
    assert doc.status == KnowledgeDocumentStatus.PENDING.value

    try:
        ingested_doc = await KnowledgeService.ingest_document(
            db=db_session,
            doc_id=doc.id,
            org_id=org_id,
            storage=storage,
            embedding_adapter=fake_adapter,
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise e
    assert ingested_doc.status == KnowledgeDocumentStatus.INGESTED.value

    search_req = KnowledgeSearchRequest(query="identity verification", top_k=5)
    response = await KnowledgeService.search_knowledge(
        db=db_session,
        org_id=org_id,
        request=search_req,
        embedding_adapter=fake_adapter,
    )
    assert response.results[0].knowledge_document_id == doc.id
