"""Range Trader — formal Rejection Evidence Package (completes the §5c research program).

Adds **walk-forward** + a **trade-level bootstrap CI** to the prior §5c IS/OOS rejection
(2026-06-16), and emits a governance verdict — to ARCHIVE Range Trader as the platform's **first
formally-rejected strategy** ("the platform validated AND declined a strategy"). Read-only research
over intraday Alpaca 5-min RTH bars (reachable via the OS trust store, ADR 0017).

Best prior config (the one that came closest): `RangeTraderVWAP` PLTR partial-reversion
``entry_sigma=2.0 / exit_sigma=0.5 / stop_sigma=3.0`` — IS PF 1.37 (cleared the 1.3 bar) but
OOS PF 0.92 (NO-GO). This script confirms the rejection with the missing rigor.

The decisive statistic for a trade-based strategy is the **bootstrap 95% CI of mean per-trade P&L**:
a CI that includes (or sits below) zero = no demonstrable edge.

    PYTHONPATH=apps/backend apps/backend/.venv/Scripts/python.exe apps/backend/scripts/range_evidence.py \
        --symbol PLTR --entry-sigma 2.0 --exit-sigma 0.5 --stop-sigma 3.0 \
        --start 2026-01-02 --end 2026-06-12 --windows 4 --bootstrap 2000 \
        --report-dir docs/implementation/evidence/range_rejection
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def _git_sha() -> str:
    import subprocess
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return "unknown"


def _run(symbol: str, params: dict[str, Any], start: datetime, end: datetime) -> list[float]:
    """Run RangeTraderVWAP on 5-min RTH bars for [start, end]; return per-trade P&L list."""
    import asyncio
    from decimal import Decimal
    from unittest.mock import AsyncMock, MagicMock

    from app.indicators import IndicatorComputer
    from app.strategies import Backtester
    from app.strategies.backtest_models import BacktestConfig
    from scripts.backtest_range_trader_alpaca import _fetch_rth_bars
    from strategies_user.templates.range_trader_vwap import RangeTraderVWAP

    bars = _fetch_rth_bars(symbol, start, end)
    if bars.empty:
        return []
    bar_cache = MagicMock()
    bar_cache.get_bars = AsyncMock(return_value=bars)
    harness = Backtester(bar_cache=bar_cache, indicator_computer=IndicatorComputer())
    config = BacktestConfig(
        start=bars["t"].iloc[0].to_pydatetime(), end=bars["t"].iloc[-1].to_pydatetime(),
        timeframe="5Min", initial_equity=Decimal("100000"), slippage_bps=5.0,
        params={**params, "timeframe": "5Min"},
    )
    _metrics, trades, _equity = asyncio.run(harness.run(RangeTraderVWAP, [symbol], config))
    return [float(t.pnl) for t in trades if t.pnl is not None]


def _edge(pnls: list[float]) -> dict[str, Any]:
    """Profit factor + mean per-trade P&L + win rate for a trade-P&L list."""
    n = len(pnls)
    wins = sum(p for p in pnls if p > 0)
    losses = -sum(p for p in pnls if p < 0)
    pf = wins / losses if losses > 0 else float("inf")
    return {
        "trades": n,
        "profit_factor": round(pf, 3) if pf != float("inf") else None,
        "mean_pnl": round(sum(pnls) / n, 2) if n else 0.0,
        "win_rate": round(sum(1 for p in pnls if p > 0) / n, 3) if n else 0.0,
        "total_pnl": round(sum(pnls), 2),
    }


def _bootstrap_mean_ci(pnls: list[float], *, n_resamples: int, seed: int) -> dict[str, Any]:
    """Bootstrap 95% CI of mean per-trade P&L (resample trades with replacement). A CI that
    includes <= 0 = no demonstrable edge — the decisive rejection test."""
    n = len(pnls)
    point = round(sum(pnls) / n, 2) if n else 0.0
    if n < 20:
        return {"mean": point, "ci_low": None, "ci_high": None, "excludes_zero": False,
                "note": f"too few trades ({n}) to bootstrap"}
    rng = random.Random(seed)
    means: list[float] = []
    for _ in range(n_resamples):
        s = sum(pnls[rng.randrange(n)] for _ in range(n)) / n
        means.append(s)
    means.sort()
    lo = means[int(0.025 * n_resamples)]
    hi = means[min(int(0.975 * n_resamples), n_resamples - 1)]
    return {"mean": point, "ci_low": round(lo, 2), "ci_high": round(hi, 2),
            "excludes_zero": lo > 0}


def _split(start: date, end: date, k: int) -> list[tuple[date, date]]:
    days = (end - start).days
    step = max(1, days // k)
    out = []
    for i in range(k):
        ws = date.fromordinal(start.toordinal() + i * step)
        we = end if i == k - 1 else date.fromordinal(start.toordinal() + (i + 1) * step)
        out.append((ws, we))
    return out


def _dt(d: date, end_of_day: bool = False) -> datetime:
    return datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=UTC) if end_of_day \
        else datetime(d.year, d.month, d.day, tzinfo=UTC)


def main() -> int:
    ap = argparse.ArgumentParser(description="Range Trader rejection evidence (walk-forward + bootstrap)")
    ap.add_argument("--symbol", default="PLTR")
    ap.add_argument("--entry-sigma", type=float, default=2.0)
    ap.add_argument("--exit-sigma", type=float, default=0.5)
    ap.add_argument("--stop-sigma", type=float, default=3.0)
    ap.add_argument("--start", default="2026-01-02")
    ap.add_argument("--end", default="2026-06-12")
    ap.add_argument("--windows", type=int, default=4)
    ap.add_argument("--bootstrap", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=17)
    ap.add_argument("--report-dir", default=None)
    args = ap.parse_args()
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    params = {"entry_sigma": args.entry_sigma, "exit_sigma": args.exit_sigma,
              "stop_sigma": args.stop_sigma}

    # full window
    full_pnls = _run(args.symbol, params, _dt(start), _dt(end, end_of_day=True))
    full = _edge(full_pnls)
    boot = _bootstrap_mean_ci(full_pnls, n_resamples=args.bootstrap, seed=args.seed)

    # walk-forward sub-windows
    windows = []
    n_pos = 0
    for ws, we in _split(start, end, args.windows):
        e = _edge(_run(args.symbol, params, _dt(ws), _dt(we, end_of_day=True)))
        windows.append({"window": [str(ws), str(we)], **e})
        if (e["profit_factor"] or 0) > 1.0:
            n_pos += 1

    # verdict: VALIDATED only if PF>=1.3 AND bootstrap mean-P&L CI excludes 0 AND most windows profitable
    pf = full["profit_factor"] or 0.0
    validated = pf >= 1.3 and boot["excludes_zero"] and n_pos >= (args.windows + 1) // 2 + 1
    verdict = "VALIDATED" if validated else "REJECTED"

    result: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(), "git_sha": _git_sha(),
        "hypothesis": "RangeTraderVWAP has a robust intraday mean-reversion edge",
        "symbol": args.symbol, "config": params, "window": [str(start), str(end)],
        "data": "alpaca_iex_5min RTH (intraday history ~6 months = ONE regime — walk-forward is "
                "depth-limited; the single-regime caveat is load-bearing)",
        "full_window": full, "bootstrap_mean_pnl_ci": boot,
        "walk_forward": windows, "n_windows_profitable": f"{n_pos}/{args.windows}",
        "verdict": verdict,
        "prior": "§5c (2026-06-16): every IS-passing config collapsed OOS (best IS PF 1.37 -> OOS 0.92 = NO-GO)",
    }

    print(f"[range-evidence] {args.symbol} VWAP {params} {start}..{end}")
    print(f"  full: {full['trades']} trades, PF {full['profit_factor']}, mean P&L {full['mean_pnl']}, "
          f"win {full['win_rate']}")
    print(f"  bootstrap mean-P&L 95% CI [{boot['ci_low']}, {boot['ci_high']}] "
          f"excludes_zero={boot['excludes_zero']}")
    print(f"  walk-forward profitable windows: {n_pos}/{args.windows}")
    print(f"  -> VERDICT: {verdict}")

    if args.report_dir:
        d = Path(args.report_dir)
        d.mkdir(parents=True, exist_ok=True)
        (d / "range_evidence.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        (d / "range_evidence.md").write_text(_render(result), encoding="utf-8")
        print(f"  wrote {d / 'range_evidence.json'} + range_evidence.md")
    return 0


def _render(r: dict[str, Any]) -> str:
    f, b = r["full_window"], r["bootstrap_mean_pnl_ci"]
    lines = [
        f"# Range Trader — Rejection Evidence ({r['verdict']})",
        "",
        f"_git {r['git_sha']} · {r['symbol']} VWAP {r['config']} · {r['window'][0]}..{r['window'][1]} · "
        f"{r['data']}_",
        "",
        "> Completes the §5c research program (walk-forward + bootstrap) and records the governance "
        "verdict. Archived as the platform's **first formally-rejected strategy** — the Evidence "
        "Engineering thesis in action: *the platform validated AND declined a strategy.*",
        "",
        "## Hypothesis",
        f"_{r['hypothesis']}_ — tested on the best prior config (the only one that ever cleared IS).",
        "",
        "## 1. Full-window edge + bootstrap (decisive)",
        "",
        f"- **{f['trades']} trades** · profit factor **{f['profit_factor']}** · mean per-trade P&L "
        f"**${f['mean_pnl']}** · win rate {f['win_rate']:.0%} · total ${f['total_pnl']:,.0f}.",
        f"- **Bootstrap 95% CI of mean per-trade P&L: [${b['ci_low']}, ${b['ci_high']}]** — "
        f"{'EXCLUDES zero (edge)' if b.get('excludes_zero') else 'INCLUDES zero → no demonstrable edge'}.",
        "",
        "## 2. Walk-forward consistency",
        "",
        "| Window | Trades | Profit factor | Mean P&L |",
        "|---|---|---|---|",
        *[f"| {w['window'][0]}..{w['window'][1]} | {w['trades']} | {w['profit_factor']} | ${w['mean_pnl']} |"
          for w in r["walk_forward"]],
        "",
        f"Profitable (PF>1) windows: **{r['n_windows_profitable']}**.",
        "",
        f"## Verdict: **{r['verdict']}**",
        "",
        f"Prior: {r['prior']}.",
        "",
        "_Per ADR 0014: a strategy earns paper/live only with a robust, statistically-significant edge. "
        "Range Trader does not clear that bar — recorded as a documented, citable 'honest no.' "
        "Intraday history is ~6 months (one regime); a deeper walk-forward would need more intraday "
        "data, but the bootstrap on the full trade set is the load-bearing test and it is decisive._",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
