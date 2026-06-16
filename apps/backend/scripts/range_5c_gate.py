"""§5c Range-Trader backtest GO/NO-GO gate (Range Trader paper-activation plan,
Finding 4 — pre-registered acceptance criteria; ADR 0014 — backtests are the
eval ground truth).

The thresholds below are **pre-registered**: they are the bar a chosen
symbol/levels must clear *before* the RangeTrader strategy may be activated to
PAPER. They are written down here (and in
``docs/implementation/TradingWorkbench_RangeTrader_5c_Backtest_PreReg_v0.1.md``)
so they cannot be moved after seeing results. Tighten, never loosen, after the
fact.

``evaluate_gate`` is a pure function (no I/O) over the backtest metrics, so the
verdict is testable and reproducible. The CLI runs the production ``Backtester``
on real RTH 5-min bars for an in-sample and an out-of-sample window, then applies
the gate. Offline use / unit tests exercise ``evaluate_gate`` directly.

    cd apps/backend
    .venv/Scripts/python.exe scripts/range_5c_gate.py KO \
        --entry 60.5 --exit 64.0 --stop 59.0 \
        --is 2026-04-01 2026-05-08 --oos 2026-05-09 2026-06-05

Exits non-zero on NO-GO so it can gate an activation pipeline.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


@dataclass(frozen=True)
class GateThresholds:
    """Pre-registered §5c acceptance criteria. Conservative defaults — tighten,
    don't loosen, after seeing results."""

    min_trades: int = 30              # below this the stats aren't meaningful
    min_profit_factor: float = 1.3    # edge must survive costs
    min_win_rate: float = 0.45        # paired with the payoff check below
    min_avg_win_loss: float = 1.0     # winners must at least match losers
    oos_pf_ratio: float = 0.8         # OOS PF >= 0.8 x IS PF (anti curve-fit)
    # Max-drawdown bound = 2 x per-trade risk x max trades/day. With the
    # template defaults (1% risk, 4 trades/day) this is 8%.
    risk_per_trade_pct: float = 0.01
    max_trades_per_day: int = 4

    @property
    def max_drawdown_bound(self) -> float:
        return 2.0 * self.risk_per_trade_pct * self.max_trades_per_day


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


@dataclass
class GateVerdict:
    go: bool = False
    checks: list[tuple[str, bool, str]] = field(default_factory=list)  # (name, passed, detail)


def _avg_win_loss_ratio(m: GateMetrics) -> float:
    loss = abs(m.avg_loss)
    if loss == 0:
        return float("inf") if m.avg_win > 0 else 0.0
    return m.avg_win / loss


def evaluate_gate(
    is_m: GateMetrics,
    oos_m: GateMetrics,
    *,
    all_trades_closed: bool,
    thresholds: GateThresholds | None = None,
) -> GateVerdict:
    """Apply the pre-registered §5c criteria. ``all_trades_closed`` is the stop-
    behavior proxy: every modeled entry was exited (no position left stuck open
    through a breakdown / overnight). GO only if EVERY check passes."""
    t = thresholds or GateThresholds()
    ratio = _avg_win_loss_ratio(is_m)
    dd = abs(is_m.max_drawdown)
    oos_floor = t.oos_pf_ratio * is_m.profit_factor

    checks: list[tuple[str, bool, str]] = [
        ("trade_count >= min",
         is_m.trade_count >= t.min_trades,
         f"{is_m.trade_count} vs >= {t.min_trades}"),
        ("profit_factor >= min",
         is_m.profit_factor >= t.min_profit_factor,
         f"{is_m.profit_factor:.2f} vs >= {t.min_profit_factor}"),
        ("win_rate >= min",
         is_m.win_rate >= t.min_win_rate,
         f"{is_m.win_rate:.0%} vs >= {t.min_win_rate:.0%}"),
        ("avg_win/avg_loss >= min",
         ratio >= t.min_avg_win_loss,
         f"{ratio:.2f} vs >= {t.min_avg_win_loss}"),
        ("max_drawdown <= bound",
         dd <= t.max_drawdown_bound,
         f"{dd:.1%} vs <= {t.max_drawdown_bound:.1%}"),
        ("OOS PF >= 0.8 x IS PF",
         oos_m.profit_factor >= oos_floor,
         f"{oos_m.profit_factor:.2f} vs >= {oos_floor:.2f}"),
        ("stop behavior (all trades closed)",
         all_trades_closed,
         "no stuck position" if all_trades_closed else "a position was left open"),
    ]
    return GateVerdict(go=all(passed for _, passed, _ in checks), checks=checks)


