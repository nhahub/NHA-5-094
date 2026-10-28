"""Opt-in real-provider and real-runtime integration checks.

Run from backend/ with VERIFIA_RUN_LIVE_TESTS=1 and provider credentials in the
repository-root .env. These checks intentionally remain outside the default,
offline suite.
"""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import uuid
from pathlib import Path

import pytest
from dotenv import dotenv_values
from sqlalchemy import delete, text

from app.core.config import settings
from app.domain.documents.intelligence import (
    DEFAULT_DOCUMENT_CLASSES,
    GroqJsonAdapter,
    classify_document,
    extract_document_fields,
)
from app.domain.documents.ocr import apply_ocr
from app.domain.documents.parsing import (
    ContentBlock,
    ParsedDocument,
    parse_document_content,
)
from app.domain.knowledge.models import KnowledgeDocumentStatus
from app.domain.knowledge.schemas import KnowledgeSearchRequest, KnowledgeSourceCreate
from app.domain.knowledge.service import KnowledgeService
from app.domain.organizations.models import Organization
from app.infrastructure.database.session import AsyncSessionLocal, async_engine
from app.infrastructure.llm.embedding import (
    BGE_M3_DIMENSION,
    CloudflareBGEEmbeddingAdapter,
)
from app.infrastructure.storage import LocalFileStorage

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.getenv("VERIFIA_RUN_LIVE_TESTS") != "1",
        reason="set VERIFIA_RUN_LIVE_TESTS=1 to enable external integration checks",
    ),
]

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
EVALUATION_ROOT = REPOSITORY_ROOT / "data" / "samples" / "evaluation"


def _root_env(name: str) -> str:
    value = os.getenv(name) or dotenv_values(REPOSITORY_ROOT / ".env").get(name)
    if not value:
        pytest.skip(f"{name} is not configured in the process environment or repository .env")
    return value


def _embedding_adapter() -> CloudflareBGEEmbeddingAdapter:
    return CloudflareBGEEmbeddingAdapter(
        account_id=_root_env("CLOUDFLARE_ACCOUNT_ID"),
        api_token=_root_env("CLOUDFLARE_API_TOKEN"),
        model_name=os.getenv("EMBEDDING_MODEL_NAME") or "@cf/baai/bge-m3",
    )


def _sample_policy() -> str:
    sample = EVALUATION_ROOT / "synthetic" / "expense_approval.txt"
    if not sample.is_file():
        pytest.skip("evaluation policy sample is missing; see data/samples/evaluation/README.md")
    return sample.read_text(encoding="utf-8")


def test_live_cloudflare_bge_m3_returns_normalized_vectors():
    adapter = _embedding_adapter()
    vectors = adapter.embed([
        "Expense claims over USD 500 need two independent manager approvals.",
        "Supplier invoices are due 30 days after receipt and validation.",
    ])

    assert len(vectors) == 2
    for vector in vectors:
        assert len(vector) == BGE_M3_DIMENSION
        assert all(math.isfinite(value) for value in vector)
        norm = sum(value * value for value in vector) ** 0.5
        assert norm == pytest.approx(1.0, abs=1e-5)
    assert vectors[0] != vectors[1]


@pytest.mark.asyncio
async def test_live_postgres_has_current_migrations_and_pgvector():
    vector_literal = "[" + ",".join(["0"] * BGE_M3_DIMENSION) + "]"
    async with async_engine.connect() as connection:
        result = await connection.execute(text("""
            SELECT current_database() AS database_name,
                   (SELECT extversion FROM pg_extension WHERE extname = 'vector') AS vector_version,
                   (SELECT version_num FROM alembic_version LIMIT 1) AS migration,
                   to_regclass('public.idx_knowledge_chunks_embedding_hnsw') IS NOT NULL AS has_hnsw
        """))
        state = result.mappings().one()
        dimensions = await connection.scalar(
            text("SELECT vector_dims(CAST(:embedding AS vector))"),
            {"embedding": vector_literal},
        )

    assert state["database_name"] == settings.POSTGRES_DB
    assert state["vector_version"]
    assert state["migration"] == "0008_human_review_comments"
    assert state["has_hnsw"] is True
    assert dimensions == BGE_M3_DIMENSION

    # Verify that pgvector computes meaningful nearest-neighbor order on this
    # PostgreSQL instance rather than only checking that the extension exists.
    async with async_engine.begin() as connection:
        await connection.execute(text(
            "CREATE TEMP TABLE phase17_vector_probe "
            "(id integer PRIMARY KEY, embedding vector(1024)) ON COMMIT DROP"
        ))
        vectors = [
            (1, "[1," + ",".join(["0"] * (BGE_M3_DIMENSION - 1)) + "]"),
            (2, "[0,1," + ",".join(["0"] * (BGE_M3_DIMENSION - 2)) + "]"),
            (3, "[0.8,0.6," + ",".join(["0"] * (BGE_M3_DIMENSION - 2)) + "]"),
        ]
        for item_id, vector in vectors:
            await connection.execute(
                text("INSERT INTO phase17_vector_probe (id, embedding) VALUES (:id, CAST(:vector AS vector))"),
                {"id": item_id, "vector": vector},
            )
        query = "[1," + ",".join(["0"] * (BGE_M3_DIMENSION - 1)) + "]"
        ranked = (await connection.execute(text(
            "SELECT id FROM phase17_vector_probe "
            "ORDER BY embedding <=> CAST(:query AS vector) LIMIT 3"
        ), {"query": query})).scalars().all()
    assert ranked == [1, 3, 2]


