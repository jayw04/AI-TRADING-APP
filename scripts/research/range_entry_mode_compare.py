#!/usr/bin/env python3
"""Phase 1 — Range entry-mode comparison (research; Range Strategy Modification Plan rev.2).

Runs the 5 entry modes over the SAME universe + window in the existing backtest harness and
tabulates trade quality + the Opportunity Funnel, so a mode is chosen on evidence (and the
promotion gate) rather than a single day. Modes A-D are param sweeps of existing knobs; E is
the new two-stage "bounce confirmation".

RUN IN A ONE-OFF CONTAINER (disarmed — cannot double-arm the live box). NOTE: the repo-root
`scripts/` dir is NOT baked into the backend image (the Dockerfile copies only apps/backend → /app),
so pipe this file in on stdin rather than referencing a path inside the container:
  docker compose run --rm --no-deps --entrypoint sh backend -c \
    "cd /app && python - --strategy 1 --start 2025-07-01 --end 2026-06-30 --timeframe 5Min" \
    < scripts/research/range_entry_mode_compare.py
For the owner's 3-year decision window: --start 2023-07-01.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone

from app.brokers.registry import BrokerRegistry
from app.config import get_settings
from app.db.models.strategy import Strategy as StrategyRow
from app.db.session import get_sessionmaker
from app.indicators import IndicatorComputer
from app.market_data.bar_cache import BarCache
from app.services.backtest_worker import STRATEGIES_ROOT, StrategyLoader
from app.strategies.backtester import BacktestConfig, Backtester

# Each mode overrides the strategy's saved params; the rest (OR window, stop, etc.) is held fixed.
MODES: dict[str, dict] = {
    "A exact-low": {"entry_zone_pct": 0.0, "entry_zone_atr_mult": 0.0, "bounce_confirm": False},
    "B zone-15%": {"entry_zone_pct": 0.15, "entry_zone_atr_mult": 0.0, "bounce_confirm": False},
    "C atr-0.25": {
        "entry_zone_atr_mult": 0.25,
        "atr20_pct": 0.03,
        "entry_zone_pct": 0.0,
        "bounce_confirm": False,
    },
    "D vwap+zone": {
        "vwap_gate_pct": 0.01,
        "entry_zone_pct": 0.15,
        "entry_zone_atr_mult": 0.0,
        "bounce_confirm": False,
    },
    "E bounce": {"bounce_confirm": True, "entry_zone_pct": 0.15, "entry_zone_atr_mult": 0.0},
}


async def main(args: argparse.Namespace) -> None:
    sf = get_sessionmaker()
    st = get_settings()
    async with sf() as s:
        strat = await s.get(StrategyRow, args.strategy)
        code_path = strat.code_path
        symbols = list(strat.symbols_json)
        base = dict(strat.params_json or {})
        user_id = strat.user_id
    sc = StrategyLoader(STRATEGIES_ROOT).load(code_path)
    reg = BrokerRegistry(sf)
    await reg.load_all()
    bc = BarCache(adapter=reg.get(user_id), root=st.bars_cache_root, max_gb=st.bars_cache_max_gb)
    ic = IndicatorComputer()
    start = datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(args.end).replace(tzinfo=timezone.utc)

    print(f"universe={symbols}  window={args.start}..{args.end}  tf={args.timeframe}\n")
    hdr = "%-12s %6s %8s %6s %6s %7s %7s | funnel univ/qual/touch/enter/stop" % (
        "mode", "trades", "ret%", "PF", "win%", "mae%", "mfe%",
    )
    print(hdr)
    print("-" * len(hdr))
    for name, ov in MODES.items():
        params = {**base, **ov}
        cfg = BacktestConfig(start=start, end=end, timeframe=args.timeframe, params=params)
        m, _trades, _eq = await Backtester(bar_cache=bc, indicator_computer=ic).run(
            sc, symbols, cfg
        )
        f = m.opportunity_funnel
        pf = m.profit_factor if m.profit_factor != float("inf") else 99.99
        print(
            "%-12s %6d %7.2f%% %6.2f %5.1f%% %6.2f%% %6.2f%% | %s/%s/%s/%s/%s"
            % (
                name, m.trade_count, m.total_return * 100, pf, m.win_rate * 100,
                m.avg_mae * 100, m.avg_mfe * 100,
                f.get("universe", 0), f.get("qualified", 0), f.get("touched", 0),
                f.get("entered", 0), f.get("stopped", 0),
            )
        )


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strategy", type=int, default=1)
    ap.add_argument("--start", default="2025-07-01")
    ap.add_argument("--end", default="2026-06-30")
    ap.add_argument("--timeframe", default="5Min")
    asyncio.run(main(ap.parse_args()))
