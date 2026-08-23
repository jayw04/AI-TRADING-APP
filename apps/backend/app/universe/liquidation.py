"""Strategy position liquidation — shared mechanics, no policy (PR S / S5.6).

Both exit-of-last-resort paths run through here:

                        StrategyPositionLiquidator
                       /                          \\
    ActivationService                              PAPER entrypoint
    (existing LIVE semantics)                      (explicit authorization)
            |                                              |
        LIVE only                                    LOW-001 PAPER only

What this component does: resolve which currently-held securities the strategy
unambiguously owns, take the quantity from the broker position, and submit closing
orders at the security's *current* ticker. What it deliberately does **not** do: decide
whether the caller is allowed to liquidate this account at all. That is policy, it differs
between the two entrypoints, and burying it here — as a mode check or a strategy-name
special case — is how a shared service quietly turns previously inert paper deactivations
into real orders platform-wide.

So: mechanics here, authorization at the entrypoint.

Results are structured rather than a count of submitted orders. Every position the broker
reports gets a disposition and, where relevant, a typed reason, so S6 can present operator
diagnostics for the normal exit path and both liquidation paths from one classification
instead of rediscovering it per caller.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any

import structlog

from app.db.enums import OrderSide, OrderSourceType, OrderType, TimeInForce
from app.universe.owned_holdings import HoldingExclusionReason, StrategyOwnedHoldingsProvider

logger = structlog.get_logger(__name__)

__all__ = [
    "LiquidationDisposition",
    "LiquidationLine",
    "LiquidationResult",
    "StrategyPositionLiquidator",
]


class LiquidationDisposition(StrEnum):
    """What happened to one currently-held position."""

    LIQUIDATED = "liquidated"
    EXCLUDED_AMBIGUOUS = "excluded_ambiguous"
    EXCLUDED_UNCLAIMED = "excluded_unclaimed"
    #: Held ticker whose permanent identity could not be established for this session.
    #: Behaviourally a fail-closed ambiguity; broken out because an operator needs to tell
    #: "two owners" from "we cannot say what this security is".
    EXCLUDED_IDENTITY_UNRESOLVED = "excluded_identity_unresolved"
    EXCLUDED_EVIDENCE_MISSING = "excluded_evidence_missing"
    #: Submission failed for this symbol. Other symbols still proceed.
    ERROR = "error"


@dataclass(frozen=True)
class LiquidationLine:
    ticker: str
    disposition: LiquidationDisposition
    security_id: str | None = None
    #: Broker quantity closed. Never derived from the order ledger (v0.3 §4.8).
    qty: Decimal | None = None
    order_id: int | None = None
    detail: str | None = None


@dataclass(frozen=True)
class LiquidationResult:
    strategy_id: int
    account_id: int
    lines: tuple[LiquidationLine, ...]

    @property
    def order_ids(self) -> list[int]:
        return [
            line.order_id
            for line in self.lines
            if line.disposition is LiquidationDisposition.LIQUIDATED and line.order_id
        ]

    @property
    def liquidated(self) -> tuple[LiquidationLine, ...]:
        return tuple(x for x in self.lines if x.disposition is LiquidationDisposition.LIQUIDATED)

    @property
    def excluded(self) -> tuple[LiquidationLine, ...]:
        return tuple(
            x
            for x in self.lines
            if x.disposition
            not in (LiquidationDisposition.LIQUIDATED, LiquidationDisposition.ERROR)
        )


_EXCLUSION_MAP = {
    HoldingExclusionReason.OWNERSHIP_UNCLAIMED: LiquidationDisposition.EXCLUDED_UNCLAIMED,
    HoldingExclusionReason.OWNERSHIP_EVIDENCE_MISSING: (
        LiquidationDisposition.EXCLUDED_EVIDENCE_MISSING
    ),
}


class StrategyPositionLiquidator:
    """Closes the positions a strategy unambiguously owns. Authorization is the caller's job.

    Orders are MANUAL-sourced with ``confirmation_text`` set: MANUAL bypasses the §6
    per-strategy cooldown and the §7 strategy-status guard, so a close still works for a
    HALTED strategy. They remain subject to the risk gates and are audited like any other
    order — this is not a bypass of the risk engine, only of the guards that exist to stop
    a *misbehaving strategy* from trading.
    """

    def __init__(self, owned_holdings_provider: StrategyOwnedHoldingsProvider, order_router: Any):
        self._provider = owned_holdings_provider
        self._router = order_router

    async def liquidate(
        self,
        *,
        strategy_id: int,
        user_id: int,
        account_id: int,
        broker_positions: list[dict[str, Any]],
    ) -> LiquidationResult:
        """Close every OWNED position the broker reports. Everything else is reported, not sold.

        ``broker_positions`` is the broker's own view (``[{"symbol", "qty"}, ...]``); the
        broker is the authority on what exists and how much. Ownership decides only
        *whether we may act on it*.
        """
        from app.risk.types import OrderRequest

        try:
            owned = await self._provider.resolve(account_id=account_id, strategy_id=strategy_id)
        except Exception:
            # Fail CLOSED. An attribution outage must never authorise closing positions of
            # unknown ownership; close nothing and surface the failure.
            logger.exception(
                "liquidation_ownership_resolution_failed",
                strategy_id=strategy_id,
                account_id=account_id,
            )
            return LiquidationResult(strategy_id, account_id, ())

        claimable = {h.ticker: h for h in owned.holdings}
        excluded_by_ticker = {e.ticker: e for e in owned.excluded}

        lines: list[LiquidationLine] = []
        for pos in broker_positions:
            symbol = (pos.get("symbol") or "").upper() if isinstance(pos, dict) else ""
            qty_raw = pos.get("qty") if isinstance(pos, dict) else None
            if not symbol or qty_raw is None:
                continue
            qty = Decimal(str(qty_raw))
            if qty == 0:
                continue

            holding = claimable.get(symbol)
            if holding is None:
                exclusion = excluded_by_ticker.get(symbol)
                lines.append(self._excluded_line(symbol, exclusion))
                continue

            side = OrderSide.SELL if qty > 0 else OrderSide.BUY
            req = OrderRequest(
                user_id=user_id,
                account_id=account_id,
                symbol_ticker=symbol,  # the CURRENT broker ticker, not the acquisition's
                side=side,
                qty=abs(qty),
                type=OrderType.MARKET,
                tif=TimeInForce.DAY,
                source_type=OrderSourceType.MANUAL,
                confirmation_text=symbol,
            )
            try:
                order = await self._router.submit(req)
            except Exception:
                logger.exception(
                    "liquidation_submit_failed", strategy_id=strategy_id, symbol=symbol
                )
                lines.append(
                    LiquidationLine(symbol, LiquidationDisposition.ERROR, holding.security_id)
                )
                continue
            lines.append(
                LiquidationLine(
                    symbol,
                    LiquidationDisposition.LIQUIDATED,
                    holding.security_id,
                    qty=abs(qty),
                    order_id=getattr(order, "id", None),
                )
            )

        for line in lines:
            if line.disposition is not LiquidationDisposition.LIQUIDATED:
                logger.warning(
                    "liquidation_position_not_attributable",
                    strategy_id=strategy_id,
                    account_id=account_id,
                    symbol=line.ticker,
                    disposition=line.disposition.value,
                    detail=line.detail,
                )
        return LiquidationResult(strategy_id, account_id, tuple(lines))

    @staticmethod
    def _excluded_line(symbol: str, exclusion: Any | None) -> LiquidationLine:
        """Classify a position we may not close. Absence of a record is itself a reason."""
        if exclusion is None:
            # The broker reports it but the provider never saw it — e.g. the local
            # positions cache has not synced. Not ours to close on that basis.
            return LiquidationLine(
                symbol,
                LiquidationDisposition.EXCLUDED_EVIDENCE_MISSING,
                detail="not_in_position_store",
            )
        if exclusion.reason is HoldingExclusionReason.OWNERSHIP_AMBIGUOUS:
            disposition = (
                LiquidationDisposition.EXCLUDED_IDENTITY_UNRESOLVED
                if exclusion.detail == "identity_unresolved"
                else LiquidationDisposition.EXCLUDED_AMBIGUOUS
            )
            return LiquidationLine(symbol, disposition, detail=exclusion.detail)
        return LiquidationLine(
            symbol,
            _EXCLUSION_MAP[exclusion.reason],
            detail=exclusion.detail,
        )
