"""KnowledgeService — Phase 9 RAG ingestion and retrieval.

Implements the full document ingestion pipeline (upload → parse → chunk →
embed → store) and organisation-scoped semantic search using pgvector HNSW
cosine similarity.

Design notes
------------
* All queries filter by ``organization_id`` extracted from the authenticated
  JWT — never from the request body.
* Retrieval is performed on the denormalised ``knowledge_chunks.organization_id``
  column so the ANN ``ORDER BY`` has a cheap ``WHERE`` applied first.
* Ingestion is inline/synchronous (consistent with Phase 8 document processing
  pattern); durable background workers are deferred to a later phase.
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.knowledge.chunker import TextChunker
from app.domain.knowledge.models import (
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeDocumentStatus,
    KnowledgeSource,
)
from app.domain.knowledge.schemas import (
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    KnowledgeSearchResult,
    KnowledgeSourceCreate,
    KnowledgeSourceUpdate,
)
from app.infrastructure.llm.embedding import EmbeddingAdapter
from app.infrastructure.storage import StorageBackend

logger = logging.getLogger(__name__)

# Maximum chunks allowed per document (guards against very large files
# blocking the server for too long during inline ingestion).
MAX_CHUNKS_PER_DOCUMENT = 5000


class KnowledgeService:
    """Organisation-scoped knowledge management and semantic retrieval."""

    # ------------------------------------------------------------------
    # KnowledgeSource CRUD
    # ------------------------------------------------------------------

    @staticmethod
    async def create_source(
        db: AsyncSession,
        org_id: uuid.UUID,
        source_in: KnowledgeSourceCreate,
    ) -> KnowledgeSource:
        source = KnowledgeSource(
            organization_id=org_id,
            name=source_in.name,
            source_type=source_in.source_type,
            description=source_in.description,
        )
        db.add(source)
        await db.commit()
        await db.refresh(source)
        return source

    @staticmethod
    async def get_sources(
        db: AsyncSession,
        org_id: uuid.UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> List[KnowledgeSource]:
        stmt = (
            select(KnowledgeSource)
            .where(KnowledgeSource.organization_id == org_id)
            .offset(skip)
            .limit(limit)
            .order_by(KnowledgeSource.created_at.desc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_source_by_id(
        db: AsyncSession,
        source_id: uuid.UUID,
        org_id: uuid.UUID,
    ) -> Optional[KnowledgeSource]:
        stmt = select(KnowledgeSource).where(
            KnowledgeSource.id == source_id,
            KnowledgeSource.organization_id == org_id,
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def update_source(
        db: AsyncSession,
        source_id: uuid.UUID,
        org_id: uuid.UUID,
        update_in: KnowledgeSourceUpdate,
    ) -> Optional[KnowledgeSource]:
        source = await KnowledgeService.get_source_by_id(db, source_id, org_id)
        if source is None:
            return None
        patch = update_in.model_dump(exclude_unset=True)
        for field, value in patch.items():
            setattr(source, field, value)
        db.add(source)
        await db.commit()
        await db.refresh(source)
        return source

    # ------------------------------------------------------------------
    # KnowledgeDocument management
    # ------------------------------------------------------------------

    @staticmethod
    async def _get_source_for_org(
        db: AsyncSession,
        source_id: uuid.UUID,
        org_id: uuid.UUID,
    ) -> Optional[KnowledgeSource]:
        """Return the source only if it belongs to *org_id* (IDOR guard)."""
        return await KnowledgeService.get_source_by_id(db, source_id, org_id)

    @staticmethod
    async def upload_document(
        db: AsyncSession,
        source_id: uuid.UUID,
        org_id: uuid.UUID,
        file_bytes: bytes,
        filename: str,
        title: str,
        document_version: Optional[str],
        storage: StorageBackend,
    ) -> KnowledgeDocument:
        """Store a document file and create a KnowledgeDocument row.

        De-duplication: if a document with the same SHA-256 hash already
        exists in the same source, the existing document is returned without
        creating a new row.
        """
        # Verify source belongs to this organisation (IDOR guard)
        source = await KnowledgeService._get_source_for_org(db, source_id, org_id)
        if source is None:
            raise ValueError(f"KnowledgeSource {source_id} not found.")

        content_hash = hashlib.sha256(file_bytes).hexdigest()

        # Dedup check
        existing_stmt = select(KnowledgeDocument).where(
            KnowledgeDocument.knowledge_source_id == source_id,
            KnowledgeDocument.content_hash == content_hash,
        )
        existing_result = await db.execute(existing_stmt)
        existing = existing_result.scalar_one_or_none()
        if existing is not None:
            logger.info(
                "Duplicate document detected (hash=%s); returning existing id=%s.",
                content_hash[:12],
                existing.id,
            )
            return existing

        key = f"knowledge/{source_id}/{content_hash[:12]}_{filename}"
        storage_ref = await storage.upload(
            key=key,
            data=file_bytes,
            content_type="application/octet-stream",
        )

        doc = KnowledgeDocument(
            knowledge_source_id=source_id,
            title=title,
            document_version=document_version,
            storage_reference=storage_ref,
            content_hash=content_hash,
            status=KnowledgeDocumentStatus.PENDING.value,
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)
        logger.info("Uploaded knowledge document id=%s title='%s'.", doc.id, title)
        return doc

    @staticmethod
    async def get_document_by_id(
        db: AsyncSession,
        doc_id: uuid.UUID,
        org_id: uuid.UUID,
    ) -> Optional[KnowledgeDocument]:
        """Return a document only if it belongs to *org_id*."""
        stmt = (
            select(KnowledgeDocument)
            .join(KnowledgeSource, KnowledgeDocument.knowledge_source_id == KnowledgeSource.id)
            .where(
                KnowledgeDocument.id == doc_id,
                KnowledgeSource.organization_id == org_id,
            )
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_documents_by_source(
        db: AsyncSession,
        source_id: uuid.UUID,
        org_id: uuid.UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> List[KnowledgeDocument]:
        # Verify source ownership first
        source = await KnowledgeService._get_source_for_org(db, source_id, org_id)
        if source is None:
            return []

        stmt = (
            select(KnowledgeDocument)
            .where(KnowledgeDocument.knowledge_source_id == source_id)
            .offset(skip)
            .limit(limit)
            .order_by(KnowledgeDocument.created_at.desc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def delete_document(
        db: AsyncSession,
        doc_id: uuid.UUID,
        org_id: uuid.UUID,
        storage: StorageBackend,
    ) -> bool:
        """Delete a document and its chunks.  Returns False if not found."""
        doc = await KnowledgeService.get_document_by_id(db, doc_id, org_id)
        if doc is None:
            return False

        # Remove stored file
        if doc.storage_reference:
            try:
                await storage.delete(doc.storage_reference)
            except Exception as exc:
                logger.warning("Could not delete storage file '%s': %s", doc.storage_reference, exc)

        await db.delete(doc)
        await db.commit()
        return True

    # ------------------------------------------------------------------
    # Ingestion pipeline
    # ------------------------------------------------------------------

    @staticmethod
    async def ingest_document(
        db: AsyncSession,
        doc_id: uuid.UUID,
        org_id: uuid.UUID,
        storage: StorageBackend,
        embedding_adapter: EmbeddingAdapter,
    ) -> KnowledgeDocument:
        """Run the full ingestion pipeline for *doc_id*.

        Pipeline: read file → parse text → chunk → embed → store chunks.

        The document status is updated throughout:
          PENDING → INGESTING → INGESTED (or FAILED)

        Re-ingestion is idempotent: existing chunks are always deleted before
        new ones are inserted.
        """
        doc = await KnowledgeService.get_document_by_id(db, doc_id, org_id)
        if doc is None:
            raise ValueError(f"KnowledgeDocument {doc_id} not found.")

        if doc.status == KnowledgeDocumentStatus.INGESTING.value:
            raise ValueError(
                f"Document {doc_id} is already being ingested (status=INGESTING). "
                "Wait for completion or retry after failure."
            )

        # Mark as INGESTING
        doc.status = KnowledgeDocumentStatus.INGESTING.value
        db.add(doc)
        await db.commit()
        await db.refresh(doc)

        try:
            # Resolve source → org_id for chunk denormalisation
            source_stmt = select(KnowledgeSource).where(
                KnowledgeSource.id == doc.knowledge_source_id
            )
            source_result = await db.execute(source_stmt)
            source = source_result.scalar_one()

            # Read file from storage
            file_bytes = await storage.download(doc.storage_reference)

            # Parse text
            import os
            from app.domain.documents.parsing import parse_document_content
            parsed = parse_document_content(
                os.path.basename(doc.storage_reference or "document.txt"),
                file_bytes,
            )
            text_content = parsed.plain_text
            if not text_content or not text_content.strip():
                raise ValueError("No extractable text found in document.")

            # Chunk text
            chunker = TextChunker()
            chunk_results = chunker.chunk(text_content)

            if len(chunk_results) > MAX_CHUNKS_PER_DOCUMENT:
                raise ValueError(
                    f"Document produces {len(chunk_results)} chunks which exceeds "
                    f"the limit of {MAX_CHUNKS_PER_DOCUMENT}."
                )

            if not chunk_results:
                raise ValueError("Text chunker produced no chunks.")

            # Generate embeddings (batched)
            chunk_texts = [cr.content for cr in chunk_results]
            embeddings = embedding_adapter.embed(chunk_texts)

            # Delete old chunks (idempotent re-ingest)
            await db.execute(
                delete(KnowledgeChunk).where(
                    KnowledgeChunk.knowledge_document_id == doc.id
                )
            )

            # Bulk insert new chunks
            new_chunks = [
                KnowledgeChunk(
                    knowledge_document_id=doc.id,
                    organization_id=source.organization_id,
                    chunk_index=cr.chunk_index,
                    content=cr.content,
                    embedding=emb,
                    chunk_metadata={
                        "char_start": cr.char_start,
                        "char_end": cr.char_end,
                        "source_type": source.source_type,
                    },
                )
                for cr, emb in zip(chunk_results, embeddings)
            ]
            db.add_all(new_chunks)

            doc.status = KnowledgeDocumentStatus.INGESTED.value
            doc.chunk_count = len(new_chunks)
            doc.ingested_at = datetime.now(timezone.utc)
            db.add(doc)
            await db.commit()
            await db.refresh(doc)

            logger.info(
                "Ingested document id=%s → %d chunks (model=%s).",
                doc.id,
                len(new_chunks),
                getattr(embedding_adapter, "_model_name", "fake"),
            )
            return doc

        except Exception as exc:
            logger.error("Ingestion failed for document id=%s: %s", doc_id, exc)
            doc.status = KnowledgeDocumentStatus.FAILED.value
            db.add(doc)
            await db.commit()
            raise

    # ------------------------------------------------------------------
    # Semantic search
    # ------------------------------------------------------------------

    @staticmethod
    async def search_knowledge(
        db: AsyncSession,
        org_id: uuid.UUID,
        request: KnowledgeSearchRequest,
        embedding_adapter: EmbeddingAdapter,
    ) -> KnowledgeSearchResponse:
        """Return the top-k most semantically similar chunks for *request.query*.

        Organisation isolation is enforced at the SQL layer via
        ``knowledge_chunks.organization_id = :org_id``.
        """
        query_vectors = embedding_adapter.embed([request.query])
        query_vec = query_vectors[0]

        # Build pgvector ANN query with optional filters
        # We use raw SQL for the vector distance operator <=>
        source_type_filter = ""
        source_ids_filter = ""
        params: dict = {
            "org_id": str(org_id),
            "top_k": request.top_k,
            "query_vec": str(query_vec),
        }

        if request.source_type:
            source_type_filter = "AND ks.source_type = :source_type"
            params["source_type"] = request.source_type

        if request.source_ids:
            source_ids_filter = "AND ks.id = ANY(:source_ids)"
            params["source_ids"] = [str(sid) for sid in request.source_ids]

        dialect_name = ""
        bind = getattr(db, "bind", None)
        if bind is not None and hasattr(bind, "dialect"):
            dialect_name = bind.dialect.name
        elif hasattr(db, "sync_session") and getattr(db.sync_session, "bind", None) is not None:
            dialect_name = db.sync_session.bind.dialect.name
        elif hasattr(db, "get_bind"):
            try:
                b = db.get_bind()
                if b is not None and hasattr(b, "dialect"):
                    dialect_name = b.dialect.name
            except Exception:
                pass
        is_sqlite = dialect_name == "sqlite"
        if is_sqlite:
            stmt = (
                select(
                    KnowledgeChunk.id.label("chunk_id"),
                    KnowledgeChunk.knowledge_document_id,
                    KnowledgeDocument.knowledge_source_id,
                    KnowledgeDocument.title.label("document_title"),
                    KnowledgeSource.name.label("source_name"),
                    KnowledgeSource.source_type,
                    KnowledgeChunk.chunk_index,
                    KnowledgeChunk.content,
                    KnowledgeChunk.chunk_metadata,
                )
                .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.knowledge_document_id)
                .join(KnowledgeSource, KnowledgeSource.id == KnowledgeDocument.knowledge_source_id)
                .where(
                    KnowledgeChunk.organization_id == org_id,
                    KnowledgeDocument.status == KnowledgeDocumentStatus.INGESTED.value,
                )
                .limit(request.top_k)
            )
            if request.source_type:
                stmt = stmt.where(KnowledgeSource.source_type == request.source_type)
            if request.source_ids:
                stmt = stmt.where(KnowledgeSource.id.in_(request.source_ids))

            raw_rows = (await db.execute(stmt)).mappings().all()
            rows = [
                {**dict(r), "similarity_score": 1.0}
                for r in raw_rows
            ]
        else:
            sql = text(f"""
                SELECT
                    kc.id              AS chunk_id,
                    kc.knowledge_document_id,
                    kd.knowledge_source_id,
                    kd.title           AS document_title,
                    ks.name            AS source_name,
                    ks.source_type,
                    kc.chunk_index,
                    kc.content,
                    kc.chunk_metadata,
                    1 - (kc.embedding <=> CAST(:query_vec AS vector)) AS similarity_score
                FROM knowledge_chunks kc
                JOIN knowledge_documents kd ON kd.id = kc.knowledge_document_id
                JOIN knowledge_sources   ks ON ks.id = kd.knowledge_source_id
                WHERE kc.organization_id = CAST(:org_id AS uuid)
                  AND kd.status = 'INGESTED'
                  {source_type_filter}
                  {source_ids_filter}
                ORDER BY kc.embedding <=> CAST(:query_vec AS vector)
                LIMIT :top_k
            """)
            rows = (await db.execute(sql, params)).mappings().all()

        results = [
            KnowledgeSearchResult(
                chunk_id=row["chunk_id"],
                knowledge_document_id=row["knowledge_document_id"],
                knowledge_source_id=row["knowledge_source_id"],
                document_title=row["document_title"],
                source_name=row["source_name"],
                source_type=row["source_type"],
                chunk_index=row["chunk_index"],
                content=row["content"],
                similarity_score=float(row["similarity_score"]),
                metadata=row["chunk_metadata"] or {},
            )
            for row in rows
        ]

        return KnowledgeSearchResponse(
            query=request.query,
            top_k=request.top_k,
            results=results,
        )