@pytest.mark.asyncio
async def test_live_knowledge_service_ingests_with_bge_and_searches(
    db_session, test_org, tmp_path
):
    adapter = _embedding_adapter()
    source = await KnowledgeService.create_source(
        db=db_session,
        org_id=test_org.id,
        source_in=KnowledgeSourceCreate(
            name="Live synthetic policy evaluation",
            source_type="POLICY",
        ),
    )
    storage = LocalFileStorage(tmp_path)
    text = _sample_policy()
    document = await KnowledgeService.upload_document(
        db=db_session,
        source_id=source.id,
        org_id=test_org.id,
        file_bytes=text.encode("utf-8"),
        filename="expense_approval.txt",
        title="Synthetic expense approval policy",
        document_version="live-test-v1",
        storage=storage,
    )
    ingested = await KnowledgeService.ingest_document(
        db_session, document.id, test_org.id, storage, adapter
    )

    assert ingested.status == KnowledgeDocumentStatus.INGESTED.value
    assert ingested.chunk_count and ingested.chunk_count > 0
    response = await KnowledgeService.search_knowledge(
        db_session,
        test_org.id,
        KnowledgeSearchRequest(query="How many approvers are needed for a large expense?", top_k=3),
        adapter,
    )
    assert response.results
    assert all(item.knowledge_document_id == document.id for item in response.results)


@pytest.mark.asyncio
async def test_live_postgres_policy_retrieval_recall_at_three(tmp_path):
    """Score labeled policy retrieval through Cloudflare BGE-M3 and real pgvector."""
    adapter = _embedding_adapter()
    manifest = json.loads((EVALUATION_ROOT.parent.parent / "phase17_evaluation" / "manifest.json").read_text(encoding="utf-8"))
    data_root = EVALUATION_ROOT.parent.parent / "phase17_evaluation"
    organization_id = uuid.uuid4()
    async with AsyncSessionLocal() as db:
        organization = Organization(
            id=organization_id,
            name=f"Phase 17 retrieval evaluation {organization_id.hex[:8]}",
            slug=f"phase17-retrieval-{organization_id.hex[:12]}",
            status="active", settings={"currency": "USD"}, is_active=True,
        )
        db.add(organization)
        await db.commit()
        try:
            source = await KnowledgeService.create_source(
                db=db, org_id=organization_id,
                source_in=KnowledgeSourceCreate(name="Fictional Phase 17 policies", source_type="POLICY"),
            )
            storage = LocalFileStorage(tmp_path)
            for item in manifest["policies"]:
                relative_path = item["file"]
                policy_path = data_root / relative_path
                document = await KnowledgeService.upload_document(
                    db=db, source_id=source.id, org_id=organization_id,
                    file_bytes=policy_path.read_bytes(), filename=policy_path.name,
                    title=policy_path.name, document_version="phase17-v1", storage=storage,
                )
                await KnowledgeService.ingest_document(db, document.id, organization_id, storage, adapter)

            reciprocal_ranks = []
            for item in manifest["retrieval_questions"]:
                response = await KnowledgeService.search_knowledge(
                    db, organization_id,
                    KnowledgeSearchRequest(query=item["query"], top_k=3), adapter,
                )
                matching_rank = next(
                    (rank for rank, result in enumerate(response.results, start=1)
                     if result.document_title == item["expected_source"]),
                    None,
                )
                reciprocal_ranks.append(1 / matching_rank if matching_rank else 0.0)

            recall_at_3 = sum(rank > 0 for rank in reciprocal_ranks) / len(reciprocal_ranks)
            mean_reciprocal_rank = sum(reciprocal_ranks) / len(reciprocal_ranks)
            print(
                f"Phase 17 pgvector retrieval: recall@3={recall_at_3:.3f}, "
                f"MRR={mean_reciprocal_rank:.3f}, queries={len(reciprocal_ranks)}"
            )
            assert len(reciprocal_ranks) >= 10
            assert recall_at_3 >= 0.8
        finally:
            await db.execute(delete(Organization).where(Organization.id == organization_id))
            await db.commit()


