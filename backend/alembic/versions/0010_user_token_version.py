"""Add per-user token version for immediate access-token revocation."""

import sqlalchemy as sa

from alembic import op

revision = "0010_user_token_version"
down_revision = "0009_global_user_email_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("token_version", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    op.drop_column("users", "token_version")
