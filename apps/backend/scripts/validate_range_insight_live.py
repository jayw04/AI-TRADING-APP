"""Validate Range Insight (P8 §5) against REAL Alpaca daily bars.

The §5/§6/§7 math (ATR, typical moves, support/resistance, the 80% bands,
classification) was unit-tested only with synthetic bars. This script fetches
real daily bars via the production BarCache + load_credentials() path and runs
``range_insight_from_bars``, printing the result and a battery of sanity checks
per symbol. It places NO orders and needs no browser.

RUN IT INSIDE THE BACKEND CONTAINER (where the .env paper keys are configured),
on a non-Norton stack:

    docker compose exec backend python scripts/validate_range_insight_live.py AAPL MSFT NVDA SPY

Exit code is non-zero if any HARD check fails for any symbol (so it can gate a
sign-off). WARN lines never fail the run — they flag "unusual but legal" data
(e.g. a symbol that just broke out of its range).
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from datetime import UTC, datetime, timedelta

from app.market_data.bar_cache import BarCache
from app.services.range_insight import (
    MIN_BARS,
    WINDOW,
    range_insight_from_bars,
)

DEFAULT_SYMBOLS = ["AAPL", "MSFT", "NVDA", "SPY"]


def _checks(ri) -> tuple[list[str], list[str], list[str]]:
    """Return (passed, failed, warned) check descriptions."""
    passed: list[str] = []
    failed: list[str] = []
    warned: list[str] = []

    def hard(name: str, ok: bool) -> None:
        (passed if ok else failed).append(name)

    def soft(name: str, ok: bool) -> None:
        if not ok:
            warned.append(name)
        else:
            passed.append(name)

    hard(f"status == ok (bars_used={ri.bars_used} >= MIN_BARS {MIN_BARS})", ri.status == "ok")
    if ri.status != "ok":
        return passed, failed, warned

    hard("atr20 > 0", (ri.atr20 or 0) > 0)
    hard("atr20_pct in (0, 0.5)", ri.atr20_pct is not None and 0 < ri.atr20_pct < 0.5)
    hard("support < resistance", (ri.support or 0) < (ri.resistance or 0))
    hard("high_band ordered (low <= high)", ri.high_band is not None and ri.high_band.low <= ri.high_band.high)
    hard("low_band ordered (low <= high)", ri.low_band is not None and ri.low_band.low <= ri.low_band.high)
    hard("low_band below high_band (low.high <= high.low)", ri.low_band.high <= ri.high_band.high)
    hard("typical_move_up.mean >= 0", ri.typical_move_up is not None and ri.typical_move_up.mean >= 0)
    hard("typical_move_down.mean >= 0", ri.typical_move_down is not None and ri.typical_move_down.mean >= 0)
    hard("classification in set", ri.classification in {"range_bound", "trending", "mixed"})
    hard("efficiency_ratio in [0, 1]", ri.efficiency_ratio is not None and 0 <= ri.efficiency_ratio <= 1.0001)
    hard("anchor set + last_close set", ri.anchor is not None and ri.last_close is not None)
    hard("disclaimer present", bool(ri.disclaimer))

    # Soft (unusual but legal):
    soft(
        "last_close within [support, resistance] (else broke out)",
        ri.support is not None and ri.resistance is not None and ri.support <= ri.last_close <= ri.resistance,
    )
    soft("bars_used == WINDOW (full history)", ri.bars_used == WINDOW)
    return passed, failed, warned


async def _validate(symbols: list[str]) -> int:
    cache_root = tempfile.mkdtemp(prefix="ri_validate_")
    bc = BarCache(adapter=None, root=cache_root, max_gb=1.0)
    now = datetime.now(UTC)
    start = now - timedelta(days=200)

    any_failed = False
    for sym in symbols:
        print(f"\n=== {sym} ===")
        try:
            bars = await bc.get_bars(sym, "1Day", start, now)
        except Exception as exc:  # noqa: BLE001 — report any fetch failure plainly
            print(f"  FETCH FAILED: {type(exc).__name__}: {exc}")
            any_failed = True
            continue

        ri = range_insight_from_bars(sym, bars, now)
        print(
            f"  bars fetched={0 if bars is None else len(bars)}  status={ri.status}  "
            f"bars_used={ri.bars_used}  low_confidence={ri.low_confidence}"
        )
        if (
            ri.status == "ok"
            and ri.atr20 is not None
            and ri.atr20_pct is not None
            and ri.support is not None
            and ri.resistance is not None
            and ri.high_band is not None
            and ri.low_band is not None
            and ri.efficiency_ratio is not None
        ):
            print(
                f"  ATR20=${ri.atr20:.2f} ({ri.atr20_pct * 100:.1f}%)  "
                f"S/R=${ri.support:.2f}/${ri.resistance:.2f}  "
                f"high_band=${ri.high_band.low:.2f}-${ri.high_band.high:.2f}  "
                f"low_band=${ri.low_band.low:.2f}-${ri.low_band.high:.2f}  "
                f"class={ri.classification} (ER={ri.efficiency_ratio:.2f})  "
                f"intraday_range={ri.intraday_range}"
            )

        passed, failed, warned = _checks(ri)
        for c in passed:
            print(f"    PASS  {c}")
        for c in warned:
            print(f"    WARN  {c}")
        for c in failed:
            print(f"    FAIL  {c}")
        if failed:
            any_failed = True

    print("\n" + ("RESULT: FAIL (see above)" if any_failed else "RESULT: PASS — all hard checks green"))
    return 1 if any_failed else 0


def main() -> None:
    symbols = [s.upper() for s in sys.argv[1:]] or DEFAULT_SYMBOLS
    sys.exit(asyncio.run(_validate(symbols)))


if __name__ == "__main__":
    main()
