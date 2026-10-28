"""HTTP-level Phase 20 security checks across the configured ASGI application."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

import app.main as main_module
from app.core.config import Settings, settings
from app.domain.documents.router import get_document_storage
from app.infrastructure.database.session import get_db
from app.infrastructure.llm.gateway import ModelGateway, ModelGatewayError
from app.main import create_app
from app.security.models import User
from app.security.router import get_current_user


def production_settings(**overrides: object) -> Settings:
    """Return a production-shaped config with test-only remote service values."""
    values: dict[str, object] = {
        "_env_file": None,
        "APP_ENV": "production",
        "DEBUG": False,
        "SECRET_KEY": "Phase20E2ESecretKey-7f3a2c9b-48d1-963e",
        "BACKEND_CORS_ORIGINS": ["https://app.verifia.example"],
        "DATABASE_URL": (
            "postgresql+psycopg2://verifia:DbCredentials-Phase20-7f3a2c9b"
            "@db.verifia.example:5432/verifia"
        ),
        "ASYNC_DATABASE_URL": (
            "postgresql+asyncpg://verifia:DbCredentials-Phase20-7f3a2c9b"
            "@db.verifia.example:5432/verifia"
        ),
        "REDIS_URL": "rediss://:RedisCredentials-Phase20-7f3a2c9b@cache.verifia.example:6380/0",
        "EXTERNAL_MODEL_DATA_POLICY": "deny",
        "DOCUMENT_MAX_FILE_SIZE_BYTES": 512,
        "REQUEST_MAX_BODY_SIZE_BYTES": 1024,
    }
    values.update(overrides)
    config = Settings(**values)
    config.validate_security_settings()
    return config


def test_production_app_factory_applies_configured_edge_controls():
    config = production_settings()
    app = create_app(config)

    assert app.state.settings is config
    assert app.docs_url is None
    assert app.redoc_url is None
    assert app.openapi_url is None
    assert any(
        middleware.cls.__name__ == "RequestBodyLimitMiddleware"
        and middleware.kwargs["max_size_bytes"] == config.REQUEST_MAX_BODY_SIZE_BYTES
        for middleware in app.user_middleware
    )


@pytest.mark.asyncio
async def test_production_http_boundary_hides_docs_limits_bodies_and_restricts_cors(
    monkeypatch: pytest.MonkeyPatch,
):
    config = production_settings()
    app = create_app(config)

    async def redis_disconnected() -> bool:
        return False

    monkeypatch.setattr(main_module, "check_redis_health", redis_disconnected)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        root = await client.get("/")
        health = await client.get("/health")
        assert root.status_code == 200
        assert root.json()["docs_url"] is None
        assert health.status_code == 200
        assert health.json()["environment"] == "production"

        for path in ("/docs", "/redoc", "/api/v1/openapi.json"):
            assert (await client.get(path)).status_code == 404

        allowed_preflight = await client.options(
            "/api/v1/auth/login",
            headers={
                "Origin": "https://app.verifia.example",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
        assert allowed_preflight.status_code == 200
        assert allowed_preflight.headers["access-control-allow-origin"] == (
            "https://app.verifia.example"
        )
        assert "access-control-allow-credentials" not in allowed_preflight.headers
        assert "POST" in allowed_preflight.headers["access-control-allow-methods"]

        rejected_preflight = await client.options(
            "/api/v1/auth/login",
            headers={
                "Origin": "https://untrusted.example",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert rejected_preflight.status_code == 400
        assert "access-control-allow-origin" not in rejected_preflight.headers

        oversized = await client.post(
            "/api/v1/auth/login",
            content=b"x" * (config.REQUEST_MAX_BODY_SIZE_BYTES + 1),
        )
        assert oversized.status_code == 413
        assert oversized.json()["detail"] == (
            "Request body exceeds the maximum permitted size."
        )


@pytest.mark.asyncio
async def test_docs_visibility_matches_development_and_explicit_production_override():
    development_app = create_app(Settings(_env_file=None, APP_ENV="development"))
    explicitly_enabled = production_settings(API_DOCS_ENABLED=True)
    production_docs_app = create_app(explicitly_enabled)

    for app in (development_app, production_docs_app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            assert (await client.get("/docs")).status_code == 200
            assert (await client.get("/redoc")).status_code == 200
            assert (await client.get("/api/v1/openapi.json")).status_code == 200


@pytest.mark.asyncio
async def test_production_upload_gate_rejects_before_storage_or_database_use(
    monkeypatch: pytest.MonkeyPatch,
    db_session: AsyncSession,
    test_user: User,
):
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "ALLOW_UNSCANNED_UPLOADS", None)
    app = create_app(production_settings())

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    async def override_current_user() -> User:
        return test_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_current_user
    app.dependency_overrides[get_document_storage] = lambda: object()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            response = await client.post(
                "/api/v1/documents",
                data={
                    "case_id": str(uuid.uuid4()),
                    "document_type": "INVOICE",
                },
                files={
                    "file": ("invoice.pdf", b"%PDF-1.7 synthetic", "application/pdf")
                },
            )
        assert response.status_code == 503
        assert response.json()["detail"] == (
            "Uploads are disabled because no malware-scanning policy is configured."
        )
    finally:
        app.dependency_overrides.clear()


def test_model_gateway_denies_unapproved_production_routes_before_provider_call(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "EXTERNAL_MODEL_DATA_POLICY", None)
    monkeypatch.setattr(settings, "EXTERNAL_MODEL_ALLOWED_ROUTES", [])

    with pytest.raises(ModelGatewayError, match="EXTERNAL_MODEL_DATA_POLICY"):
        ModelGateway.get_adapter("groq", model="synthetic-test-model")


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"SECRET_KEY": "change-me"}, "SECRET_KEY"),
        ({"DEBUG": True}, "DEBUG"),
        ({"BACKEND_CORS_ORIGINS": ["*"]}, "CORS origin"),
        ({"DATABASE_URL": None}, "DATABASE_URL"),
        ({"ALLOW_UNSCANNED_UPLOADS": True}, "ALLOW_UNSCANNED_UPLOADS"),
    ],
)
def test_production_configuration_rejects_unsafe_startup(
    overrides: dict[str, object], message: str
):
    values: dict[str, object] = {
        "_env_file": None,
        "APP_ENV": "production",
        "DEBUG": False,
        "SECRET_KEY": "Phase20E2ESecretKey-7f3a2c9b-48d1-963e",
        "BACKEND_CORS_ORIGINS": ["https://app.verifia.example"],
        "DATABASE_URL": (
            "postgresql+psycopg2://verifia:DbCredentials-Phase20-7f3a2c9b"
            "@db.verifia.example:5432/verifia"
        ),
        "ASYNC_DATABASE_URL": (
            "postgresql+asyncpg://verifia:DbCredentials-Phase20-7f3a2c9b"
            "@db.verifia.example:5432/verifia"
        ),
        "REDIS_URL": "rediss://:RedisCredentials-Phase20-7f3a2c9b@cache.verifia.example:6380/0",
        "EXTERNAL_MODEL_DATA_POLICY": "deny",
    }
    values.update(overrides)
    config = Settings(**values)

    with pytest.raises(RuntimeError, match=message):
        config.validate_security_settings()
