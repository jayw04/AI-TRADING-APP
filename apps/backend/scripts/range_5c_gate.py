"""§5c Range-Trader backtest GO/NO-GO gate (Range Trader paper-activation plan,
Finding 4 — pre-registered acceptance criteria; ADR 0014 — backtests are the
eval ground truth).

The thresholds below are **pre-registered**: they are the bar a chosen
symbol/levels must clear *before* the RangeTrader strategy may be activated to
PAPER. They are written down here (and in
``docs/implementation/TradingWorkbench_RangeTrader_5c_Backtest_PreReg_v1.0.md``)
so they cannot be moved after seeing results. Tighten, never loosen, after the
fact.

``evaluate_gate`` is a pure function (no I/O) over the backtest metrics, so the
verdict is testable and reproducible. The CLI runs the production ``Backtester``
on real RTH 5-min bars for an in-sample and an out-of-sample window, then applies
the gate. Offline use / unit tests exercise ``evaluate_gate`` directly.

    cd apps/backend
    .venv/Scripts/python.exe scripts/range_5c_gate.py KO \
        --entry 60.5 --exit 64.0 --stop 59.0 \
        --is 2026-04-01 2026-05-08 --oos 2026-05-09 2026-06-05 \
        --robustness --json evidence/KO_5c.json

Verdict is one of GO / GO-WARNING / NO-GO / INCONCLUSIVE. Exits 0 on GO and
GO-WARNING (eligible; GO-WARNING needs Owner signoff), 1 on NO-GO, 2 on
INCONCLUSIVE (insufficient trades) so it can gate an activation pipeline.

v0.2 (review response): cost model, expectancy >= 0.15R, OOS PF >= max(1.0,
0.8 x IS), >=50-trade bar with 30-49 GO-WARNING and <30 INCONCLUSIVE, robustness
(+/-0.5%), evidence JSON.
v0.3: the intraday-drift check uses **bars held** (BacktestTrade.bar_count_held),
not wall-clock duration — bars skip overnight/weekend gaps, so an EOD exit that
fills at the next session's open is ~1 session (passes) while a true multi-day
hold is ~2+ sessions (flagged). Wall-clock over-counts across session boundaries.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

GATE_VERSION = "0.3"
RTH_SESSION_SECONDS = int(6.5 * 3600)  # 23400 — one regular session
RTH_BARS_PER_SESSION = 78  # 6.5h / 5min — one regular session of 5-min bars


@dataclass(frozen=True)
class GateThresholds:
    """Pre-registered §5c acceptance criteria. Conservative defaults — tighten,
    don't loosen, after seeing results."""

    min_trades_floor: int = 30        # below this → INCONCLUSIVE (not enough evidence)
    min_trades_strong: int = 50       # 30-49 is a WARNING; >=50 is a clean sample
    min_profit_factor: float = 1.3    # edge must survive costs
    min_win_rate: float = 0.45        # paired with the payoff check below
    min_avg_win_loss: float = 1.0     # winners must at least match losers
    min_expectancy_r: float = 0.15    # avg profit per unit of risk
    oos_pf_ratio: float = 0.8         # OOS PF >= ratio x IS PF (anti curve-fit)
    oos_pf_floor: float = 1.0         # ...and OOS PF must be profitable outright
    # Intraday-drift check (bars, not wall-clock): a position must be flat by ~1
    # session. Bars skip overnight/weekend gaps, so an EOD exit that fills at the
    # next session's open is ~1 session of bars (passes), while a genuine
    # multi-day hold is ~2+ sessions (flagged). The buffer above one session
    # absorbs that next-open fill bar. (Wall-clock duration over-counts here.)
    max_bars_held: int = int(1.5 * RTH_BARS_PER_SESSION)  # 117 bars (~1.5 sessions)
    min_data_coverage: float = 0.97   # received/expected RTH bars; 5-min intraday
                                      # needs tighter coverage than daily (review #3)
    robustness_min_ratio: float = 0.8  # perturbed PF >= ratio x base PF (if run)
    robustness_min_trade_ratio: float = 0.8  # perturbed trades >= ratio x base (if run)
    # Max-drawdown bound = 2 x per-trade risk x max trades/day. With the
    # template defaults (1% risk, 4 trades/day) this is 8%.
    risk_per_trade_pct: float = 0.01
    max_trades_per_day: int = 4

    @property
    def max_drawdown_bound(self) -> float:
        return 2.0 * self.risk_per_trade_pct * self.max_trades_per_day

    def oos_floor(self, is_pf: float) -> float:
        return max(self.oos_pf_floor, self.oos_pf_ratio * is_pf)


