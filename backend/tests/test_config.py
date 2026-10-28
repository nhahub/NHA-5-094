from app.core.config import Settings


def test_settings_default_values() -> None:
    """Verify settings loads default attributes properly."""
    custom_settings = Settings(
        APP_NAME="VerifiaTest",
        POSTGRES_SERVER="db.example.com",
        POSTGRES_PORT=5432,
        POSTGRES_USER="test_user",
        POSTGRES_PASSWORD="test_password",
        POSTGRES_DB="test_db",
        DATABASE_URL=None,
        ASYNC_DATABASE_URL=None,
        # CI sets REDIS_URL for its service container; this test verifies the
        # composed default URI, so make it independent of the runner environment.
        REDIS_URL=None,
    )
    assert custom_settings.APP_NAME == "VerifiaTest"
    assert custom_settings.sync_database_uri == "postgresql+psycopg2://test_user:test_password@db.example.com:5432/test_db"
    assert custom_settings.async_database_uri == "postgresql+asyncpg://test_user:test_password@db.example.com:5432/test_db"
    assert custom_settings.redis_uri == "redis://localhost:6379/0"
    assert custom_settings.CASE_ORCHESTRATION_ENABLED is True
