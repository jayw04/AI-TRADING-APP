#!/usr/bin/env python3
"""Phase 3 — Range trend-day filter, research-first via regime segmentation.

The disciplined order (owner's plan rev.2, Phase 3): BEFORE building any runtime gate, prove that
trend days are where the long-only fade bleeds. We classify every session's *market character* from
SPY daily OHLC, re-run the Phase-1 carry-forward modes (A baseline / C atr-zone / E bounce) in the
existing backtester, bucket each trade by its entry-day regime, and report:

  1. per-regime trade quality (PF / win% / expectancy / MAE / MFE), and
  2. the trend-gate counterfactual — metrics with trend-day trades EXCLUDED vs all-days.

If range/neutral days carry the edge and trend days carry the bleed, the Phase-3 gate is justified
(then it gets built as a default-off `trend_filter` param + ADR). If not, we do NOT build it.

Regime signal — SPY intraday DIRECTIONAL EFFICIENCY, not the SMA200 macro trend. A bull *market*
does not make every *session* a trend day; an opening-range fade cares about whether SPY travelled
decisively one way (trend, fade loses) or oscillated and closed mid-range (range, fade's home turf):

    DE = |close - open| / (high - low)        per SPY daily bar

Split at the window's empirical tertiles (data-driven, not tuned to any result):
    DE <= RANGE_MAX  -> "range"      (oscillation; closed near the middle)
    DE >= TREND_MIN  -> "trend"      (decisive one-way travel)
    otherwise        -> "neutral"

RUN IN A ONE-OFF CONTAINER (disarmed). `scripts/` is NOT baked into the image, so pipe on stdin:
  docker compose run --rm --no-deps --entrypoint sh backend -c \
    "cd /app && python - --strategy 1 --start 2023-07-01 --end 2026-06-30" \
    < scripts/research/range_regime_segment.py
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone

import pandas as pd

from app.brokers.registry import BrokerRegistry
from app.config import get_settings
from app.db.models.strategy import Strategy as StrategyRow
from app.db.session import get_sessionmaker
from app.indicators import IndicatorComputer
from app.market_data.bar_cache import BarCache
from app.services.backtest_worker import STRATEGIES_ROOT, StrategyLoader
from app.strategies.backtester import BacktestConfig, Backtester

# DE tertile boundaries — measured on SPY daily 2023-07..2026-06 (33rd/66th pct = 0.33 / 0.63).
RANGE_MAX = 0.33
TREND_MIN = 0.63

# Phase-1 carry-forward: A baseline, plus the TOP 2 (C best conversion/win, E best efficiency).
MODES: dict[str, dict] = {
    "A exact-low": {"entry_zone_pct": 0.0, "entry_zone_atr_mult": 0.0, "bounce_confirm": False},
    "C atr-0.25": {
        "entry_zone_atr_mult": 0.25, "atr20_pct": 0.03, "entry_zone_pct": 0.0,
        "bounce_confirm": False,
    },
    "E bounce": {"bounce_confirm": True, "entry_zone_pct": 0.15, "entry_zone_atr_mult": 0.0},
}


def classify_days(spy: pd.DataFrame, start: datetime) -> dict:
    """Map each session date (>= start) to 'range' | 'neutral' | 'trend' from SPY DE."""
    labels: dict = {}
    for i in range(len(spy)):
        o, h, l, c = (float(spy.loc[i, k]) for k in ("o", "h", "l", "c"))
        rng = h - l
        de = abs(c - o) / rng if rng > 0 else 0.0
        d = pd.Timestamp(spy.loc[i, "t"]).date()
        if d < start.date():
            continue
        labels[d] = "range" if de <= RANGE_MAX else ("trend" if de >= TREND_MIN else "neutral")
    return labels


def trade_stats(trades: list) -> dict:
    """PF / win% / expectancy / avg MAE-MFE over a list of closed BacktestTrade."""
    closed = [t for t in trades if t.pnl is not None]
    n = len(closed)
    if n == 0:
        return {"n": 0, "pf": float("nan"), "win": 0.0, "exp": 0.0, "mae": 0.0, "mfe": 0.0}
    gp = sum(t.pnl for t in closed if t.pnl > 0)
    gl = abs(sum(t.pnl for t in closed if t.pnl < 0))
    pf = (gp / gl) if gl > 0 else (99.99 if gp > 0 else 0.0)
    win = sum(1 for t in closed if t.pnl > 0) / n * 100
    exp = sum(t.pnl for t in closed) / n
    maes = [t.mae for t in closed if t.mae is not None]
    mfes = [t.mfe for t in closed if t.mfe is not None]
    return {
        "n": n, "pf": pf, "win": win, "exp": exp,
        "mae": (sum(maes) / len(maes) * 100) if maes else 0.0,
        "mfe": (sum(mfes) / len(mfes) * 100) if mfes else 0.0,
    }


def _row(label: str, s: dict) -> str:
    return "  %-22s %5d  PF %5.2f  win %5.1f%%  exp $%7.2f  mae %6.2f%%  mfe %6.2f%%" % (
        label, s["n"], s["pf"], s["win"], s["exp"], s["mae"], s["mfe"],
    )


async def main(args: argparse.Namespace) -> None:
    sf = get_sessionmaker()
    st = get_settings()
    async with sf() as s:
        strat = await s.get(StrategyRow, args.strategy)
        code_path, symbols = strat.code_path, list(strat.symbols_json)
        base, uid = dict(strat.params_json or {}), strat.user_id
    sc = StrategyLoader(STRATEGIES_ROOT).load(code_path)
    reg = BrokerRegistry(sf)
    await reg.load_all()
    bc = BarCache(adapter=reg.get(uid), root=st.bars_cache_root, max_gb=st.bars_cache_max_gb)
    ic = IndicatorComputer()
    start = datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(args.end).replace(tzinfo=timezone.utc)

    spy = (await bc.get_bars("SPY", "1Day", start, end)).reset_index(drop=True)
    day_label = classify_days(spy, start)
    dist = Counter(day_label.values())
    print(f"universe={symbols}  window={args.start}..{args.end}")
    print(f"SPY day-regime (DE tertiles range<={RANGE_MAX} / trend>={TREND_MIN}): {dict(dist)} "
          f"of {len(day_label)} sessions\n")

    for name, ov in MODES.items():
        cfg = BacktestConfig(start=start, end=end, timeframe="5Min", params={**base, **ov})
        _m, trades, _eq = await Backtester(bar_cache=bc, indicator_computer=ic).run(sc, symbols, cfg)
        by = {"range": [], "neutral": [], "trend": [], "unknown": []}
        for t in trades:
            d = pd.Timestamp(t.entry_ts).date()
            by[day_label.get(d, "unknown")].append(t)
        print(f"=== Mode {name} ===")
        print(_row("ALL days", trade_stats(trades)))
        for reg_name in ("range", "neutral", "trend", "unknown"):
            if by[reg_name]:
                print(_row(reg_name, trade_stats(by[reg_name])))
        gated = by["range"] + by["neutral"] + by["unknown"]  # the trend-day gate: drop trend trades
        print(_row("GATED (no trend days)", trade_stats(gated)))
        print()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strategy", type=int, default=1)
    ap.add_argument("--start", default="2023-07-01")
    ap.add_argument("--end", default="2026-06-30")
    asyncio.run(main(ap.parse_args()))
