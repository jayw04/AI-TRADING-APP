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

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.enums import (
    OrderSide,
    OrderType,
    RiskDecision,
    RiskScopeType,
)
from app.db.models.account import Account
from app.db.models.account_state import AccountState
from app.db.models.order import Order
from app.db.models.position import Position
from app.db.models.risk_check import RiskCheck
from app.db.models.risk_limits import RiskLimits
from app.db.models.symbol import Symbol
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

    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def evaluate(self, req: OrderRequest, *, trading_mode: str) -> RiskOutcome:
        """Run the eight P1 checks. Always writes a RiskCheck row."""
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

            # 4. Load applicable risk limits (P1: GLOBAL only).
            limits = await self._load_global_limits(session, req.user_id)
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
        self, session: AsyncSession, user_id: int
    ) -> RiskLimits | None:
        return (
            await session.execute(
                select(RiskLimits).where(
                    RiskLimits.user_id == user_id,
                    RiskLimits.scope_type == RiskScopeType.GLOBAL,
                )
            )
        ).scalars().first()

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
