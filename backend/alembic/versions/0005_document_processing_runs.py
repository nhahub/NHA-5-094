"""Add versioned document processing runs and source locators.

Revision ID: 0005_document_processing_runs
Revises: 0004_approval_type
Create Date: 2026-09-30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0005_document_processing_runs"
down_revision: Union[str, None] = "0004_approval_type"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "document_processing_runs",
        sa.Column("document_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=40), server_default="QUEUED", nullable=False),
        sa.Column("parser_name", sa.String(length=100), nullable=True),
        sa.Column("parser_version", sa.String(length=100), nullable=True),
        sa.Column("ocr_engine", sa.String(length=100), nullable=True),
        sa.Column("classifier_model", sa.String(length=255), nullable=True),
        sa.Column("predicted_document_type", sa.String(length=100), nullable=True),
        sa.Column("classification_confidence", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("extractor_model", sa.String(length=255), nullable=True),
        sa.Column("extraction_schema_version", sa.String(length=100), nullable=True),
        sa.Column("configuration_hash", sa.String(length=64), nullable=True),
        sa.Column("normalized_content_reference", sa.Text(), nullable=True),
        sa.Column("review_required", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("review_reasons", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("safe_error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["document_version_id"], ["document_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_version_id", "run_number", name="uq_doc_processing_version_run"),
    )
    op.create_index(
        "ix_document_processing_runs_document_version_id",
        "document_processing_runs",
        ["document_version_id"],
    )
    op.create_index(
        "idx_doc_processing_status", "document_processing_runs", ["status"]
    )
    op.add_column(
        "document_processing_runs",
        sa.Column("review_task_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_document_processing_runs_review_task_id",
        "document_processing_runs",
        ["review_task_id"],
    )
    op.create_foreign_key(
        "fk_document_processing_runs_review_task_id_tasks",
        "document_processing_runs",
        "tasks",
        ["review_task_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "extracted_fields",
        sa.Column("processing_run_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column("extracted_fields", sa.Column("source_text", sa.Text(), nullable=True))
    op.add_column("extracted_fields", sa.Column("source_locator", sa.JSON(), nullable=True))
    op.create_index(
        "ix_extracted_fields_processing_run_id", "extracted_fields", ["processing_run_id"]
    )
    op.create_foreign_key(
        "fk_extracted_fields_processing_run_id_document_processing_runs",
        "extracted_fields",
        "document_processing_runs",
        ["processing_run_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_document_processing_runs_review_task_id_tasks",
        "document_processing_runs",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_document_processing_runs_review_task_id",
        table_name="document_processing_runs",
    )
    op.drop_column("document_processing_runs", "review_task_id")
    op.drop_constraint(
        "fk_extracted_fields_processing_run_id_document_processing_runs",
        "extracted_fields",
        type_="foreignkey",
    )
    op.drop_index("ix_extracted_fields_processing_run_id", table_name="extracted_fields")
    op.drop_column("extracted_fields", "source_locator")
    op.drop_column("extracted_fields", "source_text")
    op.drop_column("extracted_fields", "processing_run_id")
    op.drop_index("idx_doc_processing_status", table_name="document_processing_runs")
    op.drop_index(
        "ix_document_processing_runs_document_version_id",
        table_name="document_processing_runs",
    )
    op.drop_table("document_processing_runs")