def print_verdict(v: GateVerdict, *, symbol: str) -> None:
    print(f"\n=== §5c GATE — {symbol} ===")
    for name, passed, detail in v.checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name:<34} {detail}")
    print(f"\n  VERDICT: {'GO — eligible to activate' if v.go else 'NO-GO — do not activate'}\n")


# ---- real-data runner (CLI only; not exercised by the pure-function tests) ----


def _to_gate_metrics(m) -> GateMetrics:  # type: ignore[no-untyped-def]
    return GateMetrics(
        profit_factor=float(m.profit_factor), win_rate=float(m.win_rate),
        trade_count=int(m.trade_count), avg_win=float(m.avg_win),
        avg_loss=float(m.avg_loss), max_drawdown=float(m.max_drawdown),
    )


def _run_window(symbol, levels, start, end, slippage_bps):  # type: ignore[no-untyped-def]
    """Run the production Backtester on real RTH 5Min bars for one window.
    Returns (GateMetrics, all_trades_closed). Needs network + creds."""
    from datetime import UTC, datetime
    from decimal import Decimal
    from unittest.mock import AsyncMock, MagicMock

    from app.indicators import IndicatorComputer
    from app.strategies import Backtester
    from app.strategies.backtest_models import BacktestConfig
    from scripts.backtest_range_trader_alpaca import _fetch_rth_bars  # RTH filter

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
    from strategies_user.templates.range_trader import RangeTrader

    config = BacktestConfig(
        start=bars["t"].iloc[0].to_pydatetime(), end=bars["t"].iloc[-1].to_pydatetime(),
        timeframe="5Min", starting_equity=Decimal("100000"), slippage_bps=slippage_bps,
        params={"entry_price": levels[0], "exit_price": levels[1], "stop_price": levels[2],
                "timeframe": "5Min"},
    )
    import asyncio

    metrics, trades, _equity = asyncio.run(harness.run(RangeTrader, [symbol], config))
    all_closed = all(getattr(tr, "exit_price", None) is not None for tr in trades)
    return _to_gate_metrics(metrics), all_closed


def main() -> int:
    ap = argparse.ArgumentParser(description="§5c Range-Trader backtest GO/NO-GO gate.")
    ap.add_argument("symbol")
    ap.add_argument("--entry", type=float, required=True)
    ap.add_argument("--exit", type=float, required=True, dest="exit_")
    ap.add_argument("--stop", type=float, required=True)
    ap.add_argument("--is", nargs=2, metavar=("START", "END"), required=True, dest="is_win")
    ap.add_argument("--oos", nargs=2, metavar=("START", "END"), required=True)
    ap.add_argument("--slippage-bps", type=float, default=5.0)
    args = ap.parse_args()

    symbol = args.symbol.upper()
    levels = (args.entry, args.exit_, args.stop)
    if not (args.stop < args.entry < args.exit_):
        print("ERROR: levels must satisfy stop < entry < exit (_levels_ok).", file=sys.stderr)
        return 2

    print(f"Running IS {args.is_win[0]}..{args.is_win[1]} and OOS {args.oos[0]}..{args.oos[1]} ...")
    is_m, is_closed = _run_window(symbol, levels, *args.is_win, args.slippage_bps)
    oos_m, oos_closed = _run_window(symbol, levels, *args.oos, args.slippage_bps)

    verdict = evaluate_gate(is_m, oos_m, all_trades_closed=is_closed and oos_closed)
    print_verdict(verdict, symbol=symbol)
    print("Record this verdict + the full metrics/params/windows as activation "
          "evidence (Finding 4). NO-GO → re-select levels/symbol or shelve.")
    return 0 if verdict.go else 1


if __name__ == "__main__":
    raise SystemExit(main())
