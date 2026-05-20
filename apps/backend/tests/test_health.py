import os

import pytest
from httpx import ASGITransport, AsyncClient


async def test_healthz_ok(client: AsyncClient) -> None:
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"
    assert "version" in body


@pytest.mark.asyncio
async def test_healthz_degraded_when_db_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "WORKBENCH_DB_URL", "sqlite+aiosqlite:////nonexistent-path/does-not-exist.sqlite"
    )

    from app.config import get_settings
    from app.db import session as db_session
    from app.main import create_app

    get_settings.cache_clear()
    db_session.get_engine.cache_clear()
    db_session.get_sessionmaker.cache_clear()

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/healthz")

    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["db"] == "down"

    # Reset caches so subsequent tests get a fresh, working engine.
    monkeypatch.delenv("WORKBENCH_DB_URL", raising=False)
    os.environ["WORKBENCH_DB_URL"] = "sqlite+aiosqlite:///./data/workbench.test.sqlite"
    get_settings.cache_clear()
    db_session.get_engine.cache_clear()
    db_session.get_sessionmaker.cache_clear()