@dataclass(frozen=True)
class GateMetrics:
    """The slice of backtest metrics the gate needs (decoupled from the
    harness's BacktestMetrics so the evaluator stays import-light + testable)."""

    profit_factor: float
    win_rate: float
    trade_count: int
    avg_win: float
    avg_loss: float          # as reported by the harness (sign-carrying)
    max_drawdown: float      # negative fraction, e.g. -0.06
    p95_bars_held: float | None = None     # 95th-pctile bars-held (drift check)
    p95_hold_seconds: float | None = None  # wall-clock (reported only; over-counts gaps)
    data_coverage: float | None = None     # received/expected RTH bars in the window


@dataclass
class GateVerdict:
    verdict: str = "NO-GO"  # GO | NO-GO | INCONCLUSIVE
    checks: list[tuple[str, bool, str]] = field(default_factory=list)  # (name, passed, detail)
    warnings: list[str] = field(default_factory=list)

    @property
    def go(self) -> bool:
        return self.verdict == "GO"

    @property
    def eligible(self) -> bool:
        """Activatable — GO outright, or GO-WARNING pending operator signoff."""
        return self.verdict in ("GO", "GO-WARNING")


def _avg_win_loss_ratio(m: GateMetrics) -> float:
    loss = abs(m.avg_loss)
    if loss == 0:
        return float("inf") if m.avg_win > 0 else 0.0
    return m.avg_win / loss


def _expectancy_r(m: GateMetrics) -> float:
    """Expectancy per unit of risk. With a hard stop, |avg_loss| ~= 1R, so
    expectancy_$ / |avg_loss| approximates expectancy in R."""
    loss = abs(m.avg_loss)
    exp_cash = m.win_rate * m.avg_win - (1.0 - m.win_rate) * loss
    if loss == 0:
        return float("inf") if exp_cash > 0 else 0.0
    return exp_cash / loss


