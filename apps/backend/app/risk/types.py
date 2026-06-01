"""Value objects for the Risk Engine + Order Router boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from app.db.enums import OrderSide, OrderSourceType, OrderType, TimeInForce
from app.risk.reason_codes import ReasonCode


@dataclass(frozen=True)
class OrderRequest:
    """Caller-supplied intent. Pre-validation only; the engine validates substantively."""

    user_id: int
    account_id: int
    symbol_ticker: str
    side: OrderSide
    qty: Decimal
    type: OrderType
    tif: TimeInForce = TimeInForce.DAY
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None
    extended_hours: bool = False
    source_type: OrderSourceType = OrderSourceType.MANUAL
    source_id: str | None = None
    client_order_id: str | None = None
    # P5 §6: typed-ticker confirmation. Required by the OrderRouter when
    # source_type == MANUAL and the account is LIVE; ignored otherwise. Must
    # equal the symbol after normalization (uppercase, stripped).
    confirmation_text: str | None = None


@dataclass(frozen=True)
class RiskOutcome:
    """Engine's decision. ``risk_check_id`` is the persisted row ID."""

    decision: str  # "pass" | "reject" (values of RiskDecision)
    reason_codes: list[ReasonCode] = field(default_factory=list)
    risk_check_id: int | None = None
    # Computed context the router might want without re-querying:
    resolved_symbol_id: int | None = None
    estimated_notional: Decimal | None = None

    @property
    def passed(self) -> bool:
        return self.decision == "pass"
