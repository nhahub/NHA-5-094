import uuid
from collections.abc import AsyncGenerator, Generator
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.domain.organizations.models import Organization
from app.infrastructure.database.base import Base
from app.infrastructure.database.session import get_db
from app.main import app
from app.security.models import RoleEnum, User
from app.security.router import get_current_user

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(autouse=True)
def disable_automatic_orchestration_for_isolated_tests(monkeypatch):
    """Keep ordinary tests deterministic; orchestration has dedicated opt-in coverage."""
    monkeypatch.setattr(settings, "CASE_ORCHESTRATION_ENABLED", False)


@pytest_asyncio.fixture(scope="function")
async def async_engine():
    """Create an isolated in-memory SQLite async engine per test."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(async_engine) -> AsyncGenerator[AsyncSession, None]:
    """Provide an async session with an isolated database."""
    session_factory = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture(scope="function")
async def test_org(db_session: AsyncSession) -> Organization:
    """Seed a test organization."""
    org = Organization(
        id=uuid.uuid4(),
        name="Verifia Test Organization",
        slug="verifia-test-org",
        status="active",
        settings={"currency": "USD"},
        is_active=True,
    )
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


@pytest_asyncio.fixture(scope="function")
async def test_user(db_session: AsyncSession, test_org: Organization) -> User:
    """Seed a test authenticated user."""
    user = User(
        id=uuid.uuid4(),
        organization_id=test_org.id,
        email="testuser@verifia.ai",
        name="Test Operator",
        role=RoleEnum.ADMIN,
        hashed_password="mock_hashed_password",
        status="active",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture(scope="function")
async def async_client(
    db_session: AsyncSession, test_user: User
) -> AsyncGenerator[AsyncClient, None]:
    """Provide an authenticated AsyncClient for API testing with database overrides."""

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    async def override_get_current_user() -> User:
        return test_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture(scope="session")
def client() -> Generator[TestClient, None, None]:
    """Test client fixture for making synchronous API requests during tests."""
    with TestClient(app) as test_client:
        yield test_client
