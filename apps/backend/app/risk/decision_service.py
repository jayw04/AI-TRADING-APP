"""ADR 0042 — the single entry point for a risk-effect decision.

Steps 9 and 13 of the risk engine both call :meth:`RiskDecisionService.decide`. They do not
implement similar logic separately — implementing it twice is precisely how the gross-exposure
gate acquired the reducing-order exemption (ADR 0038) while the loss gates did not, which is
the defect ADR 0042 exists to close.

What ``decide()`` guarantees, atomically (§ D):

    per-account lock
      → live causally-complete broker snapshot (§ A; never a cache)
      → classify against reservations already held
      → if ALLOW: RESERVE the quantity
      → write the ledger row (ALLOW **and** REJECT alike)
      → commit

and, before the order is actually sent (§ A):

    verify the account version token is unchanged
      → if it moved: RELEASE the reservation, re-fetch, RE-CLASSIFY once.
        The prior decision is NEVER reused.

The exemption is source-NEUTRAL (§ C): a ``MANUAL`` reduction is classified by exactly the same
code as a ``STRATEGY`` one. ``source_type`` is recorded so that neutrality is *auditable* — not
so that it can be privileged. There is no operator-asserted risk effect.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.risk_decision import RiskDecision
from app.db.models.risk_reservation import (
    RESERVATION_HELD,
    RESERVATION_RELEASED,
    RiskReservation,
)
from app.risk.account_snapshot import fetch_snapshot
from app.risk.risk_effect import (
    AccountSnapshot,
    Decision,
    ProposedAction,
    RiskEffect,
    RiskEffectDecision,
    classify,
)

logger = structlog.get_logger(__name__)

ZERO = Decimal(0)

# Lock states recorded on every decision. The daily-loss value is a HISTORICAL trigger — a
# permitted reduction is NOT required to improve it (ADR 0042 § lock_trigger/permitted_effect).
LOCK_UNLOCKED = "UNLOCKED"
LOCK_DAILY_LOSS = "DAILY_LOSS"
LOCK_BREAKER = "BREAKER"

# One lock per account. Classification, reservation and ledger insertion must not interleave
# for the same account, or two reductions can each be approved against the same capacity.
_ACCOUNT_LOCKS: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)


class RiskDecisionService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ---------------------------------------------------------------- public
    async def decide(
        self,
        *,
        account_id: int,
        adapter: Any,
        action: ProposedAction,
        lock_state: str,
        lock_reason: str | None = None,
        daily_pnl: Decimal | None = None,
        source_type: str = "STRATEGY",
        strategy_id: int | None = None,
        strategy_version: str | None = None,
        slot_claim_id: int | None = None,
        correlation_id: str | None = None,
        supersedes_id: int | None = None,
        retry_generation: int = 0,
    ) -> tuple[RiskEffectDecision, int, int | None]:
        """Classify, reserve if allowed, and persist. Returns (decision, ledger_id, reservation_id).

        Every call writes exactly one ledger row — **including a rejection**. An order that
        never existed because a gate refused it is exactly the event you most need a record of.
        """
        corr = correlation_id or uuid.uuid4().hex

        async with _ACCOUNT_LOCKS[account_id]:
            reserved = await self._reserved_by_symbol(account_id)
            snap = await fetch_snapshot(
                session=self._session,
                account_id=account_id,
                adapter=adapter,
                reserved_reducing_qty=reserved,
            )
            result = classify(snap, action)

            reservation_id: int | None = None
            if result.is_verified_reduction and action.qty is not None:
                reservation = RiskReservation(
                    account_id=account_id,
                    symbol=action.symbol.upper(),
                    qty=action.qty,
                    state=RESERVATION_HELD,
                    created_at=datetime.now(UTC),
                )
                self._session.add(reservation)
                await self._session.flush()
                reservation_id = reservation.id

            ledger = self._to_ledger_row(
                account_id=account_id,
                action=action,
                result=result,
                snap=snap,
                lock_state=lock_state,
                lock_reason=lock_reason,
                daily_pnl=daily_pnl,
                source_type=source_type,
                strategy_id=strategy_id,
                strategy_version=strategy_version,
                slot_claim_id=slot_claim_id,
                correlation_id=corr,
                supersedes_id=supersedes_id,
                retry_generation=retry_generation,
            )
            self._session.add(ledger)
            await self._session.flush()

            if reservation_id is not None:
                res = await self._session.get(RiskReservation, reservation_id)
                if res is not None:
                    res.decision_id = ledger.id

            await self._session.commit()

            logger.info(
                "risk_decision",
                account_id=account_id,
                symbol=action.symbol,
                action=str(action.action),
                source=source_type,
                lock_state=lock_state,
                risk_effect=str(result.risk_effect),
                decision=str(result.decision),
                reasons=[str(r) for r in result.reasons],
                correlation_id=corr,
                ledger_id=ledger.id,
            )
            return result, ledger.id, reservation_id

    async def confirm_unchanged_or_reclassify(
        self,
        *,
        account_id: int,
        adapter: Any,
        action: ProposedAction,
        prior: RiskEffectDecision,
        prior_ledger_id: int,
        reservation_id: int | None,
        **decide_kwargs: Any,
    ) -> tuple[RiskEffectDecision, int, int | None]:
        """ADR 0042 § A — the pre-submission consistency check.

        If the account state moved between classification and submission, the earlier approval
        is **void**. Release its reservation, re-fetch, and re-classify **once**. The prior
        decision is never reused — an approval is a statement about a specific state, and that
        state is gone.
        """
        reserved = await self._reserved_by_symbol(account_id, exclude=reservation_id)
        fresh = await fetch_snapshot(
            session=self._session,
            account_id=account_id,
            adapter=adapter,
            reserved_reducing_qty=reserved,
        )
        if fresh.state_hash() == prior.before_state_hash:
            return prior, prior_ledger_id, reservation_id  # unchanged — the approval stands

        logger.warning(
            "risk_decision_version_conflict",
            account_id=account_id,
            symbol=action.symbol,
            detail=(
                "account state changed between classification and submission; the prior "
                "approval is void and will NOT be reused"
            ),
        )
        await self.release_reservation(reservation_id, reason="VERSION_CONFLICT")
        return await self.decide(
            account_id=account_id,
            adapter=adapter,
            action=action,
            supersedes_id=prior_ledger_id,
            retry_generation=1,
            **decide_kwargs,
        )

    async def release_reservation(self, reservation_id: int | None, *, reason: str) -> None:
        if reservation_id is None:
            return
        res = await self._session.get(RiskReservation, reservation_id)
        if res is None or res.state != RESERVATION_HELD:
            return
        res.state = RESERVATION_RELEASED
        res.released_at = datetime.now(UTC)
        res.release_reason = reason[:64]
        await self._session.commit()

    # ---------------------------------------------------------------- internals
    async def _reserved_by_symbol(
        self, account_id: int, *, exclude: int | None = None
    ) -> dict[str, Decimal]:
        """Quantities already promised to other in-flight approvals."""
        stmt = (
            select(RiskReservation.symbol, func.sum(RiskReservation.qty))
            .where(
                RiskReservation.account_id == account_id,
                RiskReservation.state == RESERVATION_HELD,
            )
            .group_by(RiskReservation.symbol)
        )
        if exclude is not None:
            stmt = stmt.where(RiskReservation.id != exclude)
        rows = (await self._session.execute(stmt)).all()
        return {sym: Decimal(str(total or 0)) for sym, total in rows}

    def _to_ledger_row(  # noqa: PLR0913 — the ledger's whole purpose is to carry every field
        self,
        *,
        account_id: int,
        action: ProposedAction,
        result: RiskEffectDecision,
        snap: AccountSnapshot,
        lock_state: str,
        lock_reason: str | None,
        daily_pnl: Decimal | None,
        source_type: str,
        strategy_id: int | None,
        strategy_version: str | None,
        slot_claim_id: int | None,
        correlation_id: str,
        supersedes_id: int | None,
        retry_generation: int,
    ) -> RiskDecision:
        return RiskDecision(
            account_id=account_id,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            slot_claim_id=slot_claim_id,
            source_type=source_type,
            action_type=str(action.action),
            symbol=action.symbol.upper(),
            side=str(action.side) if action.side else None,
            qty=action.qty,
            lock_state=lock_state,
            lock_reason=lock_reason,
            daily_pnl=daily_pnl,
            risk_policy_version=result.policy_version,
            before_state_hash=result.before_state_hash,
            projected_after_state_hash=result.projected_after_state_hash,
            broker_cursor=snap.broker_cursor,
            position_qty_before=result.position_qty_before,
            position_qty_after=result.position_qty_after,
            gross_exposure_before=result.gross_exposure_before,
            gross_exposure_after=result.gross_exposure_after,
            available_reducible_qty=result.available_reducible_qty,
            risk_effect=str(result.risk_effect),
            decision=str(result.decision),
            reason_codes=json.dumps([str(r) for r in result.reasons]),
            decided_at=datetime.now(UTC),
            correlation_id=correlation_id,
            supersedes_id=supersedes_id,
            retry_generation=retry_generation,
        )


def permits_while_locked(result: RiskEffectDecision) -> bool:
    """The locked-mode matrix, in one place (ADR 0042).

        REDUCING       ALLOW  (subject to all absolute post-trade hard limits)
        INCREASING     REJECT
        NEUTRAL        REJECT while locked, unless separately registered
        INDETERMINATE  FAIL_CLOSED
    """
    return (
        result.risk_effect is RiskEffect.RISK_REDUCING
        and result.decision is Decision.ALLOW
    )
