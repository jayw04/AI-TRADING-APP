"""EDGAR client — fair-access User-Agent + disabled-when-unset (offline via MockTransport)."""

from __future__ import annotations

import httpx
import pytest

from app.altdata.sec.client import EdgarClient, EdgarDisabled


def test_empty_user_agent_disables():
    with pytest.raises(EdgarDisabled):
        EdgarClient(user_agent="")
    with pytest.raises(EdgarDisabled):
        EdgarClient(user_agent="   ")


def test_sends_user_agent_and_parses_json():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["ua"] = request.headers.get("user-agent")
        return httpx.Response(200, json={"ok": True})

    with EdgarClient(user_agent="TestOrg contact@example.com", rate_limit_per_sec=1000,
                     transport=httpx.MockTransport(handler)) as c:
        assert c.get_json("https://data.sec.gov/x.json") == {"ok": True}
    assert seen["ua"] == "TestOrg contact@example.com"  # SEC fair-access requirement


def test_raises_for_http_error():
    client = EdgarClient(user_agent="TestOrg contact@example.com", rate_limit_per_sec=1000,
                         transport=httpx.MockTransport(lambda r: httpx.Response(404)))
    with client, pytest.raises(httpx.HTTPStatusError):
        client.get_text("https://www.sec.gov/missing")
