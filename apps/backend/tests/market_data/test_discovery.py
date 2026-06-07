"""P8 §1 — discovery feed cache + stale-on-error semantics.

Monkeypatches ``_fetch_from_alpaca`` (the only thing that touches the network /
SDK); the cache + fallback logic in ``get_discovery_feeds`` is what's exercised.
"""

from __future__ import annotations

import pytest

from app.market_data import discovery


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    discovery._FEED_CACHE.clear()
    yield
    discovery._FEED_CACHE.clear()


def _payload() -> dict:
    return {
        "most_actives": [{"symbol": "AAPL", "volume": 1000.0, "trade_count": 50.0}],
        "gainers": [
            {"symbol": "TSLA", "percent_change": 5.0, "change": 10.0, "price": 210.0}
        ],
        "losers": [
            {"symbol": "NFLX", "percent_change": -3.0, "change": -12.0, "price": 400.0}
        ],
        "last_updated": "2026-06-07T12:00:00",
    }


async def test_fetch_and_shape(monkeypatch) -> None:
    calls: list[int] = []
    monkeypatch.setattr(
        discovery,
        "_fetch_from_alpaca",
        lambda top: (calls.append(top), _payload())[1],
    )
    out = await discovery.get_discovery_feeds(20)
    assert out["stale"] is False
    assert out["error"] is None
    assert out["most_actives"][0]["symbol"] == "AAPL"
    assert out["gainers"][0]["percent_change"] == 5.0
    assert out["losers"][0]["symbol"] == "NFLX"
    assert calls == [20]


async def test_second_call_within_ttl_hits_cache(monkeypatch) -> None:
    calls: list[int] = []
    monkeypatch.setattr(
        discovery,
        "_fetch_from_alpaca",
        lambda top: (calls.append(top), _payload())[1],
    )
    await discovery.get_discovery_feeds(20)
    await discovery.get_discovery_feeds(20)
    assert calls == [20]  # second served from cache, no refetch


async def test_stale_on_error_serves_prior_cache(monkeypatch) -> None:
    monkeypatch.setattr(discovery, "_fetch_from_alpaca", lambda top: _payload())
    await discovery.get_discovery_feeds(20)  # warm the cache

    # Expire the cache and make the live fetch fail.
    monkeypatch.setattr(discovery, "_FEED_TTL_SECONDS", -1.0)

    def _boom(top: int) -> dict:
        raise RuntimeError("alpaca down")

    monkeypatch.setattr(discovery, "_fetch_from_alpaca", _boom)

    out = await discovery.get_discovery_feeds(20)
    assert out["stale"] is True
    assert out["error"] == discovery._UNAVAILABLE
    assert out["most_actives"][0]["symbol"] == "AAPL"  # prior data preserved


async def test_cold_error_returns_empty_with_flag(monkeypatch) -> None:
    def _boom(top: int) -> dict:
        raise RuntimeError("alpaca down")

    monkeypatch.setattr(discovery, "_fetch_from_alpaca", _boom)

    out = await discovery.get_discovery_feeds(20)
    assert out["stale"] is False
    assert out["error"] == discovery._UNAVAILABLE
    assert out["most_actives"] == []
    assert out["gainers"] == []
    assert out["losers"] == []
    assert out["last_updated"] is None


async def test_different_top_is_a_distinct_cache_entry(monkeypatch) -> None:
    calls: list[int] = []
    monkeypatch.setattr(
        discovery,
        "_fetch_from_alpaca",
        lambda top: (calls.append(top), _payload())[1],
    )
    await discovery.get_discovery_feeds(20)
    await discovery.get_discovery_feeds(10)
    assert calls == [20, 10]  # separate keys → two fetches