def evaluate_gate(
    is_m: GateMetrics,
    oos_m: GateMetrics,
    *,
    all_trades_closed: bool,
    robustness_runs: list[tuple[float, int]] | None = None,
    thresholds: GateThresholds | None = None,
) -> GateVerdict:
    """Apply the pre-registered §5c criteria over the IS metrics (+ the OOS PF
    consistency check). ``all_trades_closed`` is the stop-behavior proxy: every
    modeled entry was exited. ``robustness_runs`` (optional) are (profit_factor,
    trade_count) from +/-0.5% level perturbations.

    Verdict: INCONCLUSIVE if IS trade_count < floor (not enough evidence to pass
    OR fail); else, when every criterion passes, GO if >= min_trades_strong else
    GO-WARNING (operator signoff required); otherwise NO-GO."""
    t = thresholds or GateThresholds()
    ratio = _avg_win_loss_ratio(is_m)
    exp_r = _expectancy_r(is_m)
    dd = abs(is_m.max_drawdown)
    oos_floor = t.oos_floor(is_m.profit_factor)

    checks: list[tuple[str, bool, str]] = [
        ("profit_factor >= min",
         is_m.profit_factor >= t.min_profit_factor,
         f"{is_m.profit_factor:.2f} vs >= {t.min_profit_factor}"),
        ("win_rate >= min",
         is_m.win_rate >= t.min_win_rate,
         f"{is_m.win_rate:.0%} vs >= {t.min_win_rate:.0%}"),
        ("avg_win/avg_loss >= min",
         ratio >= t.min_avg_win_loss,
         f"{ratio:.2f} vs >= {t.min_avg_win_loss}"),
        ("expectancy >= min (R)",
         exp_r >= t.min_expectancy_r,
         f"{exp_r:.2f}R vs >= {t.min_expectancy_r}R"),
        ("max_drawdown <= bound",
         dd <= t.max_drawdown_bound,
         f"{dd:.1%} vs <= {t.max_drawdown_bound:.1%}"),
        ("OOS PF >= max(1.0, 0.8 x IS PF)",
         oos_m.profit_factor >= oos_floor,
         f"{oos_m.profit_factor:.2f} vs >= {oos_floor:.2f}"),
        ("stop behavior (all trades closed)",
         all_trades_closed,
         "no stuck position" if all_trades_closed else "a position was left open"),
    ]

    if is_m.p95_bars_held is not None:
        checks.append((
            "bars held (p95) <= max",
            is_m.p95_bars_held <= t.max_bars_held,
            f"{is_m.p95_bars_held:.0f} bars (~{is_m.p95_bars_held / RTH_BARS_PER_SESSION:.1f} "
            f"sessions) vs <= {t.max_bars_held}",
        ))

    if is_m.data_coverage is not None:
        checks.append((
            "data coverage >= min",
            is_m.data_coverage >= t.min_data_coverage,
            f"{is_m.data_coverage:.1%} vs >= {t.min_data_coverage:.0%}",
        ))

    if robustness_runs:
        worst_pf = min(pf for pf, _ in robustness_runs)
        worst_n = min(n for _, n in robustness_runs)
        pf_floor = t.robustness_min_ratio * is_m.profit_factor
        n_floor = t.robustness_min_trade_ratio * is_m.trade_count
        checks.append((
            "robustness (PF & trade-count)",
            worst_pf >= pf_floor and worst_n >= n_floor,
            f"worst PF {worst_pf:.2f} (>= {pf_floor:.2f}), "
            f"worst trades {worst_n} (>= {n_floor:.0f}); +/-0.5% levels",
        ))

    warnings: list[str] = []

    # Trade count drives the verdict STATE, not a pass/fail criterion.
    if is_m.trade_count < t.min_trades_floor:
        return GateVerdict(
            verdict="INCONCLUSIVE",
            checks=checks,
            warnings=[
                f"only {is_m.trade_count} IS trades (< {t.min_trades_floor}) — "
                f"not enough evidence to GO or NO-GO; widen the window / re-screen."
            ],
        )

    if not all(passed for _, passed, _ in checks):
        return GateVerdict(verdict="NO-GO", checks=checks, warnings=warnings)

    # All criteria pass. 50+ → GO; 30-49 → GO-WARNING (operator signoff required).
    if is_m.trade_count < t.min_trades_strong:
        warnings.append(
            f"thin sample: {is_m.trade_count} IS trades "
            f"(>= {t.min_trades_strong} preferred) — Owner signoff required."
        )
        return GateVerdict(verdict="GO-WARNING", checks=checks, warnings=warnings)
    return GateVerdict(verdict="GO", checks=checks, warnings=warnings)


def print_verdict(v: GateVerdict, *, symbol: str) -> None:
    print(f"\n=== §5c GATE v{GATE_VERSION} — {symbol} ===")
    for name, passed, detail in v.checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name:<34} {detail}")
    for w in v.warnings:
        print(f"  [WARN] {w}")
    label = {"GO": "GO — eligible to activate",
             "GO-WARNING": "GO-WARNING — eligible, but Owner signoff required (thin sample)",
             "NO-GO": "NO-GO — do not activate",
             "INCONCLUSIVE": "INCONCLUSIVE — insufficient evidence"}[v.verdict]
    print(f"\n  VERDICT: {label}\n")


# ---- real-data runner (CLI only; not exercised by the pure-function tests) ----


def _git_commit() -> str | None:
    """Short HEAD commit for true reproducibility (code can change without a
    version bump). None if git is unavailable."""
    import subprocess
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(BACKEND_ROOT), capture_output=True, text=True, timeout=5,
        )
        return out.stdout.strip() or None if out.returncode == 0 else None
    except Exception:
        return None


