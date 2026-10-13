"""Compare two providers' normalized daily data and explain every difference.

Each difference gets one class. Explained classes are known, documented provider conventions;
anything else is unexplained and must be investigated before the data is used.

Explained:

* ``SUSPENDED_ROW_ONLY_IN_ONE``: one provider lists a suspended day (status 0, no volume) and the
  other omits it (Tushare ``daily`` omits suspended days; Baostock lists them).
* ``VOLUME_LOT_ROUNDING``: volumes differ by less than one lot (Tushare reports lots).
* ``AMOUNT_UNIT_ROUNDING``: amounts differ within the rounding of a thousand-CNY figure.
* ``FACTOR_SCALE_ONLY``: the two factor series have different absolute scales but the same
  corporate-action dates and ratios, so adjusted returns agree.

Unexplained: ``ROW_ONLY_IN_ONE`` (a traded day missing from one side), ``PRICE_MISMATCH``,
``VOLUME_MISMATCH``, ``AMOUNT_MISMATCH``, ``FACTOR_EVENT_MISMATCH``.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from typing import Any

from app.markets.cn_ashare.adjust import FactorGap, factor_on

EXPLAINED = frozenset(
    {
        "SUSPENDED_ROW_ONLY_IN_ONE",
        "VOLUME_LOT_ROUNDING",
        "AMOUNT_UNIT_ROUNDING",
        "FACTOR_SCALE_ONLY",
    }
)
_PRICE_FIELDS = ("open", "high", "low", "close", "pre_close")
_PRICE_TOL = 0.005  # half a fen
_RATIO_TOL = 1e-5


def _index(rows: list[dict[str, Any]]) -> dict[tuple[str, date], dict[str, Any]]:
    return {(r["symbol"], r["trade_date"]): r for r in rows}


def _events(factor_rows: list[dict[str, Any]], days: list[date]) -> dict[date, float]:
    f = factor_on(factor_rows, days)
    out = {}
    for prev, cur in zip(days, days[1:], strict=False):
        ratio = f[cur] / f[prev]
        if abs(ratio - 1.0) > _RATIO_TOL:
            out[cur] = ratio
    return out


def compare(
    a_name: str,
    a_daily: list[dict[str, Any]],
    a_factors: list[dict[str, Any]],
    b_name: str,
    b_daily: list[dict[str, Any]],
    b_factors: list[dict[str, Any]],
    *,
    max_examples: int = 5,
) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    examples: dict[str, list[dict[str, Any]]] = defaultdict(list)

    def note(cls: str, **detail: Any) -> None:
        counts[cls] += 1
        if len(examples[cls]) < max_examples:
            examples[cls].append(
                {k: (v.isoformat() if isinstance(v, date) else v) for k, v in detail.items()}
            )

    a, b = _index(a_daily), _index(b_daily)
    compared = 0
    for key in sorted(set(a) | set(b)):
        sym, day = key
        ra, rb = a.get(key), b.get(key)
        if ra is None or rb is None:
            present = ra or rb
            assert present is not None
            side = a_name if ra is not None else b_name
            if present["trade_status"] == 0 or not present["volume_shares"]:
                note("SUSPENDED_ROW_ONLY_IN_ONE", symbol=sym, day=day, present_in=side)
            else:
                note("ROW_ONLY_IN_ONE", symbol=sym, day=day, present_in=side)
            continue
        if ra["trade_status"] == 0 and rb["trade_status"] == 0:
            continue
        compared += 1
        for fld in _PRICE_FIELDS:
            va, vb = ra[fld], rb[fld]
            if va is None or vb is None or abs(va - vb) > _PRICE_TOL:
                note("PRICE_MISMATCH", symbol=sym, day=day, field=fld, **{a_name: va, b_name: vb})
        dv = abs((ra["volume_shares"] or 0) - (rb["volume_shares"] or 0))
        if dv >= 100:
            note(
                "VOLUME_MISMATCH",
                symbol=sym,
                day=day,
                **{a_name: ra["volume_shares"], b_name: rb["volume_shares"]},
            )
        elif dv > 0:
            note("VOLUME_LOT_ROUNDING", symbol=sym, day=day, diff_shares=dv)
        am_a, am_b = ra["amount_cny"] or 0.0, rb["amount_cny"] or 0.0
        da = abs(am_a - am_b)
        if da > max(1.0, 1e-6 * max(am_a, am_b)):
            note("AMOUNT_MISMATCH", symbol=sym, day=day, **{a_name: am_a, b_name: am_b})
        elif da > 0.005:
            note("AMOUNT_UNIT_ROUNDING", symbol=sym, day=day, diff_cny=round(da, 4))

    # Factors: compare corporate-action dates and ratios on the days both sides traded.
    fa: dict[str, list[dict[str, Any]]] = defaultdict(list)
    fb: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in a_factors:
        fa[r["symbol"]].append(r)
    for r in b_factors:
        fb[r["symbol"]].append(r)
    traded: dict[str, list[date]] = defaultdict(list)
    for (sym, day), ra in a.items():
        rb = b.get((sym, day))
        if rb is not None and ra["trade_status"] == 1 and rb["trade_status"] == 1:
            traded[sym].append(day)
    factor_symbols = 0
    for sym in sorted(set(fa) | set(fb)):
        days = sorted(traded.get(sym, []))
        if len(days) < 2:
            continue
        try:
            ea, eb = _events(fa[sym], days), _events(fb[sym], days)
        except FactorGap as exc:
            note("FACTOR_EVENT_MISMATCH", symbol=sym, detail=str(exc))
            continue
        factor_symbols += 1
        same = set(ea) == set(eb) and all(abs(ea[d] / eb[d] - 1.0) <= _RATIO_TOL for d in ea)
        if not same:
            note(
                "FACTOR_EVENT_MISMATCH",
                symbol=sym,
                **{a_name: sorted(map(str, ea)), b_name: sorted(map(str, eb))},
            )
            continue
        first = days[0]
        sa = factor_on(fa[sym], [first])[first]
        sb = factor_on(fb[sym], [first])[first]
        if abs(sa / sb - 1.0) > _RATIO_TOL:
            note("FACTOR_SCALE_ONLY", symbol=sym, scale_ratio=round(sa / sb, 6), events=len(ea))

    unexplained = {k: v for k, v in counts.items() if k not in EXPLAINED}
    return {
        "providers": [a_name, b_name],
        "rows": {a_name: len(a_daily), b_name: len(b_daily)},
        "days_compared": compared,
        "factor_symbols_compared": factor_symbols,
        "counts": dict(sorted(counts.items())),
        "explained": sorted(k for k in counts if k in EXPLAINED),
        "unexplained": dict(sorted(unexplained.items())),
        "all_explained": not unexplained,
        "examples": {k: v for k, v in sorted(examples.items())},
    }
