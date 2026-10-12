"""Chronological portfolio scheduler (portfolio-constrained basis, D18).

Takes the signal-level trades of ONE exit candidate and applies concurrency, capital, per-name,
gross-exposure and daily-loss constraints in time order, so the portfolio result never benefits
from hindsight (R12): a trade is accepted or rejected using only what was open and realised at
its entry minute. Ties at the same minute are broken by symbol ascending, a return-independent
rule. Capital from an exit is released only strictly AFTER the exit minute.

Every limit is an explicit argument; ``limits_from_draft`` reads them from the spec and fails
closed naming each null risk field, because the screen profile leaves those fields exempt and
they become required exactly when this scheduler is used.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from app.research.range002.governance.results_guard import requires_capability
from app.research.range002.screen.errors import ParamsUnsetError, SpecBindingError
from app.research.range002.screen.types import Trade
from app.research.range002.spec.loader import spec_sha256
from app.research.range002.spec.schema import DraftSpec

REJECT_CONCURRENCY = "MAX_CONCURRENT"
REJECT_GROSS = "GROSS_CAP"
REJECT_NAME = "PER_NAME_CAP"
REJECT_DAILY_LOSS = "DAILY_LOSS_LIMIT"
REJECT_QTY = "QTY_ZERO"
REJECT_SAME_NAME = "NAME_ALREADY_OPEN"


@dataclass(frozen=True)
class PortfolioLimits:
    equity: float
    max_concurrent: int
    gross_cap: float  # fraction of equity, total open notional
    per_name_cap: float  # fraction of equity, one position's notional
    daily_loss_limit_r: float  # stop new entries once realised daily net R <= -limit


@dataclass(frozen=True)
class PortfolioRun:
    accepted: tuple[Trade, ...]
    rejected: dict[str, int]
    signal_trades: int


@requires_capability
def limits_from_draft(capability: object, draft: DraftSpec, equity: float) -> PortfolioLimits:
    if spec_sha256(draft) != getattr(capability, "spec_sha256", None):
        raise SpecBindingError("draft spec hash differs from the capability's spec hash")
    r = draft.risk
    missing = [
        f"risk.{name}"
        for name in ("max_concurrent", "gross_cap", "per_name_cap", "daily_loss_limit")
        if getattr(r, name) is None
    ]
    if missing:
        raise ParamsUnsetError("portfolio scheduler needs: " + ", ".join(missing))
    assert r.max_concurrent is not None and r.gross_cap is not None
    assert r.per_name_cap is not None and r.daily_loss_limit is not None
    return PortfolioLimits(
        equity=equity,
        max_concurrent=int(r.max_concurrent),
        gross_cap=float(r.gross_cap),
        per_name_cap=float(r.per_name_cap),
        daily_loss_limit_r=float(r.daily_loss_limit),
    )


def _schedule_day(
    trades: list[Trade], limits: PortfolioLimits, rejected: dict[str, int]
) -> list[Trade]:
    ordered = sorted(trades, key=lambda t: (t.entry_time, t.symbol))
    open_pos: list[tuple[Trade, float]] = []  # (trade, notional)
    realised_r = 0.0
    out: list[Trade] = []
    for t in ordered:
        still: list[tuple[Trade, float]] = []
        for pos, notional in open_pos:
            if pos.exit_time < t.entry_time:
                realised_r += pos.net_r_base
            else:
                still.append((pos, notional))
        open_pos = still
        notional_new = t.qty * t.entry_price
        reason: str | None = None
        if t.qty <= 0:
            reason = REJECT_QTY
        elif realised_r <= -limits.daily_loss_limit_r:
            reason = REJECT_DAILY_LOSS
        elif any(p.symbol == t.symbol for p, _ in open_pos):
            reason = REJECT_SAME_NAME
        elif len(open_pos) >= limits.max_concurrent:
            reason = REJECT_CONCURRENCY
        elif notional_new > limits.per_name_cap * limits.equity:
            reason = REJECT_NAME
        elif sum(n for _, n in open_pos) + notional_new > limits.gross_cap * limits.equity:
            reason = REJECT_GROSS
        if reason is not None:
            rejected[reason] = rejected.get(reason, 0) + 1
            continue
        open_pos.append((t, notional_new))
        out.append(t)
    return out


@requires_capability
def schedule_portfolio(
    capability: object, trades: Sequence[Trade], limits: PortfolioLimits
) -> PortfolioRun:
    by_day: dict[date, list[Trade]] = {}
    for t in trades:
        by_day.setdefault(t.day, []).append(t)
    rejected: dict[str, int] = {}
    accepted: list[Trade] = []
    for day in sorted(by_day):
        accepted.extend(_schedule_day(by_day[day], limits, rejected))
    return PortfolioRun(tuple(accepted), rejected, len(trades))
