"""Walk-forward, multi-symbol sweep for the RangeTrader template (P8 §7).

Breadth check on top of ``backtest_range_trader_alpaca.py``. The single-window
runs showed an edge that was razor-thin and carried by one trade — six trades
is not a signal. This pools trades across many symbol x window runs so the
verdict rests on dozens of trades, and it sets levels OUT OF SAMPLE to avoid
fitting and scoring on the same bars:

  For each symbol, fetch 5Min RTH bars over the whole period, split the
  sessions into consecutive blocks of ``--block-size`` sessions, then
  walk forward: derive fade-the-range levels from block i-1 (TRAIN) and
  backtest them on block i (TEST). Pool every TEST-block trade.

Levels are percentiles of the TRAIN block's RTH closes — default
stop=p10 / entry=p30 / exit=p60, which encodes the single-window finding
(a *reachable* target beats an extreme one, and a controlled stop gives
positive reward:risk). Override with --stop-pct/--entry-pct/--exit-pct.

Needs network to data.alpaca.markets (Norton SSL off) + creds in .env.

    cd apps/backend
    .venv/Scripts/python.exe scripts/backtest_range_trader_sweep.py \
        --symbols AAPL MSFT NVDA TSLA --start 2026-04-13 --end 2026-06-11 --block-size 5
"""

from __future__ import annotations

import argparse
import asyncio
import math
import sys
from datetime import UTC, datetime, time
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pandas as pd

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.indicators import IndicatorComputer  # noqa: E402
from app.market_data.bar_cache import _alpaca_fetch_bars  # noqa: E402
from app.strategies import Backtester  # noqa: E402
from app.strategies.backtest_models import BacktestConfig, BacktestTrade  # noqa: E402
from strategies_user.templates.range_trader import RangeTrader  # noqa: E402

ET = ZoneInfo("America/New_York")
RTH_OPEN = time(9, 30)
RTH_CLOSE = time(16, 0)


_CACHE_DIR = BACKEND_ROOT / "scripts" / ".sweep_cache"


def _fetch_rth(symbol: str, start: datetime, end: datetime, *, retries: int = 10) -> pd.DataFrame:
    # Norton SSL inspection re-engages intermittently even when toggled off, so
    # a fetch can SSLError one moment and succeed the next. Cache each symbol's
    # raw bars to parquet on first success so re-runs never re-hit the network,
    # and retry with capped backoff on the cold fetch.
    import time as _time

    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tag = f"{symbol}_{start:%Y%m%d}_{end:%Y%m%d}_5Min.parquet"
    cache_path = _CACHE_DIR / tag
    if cache_path.exists():
        df = pd.read_parquet(cache_path)
        print(f"    {symbol}: loaded {len(df)} bars from cache")
    else:
        last_exc: Exception | None = None
        df = None
        for attempt in range(1, retries + 1):
            try:
                df = _alpaca_fetch_bars(symbol, "5Min", start, end)
                break
            except Exception as e:  # noqa: BLE001 — network flake, retry any error
                last_exc = e
                if attempt < retries:
                    print(f"    {symbol}: fetch attempt {attempt} failed "
                          f"({type(e).__name__}), retrying...")
                    _time.sleep(min(2.0 * attempt, 6.0))
        if df is None:
            raise last_exc  # type: ignore[misc]
        df.to_parquet(cache_path, index=False)
        print(f"    {symbol}: fetched + cached {len(df)} bars")
    if df.empty:
        return df
    df["t"] = pd.to_datetime(df["t"], utc=True)
    et = df["t"].dt.tz_convert(ET)
    mask = (et.dt.time >= RTH_OPEN) & (et.dt.time < RTH_CLOSE)
    out = df[mask].copy()
    out["session"] = et[mask].dt.date
    return out.sort_values("t").reset_index(drop=True)


def _blocks(df: pd.DataFrame, block_size: int) -> list[pd.DataFrame]:
    """Split into consecutive blocks of ``block_size`` sessions each."""
    sessions = sorted(df["session"].unique())
    chunks: list[pd.DataFrame] = []
    for i in range(0, len(sessions), block_size):
        days = set(sessions[i : i + block_size])
        block = df[df["session"].isin(days)].reset_index(drop=True)
        if not block.empty:
            chunks.append(block)
    return chunks


async def _run_block(
    harness: Backtester, symbol: str, block: pd.DataFrame, levels: tuple[float, float, float]
) -> tuple[object, list[BacktestTrade]]:
    stop, entry, exit_ = levels
    bar_cache = MagicMock()
    bar_cache.get_bars = AsyncMock(return_value=block[["t", "o", "h", "l", "c", "v"]])
    harness._bar_cache = bar_cache  # per-block data source (single symbol/run)
    start = block["t"].iloc[0].to_pydatetime()
    end = block["t"].iloc[-1].to_pydatetime()
    config = BacktestConfig(
        start=start,
        end=end,
        initial_equity=Decimal("100000"),
        slippage_bps=5.0,
        timeframe="5Min",
        params={
            "entry_price": entry,
            "exit_price": exit_,
            "stop_price": stop,
            "hard_exit_before_close_minutes": 10,
        },
        seed=42,
    )
    metrics, trades, _equity = await harness.run(RangeTrader, [symbol], config)
    return metrics, trades


def _train_daily_range_pct(train: pd.DataFrame) -> float:
    """Typical intraday range of the TRAIN block, as % of price: per session
    (high-low)/mean-close, averaged across the block's sessions. A proxy for
    'how wildly does this name swing right now' — the risk a fixed-level range
    fade can't survive. Measured on train only, so the gate is out-of-sample."""
    g = train.groupby("session")
    rng = (g["h"].max() - g["l"].min()) / g["c"].mean()
    return float(rng.mean() * 100.0)


