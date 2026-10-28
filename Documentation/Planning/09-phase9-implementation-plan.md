# VerifiaAI — Phase 9 Implementation Plan: Knowledge / RAG

*Initial repository baseline: 63 backend tests passed before Phase 9 implementation.*
*Model Selection Locked: **`BAAI/bge-m3`** (1024 dimensions, 8,192 token context window, SOTA Multilingual).*

> **Implementation outcome (updated 2026-10-06):** Phase 9 code is implemented. Cloudflare Workers AI using `@cf/baai/bge-m3` is now the configured API adapter; Hugging Face, local `sentence-transformers`, and deterministic test adapters remain available. Mocked provider-adapter tests are included in the 97-test backend suite. A live synthetic smoke request succeeded and returned a normalized 1024-dimensional vector; representative-corpus retrieval quality, applying the migration to live PostgreSQL, and real pgvector ranking remain unverified. The historical plan below is retained with these implementation differences called out.

---

## 1. Executive Summary

Phase 9 implements the **Knowledge / RAG (Retrieval-Augmented Generation) layer**.

Its goal: give agents and verification processes access to organization-scoped policies, SOPs, and regulatory guidelines through **semantic vector search backed by pgvector** — without treating retrieved text as authoritative business state.

Phase 9 delivers:

1. A **document ingestion pipeline**: parse a policy/SOP file → chunk text → generate embeddings via `BAAI/bge-m3` → store in `knowledge_chunks`.
2. A **semantic retrieval service**: given a query string, return the top-k most relevant chunks within the same organization, with source references.
3. A **correct API surface**: the existing `knowledge` endpoints are all broken (service/model mismatch); they are replaced with clean, production-grade endpoints.
4. **Organization isolation**: every retrieval is hard-scoped by `organization_id` at both SQL and service layers.
5. A **pgvector HNSW index**: on `Vector(1024)` for efficient ANN similarity search.
6. **Tests**: unit tests for chunking/embedding logic; integration tests for ingestion and retrieval (using `FakeEmbeddingAdapter`).

Phase 9 does **not** implement agents. It is the infrastructure that agents (Phases 10–13) consume.

---

## 2. Repository State After Phase 8

### Architecture

```
API Layer       ── FastAPI routers (thin handlers, delegate to services)
Domain Services ── CaseService, ProcessService, VerificationService,
                   DocumentProcessingService, KnowledgeService (BROKEN stub)
Domain Models   ── SQLAlchemy 2.0 ORM (all 45+ tables already migrated)
Infrastructure  ── PostgreSQL+pgvector, Redis (queue stub), LocalFileStorage
```

### Phase Completion

| Phase | Status |
|---|---|
| 1 — Foundation | ✅ Done |
| 2 — Database (all 45+ tables) | ✅ Done (migrations 0001–0005) |
| 3 — Domain Services & API | ✅ Done |
| 4 — Workflow Engine | ✅ Done |
| 5 — Rules & Verification Engine | ✅ Done |
| 6 — Tool Gateway | 🟡 Partial (gateway built; agents not wired) |
| 7 — Storage & Document Upload | ✅ Done |
| 8 — Document Intelligence | 🟡 Partial (core done; live OCR unvalidated) |
| **9 — Knowledge / RAG** | ⏳ **This plan** |
| 10–26 — Agents, frontend, security | ⏳ Not started |

### Current `knowledge` Domain — What Exists (and Why it Fails)

