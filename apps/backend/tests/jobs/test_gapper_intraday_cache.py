"""GAPPER-001 intraday auto-cache job — no-record no-op + per-candidate caching."""

from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from app.jobs import gapper_intraday_cache as job


class _FakeCon:
    def __init__(self, mapping: dict[str, str]) -> None:
        self._m = mapping
        self._last: str | None = None

    def execute(self, sql: str, params: list) -> _FakeCon:  # noqa: ARG002
        self._last = params[0]
        return self

    def fetchone(self):
        t = self._last
        return (self._m[t],) if t in self._m else None


class _FakeStore:
    def __init__(self, sectors: dict[str, str]) -> None:
        self.con = _FakeCon(sectors)


class _StubBar:
    def __init__(self, per: dict[str, int]) -> None:
        self._p = per

    async def get_bars(self, symbol, timeframe, start, end):  # noqa: ANN001, ARG002
        return pd.DataFrame({"t": range(self._p.get(symbol, 0))})


async def test_no_record_is_noop(tmp_path) -> None:
    res = await job.run_gapper_intraday_cache_scheduled(
        bar_cache=_StubBar({}), factor_store=_FakeStore({}), directory=str(tmp_path)
    )
    assert res is None


async def test_caches_today_candidates(tmp_path) -> None:
    today = datetime.now(ZoneInfo("America/New_York")).date()
    rec = {"asof": today.isoformat(), "candidates": [{"symbol": "AMD"}, {"symbol": "NVDA"}]}
    (tmp_path / f"premarket_scan_{today.isoformat()}.json").write_text(json.dumps(rec))
    store = _FakeStore({"AMD": "Technology", "NVDA": "Technology"})
    bc = _StubBar({"AMD": 390, "NVDA": 390, "SPY": 390, "XLK": 390})
    res = await job.run_gapper_intraday_cache_scheduled(
        bar_cache=bc, factor_store=store, directory=str(tmp_path)
    )
    assert res == {"asof": today.isoformat(), "candidates": 2, "cached": 2, "excluded": 0}
