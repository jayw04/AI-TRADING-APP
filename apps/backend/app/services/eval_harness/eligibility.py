"""Opt-in eligibility double-floor (P6b §4, ADR 0006 v2 §64-68).

Read-only — §4 computes it; §5's opt-in dialog consumes it. Eligible iff:
- ≥50 Mode-B trades executed (round-trips), AND
- ≥30 calendar days since the harness started, AND
- the harness is still ACTIVE — the "not deactivated/modified during the window"
  floor is enforced upstream by the invalidation hooks (a parent param tweak or
  leaving LIVE terminates the harness, so a non-ACTIVE state already means the
  clock reset).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.eval_harness import HARNESS_ACTIVE, EvalHarness
from app.services.drift_detection import reconstruct_round_trips

EVAL_MIN_TRADES = 50
EVAL_MIN_DAYS = 30


@dataclass(frozen=True)
class EligibilityVerdict:
    eligible: bool
    b_trade_count: int
    window_days: int
    min_trades: int
    min_days: int
    harness_active: bool
    reasons: list[str]


async def check_eligibility(
    session: AsyncSession, harness: EvalHarness
) -> EligibilityVerdict:
    start = harness.started_at
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    window_days = (datetime.now(UTC) - start).days

    b_trips = await reconstruct_round_trips(session, harness.mode_b_strategy_id, start)
    b_trade_count = len(b_trips)
    active = harness.state == HARNESS_ACTIVE

    reasons: list[str] = []
    if not active:
        reasons.append("harness_not_active")
    if b_trade_count < EVAL_MIN_TRADES:
        reasons.append("insufficient_trades")
    if window_days < EVAL_MIN_DAYS:
        reasons.append("insufficient_window")

    return EligibilityVerdict(
        eligible=(
            active and b_trade_count >= EVAL_MIN_TRADES and window_days >= EVAL_MIN_DAYS
        ),
        b_trade_count=b_trade_count,
        window_days=window_days,
        min_trades=EVAL_MIN_TRADES,
        min_days=EVAL_MIN_DAYS,
        harness_active=active,
        reasons=reasons,
    )


def verdict_to_dict(v: EligibilityVerdict) -> dict[str, object]:
    return {
        "eligible": v.eligible,
        "b_trade_count": v.b_trade_count,
        "window_days": v.window_days,
        "min_trades": v.min_trades,
        "min_days": v.min_days,
        "harness_active": v.harness_active,
        "reasons": v.reasons,
    }
