"""Synthetic-fixture backtest for the RangeTrader template (P8 §7).

This is a PIPELINE validation, not an edge signal. It drives the *real*
``Backtester`` / ``BacktestContext`` against ``RangeTrader`` using a
hand-built deterministic 5Min bar series — no Alpaca, no BarCache disk
fetch (Norton SSL blocks ``data.alpaca.markets`` locally), no DB writes.

The synthetic series exercises every branch of the strategy across three
ET sessions on a fixed range (support=100, resistance=110, stop=97):

  Day 1 — clean round trip:  dip to support -> entry, rally to resistance -> exit (win)
  Day 2 — stop-out + halt:   entry, break the stop -> exit (loss), then dip
                             again with NO re-entry (fix #1)
  Day 3 — time exit:         entry, sideways all day, force-exit near close

Run from apps/backend with the backend venv:
    .venv/Scripts/python.exe scripts/backtest_range_trader_synthetic.py
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pandas as pd

# Make `app` and `strategies_user` importable when run as a plain script.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import app.strategies.backtester as backtester_mod  # noqa: E402
from app.indicators import IndicatorComputer  # noqa: E402
from app.strategies import Backtester  # noqa: E402
from app.strategies.backtest_context import BacktestContext  # noqa: E402
from app.strategies.backtest_models import BacktestConfig  # noqa: E402
from strategies_user.templates.range_trader import RangeTrader  # noqa: E402

ET = ZoneInfo("America/New_York")


def _capture_context() -> dict:
    """Wrap the BacktestContext the harness instantiates so we can read its
    in-memory ``signals`` log after the run. ``Backtester.run`` builds the
    context internally and only returns (metrics, trades, equity); the
    strategy's per-bar reasons (range_entry / range_exit / stop_loss /
    time_exit) live on ``ctx.signals`` and would otherwise be unreachable."""
    captured: dict = {}

    class _CapturingContext(BacktestContext):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            captured["ctx"] = self

    backtester_mod.BacktestContext = _CapturingContext
    return captured

SYMBOL = "SYNTH"

# ---- range under test ----
ENTRY = 100.0  # buy when price <= this (support)
EXIT = 110.0   # sell when price >= this (resistance)
STOP = 97.0    # hard stop (below support)

# 5Min bars, 09:30..15:55 ET inclusive = 78 bars/session. June -> EDT (UTC-4),
# so 09:30 ET == 13:30 UTC. Bar i covers minute (30 + 5*i) from 13:30 UTC.
BARS_PER_DAY = 78
SESSION_OPEN_UTC_MIN = 13 * 60 + 30  # 13:30 UTC


def _session_closes(day_index: int) -> list[float]:
    """Return 78 close prices describing one ET session's price path.

    All three sessions share the same range; only the path differs so each
    triggers a different strategy branch. Indices: bar i -> 09:30 + 5*i ET.
    """
    if day_index == 0:
        # Win: flat above support, dip to 99 at bar 3 (entry), hold ~105,
        # pop to 111 at bar 20 (exit), flat above support afterward.
        c = [105.0] * BARS_PER_DAY
        c[3] = 99.0                       # entry trigger (<= 100)
        for i in range(4, 20):
            c[i] = 105.0                  # held long, no trigger
        for i in range(20, BARS_PER_DAY):
            c[i] = 111.0                  # >= 110 -> exit, then flat (no re-entry)
        return c
    if day_index == 1:
        # Loss + halt: dip to 100 at bar 3 (entry), break stop to 96 at bar
        # 10 (stop-out), then recover to 99 (<= entry) but NO re-entry.
        c = [101.0] * BARS_PER_DAY
        c[3] = 100.0                      # entry trigger
        for i in range(4, 10):
            c[i] = 99.0                   # held long, above stop
        c[10] = 96.0                      # <= 97 -> stop fires
        for i in range(11, BARS_PER_DAY):
            c[i] = 99.0                   # dips back to support; halted -> no entry
        return c
    # Day 3 — time exit: entry at bar 3, sideways 101 all session, force-exit
    # near the close (hard_exit_before_close_minutes=10 -> cutoff 15:50 = bar 76).
    c = [100.0] * BARS_PER_DAY
    c[3] = 100.0                          # entry trigger
    for i in range(4, BARS_PER_DAY):
        c[i] = 101.0                      # sideways, held to time exit
    return c


def _build_bars() -> pd.DataFrame:
    """Three contiguous ET sessions of synthetic 5Min OHLCV.

    Open of bar i == close of bar i-1 (no gaps), so an order decided on bar N
    fills at bar N+1's open == the close that triggered it (± slippage). That
    makes fills land at the trigger price, which keeps the PnL legible.
    """
    rows: list[dict] = []
    prev_close: float | None = None
    base_days = ["2026-06-08", "2026-06-09", "2026-06-10"]  # Mon/Tue/Wed
    for day_index, day in enumerate(base_days):
        closes = _session_closes(day_index)
        y, m, d = (int(x) for x in day.split("-"))
        for i, close in enumerate(closes):
            minute = SESSION_OPEN_UTC_MIN + 5 * i
            ts = pd.Timestamp(
                year=y, month=m, day=d,
                hour=minute // 60, minute=minute % 60, tz="UTC",
            )
            open_ = prev_close if prev_close is not None else close
            high = max(open_, close) + 0.05
            low = min(open_, close) - 0.05
            rows.append(
                {"t": ts, "o": open_, "h": high, "l": low, "c": close, "v": 1000}
            )
            prev_close = close
    return pd.DataFrame(rows)


async def main() -> None:
    bars = _build_bars()
    print(f"Built {len(bars)} synthetic 5Min bars "
          f"({bars['t'].iloc[0]} .. {bars['t'].iloc[-1]})")

    captured = _capture_context()
    bar_cache = MagicMock()
    bar_cache.get_bars = AsyncMock(return_value=bars)
    harness = Backtester(bar_cache=bar_cache, indicator_computer=IndicatorComputer())

    config = BacktestConfig(
        start=datetime(2026, 6, 8, tzinfo=UTC),
        end=datetime(2026, 6, 11, tzinfo=UTC),
        initial_equity=Decimal("100000"),
        slippage_bps=5.0,
        commission_per_share=0.0,
        timeframe="5Min",
        params={
            "entry_price": ENTRY,
            "exit_price": EXIT,
            "stop_price": STOP,
            "hard_exit_before_close_minutes": 10,  # cutoff 15:50 so the EOD
        },                                         # exit fills on the last bar
        seed=42,
    )

    metrics, trades, equity = await harness.run(RangeTrader, [SYMBOL], config)

    print("\n=== METRICS ===")
    print(f"  starting_equity : {metrics.starting_equity:,.2f}")
    print(f"  ending_equity   : {metrics.ending_equity:,.2f}")
    print(f"  total_return    : {metrics.total_return:+.4%}")
    print(f"  trade_count     : {metrics.trade_count}")
    print(f"  win_rate        : {metrics.win_rate:.0%}")
    print(f"  profit_factor   : {metrics.profit_factor:.2f}")
    print(f"  max_drawdown    : {metrics.max_drawdown:+.4%}")
    print(f"  sharpe_ratio    : {metrics.sharpe_ratio:.3f}")
    print(f"  avg_win/avg_loss: {metrics.avg_win:+.2f} / {metrics.avg_loss:+.2f}")

    print("\n=== TRADES ===")
    for i, t in enumerate(trades, 1):
        print(f"  #{i} {t.side:>5} qty={t.qty:g} "
              f"entry={t.entry_price:.4f}@{t.entry_ts[11:16]} "
              f"exit={t.exit_price:.4f}@{(t.exit_ts or '')[11:16]} "
              f"pnl={t.pnl:+.2f} ({t.exit_reason})")

    print(f"\n=== EQUITY CURVE === ({len(equity)} points)")
    if equity:
        print(f"  first: {equity[0].equity:,.2f}  last: {equity[-1].equity:,.2f}")

    # ---- per-bar signals log (the real strategy reasons) ----
    # The trade list tags every long close as the generic 'exit_signal'; the
    # strategy's actual decision reason is recorded here via ctx.log_signal.
    ctx = captured.get("ctx")
    signals = getattr(ctx, "signals", []) if ctx is not None else []
    print(f"\n=== SIGNALS LOG === ({len(signals)} entries)")
    print(f"  {'date':<10} {'time(ET)':<8} {'type':<5} {'reason':<28} detail")
    for s in signals:
        ts = s.get("ts")
        when = datetime.fromisoformat(ts).astimezone(ET) if ts else None
        date_s = when.strftime("%Y-%m-%d") if when else "?"
        time_s = when.strftime("%H:%M") if when else "?"
        payload = s.get("payload") or {}
        reason = payload.get("reason", "")
        detail_bits = []
        if "price" in payload:
            detail_bits.append(f"px={payload['price']:g}")
        if payload.get("rejected"):
            detail_bits.append(f"REJECTED={payload['rejected']}")
        if payload.get("skipped"):
            detail_bits.append("skipped")
        detail = " ".join(detail_bits)
        print(f"  {date_s:<10} {time_s:<8} {s.get('type',''):<5} {reason:<28} {detail}")

    # Quick narrative checks (not a test framework, just a sanity gate).
    assert metrics.trade_count == 3, f"expected 3 round trips, got {metrics.trade_count}"
    assert trades[0].pnl > 0, "day 1 should be a win"
    assert trades[1].pnl < 0, "day 2 should be a loss (stop-out)"
    print("\nOK: 3 round trips, day1 win / day2 stop-loss / day3 time-exit")


if __name__ == "__main__":
    asyncio.run(main())
