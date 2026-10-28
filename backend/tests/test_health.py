from fastapi.testclient import TestClient
from app import __version__
from app.core.config import settings


def test_health_check(client: TestClient) -> None:
    """Verify that the health check endpoint returns 200 OK and expected structure."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["app"] == settings.APP_NAME
    assert data["version"] == __version__
    assert "environment" in data
    assert "services" in data
    assert "api" in data["services"]


def test_root_endpoint(client: TestClient) -> None:
    """Verify that the root endpoint returns 200 OK with doc links."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert data["docs_url"] == "/docs"
    assert data["health_url"] == "/health"
