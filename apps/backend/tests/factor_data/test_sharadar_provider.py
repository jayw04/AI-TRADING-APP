"""Sharadar REST provider: cursor pagination + config guard (no live calls).

Uses httpx.MockTransport so the datatables contract (columns/data + meta cursor)
is exercised without touching the network or spending rate limit.
"""

from __future__ import annotations

import httpx
import pytest

from app.factor_data.providers import sharadar as mod
from app.factor_data.providers.sharadar import SharadarConfigError, SharadarProvider


def _install_mock(monkeypatch, handler) -> None:
    transport = httpx.MockTransport(handler)
    real_client = httpx.Client

    def _client(**kwargs):
        kwargs.pop("follow_redirects", None)
        return real_client(transport=transport, **kwargs)

    monkeypatch.setattr(mod.httpx, "Client", _client)


def test_fetch_table_follows_cursor_pagination(monkeypatch) -> None:
    seen_keys: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_keys.append(request.url.params.get("api_key", ""))
        cursor = request.url.params.get("qopts.cursor_id")
        cols = [{"name": "ticker"}, {"name": "date"}]
        if cursor is None:
            body = {
                "datatable": {"columns": cols, "data": [["AAA", "2020-01-01"]]},
                "meta": {"next_cursor_id": "page2"},
            }
        else:
            assert cursor == "page2"
            body = {
                "datatable": {"columns": cols, "data": [["AAA", "2020-01-02"]]},
                "meta": {"next_cursor_id": None},
            }
        return httpx.Response(200, json=body)

    _install_mock(monkeypatch, handler)
    with SharadarProvider(api_key="testkey") as p:
        df = p.fetch_table("SEP", ticker="AAA")

    assert list(df.columns) == ["ticker", "date"]
    assert len(df) == 2  # both pages concatenated
    assert df["date"].tolist() == ["2020-01-01", "2020-01-02"]
    assert seen_keys == ["testkey", "testkey"]  # key sent on every page


def test_fetch_table_empty(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"datatable": {"columns": [{"name": "ticker"}], "data": []}, "meta": {}},
        )

    _install_mock(monkeypatch, handler)
    with SharadarProvider(api_key="testkey") as p:
        df = p.fetch_table("SEP", ticker="NONE")
    assert df.empty


def test_missing_key_raises() -> None:
    with pytest.raises(SharadarConfigError):
        SharadarProvider(api_key="")


def test_http_error_propagates(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": "forbidden"})

    _install_mock(monkeypatch, handler)
    with SharadarProvider(api_key="testkey") as p, pytest.raises(httpx.HTTPStatusError):
        p.fetch_table("SEP", ticker="AAA")
