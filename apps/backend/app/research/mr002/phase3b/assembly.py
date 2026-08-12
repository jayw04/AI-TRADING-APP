"""Assemble `MarketData` / `SecurityData` for the validation window from decoded parquet tables.

This is the most research-sensitive code outside the frozen producer modules, and the risk it
carries is not plumbing but **semantic reconstruction drift**: an assembly that looks like the
Phase 2B DuckDB path but hands `produce_decision` subtly different inputs would change the study's
numbers without changing any frozen rule.

Two disciplines answer that risk.

**The table-to-domain mapping is explicit and closed.** `COLUMN_PURPOSE` registers exactly one
purpose per consumed column, and `verify_column_purposes` refuses a table carrying a column nobody
registered. There are no implicit defaults, no coercions and no "if absent use X" behaviour: a
value is present and finite, or the session is not PRESENT and the frozen dispositions apply.

**The semantics are mirrored, not re-derived.** Every rule here is taken from the Phase 2B
orchestration path — calendar-aligned `closeadj` for returns, `closeunadj`/`volume` for ADV,
`PRESENT/YOUNG/UNEXPLAINED_HOLE` classification keyed off the first present session, duplicate rows
refused. In particular `HALT_WITH_EVIDENCE` is deliberately NOT produced here, because the Phase 2B
path does not produce it either, and an "improvement" would be a divergence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from ..spq1.calendar import RegisteredCalendar
from ..spq1.identities import GOVERNING_IDENTITIES, REQUIRED_IDENTITY_KEYS, InputIdentityRegistry
from ..spq1.producer import MarketData, SecurityData
from ..spq1.returns import CellStatus, arithmetic_total_returns


class AssemblyRefused(Exception):
    """An input that cannot be assembled under the frozen rules. Never coerced."""


# --- the closed table-to-domain mapping ---------------------------------------------------------
# Every consumed column has exactly one registered purpose. A column absent from this table is not
# consumed; a column present here that the table does not carry is a refusal.
COLUMN_PURPOSE: dict[tuple[str, str], str] = {
    ("prices", "ticker"): "security key",
    ("prices", "date"): "registered-session alignment key",
    ("prices", "open"): "execution open (t+1 fill; gap numerator)",
    ("prices", "high"): "UNCONSUMED",
    ("prices", "low"): "UNCONSUMED",
    ("prices", "close"): "split-adjusted close (gap denominator)",
    ("prices", "closeadj"): "total-return signal series",
    ("prices", "closeunadj"): "raw close for ADV",
    ("prices", "volume"): "raw volume for ADV",
    ("etf_prices", "ticker"): "sector-proxy / SPY key",
    ("etf_prices", "date"): "registered-session alignment key",
    ("etf_prices", "adjclose"): "factor total-return series",
}

CONSUMED = {k: v for k, v in COLUMN_PURPOSE.items() if v != "UNCONSUMED"}


def verify_column_purposes(table_name: str, columns: tuple[str, ...]) -> None:
    """Refuse a table carrying a column with no registered purpose, or missing a registered one."""
    registered = {c for (t, c) in COLUMN_PURPOSE if t == table_name}
    if not registered:
        raise AssemblyRefused(
            f"{table_name}: no registered column purposes; nothing may be consumed"
        )
    unregistered = sorted(set(columns) - registered)
    absent = sorted(registered - set(columns))
    if unregistered:
        raise AssemblyRefused(f"{table_name}: columns with no registered purpose: {unregistered}")
    if absent:
        raise AssemblyRefused(f"{table_name}: registered columns absent: {absent}")


# --- calendar -----------------------------------------------------------------------------------
def registered_calendar(
    sessions: list[str], *, expected_identity: str | None = None
) -> RegisteredCalendar:
    """Build the calendar from the REGISTERED session list, never derived from the price data.

    Deriving the calendar from whatever rows happened to arrive would let a missing bar silently
    redefine the session ordinals every window rule is expressed over.
    """
    if not sessions:
        raise AssemblyRefused("empty registered session list")
    calendar = RegisteredCalendar(tuple(sessions))
    if expected_identity is not None and calendar.identity != expected_identity:
        raise AssemblyRefused(
            f"calendar identity {calendar.identity} != registered {expected_identity}"
        )
    return calendar


# --- price series -------------------------------------------------------------------------------
@dataclass(frozen=True)
class SecuritySeries:
    """One security's calendar-aligned series, exactly the fields the producer consumes."""

    symbol: str
    stock_ret: np.ndarray
    status: list[CellStatus]
    raw_close: np.ndarray
    raw_volume: np.ndarray


def _column(table: Any, name: str) -> list:
    return table.column(name).to_pylist()


