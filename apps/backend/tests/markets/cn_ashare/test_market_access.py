"""Market grants: fail closed, and a missing grant is 403 on the direct API."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.market_access import canonical_market_access, parse_market_access
from app.auth.stub import CurrentUser, get_current_user


def test_parse_market_access_fails_closed() -> None:
    assert parse_market_access(None) == frozenset()
    assert parse_market_access("") == frozenset()
    assert parse_market_access(" ") == frozenset()
    assert parse_market_access("US") == frozenset()
    assert parse_market_access("us,jp") == frozenset()
    assert parse_market_access("us,cn,us") == frozenset({"us", "cn"})
    assert parse_market_access("cn") == frozenset({"cn"})
    assert canonical_market_access("cn,us") == "us,cn"
    with pytest.raises(ValueError):
        canonical_market_access("all")


def _as(markets: frozenset[str]) -> CurrentUser:
    return CurrentUser(
        id=1,
        email="dev@workbench.local",
        display_name="Dev",
        session_id=1,
        markets=markets,
    )


async def _client(markets: frozenset[str]) -> AsyncClient:
    from app.main import create_app

    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: _as(markets)
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _code(response) -> str | None:  # type: ignore[no-untyped-def]
    detail = response.json().get("detail")
    return detail.get("code") if isinstance(detail, dict) else None


@pytest.mark.asyncio
async def test_china_only_account(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import get_settings

    # Do not open whatever A-share file the laptop settings point at.
    monkeypatch.setenv("WORKBENCH_CN_ASHARE_DB_PATH", str(tmp_path / "cn_ashare_absent.duckdb"))
    monkeypatch.setenv("WORKBENCH_CN_ASHARE_CACHE_DIR", str(tmp_path / "cache"))
    get_settings.cache_clear()
    try:
        async with await _client(frozenset({"cn"})) as ac:
            account = await ac.get("/api/v1/account")
            orders = await ac.get("/api/v1/orders")
            us_view = await ac.get("/api/v1/markets/us_equity/results")
            cn_view = await ac.get("/api/v1/markets/cn_ashare/data-status")
            listed = await ac.get("/api/v1/markets")
            me = await ac.get("/api/v1/auth/me")
        assert account.status_code == 403 and _code(account) == "MARKET_FORBIDDEN"
        assert orders.status_code == 403 and _code(orders) == "MARKET_FORBIDDEN"
        assert us_view.status_code == 403 and _code(us_view) == "MARKET_FORBIDDEN"
        assert cn_view.status_code == 200 and cn_view.json()["market"] == "cn_ashare"
        assert [m["market"] for m in listed.json()["markets"]] == ["cn_ashare"]
        assert me.json()["markets"] == ["cn"]
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_us_only_account(client: AsyncClient) -> None:
    assert client.base_url  # schema fixture; the grant check must not depend on it
    async with await _client(frozenset({"us"})) as ac:
        cn_view = await ac.get("/api/v1/markets/cn_ashare/results")
        us_view = await ac.get("/api/v1/markets/us_equity/results")
        listed = await ac.get("/api/v1/markets")
        account = await ac.get("/api/v1/account")
    assert cn_view.status_code == 403 and _code(cn_view) == "MARKET_FORBIDDEN"
    assert us_view.status_code == 404 and _code(us_view) == "MARKET_NOT_SCOPED"
    assert [m["market"] for m in listed.json()["markets"]] == ["us_equity"]
    assert account.status_code != 403


@pytest.mark.asyncio
async def test_empty_grants_are_forbidden() -> None:
    async with await _client(frozenset()) as ac:
        account = await ac.get("/api/v1/account")
        cn_view = await ac.get("/api/v1/markets/cn_ashare/data-status")
        listed = await ac.get("/api/v1/markets")
        me = await ac.get("/api/v1/auth/me")
    assert account.status_code == 403 and _code(account) == "MARKET_FORBIDDEN"
    assert cn_view.status_code == 403 and _code(cn_view) == "MARKET_FORBIDDEN"
    assert listed.json()["markets"] == []
    assert me.json()["markets"] == []