- `domain/knowledge/models.py` — **Model matches schema docs**: `KnowledgeSource` → `KnowledgeDocument` → `KnowledgeChunk`. `KnowledgeChunk` has an initial `Vector(1536)` column created by migration `0001`.
- `domain/knowledge/service.py` — **Critically broken**: references `KnowledgeDocument.organization_id`, `.content`, `.category`, `.tags`, `.metadata_payload` — **none of which exist on the model**. The service cannot function.
- `domain/knowledge/schemas.py` — **Broken**: references the same non-existent fields.
- `domain/knowledge/router.py` — Exposes the broken service.
- `ai/embeddings/`, `ai/retrieval/` — Empty placeholders at the time of the Phase 9 review; the unused root `ai/` scaffold was later removed because active embedding and retrieval code lives under `backend/app/`.
- `infrastructure/llm/__init__.py` — 3 bytes (empty stub).
- `requirements.txt` — `sentence-transformers` is **not listed** despite being referenced in `settings.EMBEDDING_MODEL_NAME`.

---

## 3. Critical Discrepancies Found & Solutions

### DISCREPANCY 1 — Service vs. Model Mismatch (CRITICAL)

* **Model** (`knowledge/models.py`): `KnowledgeDocument` has `knowledge_source_id`, `title`, `document_version`, `storage_reference`, `content_hash`.
* **Service** (`knowledge/service.py`): References `.organization_id`, `.content`, `.category`, `.tags`, `.metadata_payload`.
* **Resolution**: Full rewrite of `service.py`, `schemas.py`, and `router.py` to align with the canonical database schema.

---

### DISCREPANCY 2 — Embedding Dimension & Model Decision (RESOLVED)

* **Previous Schema**: `knowledge_chunks.embedding Vector(1536)` (placeholder).
* **Decision**: Selected **`BAAI/bge-m3`** as the core embedding model:
  * **Dimensions**: `1024`
  * **Context Window**: `8,192 tokens` (supports long-context compliance documents)
  * **Multilingual**: SOTA across 100+ languages (native Arabic and English support)
  * **Hybrid Search Ready**: Generates dense + sparse representations
  * **Execution**: the configured API adapter uses Cloudflare Workers AI; Hugging Face API and local adapters remain available. Remote mode transmits query/document text to the configured provider.
* **Database Resolution**: Migration `0006_knowledge_rag` will update `knowledge_chunks.embedding` to `Vector(1024)`.
* **Future Upgrade Path**: The modular `EmbeddingAdapter` architecture allows dropping in custom fine-tuned weights (e.g., trained on Kaggle using Qwen3 / LoRA) with zero alterations to core services.

---

### DISCREPANCY 3 — Tenant Isolation Path

* **Current Model**: `KnowledgeSource` has `organization_id`. `KnowledgeDocument` and `KnowledgeChunk` do not have a direct `organization_id`.
* **Impact**: ANN similarity search queries would require joining through 2 tables.
* **Resolution**: Add denormalized `organization_id` to `knowledge_chunks` in migration `0006`. Populated at ingestion time for fast, single-table tenant isolation filtering before ANN ordering.

---

### DISCREPANCY 4 — Missing Dependencies

* `sentence-transformers` is missing from `requirements.txt`.
* **Resolution**: Add `sentence-transformers>=3.0.0` and `FlagEmbedding>=1.2.0` to `requirements.txt`.

---

## 4. Phase 9 Scope

### In Scope

1. Fix knowledge domain stub — rewrite `service.py`, `schemas.py`, `router.py` to match actual models.
2. Ingestion pipeline: parse → chunk → embed via `BAAI/bge-m3` → bulk-insert `knowledge_chunks`.
3. `TextChunker` (sentence-aware, configurable chunk size and overlap, Arabic & English boundary detection).
4. `EmbeddingAdapter` (`EmbeddingAdapter` protocol + `BGEM3EmbeddingAdapter` + `FakeEmbeddingAdapter` for tests).
5. Semantic search: pgvector cosine ANN on 1024-dim vectors, org-scoped, metadata-filtered.
6. Source reference in every search result (document title, source name, chunk index, similarity score).
7. Organization isolation at both SQL query and service layer.
8. CRUD API for `KnowledgeSource` and `KnowledgeDocument`.
9. Alembic migration `0006_knowledge_rag` (`Vector(1024)`, `organization_id`, HNSW index, status columns).
10. `sentence-transformers` added to `requirements.txt`.
11. ≥ 19 new tests (unit + integration + security).

