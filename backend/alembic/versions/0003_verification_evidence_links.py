"""Link evidence bundles to verification executions.

Revision ID: 0003_verification_evidence_links
Revises: 0002_tool_execution_org_scope
Create Date: 2026-09-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0003_verification_evidence_links"
down_revision: Union[str, None] = "0002_tool_execution_org_scope"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "evidence",
        sa.Column("verification_execution_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_evidence_verification_execution_id_verification_executions",
        "evidence",
        "verification_executions",
        ["verification_execution_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_evidence_verification_execution_id",
        "evidence",
        ["verification_execution_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_evidence_verification_execution_id", table_name="evidence")
    op.drop_constraint(
        "fk_evidence_verification_execution_id_verification_executions",
        "evidence",
        type_="foreignkey",
    )
    op.drop_column("evidence", "verification_execution_id")
