"""OrderRouter — the only entry point for order submission.

Per ADR 0002 there is no other path through which an OrderRequest may reach
the broker. This invariant is enforced by:

  1. AlpacaAdapter.submit_order / cancel_order / replace_order accept a
     keyword-only ``_router_token`` and refuse to run without it.
  2. The router is the only module that knows the token.
  3. A CI grep test fails any PR that calls AlpacaAdapter.submit_order from
     a module other than this one (see tests/test_adr_0002_invariant.py).

The router writes the Order row BEFORE calling Alpaca, links the RiskCheck,
and emits internal events so the WS gateway and audit trail stay in sync.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.audit import AuditAction, AuditActorType, AuditLogger
from app.brokers.alpaca import AlpacaAdapter
from app.brokers.alpaca.errors import PermanentAlpacaError, TransientAlpacaError
from app.db.enums import OrderSourceType, OrderStatus
from app.db.models.account import Account, AccountMode
from app.db.models.order import Order
from app.db.models.risk_check import RiskCheck
from app.db.models.symbol import Symbol
from app.events.bus import EventBus
from app.risk import OrderRequest, RiskEngine, RiskOutcome
from app.risk.reason_codes import ReasonCode
from app.services.strategy_cooldown import StrategyCooldownService

if TYPE_CHECKING:
    from app.brokers.base import BrokerAdapter
    from app.brokers.registry import BrokerRegistry

logger = structlog.get_logger(__name__)

# Shared token between router and adapter — guardrail against accidental bypass,
# not a security boundary. See ADR 0002 and the CI grep test.
ROUTER_TOKEN = "ADR_0002_ONLY_ORDERROUTER_MAY_CALL_THIS"


class BrokerModeError(RuntimeError):
    """Raised when an order targets a broker mode that isn't yet supported.

    P5 §1: every LIVE account is refused here, before the risk engine runs.
    Live order submission arrives in P5 §2; until then "no live trading
    happens" is guaranteed by this runtime check, not merely by the absence of
    a live code path. Defense in depth.
    """


class OrderRouter:
    def __init__(
        self,
        adapter: AlpacaAdapter,
        risk_engine: RiskEngine,
        session_factory: async_sessionmaker,
        bus: EventBus,
        broker_registry: BrokerRegistry | None = None,
    ) -> None:
        self._adapter = adapter  # default / fallback (the connected paper adapter)
        self._risk = risk_engine
        self._session_factory = session_factory
        self._bus = bus
        # P5 §2: when wired, resolve a per-account adapter from the registry.
        # When None (every pre-§2 caller and unit test), behavior is identical
        # to P5 §1 — _resolve_adapter falls back to self._adapter.
        self._broker_registry = broker_registry

    async def submit(self, req: OrderRequest) -> Order:
        """Sole order-submission entry point."""
        # P5 §1 — refuse LIVE accounts *before* any other work. Running the
        # risk engine against an order we'll reject anyway is wasted, and the
        # engine might decline a LIVE order for the wrong reason (no live-scoped
        # limits exist yet), sending the user chasing a phantom risk problem.
        account = await self._load_account(req.account_id)

        # P5 §6: typed-ticker confirmation — MANUAL orders on a LIVE account
        # require confirmation_text matching the symbol. Checked BEFORE the §1
        # LIVE guard so a missing/wrong confirmation is a clean rejection (not a
        # BrokerModeError). Every LIVE attempt is audited (LIVE_ORDER_SUBMITTED).
        if (
            account is not None
            and account.mode == AccountMode.live
            and req.source_type == OrderSourceType.MANUAL
        ):
            conf_reason = _confirmation_reject_reason(req)
            if conf_reason is not None:
                order = _ephemeral_rejected_order_with_reason(req, conf_reason)
                await self._audit_live_submission(
                    req, account, status="rejected", reason_code=conf_reason,
                    order_id=None,
                )
                return order

        # P5 §6: per-strategy cooldown — STRATEGY orders for a strategy in
        # cooldown are rejected before the (expensive) risk engine. Per-strategy:
        # other strategies and all manual orders are unaffected. Cooldown
        # rejections are NOT audited (a spinning strategy would flood the log);
        # the logger.warning is the operational signal.
        if req.source_type == OrderSourceType.STRATEGY and req.source_id:
            cooldown_strategy_id = _strategy_id_from_source(req.source_id)
            if cooldown_strategy_id is not None:
                async with self._session_factory() as session:
                    in_cd, until = await StrategyCooldownService(
                        session
                    ).is_in_cooldown(cooldown_strategy_id)
                if in_cd:
                    logger.warning(
                        "order_rejected_cooldown",
                        strategy_id=cooldown_strategy_id,
                        account_id=req.account_id,
                        cooldown_until=until.isoformat() if until else None,
                    )
                    return _ephemeral_rejected_order_with_reason(
                        req, ReasonCode.STRATEGY_COOLDOWN.value
                    )

        # P5 §1 — refuse LIVE accounts *before* any other work. Running the
        # risk engine against an order we'll reject anyway is wasted, and the
        # engine might decline a LIVE order for the wrong reason (no live-scoped
        # limits exist yet), sending the user chasing a phantom risk problem.
        if account is not None and account.mode == AccountMode.live:
            # P5 §6: record the live attempt before refusing (§7 lifts this guard).
            await self._audit_live_submission(
                req, account, status="rejected",
                reason_code="BROKER_MODE_NOT_ENABLED", order_id=None,
            )
            logger.warning(
                "order_router_refused_live",
                account_id=account.id,
                user_id=req.user_id,
                symbol=req.symbol_ticker,
                side=req.side.value,
            )
            raise BrokerModeError(
                "Live trading is not yet enabled. See P5 §2 release notes."
            )
        broker_mode = account.mode if account is not None else AccountMode.paper

        # P5 §2: resolve the per-account adapter (after the §1 LIVE guard, so a
        # live account never reaches the registry). Falls back to the default
        # adapter when no registry is wired — paper behavior is unchanged.
        adapter = self._resolve_adapter(account)
        trading_mode = "paper" if adapter.is_paper else "live"
        outcome = await self._risk.evaluate(
            req, trading_mode=trading_mode, broker_mode=broker_mode
        )

        # If the engine rejected without resolving a Symbol row (e.g. unknown
        # ticker), we cannot persist an Order — orders.symbol_id is NOT NULL.
        # The RiskCheck row already records the rejected attempt for audit;
        # return an ephemeral rejected Order so the API caller's response
        # shape stays consistent.
        if not outcome.passed and outcome.resolved_symbol_id is None:
            order = _ephemeral_rejected_order(req, outcome)
            await self._maybe_set_cooldown(req, order)
            return order

        async with self._session_factory() as session:
            order = await self._persist_initial_order(session, req, outcome)

            if not outcome.passed:
                order.status = OrderStatus.REJECTED
                order.rejection_reason = ",".join(r.value for r in outcome.reason_codes)
                order.terminal_at = datetime.now(UTC)
                order.updated_at = order.terminal_at
                await session.commit()
                await session.refresh(order)
                await self._audit(
                    session,
                    order,
                    AuditAction.ORDER_REJECTED_BY_RISK,
                    {
                        "reasons": [r.value for r in outcome.reason_codes],
                        "risk_check_id": outcome.risk_check_id,
                    },
                )
                await self._emit(order, "order.rejected", {
                    "reasons": [r.value for r in outcome.reason_codes],
                })
                logger.info(
                    "order_rejected_by_risk",
                    order_id=order.id,
                    reasons=[r.value for r in outcome.reason_codes],
                )
                # P5 §6: a STRATEGY-sourced submission that failed risk enters
                # the 60s cooldown.
                await self._maybe_set_cooldown(req, order)
                return order

            # Risk passed. Mark pending_submit and attempt broker submission.
            order.status = OrderStatus.PENDING_SUBMIT
            order.updated_at = datetime.now(UTC)
            await session.commit()
            await session.refresh(order)
            await self._audit(
                session,
                order,
                AuditAction.ORDER_RISK_PASSED,
                {"risk_check_id": outcome.risk_check_id},
            )

        # ---- broker call (outside the DB transaction) ----
        try:
            broker_response = adapter.submit_order(
                symbol=req.symbol_ticker,
                qty=req.qty,
                side=req.side.value,
                type_=req.type.value,
                tif=req.tif.value,
                limit_price=req.limit_price,
                stop_price=req.stop_price,
                extended_hours=req.extended_hours,
                client_order_id=order.client_order_id,
                _router_token=ROUTER_TOKEN,
            )
        except PermanentAlpacaError as exc:
            order = await self._mark_broker_rejected(order.id, str(exc))
            # P5 §6: broker permanently rejected a STRATEGY submission → cooldown.
            await self._maybe_set_cooldown(req, order)
            return order
        except TransientAlpacaError:
            # Leave the order in PENDING_SUBMIT; caller may retry. We do NOT
            # mark it rejected — that would be wrong if Alpaca eventually
            # accepted it on a retry.
            await self._emit_simple(order.id, "order.submit_transient_error")
            raise

        # Broker accepted.
        async with self._session_factory() as session:
            order = (
                await session.execute(select(Order).where(Order.id == order.id))
            ).scalars().first()
            order.broker_order_id = str(
                broker_response.get("id")
                or broker_response.get("broker_order_id")
                or ""
            )
            order.status = OrderStatus.SUBMITTED
            order.submitted_at = datetime.now(UTC)
            order.updated_at = order.submitted_at
            await session.commit()
            await session.refresh(order)
            await self._audit(
                session,
                order,
                AuditAction.ORDER_SUBMITTED,
                {"broker_order_id": order.broker_order_id},
            )

        await self._emit(order, "order.submitted", {})
        logger.info(
            "order_submitted",
            order_id=order.id,
            broker_order_id=order.broker_order_id,
        )
        return order

    async def cancel(self, order_id: int, *, actor_user_id: int | None = None) -> Order:  # noqa: ARG002
        async with self._session_factory() as session:
            order = (
                await session.execute(select(Order).where(Order.id == order_id))
            ).scalars().first()
            if order is None:
                raise ValueError(f"Order {order_id} not found")
            if not order.broker_order_id:
                # Local-only cancel (order never made it to broker).
                order.status = OrderStatus.CANCELED
                order.terminal_at = datetime.now(UTC)
                order.updated_at = order.terminal_at
                await session.commit()
                await session.refresh(order)
                await self._audit(session, order, AuditAction.ORDER_CANCELED_LOCAL, {})
                await self._emit(order, "order.canceled", {"local_only": True})
                return order
            order_account_id = order.account_id

        # P5 §2: cancel through the same per-account adapter that submitted it.
        adapter = await self._resolve_adapter_for_account_id(order_account_id)
        try:
            adapter.cancel_order(order.broker_order_id, _router_token=ROUTER_TOKEN)
        except PermanentAlpacaError as exc:
            logger.warning("cancel_permanent_error", order_id=order_id, error=str(exc))
            # Usually "already filled / already canceled" — trade-update stream
            # will reconcile. Audit and continue.
            async with self._session_factory() as session:
                order = (
                    await session.execute(select(Order).where(Order.id == order_id))
                ).scalars().first()
                await self._audit(
                    session,
                    order,
                    AuditAction.ORDER_CANCEL_REJECTED_BY_BROKER,
                    {"error": str(exc)},
                )
            return order

        # Optimistic; trade-update consumer will transition to terminal CANCELED.
        async with self._session_factory() as session:
            order = (
                await session.execute(select(Order).where(Order.id == order_id))
            ).scalars().first()
            await self._audit(session, order, AuditAction.ORDER_CANCEL_REQUESTED, {})
        await self._emit(order, "order.cancel_requested", {})
        return order

    async def replace(
        self,
        order_id: int,
        *,
        new_qty: Decimal | None = None,
        new_limit_price: Decimal | None = None,
        actor_user_id: int | None = None,  # noqa: ARG002 - reserved for future audit
    ) -> Order:
        async with self._session_factory() as session:
            order = (
                await session.execute(select(Order).where(Order.id == order_id))
            ).scalars().first()
            if order is None or not order.broker_order_id:
                raise ValueError(f"Order {order_id} not replaceable")
            order_account_id = order.account_id

        # P5 §2: replace through the same per-account adapter.
        adapter = await self._resolve_adapter_for_account_id(order_account_id)
        try:
            adapter.replace_order(
                order.broker_order_id,
                new_qty=new_qty,
                new_limit_price=new_limit_price,
                _router_token=ROUTER_TOKEN,
            )
        except PermanentAlpacaError as exc:
            async with self._session_factory() as session:
                order = (
                    await session.execute(select(Order).where(Order.id == order_id))
                ).scalars().first()
                await self._audit(
                    session,
                    order,
                    AuditAction.ORDER_REPLACE_REJECTED_BY_BROKER,
                    {"error": str(exc)},
                )
            return order

        async with self._session_factory() as session:
            order = (
                await session.execute(select(Order).where(Order.id == order_id))
            ).scalars().first()
            await self._audit(
                session,
                order,
                AuditAction.ORDER_REPLACE_REQUESTED,
                {
                    "new_qty": str(new_qty) if new_qty is not None else None,
                    "new_limit_price": str(new_limit_price) if new_limit_price is not None else None,
                },
            )
        await self._emit(order, "order.replace_requested", {})
        return order

    # ---- internals ----

    async def _load_account(self, account_id: int | None) -> Account | None:
        """Load the target account, or None when unset/unknown.

        A missing account is left for the existing downstream paths to handle
        (the paper flow is unchanged and the engine's mode/account check still
        runs); the LIVE guard only acts on a resolved LIVE account.
        """
        if account_id is None:
            return None
        async with self._session_factory() as session:
            return await session.get(Account, account_id)

    def _resolve_adapter(self, account: Account | None) -> BrokerAdapter:
        """Per-account adapter (P5 §2).

        Falls back to the default startup adapter when no registry is wired or
        the account isn't registered — preserving P1/P5 §1 behavior and keeping
        every existing test (constructed with ``broker_registry=None``) green.
        """
        if self._broker_registry is not None and account is not None:
            found = self._broker_registry.get(account.id)
            if found is not None:
                return found
        return self._adapter

    async def _resolve_adapter_for_account_id(
        self, account_id: int | None
    ) -> BrokerAdapter:
        """Resolve the adapter for an order's account (cancel/replace paths)."""
        account = await self._load_account(account_id)
        return self._resolve_adapter(account)

    async def _persist_initial_order(
        self,
        session: AsyncSession,
        req: OrderRequest,
        outcome: RiskOutcome,
    ) -> Order:
        now = datetime.now(UTC)
        symbol_id = outcome.resolved_symbol_id
        if symbol_id is None:
            sym = (
                await session.execute(
                    select(Symbol).where(Symbol.ticker == req.symbol_ticker)
                )
            ).scalars().first()
            symbol_id = sym.id if sym else None

        client_order_id = req.client_order_id or f"twb-{uuid.uuid4().hex[:24]}"

        order = Order(
            user_id=req.user_id,
            account_id=req.account_id,
            symbol_id=symbol_id,
            broker_order_id=None,
            client_order_id=client_order_id,
            side=req.side,
            qty=req.qty,
            type=req.type,
            limit_price=req.limit_price,
            stop_price=req.stop_price,
            tif=req.tif,
            extended_hours=req.extended_hours,
            status=OrderStatus.PENDING_RISK,
            source_type=req.source_type,
            source_id=req.source_id,
            risk_check_id=outcome.risk_check_id,
            created_at=now,
            updated_at=now,
        )
        session.add(order)
        await session.commit()
        await session.refresh(order)

        # Back-link RiskCheck.order_id (engine created it with order_id=None).
        if outcome.risk_check_id is not None:
            rc = (
                await session.execute(
                    select(RiskCheck).where(RiskCheck.id == outcome.risk_check_id)
                )
            ).scalars().first()
            if rc is not None:
                rc.order_id = order.id
                await session.commit()

        return order

    async def _mark_broker_rejected(self, order_id: int, reason: str) -> Order:
        async with self._session_factory() as session:
            order = (
                await session.execute(select(Order).where(Order.id == order_id))
            ).scalars().first()
            order.status = OrderStatus.REJECTED
            order.rejection_reason = reason[:512]
            order.terminal_at = datetime.now(UTC)
            order.updated_at = order.terminal_at
            await session.commit()
            await session.refresh(order)
            await self._audit(
                session,
                order,
                AuditAction.ORDER_REJECTED_BY_BROKER,
                {"reason": reason},
            )
        await self._emit(order, "order.rejected", {"reason": reason})
        return order

    async def _audit(
        self,
        session: AsyncSession,
        order: Order,
        action: AuditAction | str,
        payload: dict[str, Any],
    ) -> None:
        actor_type = (
            AuditActorType.USER
            if order.source_type == OrderSourceType.MANUAL
            else AuditActorType.SYSTEM
        )
        AuditLogger.write(
            session,
            actor_type=actor_type,
            actor_id=str(order.user_id),
            action=action,
            target_type="order",
            target_id=order.id,
            payload=payload,
            user_id=order.user_id,
        )
        await session.commit()

    async def _emit(self, order: Order, topic: str, extra: dict[str, Any]) -> None:
        await self._bus.publish(
            topic,
            {
                "order_id": order.id,
                "broker_order_id": order.broker_order_id,
                "status": order.status.value,
                "symbol_id": order.symbol_id,
                "side": order.side.value,
                "qty": str(order.qty),
                **extra,
            },
        )

    async def _emit_simple(self, order_id: int, topic: str) -> None:
        await self._bus.publish(topic, {"order_id": order_id})

    # ---- P5 §6: live order safety helpers ----

    async def _maybe_set_cooldown(self, req: OrderRequest, order: Order) -> None:
        """Set the 60s cooldown when a STRATEGY-sourced order failed to submit
        (router-level failures land as REJECTED). Each failure resets the window.
        No-op for manual orders and for successful/pending submissions."""
        if req.source_type != OrderSourceType.STRATEGY:
            return
        strategy_id = _strategy_id_from_source(req.source_id)
        if strategy_id is None:
            return
        if order.status != OrderStatus.REJECTED:
            return
        async with self._session_factory() as session:
            await StrategyCooldownService(session).set_cooldown(
                strategy_id,
                duration_seconds=60,
                reason=order.rejection_reason or "submission_failed",
            )

    async def _audit_live_submission(
        self,
        req: OrderRequest,
        account: Account,
        *,
        status: str,
        reason_code: str | None,
        order_id: int | None,
    ) -> None:
        """Write a LIVE_ORDER_SUBMITTED audit row for a LIVE order attempt,
        regardless of outcome. Paper attempts are never audited here (the orders
        table is their trail). Prices serialize as strings to preserve Decimal
        precision."""
        if account.mode != AccountMode.live:
            return
        actor_type = (
            AuditActorType.USER
            if req.source_type == OrderSourceType.MANUAL
            else AuditActorType.SYSTEM
        )
        async with self._session_factory() as session:
            AuditLogger.write(
                session,
                actor_type=actor_type,
                actor_id=str(req.user_id),
                action=AuditAction.LIVE_ORDER_SUBMITTED,
                target_type="order",
                target_id=order_id if order_id is not None else 0,
                payload={
                    "symbol": req.symbol_ticker,
                    "side": req.side.value,
                    "qty": str(req.qty),
                    "type": req.type.value,
                    "limit_price": (
                        str(req.limit_price) if req.limit_price is not None else None
                    ),
                    "stop_price": (
                        str(req.stop_price) if req.stop_price is not None else None
                    ),
                    "source": req.source_type.value,
                    "strategy_id": _strategy_id_from_source(req.source_id),
                    "outcome": status,
                    "reason_code": reason_code,
                    "account_id": account.id,
                },
                user_id=req.user_id,
            )
            await session.commit()


