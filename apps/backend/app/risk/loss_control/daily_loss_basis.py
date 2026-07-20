"""ADR 0043 §D3 — select the daily-loss basis, with explicit provenance.

The daily-loss control measures today's loss from a start-of-session baseline. Historically that
baseline is the broker's ``last_equity`` (prior close), which drifts under restart — the
spurious-trip class. §D3 replaces it with the immutable persisted **session baseline**.

This module is the single source-selection point. Given the reconciled equity and the authoritative
ET session date, it returns the day-change AND the exact ``basis_source`` used, so enforcement is
verifiable. The three sources, in strict precedence:

  1. SESSION_BASELINE           — a valid ACTIVE baseline for THIS account + THIS session date.
  2. LEGACY_LAST_EQUITY         — the compatibility fallback (``equity − last_equity``).
  3. LEGACY_CUMULATIVE_FALLBACK — only where the caller already sanctions it (``realized + unrealized``).

They are NOT equivalent, so every result carries a ``basis_source`` and, when the session baseline
was NOT used, a SPECIFIC ``fallback_reason`` — never a generic "fallback". A baseline from another
session is never used, and a zero/negative baseline equity fails validation rather than producing a
distorted day-change. When the session date can't be authoritatively established this never guesses
a date — it falls back.

This module makes NO decision and mutates nothing. It is consulted only when the enforcement flag is
on; with the flag off the caller uses its existing legacy path unchanged (byte-for-byte).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.risk_session_baseline import BASELINE_STATUS_ACTIVE, RiskSessionBaseline
from app.db.models.risk_session_baseline_shadow_outcome import (
    RiskSessionBaselineShadowOutcome,
)
from app.risk.loss_control.session_baseline import (
    SHADOW_INDETERMINATE,
    SHADOW_MISSING_AFTER_ACTIVITY,
)

# --- basis sources (which measure produced the day-change) ------------------------------------
BASIS_SESSION_BASELINE = "SESSION_BASELINE"
BASIS_LEGACY_LAST_EQUITY = "LEGACY_LAST_EQUITY"
BASIS_LEGACY_CUMULATIVE_FALLBACK = "LEGACY_CUMULATIVE_FALLBACK"

# --- fallback reasons (why the session baseline was NOT used; never collapsed to one) ----------
FALLBACK_NO_BASELINE_CAPTURED = "NO_BASELINE_CAPTURED"  # no baseline + no capture outcome for today
FALLBACK_MISSING_AFTER_ACTIVITY = "MISSING_AFTER_ACTIVITY"  # shadow refused: activity before capture
FALLBACK_CAPTURE_INDETERMINATE = "CAPTURE_INDETERMINATE"  # shadow refused: unverifiable
FALLBACK_BASELINE_INVALID = "BASELINE_INVALID"  # today's baseline non-ACTIVE or equity <= 0
FALLBACK_BASELINE_SESSION_MISMATCH = "BASELINE_SESSION_MISMATCH"  # only prior-session baselines exist


@dataclass(frozen=True)
class DailyLossBasis:
    """The selected daily-loss basis + full provenance for evidence."""

    day_change: Decimal | None  # None only when no basis could be computed at all
    basis_source: str | None
    fallback_reason: str | None  # set iff the session baseline was not used
    market_session_date: str | None
    current_equity: Decimal | None
    baseline_id: int | None = None
    baseline_equity: Decimal | None = None
    applicable_limit: Decimal | None = None

    def provenance(self) -> dict[str, str | None]:
        """A flat, string-valued dict for structured evidence / audit payloads."""

        def s(v: object) -> str | None:
            return str(v) if v is not None else None

        return {
            "basis_source": self.basis_source,
            "fallback_reason": self.fallback_reason,
            "market_session_date": self.market_session_date,
            "baseline_id": s(self.baseline_id),
            "baseline_equity": s(self.baseline_equity),
            "current_equity": s(self.current_equity),
            "day_change": s(self.day_change),
            "applicable_limit": s(self.applicable_limit),
        }


async def _load_today_baseline(
    session: AsyncSession, account_id: int, session_date: str
) -> RiskSessionBaseline | None:
    return await session.scalar(
        select(RiskSessionBaseline).where(
            RiskSessionBaseline.account_id == account_id,
            RiskSessionBaseline.market_session_date == session_date,
        )
    )


async def _fallback_reason_for_absent_baseline(
    session: AsyncSession, account_id: int, session_date: str
) -> str:
    """The SPECIFIC reason there is no usable baseline for today — never a generic 'fallback'."""
    outcome = await session.scalar(
        select(RiskSessionBaselineShadowOutcome.outcome).where(
            RiskSessionBaselineShadowOutcome.account_id == account_id,
            RiskSessionBaselineShadowOutcome.market_session_date == session_date,
        )
    )
    if outcome == SHADOW_MISSING_AFTER_ACTIVITY:
        return FALLBACK_MISSING_AFTER_ACTIVITY
    if outcome == SHADOW_INDETERMINATE:
        return FALLBACK_CAPTURE_INDETERMINATE
    # No usable outcome for today. Does this account have a baseline for some OTHER session?
    other = await session.scalar(
        select(RiskSessionBaseline.id).where(
            RiskSessionBaseline.account_id == account_id,
            RiskSessionBaseline.market_session_date != session_date,
        )
    )
    if other is not None:
        return FALLBACK_BASELINE_SESSION_MISMATCH
    return FALLBACK_NO_BASELINE_CAPTURED


def _legacy_basis(
    *,
    current_equity: Decimal | None,
    last_equity: Decimal | None,
    realized: Decimal,
    unrealized: Decimal,
    allow_cumulative_fallback: bool,
    session_date: str | None,
    applicable_limit: Decimal | None,
    fallback_reason: str | None,
) -> DailyLossBasis:
    """Compute the legacy day-change (the same measures today's engine uses), tagged with source."""
    if current_equity is not None and last_equity is not None and last_equity > 0:
        return DailyLossBasis(
            day_change=current_equity - last_equity,
            basis_source=BASIS_LEGACY_LAST_EQUITY,
            fallback_reason=fallback_reason,
            market_session_date=session_date,
            current_equity=current_equity,
            applicable_limit=applicable_limit,
        )
    if allow_cumulative_fallback:
        return DailyLossBasis(
            day_change=realized + unrealized,
            basis_source=BASIS_LEGACY_CUMULATIVE_FALLBACK,
            fallback_reason=fallback_reason,
            market_session_date=session_date,
            current_equity=current_equity,
            applicable_limit=applicable_limit,
        )
    # No usable legacy basis (e.g. engine step 9 with no last_equity and no cumulative sanctioned).
    return DailyLossBasis(
        day_change=None,
        basis_source=None,
        fallback_reason=fallback_reason,
        market_session_date=session_date,
        current_equity=current_equity,
        applicable_limit=applicable_limit,
    )


async def select_daily_loss_basis(
    session: AsyncSession,
    account_id: int,
    *,
    current_equity: Decimal | None,
    last_equity: Decimal | None,
    realized: Decimal = Decimal(0),
    unrealized: Decimal = Decimal(0),
    session_date: str | None,
    applicable_limit: Decimal | None,
    allow_cumulative_fallback: bool,
) -> DailyLossBasis:
    """Select the daily-loss basis for one account (call only when enforcement is ON).

    Prefers the valid ACTIVE session baseline for (account_id, session_date); otherwise returns the
    legacy basis tagged with the SPECIFIC fallback reason. Filters strictly by account_id and
    session_date, so it can neither cross account boundaries nor use another session's baseline. A
    missing session date is never guessed — it falls back.
    """
    # No authoritative session date → do NOT guess one; fall back to legacy.
    if session_date is None:
        return _legacy_basis(
            current_equity=current_equity, last_equity=last_equity, realized=realized,
            unrealized=unrealized, allow_cumulative_fallback=allow_cumulative_fallback,
            session_date=None, applicable_limit=applicable_limit,
            fallback_reason=FALLBACK_NO_BASELINE_CAPTURED,
        )

    baseline = await _load_today_baseline(session, account_id, session_date)
    if baseline is not None:
        if baseline.status == BASELINE_STATUS_ACTIVE and baseline.baseline_equity > 0:
            # THE ENFORCED BASIS: today's loss measured from the immutable session baseline.
            return DailyLossBasis(
                day_change=(current_equity - baseline.baseline_equity)
                if current_equity is not None
                else None,
                basis_source=BASIS_SESSION_BASELINE,
                fallback_reason=None,
                market_session_date=session_date,
                current_equity=current_equity,
                baseline_id=baseline.id,
                baseline_equity=baseline.baseline_equity,
                applicable_limit=applicable_limit,
            )
        # A baseline exists but is unusable (non-ACTIVE, or zero/negative equity → distorted).
        fallback_reason = FALLBACK_BASELINE_INVALID
    else:
        fallback_reason = await _fallback_reason_for_absent_baseline(
            session, account_id, session_date
        )

    return _legacy_basis(
        current_equity=current_equity, last_equity=last_equity, realized=realized,
        unrealized=unrealized, allow_cumulative_fallback=allow_cumulative_fallback,
        session_date=session_date, applicable_limit=applicable_limit,
        fallback_reason=fallback_reason,
    )
