"""Add parent linkage for delegated agent executions.

Revision ID: 0007_agent_execution_parent
Revises: 0006_knowledge_rag
Create Date: 2026-10-08
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0007_agent_execution_parent"
down_revision = "0006_knowledge_rag"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_executions",
        sa.Column("parent_execution_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_agent_executions_parent_execution_id",
        "agent_executions",
        "agent_executions",
        ["parent_execution_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_agent_executions_parent_execution_id",
        "agent_executions",
        ["parent_execution_id"],
    )
    op.create_index(
        "ix_agent_executions_parent_case",
        "agent_executions",
        ["parent_execution_id", "case_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_executions_parent_case", table_name="agent_executions")
    op.drop_index("ix_agent_executions_parent_execution_id", table_name="agent_executions")
    op.drop_constraint(
        "fk_agent_executions_parent_execution_id",
        "agent_executions",
        type_="foreignkey",
    )
    op.drop_column("agent_executions", "parent_execution_id")
