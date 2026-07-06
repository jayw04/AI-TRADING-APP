"""Range Trader daily price-setting health-check (ADR 0035 — Operational Self-Healing).

Classifies the health of the range strategy's daily setup by the ADR-0035 action
levels and reports a health state (GREEN / YELLOW / ORANGE / RED). Runs in the
backend container on a timer (pre-open / post-open / intraday). READ-ONLY over
trading state — it never submits, cancels, clears a halt, or resizes anything.
The wrapper (deploy/aws/range-healthcheck.sh) performs the single Level-1
operational correction (pre-open re-arm) and SNS-alerts on any non-GREEN state.

Output (stdout): a machine header line ``STATE=<GREEN|YELLOW|ORANGE|RED>`` and
``ACTION=<none|rearm>`` followed by a human-readable report. Exit 0 always
(a health *problem* is reported in the state, not the exit code).

The KEY signal is the strategy's own published levels: post-open, every symbol in
today's universe should have a valid ``range_levels`` signal for today. A missing
or invalid one means the daily price-setting failed for that symbol.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.db.enums import StrategyStatus
from app.db.models.account import Account, AccountMode
from app.db.models.order import Order
from app.db.models.position import Position
from app.db.models.signal import Signal
from app.db.models.strategy import Strategy
from app.db.models.symbol import Symbol
from app.db.session import get_sessionmaker
from app.risk.halt import halt_reason, is_halted
from app.utils.time import EASTERN

_NON_TERMINAL = {
    "new", "accepted", "pending_new", "pending_risk", "partially_filled",
    "submitted", "held", "pending_cancel", "pending_replace", "accepted_for_bidding",
}


@dataclass
class Finding:
    level: int          # ADR-0035 action level (1-4)
    code: str
    detail: str
    recommend: str = ""


@dataclass
class Health:
    phase: str
    strategy_id: int | None = None
    strategy_name: str | None = None
    registered: bool = False       # status is PAPER/LIVE (armed)
    universe: list[str] = field(default_factory=list)
    levels_ok: list[str] = field(default_factory=list)
    levels_missing: list[str] = field(default_factory=list)
    levels_invalid: list[str] = field(default_factory=list)
    halted: bool = False
    halt_why: str = ""
    breaker_tripped: bool = False
    open_positions: list[str] = field(default_factory=list)
    stuck_orders: int = 0
    findings: list[Finding] = field(default_factory=list)


def classify(h: Health) -> tuple[str, str]:
    """Pure: map findings → (health_state, action). See ADR 0035.

    action is 'rearm' only for the safe Level-1 pre-open case; else 'none'.
    """
    findings = h.findings
    levels = [f.level for f in findings]
    action = "none"

    # Level-1 (safe operational auto-correct): pre-open, strategy not armed.
    if h.phase == "pre_open" and not h.registered and h.strategy_id is not None:
        action = "rearm"

    # RED — the range subsystem cannot trade correctly right now.
    #  - a risk halt / tripped breaker blocks the account (Level 4, human-cleared), or
    #  - post-open with NO valid levels at all (price-setting fully failed).
    red = h.halted or h.breaker_tripped or (
        h.phase in ("post_or", "intraday")
        and h.universe
        and not h.levels_ok
    )
    if red:
        return "RED", action

    # ORANGE — needs an operator. Driven by the FINDINGS, which are already phase-gated:
    # missing levels are only a finding post-open; PRE-OPEN they're expected (no opening
    # range yet), so reading the raw levels_missing here would send a spurious ORANGE at
    # 09:00 every morning. levels_invalid always produces a finding regardless of phase.
    if any(lv in (3, 4) for lv in levels):
        return "ORANGE", action

    # YELLOW — a safe auto-correction is warranted (the wrapper will perform it).
    if action == "rearm":
        return "YELLOW", action

    return "GREEN", "none"


async def gather(phase: str) -> Health:
    sf = get_sessionmaker()
    now = datetime.now(UTC)
    today_et = now.astimezone(EASTERN).date()
    h = Health(phase=phase)

    async with sf() as s:
        # The user's range strategy: an active range_trader template (fall back to any
        # active strategy that has published range_levels recently).
        strat = (
            await s.execute(
                select(Strategy)
                .where(Strategy.code_path.like("%range_trader%"))
                .order_by(Strategy.id)
            )
        ).scalars().first()
        if strat is None:
            h.findings.append(Finding(3, "no_range_strategy", "no range_trader strategy found",
                                      "check the strategy is created + applied"))
            return h
        h.strategy_id = strat.id
        h.strategy_name = strat.name
        h.registered = str(strat.status).split(".")[-1] in {
            StrategyStatus.PAPER.value, StrategyStatus.LIVE.value
        }
        if not h.registered:
            h.findings.append(Finding(
                1 if phase == "pre_open" else 3, "not_registered",
                f"strategy status is {strat.status}", "re-arm (pre-open) or investigate"))
        h.universe = [x.upper() for x in (strat.symbols_json or [])]

        # symbol id map
        sym_rows = (
            await s.execute(select(Symbol).where(Symbol.ticker.in_(h.universe)))
        ).scalars().all() if h.universe else []
        ticker_by_id = {r.id: r.ticker for r in sym_rows}

        # today's published range_levels signals per symbol
        since = now - timedelta(hours=12)
        sigs = (
            await s.execute(
                select(Signal)
                .where(Signal.strategy_id == strat.id, Signal.received_at >= since)
                .order_by(Signal.received_at.desc())
            )
        ).scalars().all()
        seen: dict[str, dict] = {}
        for sg in sigs:
            p = sg.payload_json or {}
            if p.get("kind") != "range_levels":
                continue
            tk = ticker_by_id.get(sg.symbol_id)
            if tk and tk not in seen and sg.received_at.astimezone(EASTERN).date() == today_et:
                seen[tk] = p
        for tk in h.universe:
            lv = seen.get(tk)
            if lv is None:
                h.levels_missing.append(tk)
            else:
                buy, sell, stop = lv.get("buy"), lv.get("sell"), lv.get("stop")
                if not (buy and sell and stop) or not (stop < buy < sell):
                    h.levels_invalid.append(tk)
                else:
                    h.levels_ok.append(tk)
        # Missing levels are only a problem once the opening range should have frozen.
        if phase in ("post_or", "intraday") and h.levels_missing:
            h.findings.append(Finding(
                3, "levels_missing",
                f"no published levels today for: {', '.join(h.levels_missing)}",
                "strategy likely not dispatching — investigate bar flow / re-arm off-hours "
                "(a mid-day reload would rebuild the opening range from the wrong window)"))
        if h.levels_invalid:
            h.findings.append(Finding(
                3, "levels_invalid",
                f"invalid level ordering for: {', '.join(h.levels_invalid)}",
                "expect stop < buy < sell; check the opening-range data"))

        # Risk state (Level 4 — alert only, never auto-clear).
        h.halted = await is_halted(s)
        if h.halted:
            h.halt_why = await halt_reason(s)
            h.findings.append(Finding(
                4, "global_halt", f"global trading halt set ({h.halt_why})",
                "verify account state before clearing — risk gates are never auto-cleared"))
        acct = (
            await s.execute(select(Account).where(
                Account.user_id == strat.user_id, Account.mode == AccountMode.paper))
        ).scalars().first()
        if acct is not None:
            if acct.circuit_breaker_tripped_at is not None:
                h.breaker_tripped = True
                h.findings.append(Finding(
                    4, "breaker_tripped",
                    f"account breaker tripped at {acct.circuit_breaker_tripped_at}",
                    "verify account P&L before resetting — never auto-cleared"))
            # stranded position (pre-open, intraday info) + stuck orders
            for pos in (
                await s.execute(select(Position).where(
                    Position.account_id == acct.id, Position.qty != 0))
            ).scalars().all():
                tk = ticker_by_id.get(pos.symbol_id) or str(pos.symbol_id)
                h.open_positions.append(f"{tk}x{pos.qty}")
            if phase == "pre_open" and h.open_positions:
                h.findings.append(Finding(
                    3, "stranded_position",
                    f"position held pre-open (intraday strategy should be flat): "
                    f"{', '.join(h.open_positions)}",
                    "the strategy should exit it today; if it persists, reconcile/flatten"))
            for o in (
                await s.execute(
                    select(Order)
                    .where(Order.account_id == acct.id)
                    .order_by(Order.created_at.desc())
                    .limit(100)
                )
            ).scalars().all():
                st = str(o.status).split(".")[-1].lower()
                age = (now - o.created_at.replace(tzinfo=UTC)
                       if o.created_at.tzinfo is None else now - o.created_at)
                if st in _NON_TERMINAL and age > timedelta(minutes=60):
                    h.stuck_orders += 1
            if h.stuck_orders:
                h.findings.append(Finding(
                    3, "stuck_orders", f"{h.stuck_orders} non-terminal order(s) > 60min old",
                    "run the reconcile sweep (scripts/reconcile_stuck_orders.py)"))
    return h


def render(h: Health, state: str, action: str) -> str:
    icon = {"GREEN": "🟢", "YELLOW": "🟡", "ORANGE": "🟠", "RED": "🔴"}[state]
    et = datetime.now(EASTERN).strftime("%Y-%m-%d %H:%M ET")
    lines = [
        f"STATE={state}",
        f"ACTION={action}",
        f"STRATEGY_ID={h.strategy_id if h.strategy_id is not None else ''}",
        f"{icon} Range price-setting: {state}  ({h.phase}, {et})",
        f"strategy: {h.strategy_name} (#{h.strategy_id}) · "
        f"{'armed' if h.registered else 'NOT ARMED'} · universe {len(h.universe)}",
        f"levels: {len(h.levels_ok)} ok, {len(h.levels_missing)} missing, "
        f"{len(h.levels_invalid)} invalid",
    ]
    if h.open_positions:
        lines.append(f"positions: {', '.join(h.open_positions)}")
    if not h.findings:
        lines.append("✓ no findings")
    for f in h.findings:
        lines.append(f"  [L{f.level}] {f.code}: {f.detail}" + (f"  → {f.recommend}" if f.recommend else ""))
    return "\n".join(lines)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["pre_open", "post_or", "intraday"], default="intraday")
    args = ap.parse_args()
    h = await gather(args.phase)
    state, action = classify(h)
    print(render(h, state, action))


if __name__ == "__main__":
    asyncio.run(main())
