"""Explicit PAPER liquidation for authorized strategies (PR S / S5.6).

``ActivationService`` is the paper→live promotion flow (ADR 0005) and resolves the LIVE
account everywhere, so its ``deactivate(liquidate=True)`` is inert for a paper-only
strategy. LOW-001 v1.0.2 runs PAPER-only by G7, which would leave it with a normal-exit
repair (S4) and no working safety exit at all.

This is the missing entrypoint. It is a **separate** door onto the same
``StrategyPositionLiquidator``, so:

* ``ActivationService`` keeps its LIVE-only semantics and every existing paper strategy
  keeps its current behaviour — deactivating them still liquidates nothing;
* the mechanics (ownership attribution, broker quantity, current-ticker routing,
  fail-closed refusals) are shared, not reimplemented.

## Authorization is default-deny and explicit

Nothing here infers permission from ``account.mode == PAPER``, and nothing infers it from
a strategy name buried in the liquidator. A caller must be holding a
:class:`PaperLiquidationPolicy` that was constructed with the capability enabled AND names
the strategy. Absent policy, disabled policy, or an unlisted strategy all deny — which is
what keeps this from becoming a platform-wide "close everything on paper" shortcut.

The G1 property is therefore checkable rather than incidental: Account 5 and the momentum
books are denied by the policy, not merely un-called.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.account import Account, AccountMode
from app.db.models.strategy import Strategy
from app.universe.liquidation import LiquidationResult, StrategyPositionLiquidator

logger = structlog.get_logger(__name__)

__all__ = [
    "PaperLiquidationDenied",
    "PaperLiquidationPolicy",
    "PaperStrategyLiquidationService",
]


class PaperLiquidationDenied(PermissionError):
    """The caller is not authorized to liquidate this strategy's PAPER account."""


@dataclass(frozen=True)
class PaperLiquidationPolicy:
    """Which strategies may have their PAPER positions closed automatically.

    Default-deny by construction: ``enabled`` is False and the allow-list is empty, so an
    accidentally-default-constructed policy authorizes nothing. Both must be set
    deliberately at wiring time.
    """

    enabled: bool = False
    strategies: frozenset[str] = field(default_factory=frozenset)

    def permits(self, strategy_name: str) -> bool:
        return self.enabled and strategy_name in self.strategies

    @classmethod
    def for_pr_s(cls) -> PaperLiquidationPolicy:
        """The governed PR-S grant: LOW-001 only, nothing else (v0.3 §11 G4b)."""
        return cls(enabled=True, strategies=frozenset({"low-volatility"}))


class PaperStrategyLiquidationService:
    """Closes a strategy's owned PAPER positions, when explicitly authorized to."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        owned_holdings_provider: Any,
        order_router: Any,
        broker_registry: Any,
        policy: PaperLiquidationPolicy | None = None,
    ) -> None:
        self._session = session
        self._provider = owned_holdings_provider
        self._router = order_router
        self._broker_registry = broker_registry
        self._policy = policy or PaperLiquidationPolicy()

    async def liquidate(self, *, strategy_id: int) -> LiquidationResult:
        """Close the strategy's owned positions on its PAPER account.

        Raises :class:`PaperLiquidationDenied` when the policy does not cover the
        strategy. Returns an empty result — never an exception — when the capability is
        authorized but the environment cannot support it (no paper account, no adapter, no
        provider): those are fail-closed conditions, not permission errors, and the
        distinction matters to an operator reading the outcome.
        """
        strategy = await self._session.get(Strategy, strategy_id)
        if strategy is None:
            raise PaperLiquidationDenied(f"Strategy {strategy_id} not found")
        if not self._policy.permits(strategy.name):
            logger.warning(
                "paper_liquidation_denied",
                strategy_id=strategy_id,
                strategy_name=strategy.name,
                policy_enabled=self._policy.enabled,
            )
            raise PaperLiquidationDenied(
                f"PAPER liquidation is not authorized for strategy '{strategy.name}'"
            )

        account = (
            (
                await self._session.execute(
                    select(Account)
                    .where(Account.user_id == strategy.user_id)
                    .where(Account.mode == AccountMode.paper)
                )
            )
            .scalars()
            .first()
        )
        if account is None:
            logger.warning("paper_liquidation_no_account", strategy_id=strategy_id)
            return LiquidationResult(strategy_id, -1, ())
        if self._provider is None or self._router is None or self._broker_registry is None:
            logger.warning("paper_liquidation_capability_missing", strategy_id=strategy_id)
            return LiquidationResult(strategy_id, account.id, ())

        adapter = self._broker_registry.get(account.id)
        if adapter is None:
            logger.warning("paper_liquidation_no_adapter", strategy_id=strategy_id)
            return LiquidationResult(strategy_id, account.id, ())
        try:
            positions = adapter.get_positions()
        except Exception:
            logger.exception("paper_liquidation_position_fetch_failed", strategy_id=strategy_id)
            return LiquidationResult(strategy_id, account.id, ())

        result = await StrategyPositionLiquidator(self._provider, self._router).liquidate(
            strategy_id=strategy_id,
            user_id=strategy.user_id,
            account_id=account.id,
            broker_positions=positions,
        )
        logger.info(
            "paper_liquidation_complete",
            strategy_id=strategy_id,
            account_id=account.id,
            liquidated=len(result.liquidated),
            excluded=len(result.excluded),
        )
        return result
