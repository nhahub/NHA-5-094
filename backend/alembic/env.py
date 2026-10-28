import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

import app.agents.models  # noqa: F401

# Warm the application router graph first so domain package exports complete
# before Alembic imports individual models in isolation.
import app.api  # noqa: F401
import app.domain.approvals.models  # noqa: F401
import app.domain.audit.models  # noqa: F401
import app.domain.cases.models  # noqa: F401
import app.domain.documents.models  # noqa: F401
import app.domain.knowledge.models  # noqa: F401

# Import all models to ensure metadata registration
import app.domain.organizations.models  # noqa: F401
import app.domain.processes.models  # noqa: F401
import app.domain.rules.models  # noqa: F401
import app.domain.tasks.models  # noqa: F401
import app.domain.verifications.models  # noqa: F401
import app.domain.workflows.models  # noqa: F401
import app.events.models  # noqa: F401
import app.security.models  # noqa: F401
import app.tools.models  # noqa: F401
from alembic import context

# Import application settings and declarative Base
from app.core.config import settings
from app.infrastructure.database.base import Base

config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set database URL dynamically from app settings
config.set_main_option("sqlalchemy.url", settings.sync_database_uri)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    from sqlalchemy import create_engine

    connectable = create_engine(
        settings.sync_database_uri,
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        do_run_migrations(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
