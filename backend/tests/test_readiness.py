import socket
import uuid

import pytest
import redis.asyncio as aioredis
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.infrastructure.database.session as database_session_module
import app.infrastructure.queue.redis as redis_module
import app.main as main_module
from app.infrastructure.database.session import get_db


@pytest.mark.asyncio
async def test_liveness_does_not_depend_on_external_services(async_client):
    response = await async_client.get("/livez")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


@pytest.mark.asyncio
async def test_readiness_reports_each_dependency(async_client, monkeypatch):
    async def database_ok():
        return True

    async def redis_ok():
        return True

    monkeypatch.setattr(main_module, "check_database_health", database_ok)
    monkeypatch.setattr(main_module, "check_redis_health", redis_ok)
    ready = await async_client.get("/readyz")
    assert ready.status_code == 200
    assert ready.json()["services"] == {
        "database": "connected",
        "redis": "connected",
    }

    async def redis_down():
        return False

    monkeypatch.setattr(main_module, "check_redis_health", redis_down)
    not_ready = await async_client.get("/readyz")
    assert not_ready.status_code == 503
    assert not_ready.json()["status"] == "not_ready"
    assert not_ready.json()["services"]["redis"] == "disconnected"


@pytest.mark.parametrize("failed_dependency", ["database", "redis"])
@pytest.mark.asyncio
async def test_readiness_fails_closed_when_either_dependency_is_unavailable(
    async_client, monkeypatch, failed_dependency
):
    async def healthy():
        return True

    async def unavailable():
        return False

    monkeypatch.setattr(main_module, "check_database_health", healthy)
    monkeypatch.setattr(main_module, "check_redis_health", healthy)
    monkeypatch.setattr(
        main_module,
        "check_database_health" if failed_dependency == "database" else "check_redis_health",
        unavailable,
    )

    response = await async_client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert response.json()["services"][failed_dependency] == "disconnected"

    # Liveness describes the API process; dependency outages only fail readiness.
    assert (await async_client.get("/livez")).status_code == 200


def _closed_loopback_port() -> int:
    """Reserve then release an ephemeral loopback port for connection-refusal tests."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.mark.asyncio
async def test_real_database_and_redis_outages_keep_startup_live_but_unready(
    async_client, monkeypatch
):
    database_port = _closed_loopback_port()
    redis_port = _closed_loopback_port()
    isolated_engine = create_async_engine(
        f"postgresql+asyncpg://phase22:phase22@127.0.0.1:{database_port}/phase22_unavailable",
        connect_args={"timeout": 0.5},
        pool_pre_ping=True,
    )
    isolated_redis = aioredis.from_url(
        f"redis://127.0.0.1:{redis_port}/0",
        socket_connect_timeout=0.5,
        socket_timeout=0.5,
    )
    monkeypatch.setattr(database_session_module, "async_engine", isolated_engine)
    monkeypatch.setattr(redis_module, "redis_client", isolated_redis)

    try:
        # The documented startup contract is to start the API process and report
        # dependency health through readiness, not to claim the process is dead.
        async with main_module.app.router.lifespan_context(main_module.app):
            ready = await async_client.get("/readyz")
            assert ready.status_code == 503
            assert ready.json()["services"] == {
                "database": "disconnected",
                "redis": "disconnected",
            }
            assert (await async_client.get("/livez")).status_code == 200
    finally:
        await isolated_engine.dispose()
        await isolated_redis.aclose()


@pytest.mark.asyncio
async def test_real_database_unavailability_returns_safe_503_during_case_creation(
    async_client, monkeypatch
):
    del async_client  # The fixture installs authenticated-user overrides for this API app.
    database_port = _closed_loopback_port()
    isolated_engine = create_async_engine(
        f"postgresql+asyncpg://phase22:phase22@127.0.0.1:{database_port}/phase22_unavailable",
        connect_args={"timeout": 0.5},
        pool_pre_ping=True,
    )
    isolated_session_factory = async_sessionmaker(
        bind=isolated_engine,
        expire_on_commit=False,
    )
    monkeypatch.delitem(main_module.app.dependency_overrides, get_db)
    monkeypatch.setattr(
        database_session_module, "AsyncSessionLocal", isolated_session_factory
    )
    # Let an unhandled regression raise its real exception instead of hiding it
    # behind Starlette's generic 500 response.
    transport = ASGITransport(app=main_module.app)

    try:
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post(
                "/api/v1/cases",
                json={
                    "title": "Must not persist while the database is unavailable",
                    "process_version_id": str(uuid.uuid4()),
                },
            )

        assert response.status_code == 503, response.text
        assert response.json() == {
            "detail": "Database service is temporarily unavailable."
        }
        assert "127.0.0.1" not in response.text
        assert str(database_port) not in response.text
    finally:
        await isolated_engine.dispose()