### Out of Scope

- Agent integration (Phases 10–13).
- Tool Gateway registration of `search_knowledge` (completed in the Phase 10 integration work).
- Durable background worker (inline ingestion in Phase 9, same as Phase 8 document processing).
- Frontend UI (Phase 18).

---

## 5. Proposed Architecture

### Ingestion Pipeline

```
POST /knowledge/sources/{id}/documents   (multipart upload)
  ↓
Validate file type + size
  ↓
SHA-256 hash → dedup check (same hash + same source → return existing)
  ↓
Store binary in StorageBackend (LocalFileStorage)
  ↓
Create KnowledgeDocument row (status=PENDING)
  ↓ (trigger via POST /knowledge/documents/{id}/ingest)
parse_document_content()  [Phase 8 parsers — PDF, DOCX, TXT, CSV]
  ↓
TextChunker  (configurable chunk size + overlap, sentence-aware)
  ↓
EmbeddingAdapter.embed(chunk_texts)  [BAAI/bge-m3, 1024 dimensions]
  ↓
DELETE knowledge_chunks WHERE knowledge_document_id = X  [idempotent re-ingest]
  ↓
db.add_all(knowledge_chunks)  [bulk insert, single transaction with organization_id]
  ↓
KnowledgeDocument.status → INGESTED, chunk_count = N, ingested_at = now
  ↓
EventRecord: KNOWLEDGE_DOCUMENT_INGESTED
```

### Retrieval Pipeline

```
POST /knowledge/search
  ↓
EmbeddingAdapter.embed([query])  [1024-dim query vector]
  ↓
SELECT kc.*, kd.title, ks.name, ks.source_type,
       1 - (kc.embedding <=> :q_vec) AS similarity_score
FROM knowledge_chunks kc
JOIN knowledge_documents kd ON kd.id = kc.knowledge_document_id
JOIN knowledge_sources ks   ON ks.id = kd.knowledge_source_id
WHERE kc.organization_id = :org_id               ← always applied (Tenant Isolation)
  AND (:source_type IS NULL OR ks.source_type = :source_type)
  AND (:source_ids IS NULL  OR ks.id = ANY(:source_ids))
ORDER BY kc.embedding <=> :q_vec
LIMIT :top_k
  ↓
Return KnowledgeSearchResponse { results, query, top_k }
```

### Key Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Embedding Model | `BAAI/bge-m3` (1024 dims) | SOTA multilingual (Arabic+English), 8192-token context, hybrid search support |
| EmbeddingService injectable | Yes — Protocol + Fake for tests | No heavy model downloads in CI/test runs |
| Chunking | Sentence-aware with overlap | Clean boundaries across Arabic & English |
| Ingestion timing | Inline (sync) | Consistent with Phase 8 pattern; queue stub not a real worker |
| Bulk insert | `db.add_all()` single transaction | Fast atomic chunk writes |
| pgvector index | HNSW (`vector_cosine_ops`, m=16, ef_construction=64) | Fast query-time search on 1024-dim vectors |
| org_id in chunks | Denormalized column | Single-table WHERE before ANN; avoids JOIN on every search |

---

## 6. Database Changes — Migration `0006_knowledge_rag`

This migration updates the schema to support `BAAI/bge-m3` (1024-dim) and strict multi-tenancy.

### DDL (upgrade)

