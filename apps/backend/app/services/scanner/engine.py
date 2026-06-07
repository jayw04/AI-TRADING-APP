"""Scanner engine (P8 §2): resolve a universe + run a criterion over it.

Per-symbol: cached bars → latest indicator values → evaluate the criterion.
A symbol with no bars or a NaN referenced indicator is **skipped and recorded**
(P8 Decision: skip-and-record), never fatal. No LLM anywhere (Decision 1).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.trading_profile import TradingProfile
from app.services.scanner.criteria import (
    _MULTI_SUBNAMES,
    _NAME_TO_CORE,
    INDICATOR_NAMES,
    ParsedCriteria,
    evaluate,
    validate_criteria,
)

SCAN_TIMEFRAME_DEFAULT = "1Day"
# Lookback long enough for the slowest core indicator (SMA200) on daily bars.
_LOOKBACK_DAYS: dict[str, int] = {"1Day": 400}
_LOOKBACK_DAYS_DEFAULT = 90

# field name → bars column
_FIELD_COL: dict[str, str] = {
    "open": "o",
    "high": "h",
    "low": "l",
    "close": "c",
    "volume": "v",
    "price": "c",  # price aliases close
}

DiscoveryFeedsFn = Callable[[], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class SymbolMatch:
    symbol: str
    values: dict[str, float]  # the referenced values, for the "why"


@dataclass(frozen=True)
class SymbolSkip:
    symbol: str
    reason: str  # "no_bars" | "nan_indicator"


@dataclass(frozen=True)
class ScanResult:
    matched: list[SymbolMatch] = field(default_factory=list)
    skipped: list[SymbolSkip] = field(default_factory=list)
    universe_size: int = 0

    @property
    def evaluated(self) -> int:
        return self.universe_size - len(self.skipped)


def _lookback_start(now: datetime, timeframe: str) -> datetime:
    return now - timedelta(
        days=_LOOKBACK_DAYS.get(timeframe, _LOOKBACK_DAYS_DEFAULT)
    )


def _latest(series: pd.Series) -> float | None:
    if series is None or len(series) == 0:
        return None
    val = series.iloc[-1]
    if pd.isna(val):
        return None
    return float(val)


def _latest_values(
    bars: pd.DataFrame, computed: dict[str, Any], parsed: ParsedCriteria
) -> dict[str, float] | None:
    """Build the name→value map for exactly the referenced names. Returns None
    if any referenced value is NaN / absent (→ the symbol is skipped)."""
    values: dict[str, float] = {}
    last = bars.iloc[-1]

    for name in parsed.names:
        if name in INDICATOR_NAMES:
            core = _NAME_TO_CORE[name]
            obj = computed.get(core)
            if name in _MULTI_SUBNAMES:
                series = obj.get(name) if isinstance(obj, dict) else None
            else:
                series = obj if isinstance(obj, pd.Series) else None
            latest = _latest(series)
        else:  # bar field
            raw = last.get(_FIELD_COL[name])
            latest = None if raw is None or pd.isna(raw) else float(raw)
        if latest is None:
            return None
        values[name] = latest
    return values


async def resolve_universe(
    session: AsyncSession,
    *,
    kind: str,
    symbols: list[str] | None,
    user_id: int,
    discovery_feeds_fn: DiscoveryFeedsFn,
) -> list[str]:
    """Resolve the universe spec to a deduped, upper-cased symbol list."""
    if kind == "symbols":
        raw = list(symbols or [])
    elif kind == "discovery_feeds":
        feeds = await discovery_feeds_fn()
        raw = [
            row["symbol"]
            for key in ("most_actives", "gainers", "losers")
            for row in feeds.get(key, [])
        ]
    elif kind == "watchlist":
        profile = (
            await session.execute(
                select(TradingProfile).where(TradingProfile.user_id == user_id)
            )
        ).scalar_one_or_none()
        watchlist = (profile.watchlist_json or {}) if profile else {}
        do_not_trade = {s.upper() for s in watchlist.get("do_not_trade", [])}
        raw = [
            s
            for tier in ("core", "swing_candidates")
            for s in watchlist.get(tier, [])
            if s.upper() not in do_not_trade
        ]
    else:
        raise ValueError(f"unknown universe kind: {kind}")

    seen: set[str] = set()
    out: list[str] = []
    for s in raw:
        u = str(s).upper()
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


async def run_scan(
    session: AsyncSession,
    *,
    criteria: str,
    universe_kind: str,
    universe_symbols: list[str] | None,
    timeframe: str,
    user_id: int,
    bar_cache: Any,
    indicator_computer: Any,
    discovery_feeds_fn: DiscoveryFeedsFn,
    now: datetime,
) -> ScanResult:
    """Evaluate ``criteria`` over the resolved universe. Never raises on a
    per-symbol problem (skip-and-record); re-parses defensively."""
    parsed = validate_criteria(criteria)
    universe = await resolve_universe(
        session,
        kind=universe_kind,
        symbols=universe_symbols,
        user_id=user_id,
        discovery_feeds_fn=discovery_feeds_fn,
    )
    start = _lookback_start(now, timeframe)
    indicator_names = list(parsed.indicators)

    matched: list[SymbolMatch] = []
    skipped: list[SymbolSkip] = []
    for sym in universe:
        bars = await bar_cache.get_bars(sym, timeframe, start, now)
        if bars is None or bars.empty:
            skipped.append(SymbolSkip(sym, "no_bars"))
            continue
        computed = (
            indicator_computer.compute(
                bars, names=indicator_names, symbol=sym, timeframe=timeframe
            )
            if indicator_names
            else {}
        )
        values = _latest_values(bars, computed, parsed)
        if values is None:
            skipped.append(SymbolSkip(sym, "nan_indicator"))
            continue
        if evaluate(parsed, values):
            matched.append(
                SymbolMatch(sym, {n: values[n] for n in parsed.names})
            )

    return ScanResult(
        matched=matched, skipped=skipped, universe_size=len(universe)
    )
