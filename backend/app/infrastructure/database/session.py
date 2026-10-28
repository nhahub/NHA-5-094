from typing import AsyncGenerator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.core.config import settings


class DatabaseUnavailableError(RuntimeError):
    """A database connection failed while serving an application request."""


def _is_asyncpg_timeout(exc: TimeoutError) -> bool:
    """Distinguish driver timeouts from unrelated application-level timeouts."""
    traceback = exc.__traceback__
    while traceback is not None:
        module_name = traceback.tb_frame.f_globals.get("__name__", "")
        if module_name.startswith("asyncpg.") or module_name.startswith(
            "sqlalchemy.dialects.postgresql.asyncpg"
        ):
            return True
        traceback = traceback.tb_next
    return False


def _is_asyncpg_connection_error(exc: ConnectionError) -> bool:
    """Identify raw socket errors raised by asyncpg during connection setup."""
    traceback = exc.__traceback__
    while traceback is not None:
        module_name = traceback.tb_frame.f_globals.get("__name__", "")
        if module_name.startswith("asyncpg.") or module_name.startswith(
            "sqlalchemy.dialects.postgresql.asyncpg"
        ):
            return True
        traceback = traceback.tb_next
    return False

# Create asynchronous SQLAlchemy engine
async_engine = create_async_engine(
    settings.async_database_uri,
    echo=settings.DEBUG,
    future=True,
    pool_pre_ping=True,
)

# Create sessionmaker for async database sessions
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an asynchronous database session."""
    session = AsyncSessionLocal()
    operation_failed = False
    try:
        try:
            yield session
        except TimeoutError as exc:
            operation_failed = True
            if not _is_asyncpg_timeout(exc):
                try:
                    await session.rollback()
                except Exception:
                    pass
                raise
            try:
                await session.rollback()
            except Exception:
                # The connection may be unavailable for rollback as well.
                pass
            raise DatabaseUnavailableError from exc
        except Exception as exc:
            operation_failed = True
            try:
                await session.rollback()
            except Exception:
                # Preserve the operation error so the API can map database
                # connection failures to a safe service-unavailable response.
                pass
            if isinstance(exc, ConnectionError) and _is_asyncpg_connection_error(exc):
                raise DatabaseUnavailableError from exc
            raise
        except BaseException:
            # Cancellation and other control-flow exceptions must also survive
            # a secondary cleanup failure.
            operation_failed = True
            raise
    finally:
        try:
            await session.close()
        except Exception:
            if not operation_failed:
                raise


async def check_database_health() -> bool:
    """Check that the configured database accepts a lightweight query."""
    try:
        async with async_engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
