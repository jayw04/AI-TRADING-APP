"""Circuit breaker: account-scoped hard halt on daily loss limit (P5 §5, ADR 0004).

State model:
  - accounts.circuit_breaker_tripped_at is the source of truth for
    "is this account currently tripped?" (NULL = OK).
  - audit_log carries the history (CIRCUIT_BREAKER_TRIPPED with the PnL
    snapshot, CIRCUIT_BREAKER_RESET with the actor).

This is an ADDITIONAL, account-scoped gate. The pre-existing GLOBAL
system_config halt (app/risk/halt.py, RiskEngine step 9) is left in place —
the two compose (defense in depth); see ADR 0004.

Trip precondition:
  realized_pnl_today + unrealized_pnl_now <= -max_daily_loss

Trip actions (atomic, single commit before the rejecting order returns):
  1. Set accounts.circuit_breaker_tripped_at = now()
  2. Transition every active strategy *running in this account's mode* to HALTED
  3. Write CIRCUIT_BREAKER_TRIPPED audit row
  4. Publish system.circuit_breaker bus event (after commit)

Reset actions (atomic, audit-logged):
  1. Clear accounts.circuit_breaker_tripped_at
  2. Write CIRCUIT_BREAKER_RESET audit row with reset_by_user_id
  3. Publish system.circuit_breaker bus event
  4. Do NOT auto-restart HALTED strategies — the user restarts each manually.

Drift notes vs the v0.2 session doc (reconciled against live schema):
  - `strategies` has no account_id (deferred to P5 §7). Active strategies are
    mapped to the account via (user_id, status↔mode): a PAPER-status strategy
    belongs to the paper account, LIVE to the live account.
  - `Fill` has no signed_direction; realized PnL joins Fill→Order and signs by
    order.side.
  - Unrealized PnL is summed from the local `positions` table (kept fresh by
    position-sync) rather than a broker call, keeping the engine DB-bound.
  - SQLEnum persists the enum NAME ('PAPER'/'BUY'); comparisons use enum
    members (never .value) so they bind correctly.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import AuditAction, AuditActorType, AuditLogger
from app.db.enums import OrderSide, RiskScopeType, StrategyStatus
from app.db.models.account import Account, AccountMode
from app.db.models.fill import Fill
from app.db.models.order import Order
from app.db.models.position import Position
from app.db.models.risk_limits import RiskLimits
from app.db.models.strategy import Strategy
from app.utils.time import ensure_aware

logger = structlog.get_logger(__name__)


@dataclass
class CircuitBreakerStatus:
    account_id: int
    tripped: bool
    tripped_at: datetime | None
    realized_pnl_today: Decimal
    unrealized_pnl_now: Decimal
    max_daily_loss: Decimal
    headroom: Decimal


class CircuitBreakerError(RuntimeError):
    """Raised when the breaker is tripped (or trips) and an order is attempted."""


class CircuitBreakerService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        bus: Any = None,
        broker_registry: Any = None,
    ) -> None:
        self._session = session
        self._bus = bus
        # Retained for API/signature compatibility; unrealized PnL is computed
        # from the local positions table, so no broker call is made here.
        self._broker_registry = broker_registry

    async def status(self, account_id: int) -> CircuitBreakerStatus:
        account = await self._session.get(Account, account_id)
        if account is None:
            raise ValueError(f"Account {account_id} not found")
        limits = await self._get_active_limits(account)
        realized = await self._compute_realized_pnl_today(account_id)
        unrealized = await self._compute_unrealized_pnl(account_id)
        max_loss = (
            Decimal(str(limits.max_daily_loss))
            if limits and limits.max_daily_loss is not None
            else Decimal("0")
        )
        net = realized + unrealized
        headroom = max_loss - abs(net) if net < 0 else max_loss
        tripped_at = ensure_aware(account.circuit_breaker_tripped_at)
        return CircuitBreakerStatus(
            account_id=account_id,
            tripped=tripped_at is not None,
            tripped_at=tripped_at,
            realized_pnl_today=realized,
            unrealized_pnl_now=unrealized,
            max_daily_loss=max_loss,
            headroom=headroom,
        )

    async def check(self, account_id: int) -> None:
        """Pre-trade check: raise CircuitBreakerError if tripped OR if this
        order would push net PnL past -max_daily_loss (tripping in the process)."""
        account = await self._session.get(Account, account_id)
        if account is None:
            raise CircuitBreakerError(f"Account {account_id} not found")
        tripped_at = ensure_aware(account.circuit_breaker_tripped_at)
        if tripped_at is not None:
            raise CircuitBreakerError(
                f"Circuit breaker tripped at {tripped_at.isoformat()}. "
                f"Reset via Settings → Risk to resume trading."
            )

        limits = await self._get_active_limits(account)
        if limits is None or limits.max_daily_loss is None:
            return  # No daily-loss limit configured.

        max_loss = Decimal(str(limits.max_daily_loss))
        realized = await self._compute_realized_pnl_today(account_id)
        unrealized = await self._compute_unrealized_pnl(account_id)
        net_pnl = realized + unrealized
        if net_pnl <= -max_loss:
            await self.trip(
                account_id=account_id,
                reason="daily_loss_exceeded",
                payload={
                    "realized_pnl_today": str(realized),
                    "unrealized_pnl_now": str(unrealized),
                    "net_pnl": str(net_pnl),
                    "max_daily_loss": str(max_loss),
                },
            )
            raise CircuitBreakerError(
                f"Daily loss limit reached (net PnL {net_pnl} ≤ -{max_loss}). "
                f"All strategies on this account are now HALTED."
            )

    async def trip(self, *, account_id: int, reason: str, payload: dict[str, Any]) -> None:
        """Atomically set the trip timestamp, HALT active strategies for this
        account's mode, audit-log, then publish. Idempotent."""
        now = datetime.now(UTC)
        account = await self._session.get(Account, account_id)
        if account is None or account.circuit_breaker_tripped_at is not None:
            return  # Already tripped or missing.
        account.circuit_breaker_tripped_at = now

        target_status = self._mode_status(account.mode)
        strategies = (
            await self._session.execute(
                select(Strategy).where(
                    Strategy.user_id == account.user_id,
                    Strategy.status == target_status,
                )
            )
        ).scalars().all()
        halted_ids: list[int] = []
        for s in strategies:
            s.status = StrategyStatus.HALTED
            halted_ids.append(s.id)

        AuditLogger.write(
            self._session,
            actor_type=AuditActorType.SYSTEM,
            actor_id="circuit_breaker",
            action=AuditAction.CIRCUIT_BREAKER_TRIPPED,
            target_type="account",
            target_id=account_id,
            payload={"reason": reason, "halted_strategy_ids": halted_ids, **payload},
            user_id=account.user_id,
        )
        await self._session.commit()

        await self._publish(
            account_id=account_id,
            state="tripped",
            extra={"reason": reason, "halted_strategy_ids": halted_ids, "at": now.isoformat()},
        )
        logger.warning(
            "circuit_breaker_tripped",
            account_id=account_id,
            reason=reason,
            halted_strategies=halted_ids,
        )

    async def reset(
        self, *, account_id: int, user_id: int, confirmation_text: str
    ) -> None:
        """Manual reset by the account owner. confirmation_text must equal the
        account's label — server-side defense in depth."""
        account = await self._session.get(Account, account_id)
        if account is None:
            raise ValueError(f"Account {account_id} not found")
        if account.user_id != user_id:
            raise PermissionError(
                f"Account {account_id} does not belong to user {user_id}"
            )
        if confirmation_text != account.label:
            raise ValueError(
                f"Confirmation text does not match account label. "
                f"Type '{account.label}' to confirm reset."
            )
        if account.circuit_breaker_tripped_at is None:
            return  # Idempotent.

        prior_trip_at = ensure_aware(account.circuit_breaker_tripped_at)
        account.circuit_breaker_tripped_at = None

        AuditLogger.write(
            self._session,
            actor_type=AuditActorType.USER,
            actor_id=str(user_id),
            action=AuditAction.CIRCUIT_BREAKER_RESET,
            target_type="account",
            target_id=account_id,
            payload={
                "reset_by_user_id": user_id,
                "prior_trip_at": prior_trip_at.isoformat() if prior_trip_at else None,
            },
            user_id=user_id,
        )
        await self._session.commit()

        await self._publish(
            account_id=account_id,
            state="reset",
            extra={"reset_by_user_id": user_id, "at": datetime.now(UTC).isoformat()},
        )
        logger.info("circuit_breaker_reset", account_id=account_id, user_id=user_id)

    # ---- internals ----

    @staticmethod
    def _mode_status(mode: AccountMode) -> StrategyStatus:
        """The active strategy status that corresponds to an account's mode.

        strategies has no account_id (P5 §7); a strategy running in PAPER status
        belongs to the paper account, LIVE to the live account.
        """
        return StrategyStatus.LIVE if mode == AccountMode.live else StrategyStatus.PAPER

    async def _get_active_limits(self, account: Account) -> RiskLimits | None:
        return (
            await self._session.execute(
                select(RiskLimits).where(
                    RiskLimits.user_id == account.user_id,
                    RiskLimits.broker_mode == account.mode,
                    RiskLimits.scope_type == RiskScopeType.GLOBAL,
                )
            )
        ).scalars().first()

    async def _compute_realized_pnl_today(self, account_id: int) -> Decimal:
        """Net realized cash flow from today's fills, sign-aware.

        signed cash flow per fill: +qty*price for BUY (cash out), -qty*price for
        SELL (cash in). Realized PnL ≈ -sum(signed_cash). Conservative for
        positions opened-and-still-open today (they look like loss); the
        unrealized term corrects for that. (Fill has no signed_direction column;
        the sign comes from the joined Order.side.)
        """
        market_open = self._market_open_utc_today()
        signed_cash = case(
            (Order.side == OrderSide.BUY, Fill.qty * Fill.price),
            else_=-(Fill.qty * Fill.price),
        )
        result = await self._session.execute(
            select(func.coalesce(func.sum(signed_cash), 0))
            .select_from(Fill)
            .join(Order, Fill.order_id == Order.id)
            .where(Order.account_id == account_id)
            .where(Fill.filled_at >= market_open)
        )
        net_cash = result.scalar() or Decimal("0")
        return Decimal(str(-net_cash))

    async def _compute_unrealized_pnl(self, account_id: int) -> Decimal:
        """Sum unrealized P&L across the account's open positions (local table,
        kept fresh by position-sync). No broker round-trip — the engine stays
        DB-bound."""
        result = await self._session.execute(
            select(func.coalesce(func.sum(Position.unrealized_pl), 0)).where(
                Position.account_id == account_id
            )
        )
        total = result.scalar() or Decimal("0")
        return Decimal(str(total))

    def _market_open_utc_today(self) -> datetime:
        """09:30 US/Eastern today → UTC. Fixed -5h offset (EST). The 1-hour DST
        drift is acceptable for MVP; P5+ uses zoneinfo (Notes & Gotchas #1)."""
        now = datetime.now(UTC)
        market_open = now.replace(hour=14, minute=30, second=0, microsecond=0)
        if now < market_open:
            market_open = market_open - timedelta(days=1)
        return market_open

    async def _publish(self, *, account_id: int, state: str, extra: dict[str, Any]) -> None:
        if self._bus is None:
            return
        try:
            await self._bus.publish(
                "system.circuit_breaker",
                {"account_id": account_id, "state": state, **extra},
            )
        except Exception:
            logger.exception("circuit_breaker_publish_failed", account_id=account_id)
