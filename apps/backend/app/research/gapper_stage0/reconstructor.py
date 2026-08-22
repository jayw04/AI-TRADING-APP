"""Pure-function event-definition reconstructor (memo §6.5).

0A reconstructs the frozen event definition from **raw premarket minute bars**
— never the vendor top-N. This module computes ``gap_pct`` vs the prior close
plus the volume/price/type filters, from injected data only:

* Premarket minute bars: a pandas frame with columns ``t`` (tz-aware UTC),
  ``o h l c v`` — the ``bar_cache`` day-file shape.
* Prior daily bars: a sequence of ``{"date", "close", "volume"}`` rows.

PIT discipline is **strict and loud**: prior-close / ADV features come only
from data dated strictly ``< asof`` (mirroring
``premarket_scan.store_features_for``'s ``date < ?``), and because this module
receives injected frames rather than issuing the SQL itself, any row dated
``>= asof`` raises :class:`PITViolationError` instead of being silently
filtered — a caller that handed us future data has a leak we must surface.

NO network, NO ``get_settings()``/``get_engine()`` singletons, no I/O.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, time
from typing import Any

import pandas as pd

_ET = "America/New_York"
RTH_OPEN = time(9, 30)

#: ADV lookback, matching the store's 20-day volume average convention.
ADV_LOOKBACK = 20

# Reason codes (feed funnel.Exclusion at the tradability/coverage stages).
REASON_NO_PREMARKET_BARS = "no_premarket_bars"
REASON_NO_PRIOR_CLOSE = "no_prior_close"
REASON_PRICE_BELOW_MIN = "price_below_min"
REASON_PM_VOLUME_BELOW_MIN = "premarket_volume_below_min"
REASON_GAP_BELOW_MIN = "gap_below_min"
REASON_SECURITY_TYPE_EXCLUDED = "security_type_excluded"


class PITViolationError(ValueError):
    """Injected 'historical' data contains rows dated >= asof — a PIT leak."""


@dataclass(frozen=True)
class EventFilters:
    """Frozen volume/price/type filters applied to the reconstructed field."""

    min_price: float = 1.0
    min_premarket_volume: int = 10_000
    min_gap_pct: float = 10.0
    #: Security types admitted to the field (common stock only by default).
    allowed_security_types: tuple[str, ...] = ("CS",)


def _coerce_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _assert_pit(daily_bars: Sequence[Mapping[str, Any]], asof: date, feature: str) -> None:
    for row in daily_bars:
        row_date = _coerce_date(row["date"])
        if row_date >= asof:
            raise PITViolationError(
                f"{feature}: daily bar dated {row_date.isoformat()} is not strictly "
                f"before asof {asof.isoformat()} — PIT rule is date < asof"
            )


def prior_close(daily_bars: Sequence[Mapping[str, Any]], asof: date) -> float | None:
    """Last close strictly before ``asof``; None if no history. PIT-strict."""
    _assert_pit(daily_bars, asof, "prior_close")
    if not daily_bars:
        return None
    latest = max(daily_bars, key=lambda r: _coerce_date(r["date"]))
    close = latest.get("close")
    return None if close is None else float(close)


def adv(
    daily_bars: Sequence[Mapping[str, Any]], asof: date, lookback: int = ADV_LOOKBACK
) -> float | None:
    """Average daily volume over the last ``lookback`` PIT days; None if empty."""
    _assert_pit(daily_bars, asof, "adv")
    if not daily_bars:
        return None
    ordered = sorted(daily_bars, key=lambda r: _coerce_date(r["date"]))
    window = ordered[-lookback:]
    vols = [float(r["volume"]) for r in window if r.get("volume") is not None]
    if not vols:
        return None
    return sum(vols) / len(vols)


def premarket_slice(minute_bars: pd.DataFrame | None, asof: date) -> pd.DataFrame:
    """Bars printed on ``asof`` strictly before the 09:30 ET open, ET-sorted."""
    cols = ["t", "o", "h", "l", "c", "v", "_et"]
    if minute_bars is None or len(minute_bars) == 0:
        return pd.DataFrame(columns=cols)
    d = minute_bars.copy()
    d["_et"] = pd.to_datetime(d["t"], utc=True).dt.tz_convert(_ET)
    mask = (d["_et"].dt.date == asof) & (d["_et"].dt.time < RTH_OPEN)
    return d[mask].sort_values("_et").reset_index(drop=True)


def reconstruct_event(
    symbol: str,
    asof: date,
    minute_bars: pd.DataFrame | None,
    daily_bars: Sequence[Mapping[str, Any]],
    filters: EventFilters,
    *,
    security_type: str = "CS",
) -> dict[str, Any]:
    """Reconstruct one candidate's event row from raw premarket prints.

    Returns a dict with the computed features, ``passes`` (all filters), and a
    reason-code list for every failed filter (feeds the funnel instrumentation).
    Raises :class:`PITViolationError` if ``daily_bars`` contains rows >= asof.
    """
    reasons: list[str] = []
    pm = premarket_slice(minute_bars, asof)
    pc = prior_close(daily_bars, asof)
    average_volume = adv(daily_bars, asof) if daily_bars else None

    pm_last: float | None = None
    pm_volume = 0.0
    if pm.empty:
        reasons.append(REASON_NO_PREMARKET_BARS)
    else:
        pm_last = float(pm.iloc[-1]["c"])
        pm_volume = float(pm["v"].sum())

    gap_pct: float | None = None
    if pc is None:
        reasons.append(REASON_NO_PRIOR_CLOSE)
    elif pm_last is not None:
        gap_pct = (pm_last / pc - 1.0) * 100.0

    if security_type not in filters.allowed_security_types:
        reasons.append(REASON_SECURITY_TYPE_EXCLUDED)
    if pm_last is not None and pm_last < filters.min_price:
        reasons.append(REASON_PRICE_BELOW_MIN)
    if not pm.empty and pm_volume < filters.min_premarket_volume:
        reasons.append(REASON_PM_VOLUME_BELOW_MIN)
    if gap_pct is not None and gap_pct < filters.min_gap_pct:
        reasons.append(REASON_GAP_BELOW_MIN)

    return {
        "symbol": symbol,
        "asof": asof.isoformat(),
        "gap_pct": None if gap_pct is None else round(gap_pct, 4),
        "prior_close": pc,
        "premarket_last": pm_last,
        "premarket_volume": pm_volume,
        "premarket_bar_count": int(len(pm)),
        "adv": average_volume,
        "security_type": security_type,
        "passes": not reasons,
        "exclusion_reasons": reasons,
    }


def reconstruct_field(
    asof: date,
    minute_bars_by_symbol: Mapping[str, pd.DataFrame | None],
    daily_bars_by_symbol: Mapping[str, Sequence[Mapping[str, Any]]],
    filters: EventFilters,
    *,
    security_types: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Reconstruct the full event field for ``asof``, sorted by gap_pct desc.

    Every symbol appears in the output — passing or reason-coded — so the
    funnel record can attribute every contraction.
    """
    rows: list[dict[str, Any]] = []
    for symbol in sorted(minute_bars_by_symbol):
        rows.append(
            reconstruct_event(
                symbol,
                asof,
                minute_bars_by_symbol[symbol],
                daily_bars_by_symbol.get(symbol, ()),
                filters,
                security_type=(security_types or {}).get(symbol, "CS"),
            )
        )
    rows.sort(key=lambda r: (r["gap_pct"] is None, -(r["gap_pct"] or 0.0)))
    return rows
