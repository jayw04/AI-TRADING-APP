"""ADR 0042 — the single entry point for a risk-effect decision.

Steps 9 and 13 of the risk engine both call :meth:`RiskDecisionService.decide`. They do not
implement similar logic separately — implementing it twice is precisely how the gross-exposure
gate acquired the reducing-order exemption (ADR 0038) while the loss gates did not, which is
the defect ADR 0042 exists to close.

What ``decide()`` guarantees, atomically (§ D):

    live causally-complete broker snapshot (§ A; never a cache)
      → refresh the DURABLE capacity row for (account, symbol)
      → classify
      → if a verified reduction: CLAIM the quantity with an atomic conditional UPDATE
          (compare-and-swap in the DATABASE — see app.db.models.risk_capacity_state)
      → write the ledger row (ALLOW **and** REJECT alike), bound to the capacity version
      → commit

⚠ THE AUTHORITY IS THE DATABASE, NOT A LOCK. The original implementation guarded this with a
per-account ``asyncio.Lock``, which is process-local. On 2026-07-14 two independent Python
processes each read ``reserved = 0`` and each received ALLOW for the same 183 shares; only the
broker stopped the second order. The broker is not a safety mechanism. The lock survives here
purely as a contention optimisation — correctness may not depend on it, and does not.

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
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.enums import TERMINAL_ORDER_STATUSES
from app.db.models.fill import Fill
from app.db.models.order import Order
from app.db.models.risk_capacity_state import RiskCapacityState
from app.db.models.risk_decision import RiskDecision
from app.db.models.risk_reservation import (
    RESERVATION_CONSUMED,
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
    RiskEffectReason,
    claimable_reducible_quantity,
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
        symbol = action.symbol.upper()

        # The lock is a CONTENTION OPTIMISATION ONLY. It removes needless database round-trips
        # between coroutines in this process. It is not the safety control, and nothing below
        # depends on holding it — the conditional UPDATE is what enforces the invariant.
        async with _ACCOUNT_LOCKS[account_id]:
            reserved = await self._reserved_by_symbol(account_id)
            reserved_filled = await self._reserved_filled_by_symbol(account_id)
            snap = await fetch_snapshot(
                session=self._session,
                account_id=account_id,
                adapter=adapter,
                reserved_reducing_qty=reserved,
                reserved_filled_qty=reserved_filled,
            )
            result = classify(snap, action)

            reservation_id: int | None = None
            capacity_version: int | None = None

            if result.is_verified_reduction and action.qty is not None:
                # § D — DURABLE, CROSS-PROCESS CAPACITY CLAIM.
                #
                # The refresh below is this transaction's first WRITE, so SQLite takes the write
                # lock here and holds it through the claim, the inserts and the commit. Any other
                # writer — another coroutine, another process, another worker — blocks until we
                # commit and then sees our claim. The claim's guard lives in the WHERE clause, so
                # the decision is a compare-and-swap rather than a read-then-write.
                await self._refresh_capacity(account_id, symbol, snap)
                claimed = await self._claim_capacity(
                    account_id, symbol, action.qty, snap.state_hash()
                )
                if claimed is None:
                    # Zero rows updated: the capacity was consumed by someone else, or the
                    # snapshot moved under us. It CANNOT become an ALLOW.
                    result = self._deny_for_capacity(result, account_id, symbol, corr)
                else:
                    capacity_version = claimed
                    reservation = RiskReservation(
                        account_id=account_id,
                        symbol=symbol,
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
                capacity_state_version=capacity_version,
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
        reserved_filled = await self._reserved_filled_by_symbol(
            account_id, exclude=reservation_id
        )
        fresh = await fetch_snapshot(
            session=self._session,
            account_id=account_id,
            adapter=adapter,
            reserved_reducing_qty=reserved,
            reserved_filled_qty=reserved_filled,
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
        # Return the capacity in the SAME transaction as the state change. If these could
        # diverge, a released reservation would keep consuming capacity forever and the account
        # would slowly lose the ability to de-risk — the exact failure ADR 0042 exists to prevent.
        await self._return_capacity(res.account_id, res.symbol, Decimal(str(res.qty)))
        await self._session.commit()

    async def settle_reservation_for_order(
        self, order_id: int, *, filled: bool, reason: str
    ) -> bool:
        """Settle the HELD reservation an order was reserved against, when that order reaches
        a terminal state.

        A HELD reservation consumes reducible capacity between the moment a reduction is
        APPROVED and the moment its order is FILLED (so two concurrent sells cannot each promise
        the same shares). Once the order is terminal the reservation must stop consuming capacity
        — otherwise it leaks HELD forever and the account slowly loses the ability to de-risk,
        the exact failure ADR 0042 exists to prevent (and the one the 2026-07-15 canary caught).

        FILLED  → CONSUMED (the reduction is now real in the position).
        CANCELED/REJECTED/EXPIRED → RELEASED (the reduction did not happen).

        Either way the capacity is returned in the SAME transaction as the state change.
        No-op (returns False) if the order has no HELD reservation.
        """
        res = (
            await self._session.execute(
                select(RiskReservation).where(
                    RiskReservation.order_id == order_id,
                    RiskReservation.state == RESERVATION_HELD,
                )
            )
        ).scalars().first()
        if res is None:
            return False
        res.state = RESERVATION_CONSUMED if filled else RESERVATION_RELEASED
        res.released_at = datetime.now(UTC)
        res.release_reason = reason[:64]
        await self._return_capacity(res.account_id, res.symbol, Decimal(str(res.qty)))
        await self._session.commit()
        return True

    async def reap_orphaned_reservations(self, *, older_than_seconds: int = 300) -> int:
        """Release HELD reservations that no live order justifies — the safety net for a missed
        event-driven settle (e.g. a process killed between ALLOW and the order reaching terminal,
        which is exactly how acct 3 accumulated the leak on 2026-07-14).

        A HELD reservation is orphaned when:
          * its order is terminal (a fill/cancel/reject we failed to settle at the time); or
          * its order row is gone; or
          * it was never linked to an order and is older than ``older_than_seconds`` (the
            approval committed but the order was never created — the grace window avoids racing
            an order still mid-creation).

        Returns the number released.
        """
        cutoff = datetime.now(UTC) - timedelta(seconds=older_than_seconds)
        held = (
            await self._session.execute(
                select(RiskReservation).where(RiskReservation.state == RESERVATION_HELD)
            )
        ).scalars().all()
        reaped = 0
        for res in held:
            reason: str | None = None
            if res.order_id is None:
                created = res.created_at
                if created.tzinfo is None:
                    created = created.replace(tzinfo=UTC)
                if created < cutoff:
                    reason = "REAP_NO_ORDER"
            else:
                order = await self._session.get(Order, res.order_id)
                if order is None:
                    reason = "REAP_ORDER_MISSING"
                elif order.status in TERMINAL_ORDER_STATUSES:
                    reason = "REAP_ORDER_TERMINAL"
            if reason is None:
                continue
            res.state = RESERVATION_RELEASED
            res.released_at = datetime.now(UTC)
            res.release_reason = reason
            await self._return_capacity(res.account_id, res.symbol, Decimal(str(res.qty)))
            reaped += 1
        if reaped:
            await self._session.commit()
        return reaped

    # ------------------------------------------------- § D durable capacity claim
    async def _refresh_capacity(
        self, account_id: int, symbol: str, snap: AccountSnapshot
    ) -> None:
        """Point the capacity row at the CURRENT broker snapshot.

        ⚠ This updates ``reducible_capacity_qty`` and ``snapshot_version`` ONLY. It must never
        touch ``reserved_qty``. Recomputing the accumulator here — say from ``SUM(HELD)`` — would
        let two processes each reset it to zero before the other commits, which is precisely the
        race the capacity row exists to close. The accumulator moves only on claim and release.
        """
        # The CLAIMABLE basis, not the AVAILABLE one. `_claim_capacity` guards with
        # `reserved_qty + qty <= reducible_capacity_qty`, so the accumulator already carries every
        # HELD reservation on the left. Storing the reservation-net figure here subtracted them a
        # second time, so the second legitimate trim against a long was refused with
        # EXCEEDS_REDUCIBLE_CAPACITY — a risk gate blocking de-risking, the ADR 0042 failure mode.
        capacity = claimable_reducible_quantity(snap, symbol)
        version = snap.state_hash()
        now = datetime.now(UTC)

        # `Session.execute` is statically typed as returning `Result`, but a DML statement yields
        # a `CursorResult` at runtime — and `rowcount` is the entire point here.
        stmt = (
            update(RiskCapacityState)
            .where(
                RiskCapacityState.account_id == account_id,
                RiskCapacityState.symbol == symbol,
            )
            .values(
                reducible_capacity_qty=capacity,
                snapshot_version=version,
                updated_at=now,
            )
        )
        updated = cast("CursorResult[Any]", await self._session.execute(stmt))
        if updated.rowcount == 0:
            self._session.add(
                RiskCapacityState(
                    account_id=account_id,
                    symbol=symbol,
                    snapshot_version=version,
                    reducible_capacity_qty=capacity,
                    reserved_qty=ZERO,
                    state_version=0,
                    updated_at=now,
                )
            )
            await self._session.flush()

    async def _claim_capacity(
        self, account_id: int, symbol: str, qty: Decimal, expected_version: str
    ) -> int | None:
        """The atomic conditional claim. Returns the new capacity version, or None if refused.

        The guard is entirely in the WHERE clause, so this is a compare-and-swap: the database
        decides, and it decides once. Exactly one row updated == the capacity is ours. Zero rows
        == someone else took it, or the snapshot moved. There is no third outcome, and no reading
        beforehand can turn a refusal into an approval.
        """
        stmt = (
            update(RiskCapacityState)
            .where(
                RiskCapacityState.account_id == account_id,
                RiskCapacityState.symbol == symbol,
                RiskCapacityState.snapshot_version == expected_version,
                # THE GUARD. It lives in the WHERE clause, not in Python — that is what makes this
                # a compare-and-swap the database adjudicates, rather than a read-then-write two
                # processes can both win.
                RiskCapacityState.reserved_qty + qty <= RiskCapacityState.reducible_capacity_qty,
            )
            .values(
                reserved_qty=RiskCapacityState.reserved_qty + qty,
                state_version=RiskCapacityState.state_version + 1,
                updated_at=datetime.now(UTC),
            )
        )
        res = cast("CursorResult[Any]", await self._session.execute(stmt))
        if res.rowcount != 1:
            return None
        row = await self._session.scalar(
            select(RiskCapacityState).where(
                RiskCapacityState.account_id == account_id,
                RiskCapacityState.symbol == symbol,
            )
        )
        return int(row.state_version) if row is not None else None

    async def _return_capacity(self, account_id: int, symbol: str, qty: Decimal) -> None:
        """Give capacity back. The accumulator's only other legal movement."""
        await self._session.execute(
            update(RiskCapacityState)
            .where(
                RiskCapacityState.account_id == account_id,
                RiskCapacityState.symbol == symbol,
            )
            .values(
                reserved_qty=func.max(RiskCapacityState.reserved_qty - qty, ZERO),
                state_version=RiskCapacityState.state_version + 1,
                updated_at=datetime.now(UTC),
            )
        )

    def _deny_for_capacity(
        self, result: RiskEffectDecision, account_id: int, symbol: str, corr: str
    ) -> RiskEffectDecision:
        """A refused claim is a DETERMINATE rejection, not a fail-closed.

        The account state is known; the capacity simply is not there, because a concurrent
        decision already took it. A sell beyond available reducible capacity would cross zero,
        which is a risk-INCREASING action, so it is rejected on its merits.
        """
        logger.warning(
            "risk_capacity_claim_refused",
            account_id=account_id,
            symbol=symbol,
            correlation_id=corr,
            detail=(
                "the reducible capacity was already claimed by another decision, or the broker "
                "snapshot moved; this decision cannot be ALLOW"
            ),
        )
        return replace(
            result,
            risk_effect=RiskEffect.RISK_INCREASING,
            decision=Decision.REJECT,
            reasons=[*result.reasons, RiskEffectReason.EXCEEDS_REDUCIBLE_CAPACITY],
        )

    # ---------------------------------------------------------------- internals
    async def _reserved_filled_by_symbol(
        self, account_id: int, *, exclude: int | None = None
    ) -> dict[str, Decimal]:
        """Of the HELD reservations, how much has ALREADY FILLED — and is therefore already
        reflected in the broker position.

        A reservation keeps its full original quantity until its order reaches a terminal
        status, so a PARTIAL fill is charged twice: once by the position the fill shrank, once
        by the reservation that still names the whole quantity. `claimable_reducible_quantity`
        adds this back so the filled part is charged exactly once.

        Capped per reservation at its own quantity: an over-fill (broker fills more than the
        reservation covered) must not manufacture capacity.
        """
        stmt = (
            select(
                RiskReservation.symbol,
                RiskReservation.qty,
                func.coalesce(func.sum(Fill.qty), 0),
            )
            .select_from(RiskReservation)
            .join(Fill, Fill.order_id == RiskReservation.order_id)
            .where(
                RiskReservation.account_id == account_id,
                RiskReservation.state == RESERVATION_HELD,
                RiskReservation.order_id.is_not(None),
            )
            .group_by(RiskReservation.id, RiskReservation.symbol, RiskReservation.qty)
        )
        if exclude is not None:
            stmt = stmt.where(RiskReservation.id != exclude)
        out: dict[str, Decimal] = {}
        for sym, res_qty, filled in (await self._session.execute(stmt)).all():
            capped = min(Decimal(str(res_qty)), Decimal(str(filled or 0)))
            out[sym] = out.get(sym, ZERO) + max(ZERO, capped)
        return out

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
        capacity_state_version: int | None = None,
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
            capacity_state_version=capacity_state_version,
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


async def run_reservation_reaper_pass(
    session_factory: async_sessionmaker[AsyncSession], *, older_than_seconds: int = 300
) -> int:
    """Scheduled safety net (ADR 0042 § D): release orphaned HELD reservations so a missed
    event-driven settle can never permanently starve an account's reducible capacity.

    Runs in its own session; touches only ``risk_reservations`` + the capacity accumulator —
    never the order path. Returns the count released.
    """
    async with session_factory() as session:
        reaped = await RiskDecisionService(session).reap_orphaned_reservations(
            older_than_seconds=older_than_seconds
        )
    if reaped:
        logger.info("reservation_reaper_released", count=reaped)
    return reaped
