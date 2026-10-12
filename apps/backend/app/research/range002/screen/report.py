"""Descriptive screen metrics in R units. Computes statistics only; it chooses no threshold and
applies no verdict (criteria are adopted separately, before results are viewed). Bootstrap
intervals are NOT built here: the method and resampling unit (D06) are unresolved and the screen
must fail closed on them rather than default."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from app.research.range002.governance.results_guard import requires_capability
from app.research.range002.screen.scheduler import PortfolioRun
from app.research.range002.screen.types import UNAVAILABLE_EXIT_VALUATION_RULE, Trade
from app.research.range002.spec.schema import SCREEN_V2_UNMODELLED


def _pf(values: Sequence[float]) -> float | None:
    wins = sum(v for v in values if v > 0)
    losses = -sum(v for v in values if v < 0)
    return None if losses == 0 else wins / losses


def _max_drawdown(by_day: dict[Any, float]) -> float:
    peak = equity = worst = 0.0
    for day in sorted(by_day):
        equity += by_day[day]
        peak = max(peak, equity)
        worst = max(worst, peak - equity)
    return worst


def _side(values: Sequence[float]) -> dict[str, Any]:
    n = len(values)
    return {
        "mean_net_r": (sum(values) / n) if n else None,
        "total_net_r": sum(values),
        "profit_factor": _pf(values),
        "win_rate": (sum(1 for v in values if v > 0) / n) if n else None,
    }


@requires_capability
def summarize(capability: object, trades: Sequence[Trade]) -> dict[str, Any]:
    """Chronological, per-trade-unit (complete lifecycle) summary for ONE exit candidate."""
    ordered = sorted(trades, key=lambda t: (t.day, t.entry_time, t.symbol))
    base = [t.net_r_base for t in ordered]
    stress = [t.net_r_stress for t in ordered]
    day_base: dict[Any, float] = {}
    for t in ordered:
        day_base[t.day] = day_base.get(t.day, 0.0) + t.net_r_base
    total = sum(base)
    top5_removed = sum(sorted(base, reverse=True)[5:]) if len(base) > 5 else None
    best_day = max(day_base.values()) if day_base else None
    years: dict[int, dict[str, Any]] = {}
    for year in sorted({t.day.year for t in ordered}):
        vals = [t.net_r_base for t in ordered if t.day.year == year]
        years[year] = {"n": len(vals), "mean_net_r": sum(vals) / len(vals)}
    return {
        "trades": len(ordered),
        "traded_days": len(day_base),
        "base": _side(base),
        "stress": _side(stress),
        "max_drawdown_r_daily": _max_drawdown(day_base),
        "net_r_after_removing_top5": top5_removed,
        "best_day_share_of_net": (best_day / total)
        if (total > 0 and best_day is not None)
        else None,
        "per_year": years,
        "path_ambiguous": sum(1 for t in ordered if t.path_ambiguous),
        "gapped_entries": sum(1 for t in ordered if t.gapped_entry),
        "basis": "signal",
        # Fills are bar-level with all-in bps costs. These spec settings exist but are NOT simulated;
        # a non-null value for any of them does not imply simulated execution realism.
        "execution_realism": "NOT_MODELLED",
        "unavailable_exit_valuation": UNAVAILABLE_EXIT_VALUATION_RULE,
        "unexecutable_exits": sum(1 for t in ordered if t.exit_unexecutable),
        # Descriptive statistics only. Any statistical choice made after viewing these numbers
        # cannot be described as preregistered confirmation of the same results.
        "inferential_status": "NON_INFERENTIAL_DESCRIPTIVE",
        "unmodelled_execution_fields": list(SCREEN_V2_UNMODELLED),
    }


@requires_capability
def summarize_portfolio(capability: object, run: PortfolioRun) -> dict[str, Any]:
    """Portfolio-basis summary. The only way to report a portfolio result: it can only be built
    from a scheduler run, so the accepted/rejected ledger always travels with the numbers and an
    unconstrained signal-level list cannot be passed off as portfolio performance (A-SCREEN 6d)."""
    if not isinstance(run, PortfolioRun):
        raise TypeError("summarize_portfolio needs a scheduler PortfolioRun, not a trade list")
    out = summarize(capability, run.accepted)
    out["basis"] = "portfolio"
    out["signal_trades"] = run.signal_trades
    out["accepted_trades"] = len(run.accepted)
    out["rejected_by_reason"] = dict(sorted(run.rejected.items()))
    return out
