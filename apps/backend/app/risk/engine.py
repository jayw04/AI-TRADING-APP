"""RiskEngine — the only pre-trade gate.

Per ADR 0002, every order submission passes through `evaluate()` before it
can reach Alpaca. Purely async-DB-bound; no broker calls.

Eight checks, evaluated in order. First failure short-circuits and writes a
RiskCheck row with ``decision='reject'``. A passing evaluation also writes a
RiskCheck row (``decision='pass'``) — the audit trail is symmetric.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.enums import (
    OrderSide,
    OrderType,
    RiskDecision,
    RiskScopeType,
)
from app.db.models.account import Account, AccountMode
from app.db.models.account_state import AccountState
from app.db.models.order import Order
from app.db.models.position import Position
from app.db.models.risk_check import RiskCheck
from app.db.models.risk_limits import RiskLimits
from app.db.models.symbol import Symbol
from app.risk.buying_power import BuyingPowerChecker
from app.risk.circuit_breaker import CircuitBreakerError, CircuitBreakerService
from app.risk.halt import is_halted, set_halted
from app.risk.reason_codes import ReasonCode
from app.risk.types import OrderRequest, RiskOutcome

logger = structlog.get_logger(__name__)

# Types whose declarations actually need limit_price / stop_price.
_TYPES_NEEDING_LIMIT = (OrderType.LIMIT, OrderType.STOP_LIMIT)
_TYPES_NEEDING_STOP = (OrderType.STOP, OrderType.STOP_LIMIT)


class RiskEngine:
    """Stateless evaluator. One instance per process is fine.

    Construction takes a ``session_factory`` because the engine opens its own
    short-lived transaction (rather than sharing the caller's). This keeps
    the engine's reads consistent against a single DB snapshot and lets the
    OrderRouter use a separate transaction for the Order row write.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker,
        *,
        broker_registry: Any = None,
        bar_cache: Any = None,
        bus: Any = None,
    ) -> None:
        self._session_factory = session_factory
        # P5 §5: optional collaborators for the new account-level gates. All
        # default None so pre-§5 call sites (RiskEngine(session_factory)) and
        # every unit test keep working unchanged. broker_registry/bar_cache feed
        # the LIVE-only buying-power gate (dormant until P5 §7 enables live
        # orders); bus lets the circuit breaker publish on trip.
        self._broker_registry = broker_registry
        self._bar_cache = bar_cache
        self._bus = bus

    async def evaluate(
        self,
        req: OrderRequest,
        *,
        trading_mode: str,
        broker_mode: AccountMode = AccountMode.paper,
    ) -> RiskOutcome:
        """Run the eight P1 checks. Always writes a RiskCheck row.

        ``broker_mode`` (P5 §1) scopes which RiskLimits rows are eligible: a
        live trade only matches live-scoped limits, a paper trade only
        paper-scoped. It defaults to PAPER — the conservative scope — but the
        order path always passes the account's actual mode explicitly.
        """
        async with self._session_factory() as session:
            # 0. Halt short-circuit.
            if await is_halted(session):
                return await self._persist_and_return(
                    session,
                    decision=RiskDecision.REJECT,
                    reasons=[ReasonCode.HALT_REACHED],
                )

            # 1. Sanity / shape.
            if req.qty is None or req.qty <= 0:
                return await self._persist_and_return(
                    session,
                    decision=RiskDecision.REJECT,
                    reasons=[ReasonCode.INVALID_INPUT],
                )
            if req.type in _TYPES_NEEDING_LIMIT and (
                req.limit_price is None or req.limit_price <= 0
            ):
                return await self._persist_and_return(
                    session,
                    decision=RiskDecision.REJECT,
                    reasons=[ReasonCode.INVALID_INPUT],
                )
            if req.type in _TYPES_NEEDING_STOP and (
                req.stop_price is None or req.stop_price <= 0
            ):
                return await self._persist_and_return(
                    session,
                    decision=RiskDecision.REJECT,
                    reasons=[ReasonCode.INVALID_INPUT],
                )

            # 2. Mode/account consistency.
            account = (
                await session.execute(select(Account).where(Account.id == req.account_id))
            ).scalars().first()
            if account is None or account.mode.value != trading_mode:
                return await self._persist_and_return(
                    session,
                    decision=RiskDecision.REJECT,
                    reasons=[ReasonCode.MODE_MISMATCH],
                )

            # 3. Resolve the symbol once. Inactive symbols are treated as denied.
            symbol = (
                await session.execute(
                    select(Symbol).where(
                        Symbol.ticker == req.symbol_ticker,
                        Symbol.active.is_(True),
                    )
                )
            ).scalars().first()
            if symbol is None:
                return await self._persist_and_return(
                    session,
                    decision=RiskDecision.REJECT,
                    reasons=[ReasonCode.SYMBOL_DENIED],
                )
            resolved_symbol_id = symbol.id

            # 4. Load applicable risk limits (P1: GLOBAL only), scoped to the
            # account's broker_mode (P5 §1).
            limits = await self._load_global_limits(
                session, req.user_id, broker_mode
            )
            if limits is None:
                return await self._persist_and_return(
                    session,
                    decision=RiskDecision.REJECT,
                    reasons=[ReasonCode.NO_LIMITS_CONFIGURED],
                )

            # 5. Symbol allow/deny lists.
            if limits.denied_symbols and req.symbol_ticker in limits.denied_symbols:
                return await self._persist_and_return(
                    session,
                    decision=RiskDecision.REJECT,
                    reasons=[ReasonCode.SYMBOL_DENIED],
                )
            if limits.allowed_symbols and req.symbol_ticker not in limits.allowed_symbols:
                return await self._persist_and_return(
                    session,
                    decision=RiskDecision.REJECT,
                    reasons=[ReasonCode.SYMBOL_DENIED],
                )

            # 6. Short restriction. A SELL is "opening a short" if we don't
            # already hold >= qty long shares.
            if req.side == OrderSide.SELL and not limits.allow_short:
                pos = (
                    await session.execute(
                        select(Position).where(
                            Position.account_id == req.account_id,
                            Position.symbol_id == symbol.id,
                        )
                    )
                ).scalars().first()
                current_qty = pos.qty if pos else Decimal(0)
                if current_qty < req.qty:
                    return await self._persist_and_return(
                        session,
                        decision=RiskDecision.REJECT,
                        reasons=[ReasonCode.SHORT_NOT_ALLOWED],
                    )

            estimated_notional = self._estimate_notional(req)

            # 7. Position size cap (qty + notional).
            pos = (
                await session.execute(
                    select(Position).where(
                        Position.account_id == req.account_id,
                        Position.symbol_id == symbol.id,
                    )
                )
            ).scalars().first()
            current_qty = pos.qty if pos else Decimal(0)
            delta = req.qty if req.side == OrderSide.BUY else -req.qty
            resulting_qty = abs(current_qty + delta)

            if (
                limits.max_position_qty is not None
                and resulting_qty > limits.max_position_qty
            ):
                return await self._persist_and_return(
                    session,
                    decision=RiskDecision.REJECT,
                    reasons=[ReasonCode.POSITION_CAP_QTY],
                )
            if limits.max_position_notional is not None:
                # Use limit_price if supplied; else avg_entry_price of current
                # position; else 0 (market orders pass notional check here and
                # are picked up by gross exposure on the next position-sync).
                ref_price = req.limit_price or (
                    pos.avg_entry_price if pos else Decimal(0)
                )
                resulting_notional = resulting_qty * (ref_price or Decimal(0))
                if resulting_notional > limits.max_position_notional:
                    return await self._persist_and_return(
                        session,
                        decision=RiskDecision.REJECT,
                        reasons=[ReasonCode.POSITION_CAP_NOTIONAL],
                    )

            # 8. Gross exposure cap.
            if limits.max_gross_exposure is not None:
                gross_now = (
                    await session.execute(
                        select(
                            func.coalesce(func.sum(func.abs(Position.market_value)), 0)
                        ).where(Position.account_id == req.account_id)
                    )
                ).scalar_one()
                projected = Decimal(gross_now or 0) + (estimated_notional or Decimal(0))
                if projected > limits.max_gross_exposure:
                    return await self._persist_and_return(
                        session,
                        decision=RiskDecision.REJECT,
                        reasons=[ReasonCode.GROSS_EXPOSURE],
                    )

            # 9. Daily loss cap → trip the system halt flag.
            if limits.max_daily_loss is not None:
                state = (
                    await session.execute(
                        select(AccountState).where(
                            AccountState.account_id == req.account_id
                        )
                    )
                ).scalars().first()
                if state is not None and state.day_change <= -limits.max_daily_loss:
                    await set_halted(session, True, reason="daily_loss_cap_reached")
                    return await self._persist_and_return(
                        session,
                        decision=RiskDecision.REJECT,
                        reasons=[ReasonCode.HALT_REACHED],
                    )

            # 10. Rate limit (per minute).
            if limits.max_orders_per_minute is not None:
                since = datetime.now(UTC) - timedelta(seconds=60)
                count = (
                    await session.execute(
                        select(func.count(Order.id)).where(
                            Order.user_id == req.user_id,
                            Order.created_at >= since,
                        )
                    )
                ).scalar_one()
                if count >= limits.max_orders_per_minute:
                    return await self._persist_and_return(
                        session,
                        decision=RiskDecision.REJECT,
                        reasons=[ReasonCode.RATE_LIMIT],
                    )

            # 11. Per-day order cap (P5 §5). Orders on the account since today's
            # market open (09:30 ET, fixed -5h). NULL means unlimited.
            if limits.max_orders_per_day is not None:
                day_start = self._market_open_utc_today()
                day_count = (
                    await session.execute(
                        select(func.count(Order.id)).where(
                            Order.account_id == req.account_id,
                            Order.created_at >= day_start,
                        )
                    )
                ).scalar_one()
                if day_count >= limits.max_orders_per_day:
                    return await self._persist_and_return(
                        session,
                        decision=RiskDecision.REJECT,
                        reasons=[ReasonCode.MAX_ORDERS_PER_DAY],
                    )

            # 12. Pre-trade buying power — LIVE only (P5 §5). Dormant until P5 §7
            # opens live orders (the router's BrokerModeError short-circuits LIVE
            # before the engine today). Sells exempt; fail-open on broker error.
            if broker_mode == AccountMode.live and self._broker_registry is not None:
                bp_checker = BuyingPowerChecker(
                    broker_registry=self._broker_registry, bar_cache=self._bar_cache
                )
                bp_decision = await bp_checker.check(account, req)
                if not bp_decision.sufficient:
                    return await self._persist_and_return(
                        session,
                        decision=RiskDecision.REJECT,
                        reasons=[ReasonCode.INSUFFICIENT_BUYING_POWER],
                    )

            # 13. Circuit breaker (account-scoped, P5 §5) — evaluated LAST per
            # risk-engine convention (most likely to terminate the request).
            # check() raises if already tripped OR if this order trips it (which
            # also HALTs the account's active strategies + audits, atomically).
            # This is ADDITIONAL to the GLOBAL daily-loss halt at step 9; the two
            # compose (defense in depth) — see ADR 0004.
            cb = CircuitBreakerService(session=session, bus=self._bus)
            try:
                await cb.check(req.account_id)
            except CircuitBreakerError:
                return await self._persist_and_return(
                    session,
                    decision=RiskDecision.REJECT,
                    reasons=[ReasonCode.CIRCUIT_BREAKER],
                )

            # Pass.
            return await self._persist_and_return(
                session,
                decision=RiskDecision.PASS,
                reasons=[ReasonCode.OK],
                resolved_symbol_id=resolved_symbol_id,
                estimated_notional=estimated_notional,
            )

    # ---- internals ----

    async def _load_global_limits(
        self,
        session: AsyncSession,
        user_id: int,
        broker_mode: AccountMode = AccountMode.paper,
    ) -> RiskLimits | None:
        return (
            await session.execute(
                select(RiskLimits).where(
                    RiskLimits.user_id == user_id,
                    RiskLimits.scope_type == RiskScopeType.GLOBAL,
                    RiskLimits.broker_mode == broker_mode,
                )
            )
        ).scalars().first()

    def _market_open_utc_today(self) -> datetime:
        """09:30 US/Eastern today → UTC. Fixed -5h offset (EST); the 1-hour DST
        drift is acceptable for MVP (matches CircuitBreakerService)."""
        now = datetime.now(UTC)
        market_open = now.replace(hour=14, minute=30, second=0, microsecond=0)
        if now < market_open:
            market_open = market_open - timedelta(days=1)
        return market_open

    def _estimate_notional(self, req: OrderRequest) -> Decimal | None:
        if req.limit_price is not None:
            return req.qty * req.limit_price
        # For market orders we can't know fill price up front.
        return None

    async def _persist_and_return(
        self,
        session: AsyncSession,
        *,
        decision: RiskDecision,
        reasons: list[ReasonCode],
        resolved_symbol_id: int | None = None,
        estimated_notional: Decimal | None = None,
    ) -> RiskOutcome:
        rc = RiskCheck(
            order_id=None,
            decision=decision,
            reason_codes=[r.value for r in reasons],
            evaluated_at=datetime.now(UTC),
        )
        session.add(rc)
        await session.commit()
        await session.refresh(rc)
        logger.info(
            "risk_check_persisted",
            decision=decision.value,
            reasons=[r.value for r in reasons],
            risk_check_id=rc.id,
        )
        return RiskOutcome(
            decision=decision.value,
            reason_codes=reasons,
            risk_check_id=rc.id,
            resolved_symbol_id=resolved_symbol_id,
            estimated_notional=estimated_notional,
        )
