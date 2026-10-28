"""Enforce case-insensitive global uniqueness for login identities."""

import sqlalchemy as sa

from alembic import op

revision = "0009_global_user_email_identity"
down_revision = "0008_human_review_comments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT lower(email)
                FROM users
                GROUP BY lower(email)
                HAVING count(*) > 1
            ) THEN
                RAISE EXCEPTION
                    'Cannot enforce global user email uniqueness: duplicate case-insensitive email identities exist. Resolve duplicates with organization owners before retrying.';
            END IF;
        END
        $$;
        """
    )
    op.drop_constraint("uq_users_org_email", "users", type_="unique")
    op.create_index(
        "uq_users_email_lower",
        "users",
        [sa.text("lower(email)")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_users_email_lower", table_name="users")
    op.create_unique_constraint(
        "uq_users_org_email", "users", ["organization_id", "email"]
    )