def _percentile(values: list[float], pct: float) -> float | None:
    """Nearest-rank percentile (no numpy dependency)."""
    xs = sorted(v for v in values if v is not None)
    if not xs:
        return None
    k = max(0, min(len(xs) - 1, int(round((pct / 100.0) * (len(xs) - 1)))))
    return float(xs[k])


def _to_gate_metrics(m, trades, data_coverage=None) -> GateMetrics:  # type: ignore[no-untyped-def]
    durations = [t.duration_seconds for t in trades if getattr(t, "duration_seconds", None)]
    bars = [t.bar_count_held for t in trades if getattr(t, "bar_count_held", None) is not None]
    return GateMetrics(
        profit_factor=float(m.profit_factor), win_rate=float(m.win_rate),
        trade_count=int(m.trade_count), avg_win=float(m.avg_win),
        avg_loss=float(m.avg_loss), max_drawdown=float(m.max_drawdown),
        p95_bars_held=_percentile(bars, 95) if bars else None,
        p95_hold_seconds=_percentile(durations, 95) if durations else None,
        data_coverage=data_coverage,
    )


def _expected_rth_bars(start, end) -> int:  # type: ignore[no-untyped-def]
    """Expected RTH 5-min bars over [start, end] using the §9A calendar: 78 per
    full trading day, 42 per half-day. Lets us flag holey IEX data."""
    from datetime import UTC, datetime, time, timedelta

    from app.market.session import default_market_session

    ms = default_market_session()
    y0, m0, d0 = map(int, start.split("-"))
    y1, m1, d1 = map(int, end.split("-"))
    day = datetime(y0, m0, d0, tzinfo=UTC)
    last = datetime(y1, m1, d1, tzinfo=UTC)
    total = 0
    while day <= last:
        # classify at ~noon ET to avoid boundary effects
        info = ms.classify(datetime.combine(day.date(), time(17, 0), tzinfo=UTC))
        if info.is_trading_day:
            total += 42 if info.is_half_day else 78
        day += timedelta(days=1)
    return total


def _run_window(symbol, levels, start, end, slippage_bps):  # type: ignore[no-untyped-def]
    """Run the production Backtester on real RTH 5Min bars for one window.
    Returns (GateMetrics, all_trades_closed, trades). Needs network + creds."""
    import asyncio
    from datetime import UTC, datetime
    from decimal import Decimal
    from unittest.mock import AsyncMock, MagicMock

    from app.indicators import IndicatorComputer
    from app.strategies import Backtester
    from app.strategies.backtest_models import BacktestConfig
    from scripts.backtest_range_trader_alpaca import _fetch_rth_bars  # RTH filter
    from strategies_user.templates.range_trader import RangeTrader

    y0, m0, d0 = map(int, start.split("-"))
    y1, m1, d1 = map(int, end.split("-"))
    bars = _fetch_rth_bars(
        symbol, datetime(y0, m0, d0, tzinfo=UTC), datetime(y1, m1, d1, 23, 59, 59, tzinfo=UTC)
    )
    if bars.empty:
        raise SystemExit(f"No bars for {symbol} {start}..{end} — check creds/network/range.")

    bar_cache = MagicMock()
    bar_cache.get_bars = AsyncMock(return_value=bars)
    harness = Backtester(bar_cache=bar_cache, indicator_computer=IndicatorComputer())
    config = BacktestConfig(
        start=bars["t"].iloc[0].to_pydatetime(), end=bars["t"].iloc[-1].to_pydatetime(),
        timeframe="5Min", initial_equity=Decimal("100000"), slippage_bps=slippage_bps,
        params={"entry_price": levels[0], "exit_price": levels[1], "stop_price": levels[2],
                "timeframe": "5Min"},
    )
    metrics, trades, _equity = asyncio.run(harness.run(RangeTrader, [symbol], config))
    all_closed = all(getattr(tr, "exit_price", None) is not None for tr in trades)
    expected = _expected_rth_bars(start, end)
    coverage = min(1.0, len(bars) / expected) if expected else None
    return _to_gate_metrics(metrics, trades, coverage), all_closed, trades