def price_series_by_symbol(prices: Any, calendar: RegisteredCalendar) -> dict[str, dict]:
    """Calendar-align every security's series, mirroring `adapters.price_adapter.load_price_series`.

    A duplicate (ticker, session) row is refused rather than last-wins: silently keeping one of two
    contradictory bars is how a price becomes unreproducible.
    """
    verify_column_purposes("prices", tuple(prices.column_names))
    tickers = _column(prices, "ticker")
    dates = [str(d) for d in _column(prices, "date")]
    aligned_fields = ("closeadj", "closeunadj", "volume", "open", "close")
    fields = {name: _column(prices, name) for name in aligned_fields}

    by_symbol: dict[str, dict[str, tuple[float, float, float]]] = {}
    for i, ticker in enumerate(tickers):
        symbol, session = str(ticker), dates[i]
        rows = by_symbol.setdefault(symbol, {})
        if session in rows:
            raise AssemblyRefused(f"duplicate price row for {symbol} {session}")
        rows[session] = tuple(
            float("nan") if fields[name][i] is None else float(fields[name][i])
            for name in aligned_fields
        )

    n = len(calendar)
    out: dict[str, dict] = {}
    for symbol, rows in by_symbol.items():
        arrays = {k: np.full(n, np.nan, dtype=np.float64) for k in aligned_fields}
        for i, session in enumerate(calendar.sessions):
            if session in rows:
                for name, value in zip(aligned_fields, rows[session], strict=True):
                    arrays[name][i] = value
        out[symbol] = arrays
    return out


def classify(closeadj: np.ndarray) -> list[CellStatus]:
    """PRESENT / YOUNG / UNEXPLAINED_HOLE, keyed off the first present session.

    Mirrors the Phase 2B path exactly. HALT_WITH_EVIDENCE is not produced here because that path
    does not produce it; adding it would be a divergence, not an improvement.
    """
    present = np.isfinite(closeadj)
    if not present.any():
        raise AssemblyRefused("security has no present session in the window")
    first = int(np.argmax(present))
    return [
        CellStatus.PRESENT
        if present[i]
        else (CellStatus.YOUNG if i < first else CellStatus.UNEXPLAINED_HOLE)
        for i in range(len(closeadj))
    ]


def security_series(prices: Any, calendar: RegisteredCalendar) -> dict[str, SecuritySeries]:
    """Every security with at least one present session, in canonical symbol order."""
    out: dict[str, SecuritySeries] = {}
    for symbol, arrays in sorted(price_series_by_symbol(prices, calendar).items()):
        closeadj = arrays["closeadj"]
        if not np.isfinite(closeadj).any():
            continue  # mirrors the Phase 2B skip: no present bar, no security
        out[symbol] = SecuritySeries(
            symbol=symbol,
            stock_ret=arithmetic_total_returns(closeadj),
            status=classify(closeadj),
            raw_close=arrays["closeunadj"],
            raw_volume=arrays["volume"],
        )
    return out


# --- factor series ------------------------------------------------------------------------------
def factor_returns(
    etf_prices: Any, calendar: RegisteredCalendar, etf_by_sector: dict[str, str], spy_ticker: str
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """SPY and per-sector total returns, calendar-aligned then differenced.

    Alignment happens BEFORE differencing, so a missing session produces NaN returns on both sides
    of the hole rather than silently splicing across it.
    """
    verify_column_purposes("etf_prices", tuple(etf_prices.column_names))
    tickers = [str(t) for t in _column(etf_prices, "ticker")]
    dates = [str(d) for d in _column(etf_prices, "date")]
    values = _column(etf_prices, "adjclose")

    series: dict[str, dict[str, float]] = {}
    for i, ticker in enumerate(tickers):
        rows = series.setdefault(ticker, {})
        session = dates[i]
        if session in rows:
            raise AssemblyRefused(f"duplicate etf row for {ticker} {session}")
        rows[session] = float("nan") if values[i] is None else float(values[i])

    def aligned(ticker: str) -> np.ndarray:
        rows = series.get(ticker, {})
        return np.array([rows.get(s, np.nan) for s in calendar.sessions], dtype=np.float64)

    spy_levels = aligned(spy_ticker)
    if not np.isfinite(spy_levels).any():
        raise AssemblyRefused(f"no {spy_ticker} observation in the registered window")
    spy_ret = arithmetic_total_returns(spy_levels)
    sector_ret = {
        sector: arithmetic_total_returns(aligned(etf))
        for sector, etf in sorted(etf_by_sector.items())
    }
    return spy_ret, sector_ret


# --- assembled structures -----------------------------------------------------------------------
def identity_registry(
    calendar: RegisteredCalendar, observed: dict[str, str]
) -> InputIdentityRegistry:
    """Bind every required identity slot; a missing slot refuses rather than defaulting."""
    ids = dict(observed)
    ids["registered_exchange_calendar"] = calendar.identity
    ids.update(GOVERNING_IDENTITIES)
    absent = sorted(set(REQUIRED_IDENTITY_KEYS) - set(ids))
    if absent:
        raise AssemblyRefused(f"required input identities absent: {absent}")
    return InputIdentityRegistry(ids)


def market_data(
    calendar: RegisteredCalendar,
    spy_ret: np.ndarray,
    sector_ret: dict[str, np.ndarray],
    observed_identities: dict[str, str],
) -> MarketData:
    ids = dict(observed_identities)
    ids["registered_exchange_calendar"] = calendar.identity
    return MarketData(calendar, spy_ret, sector_ret, ids)


def security_data(
    series: SecuritySeries, sector_records: list, eligibility_checks: list
) -> SecurityData:
    return SecurityData(
        series.symbol,
        series.stock_ret,
        series.status,
        series.raw_close,
        series.raw_volume,
        sector_records,
        eligibility_checks,
    )
