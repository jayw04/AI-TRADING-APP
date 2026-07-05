"""QuiverClient — auth/header shape + disabled-when-empty (offline; httpx MockTransport)."""

from __future__ import annotations

import httpx
import pytest

from app.altdata.quiver.client import QuiverClient, QuiverDisabled


def test_empty_key_disables():
    with pytest.raises(QuiverDisabled):
        QuiverClient(api_key="")


def test_sends_token_auth_and_browser_user_agent():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("Authorization")
        seen["ua"] = request.headers.get("User-Agent")
        seen["path"] = request.url.path
        return httpx.Response(200, json=[{"Ticker": "LMT", "action_date": "2026-07-02"}])

    with QuiverClient(api_key="tok123", transport=httpx.MockTransport(handler)) as c:
        rows = c.govcontracts_history("lmt")

    assert seen["auth"] == "Token tok123"                      # Token scheme, not Bearer
    assert "Mozilla/" in seen["ua"] and "Chrome/" in seen["ua"]  # Cloudflare needs a browser UA
    assert seen["path"] == "/beta/historical/govcontractsall/LMT"
    assert rows == [{"Ticker": "LMT", "action_date": "2026-07-02"}]


def test_raises_on_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="error code: 1010")

    with (
        QuiverClient(api_key="tok", transport=httpx.MockTransport(handler)) as c,
        pytest.raises(httpx.HTTPStatusError),
    ):
        c.govcontracts_live()
