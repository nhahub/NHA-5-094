"""Persist human review comments and evidence links.

Revision ID: 0008_human_review_comments
Revises: 0007_agent_execution_parent
Create Date: 2026-10-08
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0008_human_review_comments"
down_revision = "0007_agent_execution_parent"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "task_review_comments",
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_task_review_comments_id", "task_review_comments", ["id"], unique=False)
    op.create_index("ix_task_review_comments_task_id", "task_review_comments", ["task_id"], unique=False)
    op.create_index("ix_task_review_comments_author_id", "task_review_comments", ["author_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_task_review_comments_author_id", table_name="task_review_comments")
    op.drop_index("ix_task_review_comments_task_id", table_name="task_review_comments")
    op.drop_index("ix_task_review_comments_id", table_name="task_review_comments")
    op.drop_table("task_review_comments")
