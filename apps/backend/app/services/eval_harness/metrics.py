"""The six ADR-0006-v2 comparison metrics (P6b §4).

Three EQUITY deltas (win-rate / Sharpe / max-drawdown, B − A) reuse the §1a/§2b
round-trip + equity-curve reconstruction over each mode's ``source_id`` (the
live-verified path). Three DECISION metrics come from the paired decision rows:
- agreement rate: Mode A always acts, so agreement == B's act rate.
- disagreement asymmetry: among the signals B skipped, was B right to skip
  (A's order lost) more often than wrong (A's order won)? Signed; + favors B.
- worst single-decision divergence: the largest |A outcome| among B's skips
  (B's outcome is 0 — it didn't trade) — the worst call the LLM gate made.

Outcomes are DERIVED on demand (no real-time fill hook): a focused FIFO walk
attributes each round-trip's realized PnL to the entry order that opened it.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import OrderSide, OrderSourceType
from app.db.models.eval_harness import EvalHarness, EvalHarnessDecision
from app.db.models.fill import Fill
from app.db.models.order import Order
from app.db.models.symbol import Symbol
from app.services.drift_detection import reconstruct_round_trips
from app.services.equity_curve import DEFAULT_CAPITAL_BASE, reconstruct_equity_curve
from app.strategies.metrics import max_drawdown, sharpe_ratio, win_rate


@dataclass(frozen=True)
class SideMetrics:
    trade_count: int
    win_rate: float
    sharpe_ratio: float
    max_drawdown: float


@dataclass(frozen=True)
class EvalHarnessComparison:
    window_start: datetime
    window_end: datetime
    mode_a: SideMetrics
    mode_b: SideMetrics
    # B − A deltas (ADR §51-53).
    win_rate_delta: float
    sharpe_delta: float
    max_drawdown_delta: float
    # Decision metrics (ADR §54-56).
    total_decisions: int
    decision_agreement_rate: float
    disagreement_asymmetry: float
    worst_single_divergence: float


async def _order_realized_pnl(
    session: AsyncSession, strategy_id: int, cutoff: datetime
) -> dict[int, float]:
    """FIFO-attribute each round-trip's realized PnL to the ENTRY order that
    opened it → {entry_order_id: total_realized_pnl}. (A focused variant of
    §1a's reconstruct_round_trips that also tracks order ids.)"""
    rows = (
        await session.execute(
            select(
                Fill.qty, Fill.price, Fill.commission, Order.id, Order.side, Symbol.ticker
            )
            .join(Order, Fill.order_id == Order.id)
            .join(Symbol, Order.symbol_id == Symbol.id)
            .where(Order.source_type == OrderSourceType.STRATEGY)
            .where(Order.source_id == str(strategy_id))
            .where(Fill.filled_at >= cutoff)
            .order_by(Fill.filled_at.asc())
        )
    ).all()

    open_legs: dict[str, list[dict[str, Any]]] = {}
    pnl_by_order: dict[int, float] = {}

    for qty_d, price_d, comm_d, order_id, side, ticker in rows:
        qty = float(qty_d)
        price = float(price_d)
        comm_ps = (float(comm_d) / qty) if qty else 0.0
        queue = open_legs.setdefault(ticker, [])
        open_dir = queue[0]["direction"] if queue else None
        is_buy = side == OrderSide.BUY

        if open_dir is None:
            queue.append({"direction": "long" if is_buy else "short", "qty": qty,
                          "price": price, "comm_ps": comm_ps, "order_id": order_id})
            continue
        scale_in = (open_dir == "long" and is_buy) or (open_dir == "short" and not is_buy)
        if scale_in:
            queue.append({"direction": open_dir, "qty": qty, "price": price,
                          "comm_ps": comm_ps, "order_id": order_id})
            continue

        remaining = qty
        while remaining > 0 and queue:
            entry = queue[0]
            matched = min(entry["qty"], remaining)
            sign = 1.0 if entry["direction"] == "long" else -1.0
            gross = sign * (price - entry["price"]) * matched
            commission = matched * (entry["comm_ps"] + comm_ps)
            pnl = gross - commission
            pnl_by_order[entry["order_id"]] = pnl_by_order.get(entry["order_id"], 0.0) + pnl
            entry["qty"] -= matched
            remaining -= matched
            if entry["qty"] <= 0:
                queue.pop(0)
    return pnl_by_order


async def _side_metrics(
    session: AsyncSession, strategy_id: int, start: datetime, end: datetime,
    bar_cache: Any,
) -> SideMetrics:
    trips = await reconstruct_round_trips(session, strategy_id, start)
    curve = await reconstruct_equity_curve(
        session, strategy_id, start, end, DEFAULT_CAPITAL_BASE, bar_cache=bar_cache
    )
    ec = [(t, float(e)) for t, e in curve]
    return SideMetrics(
        trade_count=len(trips),
        win_rate=win_rate([t.pnl for t in trips]),
        sharpe_ratio=sharpe_ratio(ec),
        max_drawdown=max_drawdown(ec),
    )


async def compute_eval_harness_comparison(
    session: AsyncSession, harness: EvalHarness, bar_cache: Any = None
) -> EvalHarnessComparison:
    start = harness.started_at
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    end = datetime.now(UTC)

    a = await _side_metrics(session, harness.mode_a_strategy_id, start, end, bar_cache)
    b = await _side_metrics(session, harness.mode_b_strategy_id, start, end, bar_cache)

    decisions = (
        await session.execute(
            select(EvalHarnessDecision).where(
                EvalHarnessDecision.harness_id == harness.id
            )
        )
    ).scalars().all()
    total = len(decisions)
    agree = sum(1 for d in decisions if d.mode_a_decision == d.mode_b_decision)
    agreement_rate = (agree / total) if total else 0.0

    # Disagreements: A acts, B skips. Was B right (A's order lost) or wrong (won)?
    a_outcomes = await _order_realized_pnl(session, harness.mode_a_strategy_id, start)
    skips = [d for d in decisions if d.mode_b_decision == "skip"]
    b_right = b_wrong = 0
    worst_div = 0.0
    for d in skips:
        out = a_outcomes.get(d.mode_a_order_id) if d.mode_a_order_id is not None else None
        if out is None:
            continue
        if out < 0:
            b_right += 1   # B skipped a loser
        elif out > 0:
            b_wrong += 1   # B skipped a winner
        worst_div = max(worst_div, abs(out))
    scored = b_right + b_wrong
    asymmetry = ((b_right - b_wrong) / scored) if scored else 0.0

    return EvalHarnessComparison(
        window_start=start,
        window_end=end,
        mode_a=a,
        mode_b=b,
        win_rate_delta=b.win_rate - a.win_rate,
        sharpe_delta=b.sharpe_ratio - a.sharpe_ratio,
        max_drawdown_delta=b.max_drawdown - a.max_drawdown,
        total_decisions=total,
        decision_agreement_rate=agreement_rate,
        disagreement_asymmetry=asymmetry,
        worst_single_divergence=worst_div,
    )


def comparison_to_dict(c: EvalHarnessComparison) -> dict[str, Any]:
    def _side(m: SideMetrics) -> dict[str, Any]:
        return {
            "trade_count": m.trade_count, "win_rate": m.win_rate,
            "sharpe_ratio": m.sharpe_ratio, "max_drawdown": m.max_drawdown,
        }

    return {
        "window_start": c.window_start.isoformat(),
        "window_end": c.window_end.isoformat(),
        "mode_a": _side(c.mode_a),
        "mode_b": _side(c.mode_b),
        "deltas": {
            "win_rate_delta": c.win_rate_delta,
            "sharpe_delta": c.sharpe_delta,
            "max_drawdown_delta": c.max_drawdown_delta,
        },
        "decision_metrics": {
            "total_decisions": c.total_decisions,
            "decision_agreement_rate": c.decision_agreement_rate,
            "disagreement_asymmetry": c.disagreement_asymmetry,
            "worst_single_divergence": c.worst_single_divergence,
        },
    }
