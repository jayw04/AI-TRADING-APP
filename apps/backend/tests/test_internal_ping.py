import os

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def internal_auth_client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MCP_BACKEND_TOKEN", "test-secret-xyz")

    from app.config import get_settings
    from app.main import create_app

    get_settings.cache_clear()
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    get_settings.cache_clear()
    os.environ.pop("MCP_BACKEND_TOKEN", None)


async def test_internal_ping_requires_header(internal_auth_client: AsyncClient) -> None:
    resp = await internal_auth_client.get("/api/v1/internal/ping")
    assert resp.status_code == 401


async def test_internal_ping_rejects_wrong_token(internal_auth_client: AsyncClient) -> None:
    resp = await internal_auth_client.get(
        "/api/v1/internal/ping", headers={"X-Workbench-Auth": "wrong-token"}
    )
    assert resp.status_code == 401


async def test_internal_ping_accepts_correct_token(internal_auth_client: AsyncClient) -> None:
    resp = await internal_auth_client.get(
        "/api/v1/internal/ping", headers={"X-Workbench-Auth": "test-secret-xyz"}
    )
    assert resp.status_code == 200
    assert resp.json() == {"pong": True}
