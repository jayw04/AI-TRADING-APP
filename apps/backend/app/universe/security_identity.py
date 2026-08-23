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
        self._readiness: bool | None = None

    def current_identity_date(self) -> date | None:
        """The date "who is this security *now*" should be asked on.

        The identity frontier of the data, not the wall clock. See
        ``FactorDataStore.identity_coverage_date`` — asking on today's calendar date makes
        every interval look closed on a weekend or a pre-ingest morning, which is exactly
        how S8.6 failed with a perfectly healthy store.
        """
        if self._store is None:
            return None
        try:
            return self._store.identity_coverage_date()
        except Exception:
            logger.exception("security_identity_coverage_date_failed")
            return None

    @property
    def ready(self) -> bool:
        """Whether this resolver can actually ANSWER — not merely whether a store exists.

        ``store is not None`` was the earlier test and it was insufficient in the way that
        matters: a provisioned-but-unusable identity source resolves every ticker to
        ``None``, ownership silently becomes "nothing is ours", and the whole thing reads
        as healthy. The S8.6 deployment proved it — ``ready`` was True while not a single
        Account-6 holding could be attributed.

        So readiness resolves a real symbol end to end. It fails for: an absent store,
        empty identity data, all-null or otherwise unresolvable identity data, and an
        unestablishable current identity date. Cached — this is a startup gate, not a
        per-call check.
        """
        if self._readiness is not None:
            return self._readiness
        self._readiness = self._probe()
        return self._readiness

    def _probe(self) -> bool:
        if self._store is None:
            logger.warning("security_identity_not_ready", reason="no_store")
            return False
        as_of = self.current_identity_date()
        if as_of is None:
            logger.warning("security_identity_not_ready", reason="no_identity_coverage_date")
            return False
        try:
            probe = self._store.identity_probe_ticker(as_of)
        except Exception:
            logger.exception("security_identity_not_ready", reason="probe_query_failed")
            return False
        if not probe:
            logger.warning(
                "security_identity_not_ready", reason="no_resolvable_identity", as_of=str(as_of)
            )
            return False
        resolved = self.resolve(probe, as_of)
        if resolved is None:
            logger.warning(
                "security_identity_not_ready",
                reason="probe_did_not_resolve",
                probe=probe,
                as_of=str(as_of),
            )
            return False
        logger.info("security_identity_ready", probe=probe, as_of=str(as_of), permaticker=resolved)
        return True

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
    strategy_name: str,
    owned_holdings_provider: Any | None,
    *,
    paper_liquidation_policy: Any | None = None,
) -> None:
    """Raise if a PR-S safety-critical strategy would start without ownership attribution.

    Static strategies are unaffected: an absent capability leaves their legacy behaviour
    intact. Only the strategies listed above treat absence as fatal, because for them
    "registered-only" is precisely the defect PR S repairs — and a deployment where
    LOW-001 looks healthy while S3-S5 silently run their fallback paths is the specific
    failure this prevents.

    Checks the capability can actually ANSWER, not merely that an object was injected: a
    provider whose identity source is unprovisioned resolves nothing.

    Runtime lookup failures remain fail-closed-to-registered-only. Only *initialization*
    absence is fatal; that distinction is deliberate (v0.3 §5.5).
    """
    if strategy_name not in PR_S_SAFETY_CRITICAL_STRATEGIES:
        return
    missing = []
    if owned_holdings_provider is None:
        missing.append("owned_holdings_provider")
    elif not getattr(owned_holdings_provider, "ready", False):
        missing.append("security_identity_resolver")
    if paper_liquidation_policy is not None and not paper_liquidation_policy.permits(strategy_name):
        missing.append("paper_liquidation_capability")
    if missing:
        raise PrSCapabilityUnavailable(
            f"{strategy_name} requires the PR-S ownership capability; not ready: "
            + ", ".join(missing)
        )


class PrSCapabilityUnavailable(RuntimeError):
    """A PR-S safety-critical strategy cannot start without ownership attribution."""
