"""Real-data backtest for the RangeTrader template (P8 §7) using Alpaca 5Min bars.

Sibling to ``backtest_range_trader_synthetic.py``. Same harness, real bars:
fetches IEX 5Min bars for one symbol/window, filters to regular trading
hours, derives the fade-the-range levels from the window's own price
distribution (so they are principled rather than hand-picked), then runs
``RangeTrader`` through the production ``Backtester`` and prints metrics,
trades, and the per-bar signals log.

This needs network access to ``data.alpaca.markets`` (Norton SSL inspection
blocks it on some machines — run where it is reachable) and Alpaca creds in
``.env``.

    cd apps/backend
    .venv/Scripts/python.exe scripts/backtest_range_trader_alpaca.py AAPL 2026-05-22 2026-06-05

Levels are derived as: entry=25th pctile, exit=75th pctile, stop=10th pctile
of RTH closes over the window. Override any of them with --entry/--exit/--stop.
IEX free tier is a thin feed; treat results as indicative, not precise.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime, time
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
from app.market_data.bar_cache import _alpaca_fetch_bars  # noqa: E402
from app.strategies import Backtester  # noqa: E402
from app.strategies.backtest_context import BacktestContext  # noqa: E402
from app.strategies.backtest_models import BacktestConfig  # noqa: E402
from strategies_user.templates.range_trader import RangeTrader  # noqa: E402

ET = ZoneInfo("America/New_York")
RTH_OPEN = time(9, 30)
RTH_CLOSE = time(16, 0)


def _capture_context() -> dict:
    """Wrap the BacktestContext the harness builds so we can read ctx.signals
    (the strategy's per-bar reasons) after the run."""
    captured: dict = {}

    class _CapturingContext(BacktestContext):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            captured["ctx"] = self

    backtester_mod.BacktestContext = _CapturingContext
    return captured


def _fetch_rth_bars(symbol: str, start: datetime, end: datetime) -> pd.DataFrame:
    """Fetch 5Min bars and keep only regular-trading-hours rows, sorted by time.

    Filtering to RTH keeps the session semantics clean: the strategy's
    time-of-day gates assume an intraday session, and dropping pre/post-market
    bars means the end-of-day time-exit fills on the same session's last bar
    rather than gapping into the next morning."""
    df = _alpaca_fetch_bars(symbol, "5Min", start, end)
    if df.empty:
        return df
    df["t"] = pd.to_datetime(df["t"], utc=True)
    et = df["t"].dt.tz_convert(ET)
    mask = (et.dt.time >= RTH_OPEN) & (et.dt.time < RTH_CLOSE)
    return df[mask].sort_values("t").reset_index(drop=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol", nargs="?", default="AAPL")
    ap.add_argument("start", nargs="?", default="2026-05-22")
    ap.add_argument("end", nargs="?", default="2026-06-05")
    ap.add_argument("--entry", type=float, default=None)
    ap.add_argument("--exit", type=float, default=None, dest="exit_")
    ap.add_argument("--stop", type=float, default=None)
    ap.add_argument("--slippage-bps", type=float, default=5.0)
    args = ap.parse_args()

    symbol = args.symbol.upper()
    y0, m0, d0 = map(int, args.start.split("-"))
    y1, m1, d1 = map(int, args.end.split("-"))
    start = datetime(y0, m0, d0, 0, 0, tzinfo=UTC)
    end = datetime(y1, m1, d1, 23, 59, 59, tzinfo=UTC)

    print(f"Fetching {symbol} 5Min RTH bars {args.start} .. {args.end} ...")
    bars = _fetch_rth_bars(symbol, start, end)
    if bars.empty:
        print("No bars returned — check creds / network / date range.", file=sys.stderr)
        return 1
    et = bars["t"].dt.tz_convert(ET)
    sessions = sorted({d.isoformat() for d in et.dt.date.unique()})
    print(f"  {len(bars)} RTH bars across {len(sessions)} sessions: "
          f"{sessions[0]} .. {sessions[-1]}")

    # Derive levels from the window's own close distribution (overridable).
    closes = bars["c"]
    entry = args.entry if args.entry is not None else round(float(closes.quantile(0.25)), 2)
    exit_ = args.exit_ if args.exit_ is not None else round(float(closes.quantile(0.75)), 2)
    stop = args.stop if args.stop is not None else round(float(closes.quantile(0.10)), 2)
    print(f"  close range [{closes.min():.2f} .. {closes.max():.2f}]  "
          f"levels: stop={stop} entry={entry} exit={exit_}")
    if not (stop < entry < exit_):
        print("  WARNING: levels not ordered stop<entry<exit — strategy will be "
              "inert for entries.")

    captured = _capture_context()
    bar_cache = MagicMock()
    bar_cache.get_bars = AsyncMock(return_value=bars)
    harness = Backtester(bar_cache=bar_cache, indicator_computer=IndicatorComputer())

    config = BacktestConfig(
        start=start,
        end=end,
        initial_equity=Decimal("100000"),
        slippage_bps=args.slippage_bps,
        commission_per_share=0.0,
        timeframe="5Min",
        params={
            "entry_price": entry,
            "exit_price": exit_,
            "stop_price": stop,
            "hard_exit_before_close_minutes": 10,  # cutoff 15:50 -> EOD exit
        },                                         # fills on the 15:55 bar
        seed=42,
    )

    import asyncio
    metrics, trades, equity = asyncio.run(
        harness.run(RangeTrader, [symbol], config)
    )

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

    def _et(iso: str | None) -> str:
        if not iso:
            return "—"
        return datetime.fromisoformat(iso).astimezone(ET).strftime("%Y-%m-%d %H:%M")

    print(f"\n=== TRADES === ({len(trades)})  [times in ET, = fill time]")
    for i, t in enumerate(trades, 1):
        print(f"  #{i} {t.side:>5} qty={t.qty:g} "
              f"entry={t.entry_price:.2f}@{_et(t.entry_ts)} "
              f"exit={(t.exit_price or 0):.2f}@{_et(t.exit_ts)} "
              f"pnl={t.pnl:+.2f} ({t.exit_reason})")

    ctx = captured.get("ctx")
    signals = getattr(ctx, "signals", []) if ctx is not None else []
    print(f"\n=== SIGNALS LOG === ({len(signals)} entries)")
    print(f"  {'date':<10} {'time(ET)':<8} {'type':<5} {'reason':<28} detail")
    for s in signals:
        ts = s.get("ts")
        when = datetime.fromisoformat(ts).astimezone(ET) if ts else None
        payload = s.get("payload") or {}
        reason = payload.get("reason", "")
        detail_bits = []
        if "price" in payload:
            detail_bits.append(f"px={payload['price']:g}")
        if payload.get("rejected"):
            detail_bits.append(f"REJECTED={payload['rejected']}")
        if payload.get("skipped"):
            detail_bits.append("skipped")
        print(f"  {when.strftime('%Y-%m-%d') if when else '?':<10} "
              f"{when.strftime('%H:%M') if when else '?':<8} "
              f"{s.get('type',''):<5} {reason:<28} {' '.join(detail_bits)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
