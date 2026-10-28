"""Add organization scope to tool execution audit records.

Revision ID: 0002_tool_execution_org_scope
Revises: 0001_initial_schema
Create Date: 2026-09-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0002_tool_execution_org_scope"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tool_executions",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_tool_executions_organization_id_organizations",
        "tool_executions",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_tool_executions_organization_id",
        "tool_executions",
        ["organization_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_tool_executions_organization_id", table_name="tool_executions")
    op.drop_constraint(
        "fk_tool_executions_organization_id_organizations",
        "tool_executions",
        type_="foreignkey",
    )
    op.drop_column("tool_executions", "organization_id")
