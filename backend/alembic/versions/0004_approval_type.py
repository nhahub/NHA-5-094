"""Add approval type to persisted approval requests.

Revision ID: 0004_approval_type
Revises: 0003_verification_evidence_links
Create Date: 2026-09-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_approval_type"
down_revision: Union[str, None] = "0003_verification_evidence_links"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "approvals",
        sa.Column("approval_type", sa.String(length=100), nullable=False, server_default="GENERAL"),
    )
    op.alter_column("approvals", "approval_type", server_default=None)


def downgrade() -> None:
    op.drop_column("approvals", "approval_type")
