"""Reproducible price adjustment from stored raw prices and provider factors.

Raw prices are never overwritten. An adjusted series is computed on demand:

* ``hfq`` (后复权) price = raw price x the back-adjustment factor in force that day.
* ``qfq`` (前复权) price = raw price x factor / factor on a stated ``reference_date``. The reference
  date is part of the result, because a forward-adjusted history changes every time a new corporate
  action occurs.

Providers publish factors on different scales (Tushare's cumulative factor, Baostock's step factor),
so only factor *ratios* are comparable between providers. Returns computed from either are equal.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any


class FactorGap(ValueError):
    """A bar has no factor in force (no factor row on or before its date)."""


@dataclass(frozen=True)
class AdjustedSeries:
    symbol: str
    basis: str  # "HFQ" or "QFQ"
    reference_date: date | None  # QFQ only
    dates: tuple[date, ...]
    close: tuple[float, ...]
    open: tuple[float, ...]


def factor_on(factor_rows: Iterable[Mapping[str, Any]], days: Iterable[date]) -> dict[date, float]:
    """The factor in force on each of ``days``.

    Works for both kinds: a cumulative factor published daily and a step factor published on change
    dates are both "the latest row on or before the day". A day earlier than every row raises."""
    pts = sorted(
        (r["trade_date"], float(r["factor"])) for r in factor_rows if r["factor"] is not None
    )
    if not pts:
        raise FactorGap("no factor rows")
    keys = [d for d, _ in pts]
    out: dict[date, float] = {}
    for day in days:
        i = bisect_right(keys, day)
        if i == 0:
            raise FactorGap(f"no factor on or before {day} (first factor row {keys[0]})")
        out[day] = pts[i - 1][1]
    return out


def _traded(bars: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    rows = [b for b in bars if b.get("trade_status", 1) == 1 and b.get("close") is not None]
    return sorted(rows, key=lambda b: b["trade_date"])


def hfq(
    symbol: str, bars: Iterable[Mapping[str, Any]], factor_rows: Iterable[Mapping[str, Any]]
) -> AdjustedSeries:
    rows = _traded(bars)
    f = factor_on(factor_rows, [b["trade_date"] for b in rows])
    return AdjustedSeries(
        symbol=symbol,
        basis="HFQ",
        reference_date=None,
        dates=tuple(b["trade_date"] for b in rows),
        close=tuple(b["close"] * f[b["trade_date"]] for b in rows),
        open=tuple(b["open"] * f[b["trade_date"]] for b in rows),
    )


def qfq(
    symbol: str,
    bars: Iterable[Mapping[str, Any]],
    factor_rows: Iterable[Mapping[str, Any]],
    *,
    reference_date: date,
) -> AdjustedSeries:
    rows_f = list(factor_rows)
    rows = _traded(bars)
    f = factor_on(rows_f, [b["trade_date"] for b in rows])
    ref = factor_on(rows_f, [reference_date])[reference_date]
    return AdjustedSeries(
        symbol=symbol,
        basis="QFQ",
        reference_date=reference_date,
        dates=tuple(b["trade_date"] for b in rows),
        close=tuple(b["close"] * f[b["trade_date"]] / ref for b in rows),
        open=tuple(b["open"] * f[b["trade_date"]] / ref for b in rows),
    )


def total_return(series: AdjustedSeries, start: date, end: date) -> float | None:
    """Close-to-close adjusted return between the last closes on or before ``start`` and ``end``."""
    i = bisect_right(series.dates, start)
    j = bisect_right(series.dates, end)
    if i == 0 or j == 0:
        return None
    a, b = series.close[i - 1], series.close[j - 1]
    return b / a - 1.0
