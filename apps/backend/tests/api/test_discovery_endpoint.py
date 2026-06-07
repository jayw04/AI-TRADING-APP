"""P8 §1 — ``GET /api/v1/discovery/feeds`` endpoint shape.

The service (``get_discovery_feeds``) is monkeypatched; this asserts the
endpoint maps the payload onto ``DiscoveryFeedsResponse`` and never 5xx's on a
feed error (the stale/error fields pass through with 200). Auth is handled by
the autouse override in conftest (authenticated as user 1).
"""

from __future__ import annotations


async def test_feeds_endpoint_happy_shape(client, monkeypatch) -> None:
    from app.api.v1 import discovery as ep

    async def _fake(top: int = 20) -> dict:
        return {
            "most_actives": [
                {"symbol": "AAPL", "volume": 1000.0, "trade_count": 50.0}
            ],
            "gainers": [
                {"symbol": "TSLA", "percent_change": 5.0, "change": 10.0, "price": 210.0}
            ],
            "losers": [],
            "last_updated": "2026-06-07T12:00:00",
            "stale": False,
            "error": None,
        }

    monkeypatch.setattr(ep, "get_discovery_feeds", _fake)

    resp = await client.get("/api/v1/discovery/feeds")
    assert resp.status_code == 200
    body = resp.json()
    assert body["most_actives"][0]["symbol"] == "AAPL"
    assert body["gainers"][0]["percent_change"] == 5.0
    assert body["losers"] == []
    assert body["stale"] is False
    assert body["error"] is None


async def test_feeds_endpoint_error_passes_through_200(client, monkeypatch) -> None:
    from app.api.v1 import discovery as ep

    async def _fake(top: int = 20) -> dict:
        return {
            "most_actives": [],
            "gainers": [],
            "losers": [],
            "last_updated": None,
            "stale": False,
            "error": "discovery feeds unavailable",
        }

    monkeypatch.setattr(ep, "get_discovery_feeds", _fake)

    resp = await client.get("/api/v1/discovery/feeds")
    assert resp.status_code == 200  # graceful — never 5xx on a feed blip
    body = resp.json()
    assert body["error"] == "discovery feeds unavailable"
    assert body["most_actives"] == []
