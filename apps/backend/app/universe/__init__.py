"""Universe resolution — what a strategy may claim, and (later) what it may execute.

Two concerns live here, deliberately as separate modules:

* ``strategy_ownership`` (PR S) — **historical acquisition provenance**. Which permanent
  securities may a strategy claim as ones *it* acquired on an account? Read-only over the
  order/fill ledger. Answers nothing about quantity, current holding status, or eligibility.
* ``dynamic_symbol_resolver`` (PR B, not yet present) — **live broker eligibility**. Can a
  research-selected symbol be executed right now?

They are conceptually different questions — one looks backwards at the ledger, one looks
outwards at the broker — and they stay in different modules even though Dynamic PIT consumes
both (LOW-PIT v0.3 §5.3).

This package exists outside ``app/strategies/`` because ``check_strategy_isolation.sh``
forbids strategy-plane code from importing ``app.brokers``, and the PR-B resolver must read
broker asset metadata. The engine injects these into ``StrategyContext`` the same way it
injects ``submit_order_fn``; strategy code never imports a broker SDK.
"""

from app.universe.strategy_ownership import (
    SECURITY_IDENTITY_CONTRACT,
    AmbiguityReason,
    OwnedSecurity,
    OwnershipResolution,
    OwnershipStatus,
    SecurityIdentityResolver,
    StrategyOwnedSecurityResolver,
)

__all__ = [
    "SECURITY_IDENTITY_CONTRACT",
    "AmbiguityReason",
    "OwnedSecurity",
    "OwnershipResolution",
    "OwnershipStatus",
    "SecurityIdentityResolver",
    "StrategyOwnedSecurityResolver",
]
