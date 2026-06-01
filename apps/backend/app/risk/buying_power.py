"""Pre-trade buying-power check (P5 §5), LIVE-only.

For LIVE: calls BrokerAdapter.get_account() to read live buying power.
For PAPER: skipped by the caller (Alpaca paper enforces buying power broker-side;
a round-trip on every paper order would slow paper smoke without benefit).

Dormant in §5: the OrderRouter refuses LIVE accounts with BrokerModeError before
the risk engine runs, so this check is not reached at runtime until P5 §7 opens
live order submission. It is implemented and tested now so §7 inherits it.

Fail-open posture (Notes & Gotchas #14): on any adapter error we return
sufficient=True and let Alpaca be the authoritative buying-power check. The
adapter is sync and returns dict[str, Any] (Session 2 v1.0).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import structlog

from app.db.enums import OrderSide, OrderType
from app.db.models.account import Account

logger = structlog.get_logger(__name__)


# Estimated worst-case fill premium over the reference price for market/stop
# orders. 1% is generous for liquid US equities.
MARKET_SLIPPAGE_BUFFER = Decimal("0.01")


@dataclass
class BuyingPowerDecision:
    sufficient: bool
    required_notional: Decimal
    available_buying_power: Decimal
    rejection_reason: str | None = None


class BuyingPowerChecker:
    def __init__(self, *, broker_registry: Any, bar_cache: Any = None) -> None:
        self._broker_registry = broker_registry
        self._bar_cache = bar_cache

    async def check(self, account: Account, request: Any) -> BuyingPowerDecision:
        # Sells never consume buying power.
        if request.side == OrderSide.SELL:
            return BuyingPowerDecision(
                sufficient=True,
                required_notional=Decimal("0"),
                available_buying_power=Decimal("0"),
            )

        required = await self._estimate_worst_case_notional(request)
        adapter = self._broker_registry.get(account.id) if self._broker_registry else None
        if adapter is None:
            return BuyingPowerDecision(
                sufficient=True,
                required_notional=required,
                available_buying_power=Decimal("0"),
                rejection_reason="No broker adapter — deferred to broker",
            )
        try:
            snap = adapter.get_account()  # sync, dict[str, Any]
        except Exception as exc:
            logger.warning(
                "buying_power_check_failed_open", account_id=account.id, error=str(exc)
            )
            return BuyingPowerDecision(
                sufficient=True,
                required_notional=required,
                available_buying_power=Decimal("0"),
                rejection_reason=f"Broker unreachable for buying-power check: {exc}",
            )

        available = Decimal(str(snap.get("buying_power", "0")))
        if available < required:
            return BuyingPowerDecision(
                sufficient=False,
                required_notional=required,
                available_buying_power=available,
                rejection_reason=(
                    f"INSUFFICIENT_BUYING_POWER: need ${required} "
                    f"(worst-case estimate), have ${available}."
                ),
            )
        return BuyingPowerDecision(
            sufficient=True,
            required_notional=required,
            available_buying_power=available,
        )

    async def _estimate_worst_case_notional(self, request: Any) -> Decimal:
        qty = Decimal(str(request.qty))
        if request.type in (OrderType.LIMIT, OrderType.STOP_LIMIT):
            return Decimal(str(request.limit_price)) * qty
        if request.type == OrderType.STOP:
            buffer = Decimal("1") + MARKET_SLIPPAGE_BUFFER
            return Decimal(str(request.stop_price)) * qty * buffer
        # MARKET: use the latest cached bar close.
        last_price = await self._fetch_latest_price(request.symbol_ticker)
        if last_price is None:
            return Decimal("0")  # fail open
        buffer = Decimal("1") + MARKET_SLIPPAGE_BUFFER
        return last_price * qty * buffer

    async def _fetch_latest_price(self, symbol: str) -> Decimal | None:
        if self._bar_cache is None:
            return None
        try:
            bar = await self._bar_cache.get_latest_bar(symbol)
            if bar is None:
                return None
            return Decimal(str(bar.get("c") if isinstance(bar, dict) else bar.close))
        except Exception:
            return None
