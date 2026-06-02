"""workbench-mcp tool tests — verify each tool hits the right backend path with
the bearer header, using a mocked HTTP layer (pytest-httpx). No live backend."""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_workbench import server
from mcp_workbench.config import get_settings

API = "http://test"
KEY = "wbm-test-key"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("WORKBENCH_API_BASE", API)
    monkeypatch.setenv("WORKBENCH_MCP_KEY", KEY)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def test_status_calls_healthz(httpx_mock):
    httpx_mock.add_response(url=f"{API}/healthz", json={"status": "ok"})
    out = await server.workbench_status()
    assert out == {"status": "ok"}
    assert httpx_mock.get_request().url.path == "/healthz"


async def test_bearer_header_on_every_request(httpx_mock):
    httpx_mock.add_response(json={})
    await server.workbench_trading_profile_get()
    req = httpx_mock.get_request()
    assert req.headers["Authorization"] == f"Bearer {KEY}"
    assert req.url.path == "/api/v1/users/me/trading-profile"


async def test_morning_brief_generate_is_a_post(httpx_mock):
    httpx_mock.add_response(url=f"{API}/api/v1/morning-brief/generate", json={"ok": 1})
    await server.workbench_morning_brief_generate()
    req = httpx_mock.get_request()
    assert req.method == "POST"
    assert req.url.path == "/api/v1/morning-brief/generate"


@pytest.mark.parametrize(
    ("call", "path", "method"),
    [
        (lambda: server.workbench_morning_brief_today(), "/api/v1/morning-brief/today", "GET"),
        (lambda: server.workbench_list_accounts(), "/api/v1/accounts", "GET"),
        (lambda: server.workbench_list_strategies(), "/api/v1/strategies", "GET"),
        (lambda: server.workbench_list_positions(7), "/api/v1/accounts/7/positions", "GET"),
        (lambda: server.workbench_list_orders(5), "/api/v1/orders", "GET"),
        (lambda: server.workbench_account_risk_state(3), "/api/v1/accounts/3/risk-state", "GET"),
        (lambda: server.workbench_strategy_activation_status(9), "/api/v1/strategies/9/activation", "GET"),
        (lambda: server.workbench_recent_briefs(), "/api/v1/morning-brief/recent", "GET"),
        (lambda: server.workbench_audit_recent(), "/api/v1/audit", "GET"),
    ],
)
async def test_tools_pass_through(httpx_mock, call, path, method):
    httpx_mock.add_response(json={})
    await call()
    req = httpx_mock.get_request()
    assert req.method == method
    assert req.url.path == path


async def test_list_orders_caps_limit(httpx_mock):
    httpx_mock.add_response(json={})
    await server.workbench_list_orders(9999)
    assert httpx_mock.get_request().url.params["limit"] == "100"


async def test_recent_briefs_caps_limit(httpx_mock):
    httpx_mock.add_response(json={})
    await server.workbench_recent_briefs(9999)
    assert httpx_mock.get_request().url.params["limit"] == "30"


async def test_api_error_propagates(httpx_mock):
    import httpx

    httpx_mock.add_response(status_code=503, json={"detail": "down"})
    with pytest.raises(httpx.HTTPStatusError):
        await server.workbench_status()


def test_server_has_no_db_imports():
    """Sanity: the server module must not reach into the DB layer."""
    src = (Path(server.__file__)).read_text(encoding="utf-8")
    assert "sqlalchemy" not in src
    assert "app.db" not in src


def test_build_server_registers_twelve_tools():
    srv = server.build_server()
    assert len(server._TOOLS) == 12
    assert srv.name == "Trading Workbench State"
