"""FMP /stable provider: request shape, error handling, retry, config guard.

Uses httpx.MockTransport so the contract (JSON-array → DataFrame, apikey on every
request, /stable base, error-payload detection, transient retry) is exercised
without touching the network or spending rate limit.
"""

from __future__ import annotations

import httpx
import pytest

from app.factor_data.providers import fmp as mod
from app.factor_data.providers.fmp import FMPConfigError, FMPError, FMPProvider


def _install_mock(monkeypatch, handler) -> None:
    transport = httpx.MockTransport(handler)
    real_client = httpx.Client

    def _client(**kwargs):
        kwargs.pop("follow_redirects", None)
        return real_client(transport=transport, **kwargs)

    monkeypatch.setattr(mod.httpx, "Client", _client)


def test_fetch_returns_dataframe_and_sends_key_on_stable_base(monkeypatch) -> None:
    seen: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        return httpx.Response(200, json=[
            {"symbol": "AAPL", "date": "2025-09-27", "revenue": 416161000000},
        ])

    _install_mock(monkeypatch, handler)
    with FMPProvider(api_key="testkey") as p:
        df = p.income_statement("AAPL", period="annual", limit=40)

    assert list(df.columns) == ["symbol", "date", "revenue"]
    assert len(df) == 1
    url = seen[0]
    assert str(url).startswith("https://financialmodelingprep.com/stable/income-statement")
    assert url.params.get("apikey") == "testkey"  # key sent
    assert url.params.get("symbol") == "AAPL"
    assert url.params.get("period") == "annual"
    assert url.params.get("limit") == "40"


def test_empty_array_yields_empty_dataframe(monkeypatch) -> None:
    _install_mock(monkeypatch, lambda req: httpx.Response(200, json=[]))
    with FMPProvider(api_key="k") as p:
        df = p.delisted_companies(limit=5)
    assert df.empty


def test_error_payload_raises(monkeypatch) -> None:
    _install_mock(
        monkeypatch,
        lambda req: httpx.Response(200, json={"Error Message": "Exclusive Endpoint"}),
    )
    with FMPProvider(api_key="k") as p, pytest.raises(FMPError, match="Exclusive Endpoint"):
        p.ratios("AAPL")


def test_none_params_are_dropped(monkeypatch) -> None:
    seen: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        return httpx.Response(200, json=[{"x": 1}])

    _install_mock(monkeypatch, handler)
    with FMPProvider(api_key="k") as p:
        p.fetch("profile", symbol="AAPL", period=None)
    assert "period" not in seen[0].params  # None filtered out
    assert seen[0].params.get("symbol") == "AAPL"


def test_403_legacy_fails_fast_without_retry(monkeypatch) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(403, json={"Error Message": "Legacy Endpoint"})

    _install_mock(monkeypatch, handler)
    with FMPProvider(api_key="k") as p, pytest.raises(httpx.HTTPStatusError):
        p.income_statement("AAPL")
    assert calls["n"] == 1  # 4xx (non-429) is not retried


def test_transient_5xx_is_retried_then_succeeds(monkeypatch) -> None:
    monkeypatch.setattr(mod.time, "sleep", lambda *_: None)  # no real backoff sleep
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, json={"Error Message": "temporary"})
        return httpx.Response(200, json=[{"ok": 1}])

    _install_mock(monkeypatch, handler)
    with FMPProvider(api_key="k") as p:
        df = p.fetch("income-statement", symbol="AAPL")
    assert calls["n"] == 2  # one 503 retry, then success
    assert len(df) == 1


def test_missing_key_raises_config_error(monkeypatch) -> None:
    # No explicit key and an empty configured key → guard fires.
    import app.factor_data.providers.fmp as fmpmod

    class _S:
        fmp_api_key = ""

    monkeypatch.setattr(fmpmod, "get_settings", lambda: _S())
    with pytest.raises(FMPConfigError):
        FMPProvider()
