"""The one seam that routes an explicit stop/liquidate request (PR S / S5.7).

Before this, neither operator control could express "stop LOW-001 and flatten what it
owns":

* ``POST /strategies/{id}/stop`` works for any status but has no liquidate option;
* ``ActivationService.deactivate(liquidate=True)`` has the option but rejects anything
  that is not LIVE or HALTED, and resolves the LIVE account — LOW-001 runs PAPER.

So the disposal capability built in S5/S5.6 had no caller, and "PR S is the safe rollback
baseline" was not yet true in production.

## The contract

    deactivate(liquidate=False)  -> stop only, no orders
    deactivate(liquidate=True)   -> resolve account mode, then:

        LIVE   -> ActivationService, unchanged semantics
        PAPER  -> PaperLiquidationPolicy -> PaperStrategyLiquidationService

Both branches converge on the shared ``StrategyPositionLiquidator``, so ownership
attribution, broker quantity, current-ticker routing and fail-closed refusals cannot
diverge between them.

## Why routing lives here and nowhere else

Mode routing exists in exactly one place. If a second caller re-derived "is this PAPER?"
it could reach the liquidator without passing the PR-S policy, and the default-deny
authorization would be bypassable by accident rather than by intent. Callers ask this
service; they do not ask the account.

## What must NOT trigger this

A circuit-breaker trip is not a liquidation request. The breaker stops *new* risk while
deliberately preserving risk-reducing activity; redefining a trip as "flatten the book"
would be a major change to platform risk semantics wearing the costume of a bug fix.
Liquidation is an explicit operator or system decision, and it arrives here as one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import StrategyStatus
from app.db.models.account import Account, AccountMode
from app.db.models.strategy import Strategy
from app.services.activation import ActivationService
from app.services.paper_strategy_liquidation import (
    PaperLiquidationDenied,
    PaperLiquidationPolicy,
    PaperStrategyLiquidationService,
)
from app.universe.liquidation import LiquidationResult

logger = structlog.get_logger(__name__)

__all__ = ["StrategyControlService", "StrategyStopOutcome"]

#: Statuses ActivationService is willing to deactivate. Anything else takes the plain
#: engine-unregister stop path.
_ACTIVATION_STATUSES = (StrategyStatus.LIVE, StrategyStatus.HALTED)


@dataclass(frozen=True)
class StrategyStopOutcome:
    strategy_id: int
    stopped: bool
    liquidation_requested: bool
    #: Which branch ran: ``"live"``, ``"paper"``, or ``None`` when no liquidation ran.
    liquidation_route: str | None = None
    #: Structured per-position dispositions from the PAPER branch (S5.6).
    liquidation: LiquidationResult | None = None
    #: Order ids from the LIVE branch, which returns ids rather than dispositions.
    liquidation_order_ids: tuple[int, ...] = ()
    denied_reason: str | None = None


class StrategyControlService:
    """Explicit operator/system control over stopping a strategy, with optional disposal."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        engine: Any = None,
        broker_registry: Any = None,
        order_router: Any = None,
        owned_holdings_provider: Any = None,
        paper_liquidation_policy: PaperLiquidationPolicy | None = None,
    ) -> None:
        self._session = session
        self._engine = engine
        self._broker_registry = broker_registry
        self._order_router = order_router
        self._provider = owned_holdings_provider
        self._policy = paper_liquidation_policy or PaperLiquidationPolicy()

    async def deactivate(
        self, *, strategy_id: int, user_id: int, liquidate: bool = False
    ) -> StrategyStopOutcome:
        """Stop ``strategy_id``, optionally flattening the positions it owns.

        ``liquidate=False`` is the pre-existing behaviour on both branches: stop, no
        orders. Nothing about this service makes a stop liquidate by default.
        """
        strategy = await self._session.get(Strategy, strategy_id)
        if strategy is None:
            raise LookupError(f"Strategy {strategy_id} not found")
        if strategy.user_id != user_id:
            raise PermissionError(f"Strategy {strategy_id} does not belong to user {user_id}")

        if not liquidate:
            await self._stop(strategy)
            return StrategyStopOutcome(strategy_id, stopped=True, liquidation_requested=False)

        mode = await self._account_mode(strategy)
        if mode is AccountMode.live:
            # Unchanged LIVE semantics, including the status guard and the audit entry.
            result = await ActivationService(
                session=self._session,
                broker_registry=self._broker_registry,
                order_router=self._order_router,
                owned_holdings_provider=self._provider,
            ).deactivate(strategy_id=strategy_id, user_id=user_id, liquidate=True)
            return StrategyStopOutcome(
                strategy_id,
                stopped=True,
                liquidation_requested=True,
                liquidation_route="live",
                liquidation_order_ids=tuple(result.get("liquidation_orders") or ()),
            )

        # PAPER. Authorization is the policy's, not this method's, and not the account's:
        # neither `mode is paper` nor the strategy's name alone is sufficient.
        service = PaperStrategyLiquidationService(
            session=self._session,
            owned_holdings_provider=self._provider,
            order_router=self._order_router,
            broker_registry=self._broker_registry,
            policy=self._policy,
        )
        try:
            liquidation = await service.liquidate(strategy_id=strategy_id)
        except PaperLiquidationDenied as exc:
            # Deny the LIQUIDATION, not the stop: the operator asked for two things and is
            # entitled to the one they are authorized for. Silently stopping without
            # saying the disposal was refused would be the dangerous shape.
            logger.warning(
                "strategy_stop_liquidation_denied",
                strategy_id=strategy_id,
                strategy_name=strategy.name,
                reason=str(exc),
            )
            await self._stop(strategy)
            return StrategyStopOutcome(
                strategy_id,
                stopped=True,
                liquidation_requested=True,
                liquidation_route=None,
                denied_reason=str(exc),
            )

        await self._stop(strategy)
        return StrategyStopOutcome(
            strategy_id,
            stopped=True,
            liquidation_requested=True,
            liquidation_route="paper",
            liquidation=liquidation,
            liquidation_order_ids=tuple(liquidation.order_ids),
        )

    # ---- internals ----

    async def _account_mode(self, strategy: Strategy) -> AccountMode:
        """The mode of the account this strategy trades on.

        ``strategies`` has no account FK; the mapping is user + mode. A user with a LIVE
        account is treated as LIVE so an activated strategy keeps the ADR 0005 path.
        """
        modes = (
            (
                await self._session.execute(
                    select(Account.mode).where(Account.user_id == strategy.user_id)
                )
            )
            .scalars()
            .all()
        )
        return AccountMode.live if AccountMode.live in modes else AccountMode.paper

    async def _stop(self, strategy: Strategy) -> None:
        """Stop the strategy itself.

        LIVE/HALTED goes through ActivationService so the status transition and audit
        entry are exactly what they were. Anything else (PAPER, IDLE) unregisters from the
        engine, which is what ``POST /strategies/{id}/stop`` already does.
        """
        if strategy.status in _ACTIVATION_STATUSES:
            await ActivationService(
                session=self._session,
                broker_registry=self._broker_registry,
                order_router=self._order_router,
            ).deactivate(strategy_id=strategy.id, user_id=strategy.user_id, liquidate=False)
            return
        if self._engine is not None:
            await self._engine.unregister(strategy.id, reason="user_stop")