def _confirmation_reject_reason(req: OrderRequest) -> str | None:
    """For a MANUAL+LIVE order, return the rejection reason code if the typed
    confirmation is missing or doesn't match the symbol, else None.

    Match is case-insensitive and whitespace-stripped on both sides
    ('aapl' / '  AAPL  ' both match 'AAPL'; 'AAPL.US' does not match 'AAPL')."""
    if not req.confirmation_text:
        return ReasonCode.CONFIRMATION_REQUIRED.value
    if req.confirmation_text.strip().upper() != req.symbol_ticker.strip().upper():
        return ReasonCode.CONFIRMATION_MISMATCH.value
    return None


def _strategy_id_from_source(source_id: str | None) -> int | None:
    """Strategy orders carry source_id = str(strategy_id) (see
    StrategyContext.submit_order). Parse it back to an int; None if absent or
    non-numeric."""
    if not source_id:
        return None
    try:
        return int(source_id)
    except (TypeError, ValueError):
        return None


def _ephemeral_rejected_order_with_reason(req: OrderRequest, reason_code: str) -> Order:
    """Build a non-persisted REJECTED Order carrying a single P5 §6 reason code
    (CONFIRMATION_* / STRATEGY_COOLDOWN). Pre-risk rejections never resolved a
    symbol, so symbol_id is the ephemeral sentinel 0 (never written to the DB)."""
    now = datetime.now(UTC)
    return Order(
        user_id=req.user_id,
        account_id=req.account_id,
        symbol_id=0,  # ephemeral — never reaches the DB
        broker_order_id=None,
        client_order_id=req.client_order_id,
        side=req.side,
        qty=req.qty,
        type=req.type,
        limit_price=req.limit_price,
        stop_price=req.stop_price,
        tif=req.tif,
        extended_hours=req.extended_hours,
        status=OrderStatus.REJECTED,
        rejection_reason=reason_code,
        source_type=req.source_type,
        source_id=req.source_id,
        risk_check_id=None,
        created_at=now,
        terminal_at=now,
        updated_at=now,
    )


def _ephemeral_rejected_order(req: OrderRequest, outcome: RiskOutcome) -> Order:
    """Build a non-persisted Order in REJECTED state.

    Used when the engine rejected before a Symbol could be resolved
    (orders.symbol_id is NOT NULL, so we can't write the row). The RiskCheck
    row written by the engine remains the authoritative audit record.
    """
    now = datetime.now(UTC)
    return Order(
        user_id=req.user_id,
        account_id=req.account_id,
        symbol_id=0,  # ephemeral — never reaches the DB
        broker_order_id=None,
        client_order_id=req.client_order_id,
        side=req.side,
        qty=req.qty,
        type=req.type,
        limit_price=req.limit_price,
        stop_price=req.stop_price,
        tif=req.tif,
        extended_hours=req.extended_hours,
        status=OrderStatus.REJECTED,
        rejection_reason=",".join(r.value for r in outcome.reason_codes),
        source_type=req.source_type,
        source_id=req.source_id,
        risk_check_id=outcome.risk_check_id,
        created_at=now,
        terminal_at=now,
        updated_at=now,
    )