def _pool_stats(trades: list[BacktestTrade]) -> dict:
    pnls = [t.pnl for t in trades if t.pnl is not None]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gross_w = sum(wins)
    gross_l = abs(sum(losses))
    return {
        "n": len(pnls),
        "win_rate": (len(wins) / len(pnls)) if pnls else 0.0,
        "pf": (gross_w / gross_l) if gross_l > 0 else (math.inf if gross_w > 0 else 0.0),
        "avg_w": (gross_w / len(wins)) if wins else 0.0,
        "avg_l": (-gross_l / len(losses)) if losses else 0.0,
        "expectancy": (sum(pnls) / len(pnls)) if pnls else 0.0,
        "net": sum(pnls),
    }


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="+", default=["AAPL", "MSFT", "NVDA", "TSLA"])
    ap.add_argument("--start", default="2026-04-13")
    ap.add_argument("--end", default="2026-06-11")
    ap.add_argument("--block-size", type=int, default=5, help="sessions per window")
    ap.add_argument("--stop-pct", type=float, default=10.0)
    ap.add_argument("--entry-pct", type=float, default=30.0)
    ap.add_argument("--exit-pct", type=float, default=60.0)
    ap.add_argument("--max-range-pct", type=float, default=3.5,
                    help="skip a window if the TRAIN block's avg intraday "
                         "range%% exceeds this (volatility gate; 0 disables)")
    args = ap.parse_args()

    y0, m0, d0 = map(int, args.start.split("-"))
    y1, m1, d1 = map(int, args.end.split("-"))
    start = datetime(y0, m0, d0, 0, 0, tzinfo=UTC)
    end = datetime(y1, m1, d1, 23, 59, 59, tzinfo=UTC)

    gate = args.max_range_pct
    gate_desc = f"skip train range% > {gate:g}" if gate > 0 else "disabled"
    print(f"Walk-forward sweep | block={args.block_size} sessions | "
          f"levels = train p{args.stop_pct:g}/p{args.entry_pct:g}/p{args.exit_pct:g} "
          f"(stop/entry/exit)")
    print(f"Window {args.start} .. {args.end} | vol gate: {gate_desc} | "
          f"symbols: {', '.join(args.symbols)}\n")

    harness = Backtester(bar_cache=MagicMock(), indicator_computer=IndicatorComputer())

    all_trades: list[BacktestTrade] = []
    window_returns: list[float] = []
    per_symbol: dict[str, list[BacktestTrade]] = {}
    n_windows = 0
    n_skipped = 0

    print(f"  {'symbol':<6} {'traded':>6} {'skip':>4} {'trades':>6} {'win%':>5} "
          f"{'PF':>5} {'expect':>7} {'net$':>9}")
    for symbol in args.symbols:
        symbol = symbol.upper()
        try:
            df = _fetch_rth(symbol, start, end)
        except Exception as e:  # noqa: BLE001
            print(f"  {symbol:<6}  fetch failed: {type(e).__name__}: {str(e)[:60]}")
            continue
        if df.empty:
            print(f"  {symbol:<6}  no bars")
            continue
        blocks = _blocks(df, args.block_size)
        sym_trades: list[BacktestTrade] = []
        sym_traded = sym_skipped = 0
        for i in range(1, len(blocks)):  # walk-forward: need a prior (train) block
            train, test = blocks[i - 1], blocks[i]
            # Volatility gate (out-of-sample, measured on train).
            if gate > 0 and _train_daily_range_pct(train) > gate:
                sym_skipped += 1
                n_skipped += 1
                continue
            tc = train["c"]
            levels = (
                round(float(tc.quantile(args.stop_pct / 100)), 2),
                round(float(tc.quantile(args.entry_pct / 100)), 2),
                round(float(tc.quantile(args.exit_pct / 100)), 2),
            )
            if not (levels[0] < levels[1] < levels[2]):
                continue
            metrics, trades = await _run_block(harness, symbol, test, levels)
            sym_trades.extend(trades)
            window_returns.append(metrics.total_return)
            n_windows += 1
            sym_traded += 1
        per_symbol[symbol] = sym_trades
        all_trades.extend(sym_trades)
        s = _pool_stats(sym_trades)
        pf = "inf" if s["pf"] == math.inf else f"{s['pf']:.2f}"
        print(f"  {symbol:<6} {sym_traded:>6} {sym_skipped:>4} {s['n']:>6} "
              f"{s['win_rate']:>4.0%} {pf:>5} {s['expectancy']:>+7.2f} {s['net']:>+9.2f}")

    print("\n=== POOLED (all symbols, all walk-forward windows) ===")
    p = _pool_stats(all_trades)
    pf = "inf" if p["pf"] == math.inf else f"{p['pf']:.2f}"
    avg_win_ret = (sum(window_returns) / len(window_returns)) if window_returns else 0.0
    print(f"  windows tested      : {n_windows}  (skipped by vol gate: {n_skipped})")
    print(f"  total trades        : {p['n']}")
    print(f"  win rate            : {p['win_rate']:.0%}")
    print(f"  profit factor       : {pf}")
    print(f"  avg win / avg loss  : {p['avg_w']:+.2f} / {p['avg_l']:+.2f}")
    print(f"  expectancy / trade  : {p['expectancy']:+.2f}")
    print(f"  net P&L (pooled)    : {p['net']:+.2f}")
    print(f"  mean window return  : {avg_win_ret:+.4%}  (equal-weight per window)")
    verdict = ("positive expectancy" if p["expectancy"] > 0 else
               "negative/flat expectancy")
    print(f"  -> {verdict} across {p['n']} out-of-sample trades")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
