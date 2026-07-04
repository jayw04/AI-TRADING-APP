"""AlpacaDistributionsProvider (PORT-001 total-return pricing) — parsing, validation, retry, fail-open.

Offline: a fake corporate-actions client (dict payloads, no network). The provider's pure grouping +
validation and its retry/fail-open control flow are what's exercised; the total-return math itself is
covered by tests/factor_data/test_total_return.py."""

from __future__ import annotations

from datetime import date

import pandas as pd

from app.market_data.alpaca_distributions import AlpacaDistributionsProvider

_START, _END = date(2026, 1, 1), date(2026, 6, 1)


class _FakeCAClient:
    """Stands in for alpaca CorporateActionsClient. Returns the category dict directly (the provider
    reads ``getattr(resp, "data", resp)``). Optionally fails the first ``fail_times`` calls."""

    def __init__(self, data: dict, *, fail_times: int = 0, exc: Exception | None = None) -> None:
        self._data = data
        self._fail_times = fail_times
        self._exc = exc or RuntimeError("transient")
        self.calls = 0

    def get_corporate_actions(self, req):  # noqa: ANN001 — req ignored by the fake
        self.calls += 1
        if self.calls <= self._fail_times:
            raise self._exc
        return self._data


_DIVS_AND_SPLITS = {
    "cash_dividends": [
        {"symbol": "TLT", "ex_date": date(2026, 1, 10), "rate": 0.30, "process_date": date(2026, 1, 12)},
        {"symbol": "TLT", "ex_date": date(2026, 2, 10), "rate": 0.31, "process_date": date(2026, 2, 12)},
        # duplicate ex_date, later process_date → kept (deduped, not double-counted)
        {"symbol": "TLT", "ex_date": date(2026, 1, 10), "rate": 0.30, "process_date": date(2026, 1, 15)},
        {"symbol": "TLT", "ex_date": date(2026, 3, 10), "rate": -1.0},          # negative → reject
        {"symbol": "TLT", "ex_date": date(2020, 1, 1), "rate": 0.5},            # out of window → reject
        {"symbol": "TLT", "ex_date": date(2026, 4, 10), "rate": float("nan")},  # NaN → reject
    ],
    "forward_splits": [
        {"symbol": "GLD", "ex_date": date(2026, 1, 20), "new_rate": 2.0, "old_rate": 1.0},   # 2:1 → 2.0
    ],
    "reverse_splits": [
        {"symbol": "GLD", "ex_date": date(2026, 2, 20), "new_rate": 1.0, "old_rate": 10.0},  # 1:10 → 0.1
        {"symbol": "GLD", "ex_date": date(2026, 3, 20), "new_rate": 1.0, "old_rate": 0.0},   # old_rate 0 → reject
    ],
}


async def test_dividends_grouped_and_deduped() -> None:
    p = AlpacaDistributionsProvider(client=_FakeCAClient(_DIVS_AND_SPLITS))
    summary = await p.prefetch(["TLT", "GLD"], _START, _END)
    div, spl = p.distributions("TLT", pd.Timestamp(_START), pd.Timestamp(_END))
    assert list(div.index) == [pd.Timestamp("2026-01-10"), pd.Timestamp("2026-02-10")]  # sorted, deduped
    assert list(div.round(4)) == [0.30, 0.31]
    assert spl.empty
    assert summary.dividends == 2 and summary.fallback is False


async def test_split_multiplier_new_over_old() -> None:
    p = AlpacaDistributionsProvider(client=_FakeCAClient(_DIVS_AND_SPLITS))
    await p.prefetch(["TLT", "GLD"], _START, _END)
    _div, spl = p.distributions("GLD", pd.Timestamp(_START), pd.Timestamp(_END))
    assert list(spl.index) == [pd.Timestamp("2026-01-20"), pd.Timestamp("2026-02-20")]
    assert list(spl.round(4)) == [2.0, 0.1]  # forward 2:1 → 2.0 ; reverse 1:10 → 0.1


async def test_validation_rejects_bad_records() -> None:
    p = AlpacaDistributionsProvider(client=_FakeCAClient(_DIVS_AND_SPLITS))
    summary = await p.prefetch(["TLT", "GLD"], _START, _END)
    # 3 bad dividends (negative, out-of-window, NaN) + 1 bad split (old_rate 0) = 4 rejected
    assert summary.rejected == 4
    assert summary.dividends == 2 and summary.splits == 2


async def test_unknown_symbol_yields_empty() -> None:
    p = AlpacaDistributionsProvider(client=_FakeCAClient(_DIVS_AND_SPLITS))
    await p.prefetch(["TLT"], _START, _END)
    div, spl = p.distributions("ZZZZ", pd.Timestamp(_START), pd.Timestamp(_END))
    assert div.empty and spl.empty


async def test_retry_then_success() -> None:
    client = _FakeCAClient(_DIVS_AND_SPLITS, fail_times=1)  # one transient failure, then success
    p = AlpacaDistributionsProvider(client=client)
    summary = await p.prefetch(["TLT", "GLD"], _START, _END)
    assert client.calls == 2  # retried once
    assert summary.fallback is False and summary.dividends == 2


async def test_persistent_error_fails_open() -> None:
    client = _FakeCAClient(_DIVS_AND_SPLITS, fail_times=99)  # always fails
    p = AlpacaDistributionsProvider(client=client)
    summary = await p.prefetch(["TLT", "GLD"], _START, _END)
    assert summary.fallback is True and summary.dividends == 0
    div, spl = p.distributions("TLT", pd.Timestamp(_START), pd.Timestamp(_END))
    assert div.empty and spl.empty  # cache empty → raw pricing downstream


async def test_auth_error_is_not_retried() -> None:
    err = RuntimeError("forbidden")
    err.status_code = 403  # type: ignore[attr-defined]  — non-transient 4xx fails fast
    client = _FakeCAClient(_DIVS_AND_SPLITS, fail_times=99, exc=err)
    p = AlpacaDistributionsProvider(client=client)
    summary = await p.prefetch(["TLT"], _START, _END)
    assert client.calls == 1  # no retry on a 4xx
    assert summary.fallback is True