```sql
-- Step 1: clear placeholder/stale data
DELETE FROM knowledge_chunks;

-- Step 2: update embedding column to Vector(1024) for BGE-M3
ALTER TABLE knowledge_chunks DROP COLUMN IF EXISTS embedding;
ALTER TABLE knowledge_chunks ADD COLUMN embedding vector(1024);

-- Step 3: denormalized organization isolation column
ALTER TABLE knowledge_chunks
  ADD COLUMN organization_id UUID NOT NULL
  REFERENCES organizations(id) ON DELETE CASCADE;

CREATE INDEX idx_knowledge_chunks_org_id ON knowledge_chunks (organization_id);

-- Step 4: HNSW index for ANN cosine search
CREATE INDEX idx_knowledge_chunks_embedding_hnsw
  ON knowledge_chunks USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

-- Step 5: ingestion lifecycle columns on knowledge_documents
ALTER TABLE knowledge_documents
  ADD COLUMN status      VARCHAR(40) NOT NULL DEFAULT 'PENDING',
  ADD COLUMN chunk_count INTEGER,
  ADD COLUMN ingested_at TIMESTAMPTZ;
```

### DDL (downgrade)

```sql
DROP INDEX IF EXISTS idx_knowledge_chunks_embedding_hnsw;
DROP INDEX IF EXISTS idx_knowledge_chunks_org_id;
ALTER TABLE knowledge_chunks DROP COLUMN IF EXISTS organization_id;
ALTER TABLE knowledge_chunks DROP COLUMN IF EXISTS embedding;
ALTER TABLE knowledge_chunks ADD COLUMN embedding vector(1536);
ALTER TABLE knowledge_documents DROP COLUMN IF EXISTS ingested_at;
ALTER TABLE knowledge_documents DROP COLUMN IF EXISTS chunk_count;
ALTER TABLE knowledge_documents DROP COLUMN IF EXISTS status;
```

---

## 7. API Changes

### Endpoints Surface

#### 1. Knowledge Source Management
* `POST /api/v1/knowledge/sources` (Create source, Role: MANAGER/ADMIN)
* `GET /api/v1/knowledge/sources` (List sources, org-scoped, Role: EMPLOYEE+)
* `GET /api/v1/knowledge/sources/{source_id}` (Get source by ID, Role: EMPLOYEE+)
* `PATCH /api/v1/knowledge/sources/{source_id}` (Update source, Role: MANAGER/ADMIN)

#### 2. Knowledge Document Management & Ingestion
* `POST /api/v1/knowledge/sources/{source_id}/documents` (Upload document, multipart, Role: MANAGER/ADMIN)
* `POST /api/v1/knowledge/documents/{document_id}/ingest` (Run ingestion pipeline, Role: MANAGER/ADMIN)
* `GET /api/v1/knowledge/sources/{source_id}/documents` (List documents in source, Role: EMPLOYEE+)
* `GET /api/v1/knowledge/documents/{document_id}` (Get document details & ingestion status, Role: EMPLOYEE+)
* `DELETE /api/v1/knowledge/documents/{document_id}` (Delete doc & cascade chunks, Role: MANAGER/ADMIN)

#### 3. Semantic Search
* `POST /api/v1/knowledge/search` (Search knowledge base, Role: EMPLOYEE+)
  ```json
  {
    "query": "What are the AML verification guidelines for high risk clients?",
    "source_type": "POLICY",
    "top_k": 5
  }
  ```

---

## 8. Service / Domain Design

### 1. `TextChunker` (`domain/knowledge/chunker.py`)
Sentence-aware chunking supporting punctuation boundaries in both Latin and Arabic scripts (`.`, `!`, `?`, `؛`, `\n\n`), with customizable window size and overlap.

### 2. `EmbeddingAdapter` (`infrastructure/llm/embedding.py`)
```python
class EmbeddingAdapter(Protocol):
    def embed(self, texts: List[str]) -> List[List[float]]: ...
    @property
    def dimension(self) -> int: ...

class BGEM3EmbeddingAdapter:
    """Production adapter using BAAI/bge-m3 (1024 dimensions)."""
    DIMENSION = 1024
    def __init__(self, model_name: str = "BAAI/bge-m3"): ...
    def embed(self, texts: List[str]) -> List[List[float]]: ...
    @property
    def dimension(self) -> int: return self.DIMENSION

class FakeEmbeddingAdapter:
    """Deterministic vectors for unit/integration tests without downloading models."""
    def __init__(self, dimension: int = 1024): ...
    def embed(self, texts: List[str]) -> List[List[float]]: ...
    @property
    def dimension(self) -> int: return self.dimension
```

