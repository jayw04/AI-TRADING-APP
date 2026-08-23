"""Concrete permanent-security-identity adapter over the factor store (PR S / S5.5).

Implements the ``SecurityIdentityResolver`` protocol against the governed
``tickers`` slice, which is the only place ``permaticker`` — the vendor permanent
identifier behind ``PERMATICKER_EFFECTIVE_INTERVAL_V1`` — actually lives.

## Why this is its own module

``strategy_ownership`` and ``owned_holdings`` depend on the *protocol*, never on a data
source, so the identity rule stays substitutable and those modules carry no factor-store
import. This adapter is where the research-plane coupling is confined, and it is
deliberately kept apart from the future ``dynamic_symbol_resolver`` (PR B), which couples
to the *broker*. One module importing both the factor store and the broker layer would
make the two planes inseparable at exactly the point where the isolation invariants care.

    security_identity        -> factor store `tickers` (identity data)
    dynamic_symbol_resolver  -> broker asset metadata   (eligibility data)

The engine/bootstrap composes them; neither imports the other.

## Resolution is dated, and failure is silence

``resolve(ticker, as_of)`` answers *which security did this symbol denote on that date*.
It returns ``None`` — never a guess — when the store has no row, ``permaticker`` is NULL
(an unrefreshed store), the effective bounds are missing, ``as_of`` falls outside them, or
more than one row claims the ticker. Callers translate ``None`` into
``identity_unresolved`` and fail closed. There is deliberately no ticker-equality
fallback: that fallback is the defect the contract exists to prevent, and it would be most
tempting exactly where it is most dangerous — at a reuse boundary.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

__all__ = [
    "PR_S_SAFETY_CRITICAL_STRATEGIES",
    "FactorStoreSecurityIdentityResolver",
    "PrSCapabilityUnavailable",
    "assert_pr_s_capability_ready",
]


class FactorStoreSecurityIdentityResolver:
    """Resolves ``(ticker, as_of)`` to a permaticker via a read-only factor store.

    ``store`` is a ``FactorDataStore`` (typed loosely so this module needs no import of
    the research plane at definition time). ``None`` means the store is not provisioned —
    every lookup then fails closed, which is the correct posture: an unresolvable identity
    must never be silently downgraded to ticker equality.

    Results are memoised per ``(ticker, as_of)``. The underlying ``tickers`` slice is
    immutable for the life of a read-only store handle, and a rebalance resolves the same
    handful of symbols repeatedly across a 200-symbol dispatch.
    """

    def __init__(self, store: Any | None) -> None:
        self._store = store
        self._cache: dict[tuple[str, date], str | None] = {}

    @property
    def ready(self) -> bool:
        """Whether a store is provisioned at all. Used by the LOW-001 readiness assertion."""
        return self._store is not None

    def resolve(self, ticker: str, as_of: date) -> str | None:
        if self._store is None:
            return None
        key = (ticker.upper(), as_of)
        if key in self._cache:
            return self._cache[key]
        try:
            value = self._store.permaticker_asof(ticker, as_of)
        except Exception:
            # A store error is an unresolved identity, not an exception the ownership
            # layer should handle differently from "the vendor has no answer". Both fail
            # closed; logging keeps the distinction visible to an operator.
            logger.exception("security_identity_lookup_failed", ticker=ticker, as_of=str(as_of))
            value = None
        self._cache[key] = value
        return value


#: Strategies whose PR-S safety repair (owned-holding discovery, exit and liquidation)
#: is load-bearing. For these, an ABSENT capability at startup is a deployment failure,
#: not a quiet degradation: PR S could otherwise deploy green while none of the repair it
#: exists for actually operates. Runtime lookup failures still fail closed to
#: registered-only behaviour — that distinction is deliberate (v0.3 §5.5).
PR_S_SAFETY_CRITICAL_STRATEGIES = frozenset({"low-volatility"})


def assert_pr_s_capability_ready(
    strategy_name: str, identity_resolver: Any | None, owned_holdings_provider: Any | None
) -> None:
    """Raise if a PR-S safety-critical strategy would start without ownership attribution.

    Static strategies are unaffected: absent capability leaves their legacy behaviour
    intact. Only the strategies listed above treat absence as fatal, because for them
    "registered-only" is precisely the defect PR S repairs.
    """
    if strategy_name not in PR_S_SAFETY_CRITICAL_STRATEGIES:
        return
    missing = []
    if owned_holdings_provider is None:
        missing.append("owned_holdings_provider")
    if identity_resolver is None or not getattr(identity_resolver, "ready", False):
        missing.append("identity_resolver")
    if missing:
        raise PrSCapabilityUnavailable(
            f"{strategy_name} requires the PR-S ownership capability; not ready: "
            + ", ".join(missing)
        )


class PrSCapabilityUnavailable(RuntimeError):
    """A PR-S safety-critical strategy cannot start without ownership attribution."""
