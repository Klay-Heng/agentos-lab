"""Check the API's liveness contract and real settings sources."""

import httpx
import pytest

from agentos.core.config import Settings
from agentos.main import create_app

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def test_health_contract():
    settings = Settings(app_name="AgentOS Test", environment="test", _env_file=None)
    transport = httpx.ASGITransport(app=create_app(settings))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {
        "status": "ok",
        "app_name": "AgentOS Test",
        "environment": "test",
    }


async def test_factory_reads_environment(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AGENTOS_APP_NAME", "Environment API")
    monkeypatch.setenv("AGENTOS_ENVIRONMENT", "staging")

    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "app_name": "Environment API",
        "environment": "staging",
    }


async def test_dotenv_and_environment_precedence(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AGENTOS_APP_NAME", raising=False)
    monkeypatch.delenv("AGENTOS_ENVIRONMENT", raising=False)
    (tmp_path / ".env").write_text(
        "AGENTOS_APP_NAME=Dotenv API\nAGENTOS_ENVIRONMENT=development\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENTOS_ENVIRONMENT", "test")

    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "app_name": "Dotenv API",
        "environment": "test",
    }
