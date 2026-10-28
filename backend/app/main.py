import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

from app import __version__
from app.api import api_router
from app.core.config import Settings, settings
from app.core.logging import setup_logging
from app.core.middleware import RequestBodyLimitMiddleware

# Initialize logging configuration
setup_logging()


from app.infrastructure.database.session import (
    DatabaseUnavailableError,
    check_database_health,
)
from app.infrastructure.queue import check_redis_health, close_redis_client


def create_app(config: Settings = settings) -> FastAPI:
    """Build an API instance with an explicit, validated runtime configuration."""
    config.validate_security_settings()
    app_logger = logging.getLogger(config.APP_NAME)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        """Application lifespan manager for startup and shutdown events."""
        app_logger.info(
            "Starting %s (v%s) in [%s] mode...",
            config.APP_NAME,
            __version__,
            config.APP_ENV,
        )
        app_logger.info(
            "External model data policy is [%s] with %d explicitly allowed route(s).",
            config.effective_external_model_data_policy,
            len(config.EXTERNAL_MODEL_ALLOWED_ROUTES),
        )
        app_logger.info(
            "API docs enabled: %s; configured CORS origin count: %d.",
            config.api_docs_enabled,
            len(config.BACKEND_CORS_ORIGINS),
        )
        app_logger.info(
            "Upload policy: unscanned uploads %s; max file size %d bytes; max request body %d bytes.",
            "enabled" if config.allow_unscanned_uploads else "disabled",
            config.DOCUMENT_MAX_FILE_SIZE_BYTES,
            config.REQUEST_MAX_BODY_SIZE_BYTES,
        )
        if config.APP_ENV in {"production", "staging"} and config.api_docs_enabled:
            app_logger.warning(
                "API documentation routes are enabled in a production-like environment."
            )
        if (
            config.APP_ENV in {"production", "staging"}
            and config.allow_unscanned_uploads
        ):
            app_logger.warning(
                "Unscanned file uploads are enabled in a production-like environment; "
                "no malware scanner is configured."
            )
        yield
        app_logger.info("Shutting down %s...", config.APP_NAME)
        await close_redis_client()

    app = FastAPI(
        title=config.APP_NAME,
        version=__version__,
        description=(
            "A configurable agentic business-process verification and orchestration platform "
            "for organizations whose processes depend on documents, evidence, rules, and human decisions."
        ),
        openapi_url=f"{config.API_V1_PREFIX}/openapi.json"
        if config.api_docs_enabled
        else None,
        docs_url="/docs" if config.api_docs_enabled else None,
        redoc_url="/redoc" if config.api_docs_enabled else None,
        lifespan=lifespan,
    )
    app.state.settings = config

    @app.exception_handler(OperationalError)
    async def database_unavailable_handler(
        request: Request, exc: OperationalError
    ) -> JSONResponse:
        """Return a safe service-unavailable response for database outages."""
        del request, exc
        return JSONResponse(
            status_code=503,
            content={"detail": "Database service is temporarily unavailable."},
        )

    @app.exception_handler(DatabaseUnavailableError)
    async def database_unavailable_error_handler(
        request: Request, exc: DatabaseUnavailableError
    ) -> JSONResponse:
        """Return a safe response when a database connection is unavailable."""
        del request, exc
        return JSONResponse(
            status_code=503,
            content={"detail": "Database service is temporarily unavailable."},
        )

    # Cap streamed request bodies before Starlette parses multipart uploads.
    app.add_middleware(
        RequestBodyLimitMiddleware,
        max_size_bytes=config.REQUEST_MAX_BODY_SIZE_BYTES,
    )

    if config.BACKEND_CORS_ORIGINS:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=config.BACKEND_CORS_ORIGINS,
            allow_credentials=False,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=[
                "Accept",
                "Authorization",
                "Content-Type",
                "Origin",
                "X-Request-ID",
            ],
        )

    app.include_router(api_router, prefix=config.API_V1_PREFIX)

    @app.get("/health", tags=["System"])
    async def health_check() -> dict[str, Any]:
        """Health check endpoint to verify that the API is serving requests."""
        redis_ok = await check_redis_health()
        return {
            "status": "healthy",
            "app": config.APP_NAME,
            "version": __version__,
            "environment": config.APP_ENV,
            "services": {
                "api": "healthy",
                "redis": "connected" if redis_ok else "disconnected",
            },
        }

    @app.get("/livez", tags=["System"])
    async def liveness_check() -> dict[str, str]:
        """Report that the API process is running without checking dependencies."""
        return {"status": "alive"}

    @app.get("/readyz", tags=["System"])
    async def readiness_check() -> JSONResponse:
        """Report whether the API can reach its database and Redis dependencies."""
        database_ok, redis_ok = await asyncio.gather(
            check_database_health(),
            check_redis_health(),
        )
        ready = database_ok and redis_ok
        return JSONResponse(
            status_code=200 if ready else 503,
            content={
                "status": "ready" if ready else "not_ready",
                "app": config.APP_NAME,
                "version": __version__,
                "environment": config.APP_ENV,
                "services": {
                    "database": "connected" if database_ok else "disconnected",
                    "redis": "connected" if redis_ok else "disconnected",
                },
            },
        )

    @app.get("/", tags=["System"])
    async def root() -> dict[str, Any]:
        """Root entry point providing API documentation links."""
        return {
            "message": f"Welcome to {config.APP_NAME} API",
            "version": __version__,
            "docs_url": "/docs" if config.api_docs_enabled else None,
            "health_url": "/health",
            "readiness_url": "/readyz",
        }

    return app


app = create_app(settings)
