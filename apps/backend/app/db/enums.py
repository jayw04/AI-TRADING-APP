"""Trading-domain enums.

Every enum is a `StrEnum` so it serializes naturally to strings in JSON and
maps cleanly to a VARCHAR column in SQLite (we use `native_enum=False` in the
model declarations).
"""

from __future__ import annotations

from enum import StrEnum


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class TimeInForce(StrEnum):
    DAY = "day"
    GTC = "gtc"  # good til canceled
    IOC = "ioc"  # immediate or cancel
    FOK = "fok"  # fill or kill


class OrderStatus(StrEnum):
    """Internal order lifecycle.

    Happy path:
        PENDING_RISK -> PENDING_SUBMIT -> SUBMITTED
            -> PARTIALLY_FILLED -> FILLED       (terminal)

    Other terminal states: CANCELED, EXPIRED, REJECTED, REPLACED.

    Alpaca's own order statuses (new, pending_new, accepted, ...) are mapped
    to these by the trade-update consumer in Session 5.
    """

    PENDING_RISK = "pending_risk"
    PENDING_SUBMIT = "pending_submit"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    EXPIRED = "expired"
    REJECTED = "rejected"
    REPLACED = "replaced"


# Terminal states — orders in these states never transition again.
TERMINAL_ORDER_STATUSES = frozenset(
    {
        OrderStatus.FILLED,
        OrderStatus.CANCELED,
        OrderStatus.EXPIRED,
        OrderStatus.REJECTED,
        OrderStatus.REPLACED,
    }
)


class OrderSourceType(StrEnum):
    """Who initiated the order. Audited on every order row."""

    MANUAL = "manual"
    STRATEGY = "strategy"
    AGENT_STRATEGY = "agent_strategy"  # B3 in Implementation Plan §13.3
    AGENT_PROPOSAL = "agent_proposal"  # B2 approved-by-human
    PINE = "pine"  # webhook from TradingView


class RiskDecision(StrEnum):
    PASS = "pass"
    REJECT = "reject"


class RiskScopeType(StrEnum):
    """Scope at which a RiskLimits row applies.

    For P1 only GLOBAL is used. STRATEGY and AGENT_SESSION become relevant in
    P2 and P3 respectively; their referenced tables don't exist yet, so the
    risk_limits.scope_id column is a bare INTEGER for now (no FK).
    """

    GLOBAL = "global"
    ACCOUNT = "account"
    STRATEGY = "strategy"
    AGENT_SESSION = "agent_session"