### 3. `KnowledgeService` (`domain/knowledge/service.py`)
Rewritten with full multi-tenancy validation, atomic ingestion, and search score calculation.

---

## 9. Security & Multi-Tenancy

1. **Tenant Isolation**: `org_id = current_user.organization_id` is extracted from the JWT token and enforced at:
   - Route layer
   - Service layer
   - SQL query layer (`WHERE kc.organization_id = :org_id`)
2. **IDOR Protection**: Requests for non-existent or cross-tenant resources return `404 Not Found` (never revealing resource existence).
3. **Data Privacy**: Tenant filters apply to retrieval. In the default Hugging Face API mode, source text/query text is sent to the configured external inference provider; use the local adapter where that transfer is not permitted. Do not describe default operation as local-only.

---

## 10. File-by-File Plan

### Files to CREATE
1. `backend/app/domain/knowledge/chunker.py` — `TextChunker` & `ChunkResult`.
2. `backend/app/infrastructure/llm/embedding.py` — `EmbeddingAdapter`, `BGEM3EmbeddingAdapter`, `FakeEmbeddingAdapter`.
3. `backend/alembic/versions/0006_knowledge_rag.py` — Vector(1024) migration, index, and columns.
4. `backend/tests/test_knowledge_rag.py` — Comprehensive unit, integration, and security test suite.

### Files to MODIFY
1. `backend/app/domain/knowledge/models.py` — Add `KnowledgeDocumentStatus`, update models.
2. `backend/app/domain/knowledge/schemas.py` — Full rewrite to match actual models.
3. `backend/app/domain/knowledge/service.py` — Full rewrite (10 methods).
4. `backend/app/domain/knowledge/router.py` — Full rewrite (9 endpoints).
5. `backend/app/domain/knowledge/__init__.py` — Clean exports.
6. `backend/app/infrastructure/llm/__init__.py` — Export adapters.
7. `backend/requirements.txt` — Add `sentence-transformers>=3.0.0` and `FlagEmbedding>=1.2.0`.
8. `backend/app/core/config.py` — Set default `EMBEDDING_MODEL_NAME = "BAAI/bge-m3"`.

---

## 11. Implementation Order

```
Step 1  — Write and review migration 0006_knowledge_rag.py (Vector 1024)
Step 2  — Update ORM models (models.py): new columns, KnowledgeDocumentStatus enum
Step 3  — Implement TextChunker (chunker.py)
Step 4  — Implement EmbeddingAdapter (infrastructure/llm/embedding.py) + update config & requirements
Step 5  — Rewrite schemas (schemas.py)
Step 6  — Rewrite KnowledgeService (service.py)
Step 7  — Rewrite router (router.py)
Step 8  — Update __init__.py exports
Step 9  — Write tests (test_knowledge_rag.py) with FakeEmbeddingAdapter
Step 10 — Run test suite: all 63 pre-existing tests plus at least 19 Phase 9 tests must pass
```

---

## 12. Production Definition of Done

- [x] Migration `0006_knowledge_rag` created; offline SQL generation succeeds. Online application remains unverified here.
- [x] Vector dimensions set to `Vector(1024)` matching `BAAI/bge-m3`.
- [x] `knowledge_chunks.organization_id` indexed and enforced in the retrieval query.
- [x] HNSW cosine index defined in the migration.
- [x] Document ingestion pipeline (upload → parse → chunk → embed → store) covered by tests.
- [x] At least 19 phase-specific tests pass: 21 Phase 9 tests; the full 92-test suite passes.
- [ ] Apply migration and exercise HNSW ranking against a live PostgreSQL/pgvector instance.