def _robustness_runs(symbol, levels, start, end, slippage_bps):  # type: ignore[no-untyped-def]
    """(profit_factor, trade_count) under +/-0.5% perturbation of each level
    (others fixed), skipping any that break stop < entry < exit."""
    runs: list[tuple[float, int]] = []
    for i, base in enumerate(levels):
        for delta in (-0.005, 0.005):
            pert = list(levels)
            pert[i] = base * (1 + delta)
            e, x, s = pert
            if not (s < e < x):
                continue
            m, _closed, _tr = _run_window(symbol, tuple(pert), start, end, slippage_bps)
            runs.append((m.profit_factor, m.trade_count))
    return runs


def main() -> int:
    ap = argparse.ArgumentParser(description="§5c Range-Trader backtest GO/NO-GO gate.")
    ap.add_argument("symbol")
    ap.add_argument("--entry", type=float, required=True)
    ap.add_argument("--exit", type=float, required=True, dest="exit_")
    ap.add_argument("--stop", type=float, required=True)
    ap.add_argument("--is", nargs=2, metavar=("START", "END"), required=True, dest="is_win")
    ap.add_argument("--oos", nargs=2, metavar=("START", "END"), required=True)
    ap.add_argument("--slippage-bps", type=float, default=5.0)
    ap.add_argument("--robustness", action="store_true",
                    help="Also re-run IS with +/-0.5% level perturbations (slower).")
    ap.add_argument("--json", default=None, help="Persist the gate-evaluation evidence to this path.")
    args = ap.parse_args()

    symbol = args.symbol.upper()
    levels = (args.entry, args.exit_, args.stop)
    if not (args.stop < args.entry < args.exit_):
        print("ERROR: levels must satisfy stop < entry < exit (_levels_ok).", file=sys.stderr)
        return 2

    print(f"Running IS {args.is_win[0]}..{args.is_win[1]} and OOS {args.oos[0]}..{args.oos[1]} ...")
    is_m, is_closed, _ = _run_window(symbol, levels, *args.is_win, args.slippage_bps)
    oos_m, oos_closed, _ = _run_window(symbol, levels, *args.oos, args.slippage_bps)
    rob = _robustness_runs(symbol, levels, *args.is_win, args.slippage_bps) if args.robustness else None

    verdict = evaluate_gate(
        is_m, oos_m, all_trades_closed=is_closed and oos_closed, robustness_runs=rob
    )
    print_verdict(verdict, symbol=symbol)

    if args.json:
        import json

        from app.strategies.backtest_models import BacktestConfig
        from strategies_user.templates.range_trader import RangeTrader
        evidence = {
            "gate_version": GATE_VERSION,
            "strategy_version": RangeTrader.version,
            "git_commit": _git_commit(),
            "random_seed": BacktestConfig.__dataclass_fields__["seed"].default,
            "symbol": symbol,
            "levels": {"entry": args.entry, "exit": args.exit_, "stop": args.stop},
            "is_window": args.is_win, "oos_window": args.oos,
            "data_source": "alpaca_iex_5min", "slippage_bps": args.slippage_bps,
            "is_metrics": vars(is_m), "oos_metrics": vars(oos_m),
            "robustness_runs": rob,
            "checks": [{"criterion": n, "passed": p, "detail": d} for n, p, d in verdict.checks],
            "warnings": verdict.warnings, "verdict": verdict.verdict,
        }
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(evidence, indent=2, default=str))
        print(f"Evidence written -> {args.json}")

    print("Record the verdict + metrics/params/windows as activation evidence "
          "(Finding 4). NO-GO/INCONCLUSIVE -> re-select levels/symbol or widen window. "
          "GO-WARNING -> eligible but requires Owner signoff.")
    return {"GO": 0, "GO-WARNING": 0, "NO-GO": 1, "INCONCLUSIVE": 2}[verdict.verdict]


if __name__ == "__main__":
    raise SystemExit(main())
