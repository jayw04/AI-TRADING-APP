"""P8 §2 — scanner engine: match / skip-and-record + universe resolution."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pandas as pd

from app.db.models.trading_profile import TradingProfile
from app.db.models.user import User
from app.services.scanner.engine import resolve_universe, run_scan


def _bars(rows: int = 5) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "t": pd.date_range("2026-01-01", periods=rows, tz="UTC"),
            "o": [100.0] * rows,
            "h": [101.0] * rows,
            "l": [99.0] * rows,
            "c": [100.0] * rows,
            "v": [1_000_000] * rows,
        }
    )


class _FakeBarCache:
    def __init__(self, bars_by_symbol: dict[str, pd.DataFrame]) -> None:
        self._b = bars_by_symbol

    async def get_bars(
        self, symbol: str, timeframe: str, start: Any, end: Any
    ) -> pd.DataFrame:
        return self._b.get(symbol, pd.DataFrame())


class _FakeComputer:
    def __init__(self, series_by_symbol: dict[str, dict[str, pd.Series]]) -> None:
        self._s = series_by_symbol

    def compute(
        self, bars: pd.DataFrame, names: list[str], symbol: str, timeframe: str
    ) -> dict[str, Any]:
        return self._s.get(symbol, {})


async def _feeds() -> dict[str, Any]:
    return {
        "most_actives": [{"symbol": "AAPL"}],
        "gainers": [{"symbol": "MSFT"}],
        "losers": [{"symbol": "aapl"}],  # dup (case) — must dedupe
    }


async def test_match_and_skip(session_factory) -> None:
    bar_cache = _FakeBarCache({"AAPL": _bars(), "MSFT": _bars()})  # TSLA absent
    computer = _FakeComputer(
        {
            "AAPL": {"RSI14": pd.Series([50.0, 30.0])},  # matches < 35
            "MSFT": {"RSI14": pd.Series([60.0, 40.0])},  # evaluated, no match
        }
    )
    async with session_factory() as session:
        result = await run_scan(
            session,
            criteria="RSI14 < 35",
            universe_kind="symbols",
            universe_symbols=["AAPL", "MSFT", "TSLA"],
            timeframe="1Day",
            user_id=1,
            bar_cache=bar_cache,
            indicator_computer=computer,
            discovery_feeds_fn=_feeds,
            now=datetime.now(UTC),
        )
    assert [m.symbol for m in result.matched] == ["AAPL"]
    assert result.matched[0].values == {"RSI14": 30.0}
    assert {(s.symbol, s.reason) for s in result.skipped} == {("TSLA", "no_bars")}
    assert result.universe_size == 3
    assert result.evaluated == 2  # AAPL + MSFT (TSLA skipped)


async def test_nan_indicator_is_skipped(session_factory) -> None:
    bar_cache = _FakeBarCache({"AAPL": _bars()})
    computer = _FakeComputer({"AAPL": {"RSI14": pd.Series([50.0, float("nan")])}})
    async with session_factory() as session:
        result = await run_scan(
            session,
            criteria="RSI14 < 35",
            universe_kind="symbols",
            universe_symbols=["AAPL"],
            timeframe="1Day",
            user_id=1,
            bar_cache=bar_cache,
            indicator_computer=computer,
            discovery_feeds_fn=_feeds,
            now=datetime.now(UTC),
        )
    assert result.matched == []
    assert [(s.symbol, s.reason) for s in result.skipped] == [("AAPL", "nan_indicator")]


async def test_field_only_criterion_needs_no_indicator(session_factory) -> None:
    bar_cache = _FakeBarCache({"AAPL": _bars()})
    computer = _FakeComputer({})  # never consulted — no indicators referenced
    async with session_factory() as session:
        result = await run_scan(
            session,
            criteria="close > 50",
            universe_kind="symbols",
            universe_symbols=["AAPL"],
            timeframe="1Day",
            user_id=1,
            bar_cache=bar_cache,
            indicator_computer=computer,
            discovery_feeds_fn=_feeds,
            now=datetime.now(UTC),
        )
    assert [m.symbol for m in result.matched] == ["AAPL"]  # close 100 > 50


async def test_resolve_universe_symbols_dedup_upper(session_factory) -> None:
    async with session_factory() as session:
        out = await resolve_universe(
            session,
            kind="symbols",
            symbols=["aapl", "MSFT", "AAPL"],
            user_id=1,
            discovery_feeds_fn=_feeds,
        )
    assert out == ["AAPL", "MSFT"]


async def test_resolve_universe_discovery_feeds(session_factory) -> None:
    async with session_factory() as session:
        out = await resolve_universe(
            session,
            kind="discovery_feeds",
            symbols=None,
            user_id=1,
            discovery_feeds_fn=_feeds,
        )
    assert out == ["AAPL", "MSFT"]  # losers' lowercase aapl deduped


async def test_resolve_universe_watchlist_excludes_do_not_trade(
    session_factory,
) -> None:
    async with session_factory() as session:
        now = datetime.now(UTC)
        session.add(User(id=1, email="dev@x", display_name="Dev"))
        session.add(
            TradingProfile(
                user_id=1,
                watchlist_json={
                    "core": ["AAPL"],
                    "swing_candidates": ["MSFT", "NVDA"],
                    "do_not_trade": ["NVDA"],
                },
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()
        out = await resolve_universe(
            session,
            kind="watchlist",
            symbols=None,
            user_id=1,
            discovery_feeds_fn=_feeds,
        )
    assert out == ["AAPL", "MSFT"]
