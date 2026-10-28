"""Phase 9 — Knowledge / RAG: Fix embedding dimension to 1024 (BAAI/bge-m3),
add organisation isolation to knowledge_chunks, add HNSW index,
and add ingestion lifecycle columns to knowledge_documents.

Revision ID: 0006_knowledge_rag
Revises: 0005_document_processing_runs
Create Date: 2026-10-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "0006_knowledge_rag"
down_revision: Union[str, None] = "0005_document_processing_runs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # Step 1: Clear any placeholder / stale chunk data.                   #
    # (knowledge_chunks has never been functional — no real data exists.) #
    # ------------------------------------------------------------------ #
    op.execute("DELETE FROM knowledge_chunks;")

    # ------------------------------------------------------------------ #
    # Step 2: Replace the placeholder Vector(1536) with Vector(1024)      #
    # to match BAAI/bge-m3's native output dimension.                    #
    # ------------------------------------------------------------------ #
    op.drop_column("knowledge_chunks", "embedding")
    op.add_column(
        "knowledge_chunks",
        sa.Column("embedding", Vector(1024), nullable=True),
    )

    # ------------------------------------------------------------------ #
    # Step 3: Add denormalized organization_id to knowledge_chunks for    #
    # fast single-table tenant isolation before every ANN query.          #
    # ------------------------------------------------------------------ #
    op.add_column(
        "knowledge_chunks",
        sa.Column(
            "organization_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=True,   # nullable during migration; backfill not needed (table is empty)
        ),
    )
    # Make it NOT NULL now that the column exists and the table is empty
    op.alter_column("knowledge_chunks", "organization_id", nullable=False)
    op.create_foreign_key(
        "fk_knowledge_chunks_organization_id",
        "knowledge_chunks",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "idx_knowledge_chunks_org_id",
        "knowledge_chunks",
        ["organization_id"],
    )

    # ------------------------------------------------------------------ #
    # Step 4: HNSW index for approximate nearest-neighbour cosine search  #
    # on the 1024-dim embedding column.                                   #
    # ------------------------------------------------------------------ #
    op.execute(
        """
        CREATE INDEX idx_knowledge_chunks_embedding_hnsw
        ON knowledge_chunks
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64);
        """
    )

    # ------------------------------------------------------------------ #
    # Step 5: Add ingestion lifecycle tracking columns to                 #
    # knowledge_documents so the API can expose PENDING/INGESTING/        #
    # INGESTED/FAILED status, chunk count, and ingested timestamp.        #
    # ------------------------------------------------------------------ #
    op.add_column(
        "knowledge_documents",
        sa.Column(
            "status",
            sa.String(40),
            nullable=False,
            server_default="PENDING",
        ),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("chunk_count", sa.Integer(), nullable=True),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column(
            "ingested_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    # Reverse Step 5
    op.drop_column("knowledge_documents", "ingested_at")
    op.drop_column("knowledge_documents", "chunk_count")
    op.drop_column("knowledge_documents", "status")

    # Reverse Step 4
    op.execute("DROP INDEX IF EXISTS idx_knowledge_chunks_embedding_hnsw;")

    # Reverse Step 3
    op.drop_index("idx_knowledge_chunks_org_id", table_name="knowledge_chunks")
    op.drop_constraint(
        "fk_knowledge_chunks_organization_id",
        "knowledge_chunks",
        type_="foreignkey",
    )
    op.drop_column("knowledge_chunks", "organization_id")

    # Reverse Step 2: restore original 1536-dim placeholder
    op.drop_column("knowledge_chunks", "embedding")
    op.add_column(
        "knowledge_chunks",
        sa.Column("embedding", Vector(1536), nullable=True),
    )
