"""Add durable delivery state for trusted orchestration events."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0011_durable_event_deliveries"
down_revision = "0010_user_token_version"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "event_deliveries",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="PENDING"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_token", sa.String(length=36), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=100), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id"),
    )
    op.create_index("ix_event_deliveries_event_id", "event_deliveries", ["event_id"])
    op.create_index("ix_event_deliveries_available_at", "event_deliveries", ["available_at"])
    op.create_index(
        "idx_event_deliveries_status_available",
        "event_deliveries",
        ["status", "available_at"],
    )
    op.create_index(
        "idx_event_deliveries_status_lease",
        "event_deliveries",
        ["status", "lease_until"],
    )


def downgrade() -> None:
    op.drop_index("idx_event_deliveries_status_lease", table_name="event_deliveries")
    op.drop_index("idx_event_deliveries_status_available", table_name="event_deliveries")
    op.drop_index("ix_event_deliveries_available_at", table_name="event_deliveries")
    op.drop_index("ix_event_deliveries_event_id", table_name="event_deliveries")
    op.drop_table("event_deliveries")
