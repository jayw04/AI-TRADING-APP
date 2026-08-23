"""Strategy-owned current holdings — acquisition provenance composed with the live book.

S2 (:mod:`app.universe.strategy_ownership`) answers *may this strategy claim this permanent
security?* The position store answers *is it held now, and how many shares?* This module is
the only place those two are combined, and it combines them in one direction only::

    owned securities (S2)  ∩  current positions where qty > 0
        = strategy-owned current holdings

It never asks S2 whether something is held, and it never asks the ledger how much exists.
A security with a Strategy-8 BUY from months ago whose position is now flat is **not** a
current holding and does not enter the read set.

## What the result is used for

Exactly one thing: widening **READ** authority inside ``StrategyContext`` so a strategy can
see, price, and therefore exit a holding that is not in its static registration
(LOW-PIT v0.3 §4.7). It is not a buy authorization, it is not ``ctx.symbols``, and it does
not participate in target selection or dispatch. Those separations are what make
"visibility does not confer permission" checkable rather than aspirational.

## Absence is not permission

S2's ``UNCLAIMED`` is a positive classification, so a position missing from S2's output is
not silently "probably ours". Every current position lands in exactly one bucket:

===================  ==========================================================
OWNED                widen READ authority
AMBIGUOUS            excluded, ``ownership_ambiguous``
UNCLAIMED            excluded, ``ownership_unclaimed``
no classification    excluded, ``ownership_evidence_missing``
===================  ==========================================================

The fourth case is the one that matters later: a restored, transferred, or externally
acquired position has no acquisition row at all. Account 6 happens to have Strategy-8
provenance for all 39 of its current holdings today, but that is a fact about Account 6,
not a licence to read "no evidence" as ownership (v0.3 §5.4.2). Every non-OWNED case fails
closed with a stated reason rather than being dropped.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models.position import Position
from app.db.models.symbol import Symbol
from app.universe.strategy_ownership import (
    OwnershipStatus,
    SecurityIdentityResolver,
    StrategyOwnedSecurityResolver,
    market_date,
)

__all__ = [
    "ExcludedHolding",
    "HoldingExclusionReason",
    "OwnedHolding",
    "OwnedHoldings",
    "StrategyOwnedHoldingsProvider",
]


class HoldingExclusionReason(StrEnum):
    """Why a currently-held security was not admitted to this strategy's read scope.

    Every value fails closed. They are distinguished so an operator can tell a
    genuinely-contested holding from one the system simply has no record of.
    """

    #: This strategy acquired it, but so did someone else (S2 AMBIGUOUS).
    OWNERSHIP_AMBIGUOUS = "ownership_ambiguous"
    #: Acquired on this account by someone else, never by us (S2 UNCLAIMED).
    OWNERSHIP_UNCLAIMED = "ownership_unclaimed"
    #: Held, but no acquisition provenance exists at all — restored, transferred, or
    #: externally acquired. Also covers a held ticker whose permanent identity cannot be
    #: established, since we then cannot even pose the ownership question.
    OWNERSHIP_EVIDENCE_MISSING = "ownership_evidence_missing"


@dataclass(frozen=True)
class OwnedHolding:
    """A currently-held security this strategy may unambiguously claim."""

    #: The ticker the position is held under *today* — the broker-plane key. A rename
    #: within one lineage resolves through identity, so this is the current ticker even
    #: when the acquisition was recorded under the old one.
    ticker: str
    security_id: str


@dataclass(frozen=True)
class ExcludedHolding:
    """A currently-held security deliberately kept out of the read scope."""

    ticker: str
    reason: HoldingExclusionReason
    #: Free-text refinement (e.g. the S2 ambiguity reason, or ``identity_unresolved``).
    detail: str | None = None
    #: Permanent identity when it could be established. ``None`` for an unresolved
    #: identity (there is nothing to report) and for a position with no provenance.
    #: Carried so operator diagnostics can name the security, not just today's ticker.
    security_id: str | None = None


@dataclass(frozen=True)
class OwnedHoldings:
    account_id: int
    strategy_id: int
    holdings: tuple[OwnedHolding, ...]
    excluded: tuple[ExcludedHolding, ...]

    @property
    def tickers(self) -> frozenset[str]:
        """Uppercased tickers admitted to the read scope."""
        return frozenset(h.ticker for h in self.holdings)


class StrategyOwnedHoldingsProvider:
    """Composes S2 ownership with the current position book. Read-only.

    Constructed in the ``app.universe`` layer and injected into ``StrategyContext`` as a
    capability, the same seam ``submit_order_fn`` uses. ``StrategyContext`` therefore never
    imports the ownership resolver, the position query, or any identity source — which is
    what keeps ``check_strategy_isolation.sh`` satisfiable once the PR-B resolver adds
    broker imports to this package.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        identity_resolver: SecurityIdentityResolver,
    ) -> None:
        self._session_factory = session_factory
        self._identity = identity_resolver
        self._ownership = StrategyOwnedSecurityResolver(session_factory, identity_resolver)

    @property
    def ready(self) -> bool:
        """Whether attribution can actually answer — i.e. the identity source is provisioned.

        A provider whose resolver has no store returns ``None`` for every identity, so it
        is present but useless. The PR-S readiness assertion checks THIS, not merely that
        an object was injected.
        """
        return bool(getattr(self._identity, "ready", True))

    async def resolve(
        self, *, account_id: int, strategy_id: int, as_of: date | None = None
    ) -> OwnedHoldings:
        """Classify every current holding for ``strategy_id``.

        ``as_of`` is the session the CURRENT positions' identities resolve on, defaulting
        to today's exchange date. Acquisitions resolve on their own fill dates inside the
        ownership layer — the two dates are deliberately different, because a rename means
        the same permanent identity was reached from two different tickers at two
        different times, and that is exactly the case attribution must survive.
        """
        as_of = as_of or market_date(datetime.now(UTC))
        held = await self._held_tickers(account_id)
        if not held:
            return OwnedHoldings(account_id, strategy_id, (), ())

        ownership = await self._ownership.resolve(account_id=account_id, strategy_id=strategy_id)
        by_identity = {s.security_id: s for s in ownership.securities if s.security_id}

        holdings: list[OwnedHolding] = []
        excluded: list[ExcludedHolding] = []
        for ticker in sorted(held):
            identity = self._identity.resolve(ticker, as_of)
            if identity is None:
                # NEVER fall back to ticker equality here. An earlier revision matched the
                # held ticker against the acquisition's tickers when current resolution
                # failed, and the S5.5 integration test caught what that does: a symbol
                # whose lineage ENDED (acquired in March under one issuer, the bare ticker
                # now belonging to another) was matched to its own stale acquisition and
                # admitted. Ticker equality after identity resolution fails is precisely
                # the defect the contract exists to prevent, and it is most tempting
                # exactly at a reuse boundary.
                excluded.append(
                    ExcludedHolding(
                        ticker,
                        HoldingExclusionReason.OWNERSHIP_AMBIGUOUS,
                        "identity_unresolved",
                    )
                )
                continue

            # Match on permanent identity, so a position held under a renamed ticker finds
            # the acquisition recorded under the old one.
            security = by_identity.get(identity)

            if security is None:
                excluded.append(
                    ExcludedHolding(ticker, HoldingExclusionReason.OWNERSHIP_EVIDENCE_MISSING, None)
                )
            elif security.status is OwnershipStatus.OWNED:
                assert security.security_id is not None  # OWNED implies resolved identity
                holdings.append(OwnedHolding(ticker, security.security_id))
            elif security.status is OwnershipStatus.AMBIGUOUS:
                excluded.append(
                    ExcludedHolding(
                        ticker,
                        HoldingExclusionReason.OWNERSHIP_AMBIGUOUS,
                        security.reason.value if security.reason else None,
                        security_id=security.security_id,
                    )
                )
            else:
                excluded.append(
                    ExcludedHolding(
                        ticker,
                        HoldingExclusionReason.OWNERSHIP_UNCLAIMED,
                        security_id=security.security_id,
                    )
                )

        return OwnedHoldings(account_id, strategy_id, tuple(holdings), tuple(excluded))

    async def readable_tickers(
        self, *, account_id: int, strategy_id: int, as_of: date | None = None
    ) -> frozenset[str]:
        """Just the admitted tickers — the shape ``StrategyContext`` consumes."""
        resolution = await self.resolve(account_id=account_id, strategy_id=strategy_id, as_of=as_of)
        return resolution.tickers

    async def _held_tickers(self, account_id: int) -> set[str]:
        """Tickers with a live long position on the account.

        ``qty > 0`` per v0.3 §5.4: the read scope exists to manage holdings the strategy
        has, and a flat security is not one — a Strategy-8 BUY from months ago whose
        position has since gone to zero must not re-enter the read set. Shorts are out of
        scope (``allow_short`` is false on every account).
        """
        stmt = (
            select(Symbol.ticker)
            .join(Position, Position.symbol_id == Symbol.id)
            .where(Position.account_id == account_id, Position.qty > Decimal(0))
        )
        async with self._session_factory() as session:
            rows = (await session.execute(stmt)).scalars().all()
        return {t.upper() for t in rows}