@pytest.mark.asyncio
async def test_live_groq_classifies_and_extracts_representative_synthetic_documents(monkeypatch):
    api_key = _root_env("GROQ_API_KEY")
    env_values = dotenv_values(REPOSITORY_ROOT / ".env")
    monkeypatch.setattr(settings, "GROQ_API_KEY", api_key)
    monkeypatch.setattr(
        settings,
        "GROQ_API_KEY_FALLBACK_1",
        os.getenv("GROQ_API_KEY_FALLBACK_1") or env_values.get("GROQ_API_KEY_FALLBACK_1"),
    )
    monkeypatch.setattr(
        settings,
        "GROQ_API_KEY_FALLBACK_2",
        os.getenv("GROQ_API_KEY_FALLBACK_2") or env_values.get("GROQ_API_KEY_FALLBACK_2"),
    )
    monkeypatch.setattr(
        settings,
        "GROQ_DOCUMENT_MODEL",
        os.getenv("GROQ_DOCUMENT_MODEL") or "qwen/qwen3.8-27b",
    )
    samples = [
        (
            "invoice",
            [
                "TAX INVOICE", "Invoice Number: INV-SYN-2026-041",
                "Supplier: Northwind Trading Ltd", "Invoice Date: 2026-10-01",
                "Currency: USD", "Item: Safety gloves; Quantity: 2; Unit price: 12.50; Amount: 25.00",
                "Total Due: USD 25.00",
            ],
            {
                "invoice_number": "INV-SYN-2026-041", "supplier": "Northwind Trading Ltd",
                "invoice_date": "2026-10-01", "currency": "USD", "total": 25.0,
            },
        ),
        (
            "purchase_order",
            [
                "PURCHASE ORDER", "Order Number: PO-SYN-204", "Buyer: Verifia Demo Imports",
                "Supplier: Alpine Components GmbH", "Order Date: 2026-09-28", "Currency: EUR",
                "Item: Valve assembly; Quantity: 4", "Total: EUR 680.00",
            ],
            {
                "order_number": "PO-SYN-204", "buyer": "Verifia Demo Imports",
                "supplier": "Alpine Components GmbH", "order_date": "2026-09-28",
                "currency": "EUR", "total": 680.0,
            },
        ),
        (
            "packing_list",
            [
                "PACKING LIST", "Shipment Reference: SHP-SYN-781",
                "Shipper: Alpine Components GmbH", "Consignee: Verifia Demo Imports",
                "Package Count: 3", "Gross Weight: 18.5 kg", "Net Weight: 16.0 kg",
                "Items: Valve assemblies, 12 units",
            ],
            {
                "shipment_reference": "SHP-SYN-781", "shipper": "Alpine Components GmbH",
                "consignee": "Verifia Demo Imports", "package_count": 3,
                "gross_weight": 18.5, "net_weight": 16.0,
            },
        ),
    ]
    adapter = GroqJsonAdapter()
    expected_total = 0
    exact_matches = 0
    for document_class, lines, expected_fields in samples:
        parsed = ParsedDocument(
            source_format="txt",
            parser_name="generated-live-fixture",
            parser_version="1",
            blocks=[
                ContentBlock(kind="text", text=line, source={"line": index + 1})
                for index, line in enumerate(lines)
            ],
        )
        prediction = await classify_document(
            parsed, catalog=DEFAULT_DOCUMENT_CLASSES, adapter=adapter
        )
        assert prediction.class_id == document_class
        extracted = await extract_document_fields(
            parsed, document_class=document_class, configuration={}, adapter=adapter
        )
        for field_name, expected_value in expected_fields.items():
            expected_total += 1
            field = extracted.fields[field_name]
            if isinstance(expected_value, float):
                assert float(field.value) == pytest.approx(expected_value)
            else:
                assert re.sub(r"\s+", " ", str(field.value)).strip().casefold() == str(expected_value).casefold()
            assert field.citations
            exact_matches += 1

    assert len(samples) == 3
    assert exact_matches == expected_total == 17


def test_live_tesseract_reads_sroie_sample_with_ground_truth():
    configured_tesseract = settings.TESSERACT_CMD
    if configured_tesseract:
        executable_available = (
            Path(configured_tesseract).is_file()
            or shutil.which(configured_tesseract) is not None
        )
    else:
        executable_available = shutil.which("tesseract") is not None
    if not executable_available:
        pytest.skip("Tesseract executable is not installed")
    image_path = EVALUATION_ROOT / "sroie" / "0000.jpg"
    annotation_path = EVALUATION_ROOT / "sroie" / "0000.json"
    if not image_path.is_file() or not annotation_path.is_file():
        pytest.skip("SROIE evaluation image and annotation are not installed")

    import json

    annotation = json.loads(annotation_path.read_text(encoding="utf-8"))
    content = image_path.read_bytes()
    parsed = parse_document_content(image_path.name, content)
    processed = apply_ocr(image_path.name, content, parsed)
    recognized = re.sub(r"\s+", " ", processed.plain_text).casefold()
    company = re.sub(r"\s+", " ", annotation["entities"]["company"]).casefold()
    assert processed.pages_requiring_ocr == []
    expected_tokens = set(re.findall(r"[a-z0-9]+", company))
    recognized_tokens = set(re.findall(r"[a-z0-9]+", recognized))
    assert expected_tokens
    assert len(expected_tokens & recognized_tokens) / len(expected_tokens) >= 0.5
