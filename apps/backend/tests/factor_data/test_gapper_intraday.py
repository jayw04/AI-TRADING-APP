"""GAPPER-001 intraday auto-cache — sector resolution + the v0.2 §7 exclusion rules."""

from __future__ import annotations

from datetime import date

import pandas as pd

from app.factor_data.gapper_intraday import (
    SECTOR_SPDR,
    cache_candidate_event,
    resolve_sector_etf,
)


class _FakeCon:
    """Minimal DuckDB-con stand-in: ``execute(sql, params).fetchone()`` → ``(sector,)`` or ``None``."""

    def __init__(self, mapping: dict[str, str | None]) -> None:
        self._m = mapping
        self._last: str | None = None

    def execute(self, sql: str, params: list) -> _FakeCon:  # noqa: ARG002
        self._last = params[0]
        return self

    def fetchone(self):
        t = self._last
        return (self._m[t],) if t in self._m else None


class _StubBar:
    def __init__(self, per_symbol: dict[str, int]) -> None:
        self._p = per_symbol

    async def get_bars(self, symbol, timeframe, start, end):  # noqa: ANN001, ARG002
        return pd.DataFrame({"t": range(self._p.get(symbol, 0))})


def test_sector_spdr_covers_11_gics_sectors() -> None:
    assert len(SECTOR_SPDR) == 11
    assert set(SECTOR_SPDR.values()) == {
        "XLK", "XLC", "XLF", "XLV", "XLI", "XLY", "XLP", "XLE", "XLU", "XLB", "XLRE",
    }


def test_resolve_sector_etf_maps_known_sector() -> None:
    con = _FakeCon({"AMD": "Technology", "JPM": "Financial Services"})
    assert resolve_sector_etf(con, "AMD") == "XLK"
    assert resolve_sector_etf(con, "JPM") == "XLF"


def test_resolve_sector_etf_unresolved() -> None:
    con = _FakeCon({"XYZ": "Made-Up Sector", "NUL": None})
    assert resolve_sector_etf(con, "MISSING") is None  # ticker absent
    assert resolve_sector_etf(con, "XYZ") is None       # sector not mapped to a SPDR
    assert resolve_sector_etf(con, "NUL") is None        # null sector


async def test_cache_event_excludes_unresolved_sector() -> None:
    res = await cache_candidate_event(_StubBar({}), _FakeCon({}), "MISSING", date(2026, 7, 7))
    assert res["cached"] is False
    assert res["excluded_reason"] == "sector_etf_unresolved"


async def test_cache_event_caches_candidate_spy_and_sector() -> None:
    con = _FakeCon({"AMD": "Technology"})
    bc = _StubBar({"AMD": 390, "SPY": 390, "XLK": 390})
    res = await cache_candidate_event(bc, con, "AMD", date(2026, 7, 7))
    assert res["cached"] is True
    assert res["sector_etf"] == "XLK"
    assert set(res["bars"]) == {"AMD", "SPY", "XLK"}
    assert res["excluded_reason"] is None


async def test_cache_event_flags_missing_candidate_intraday() -> None:
    con = _FakeCon({"THIN": "Technology"})
    bc = _StubBar({"THIN": 0, "SPY": 390, "XLK": 390})  # candidate has no intraday
    res = await cache_candidate_event(bc, con, "THIN", date(2026, 7, 7))
    assert res["cached"] is False
    assert res["excluded_reason"] == "candidate_intraday_missing"
