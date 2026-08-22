"""Strategy acquisition provenance — which permanent securities a strategy may claim.

This module answers exactly one question, and refuses to answer several adjacent ones:

    Which permanent securities may strategy <id> claim as historically acquired
    on account <id>?

It does **not** answer how many shares exist, whether the security is currently held,
whether it may be bought, or which ticker it trades under today. Those belong to later
layers (LOW-PIT v0.3 §5.4). Keeping the boundary sharp is the point: the caller composes

    owned securities  ∩  current broker positions where qty > 0
        = strategy-owned current holdings

and the *broker* remains the sole authority on existence and quantity.

## Why quantity is not derivable here, ever

LOW-PIT v0.3 §4.8 makes this a non-negotiable invariant:

    Order provenance is authoritative for WHICH strategy may claim a security.
    The broker position is authoritative for HOW MUCH of it exists now.
    Neither may substitute for the other.

That is not a stylistic preference; it was measured. On Account 6, 42 MANUAL SELL orders
filled on 2026-07-07 consumed shares LOW-001 had acquired, with no rule anywhere in the
system saying whose shares a manual sell consumes. Netting the strategy's own fills
therefore disagrees with the live position on 41 of 43 tickers — and goes *negative* on
one (AXP: the strategy sold shares it never bought under its own ``source_id``). A
reconstruction would be confidently wrong, which is worse than declining to answer.

So this module never sums quantities. ``tests/universe/test_strategy_ownership.py``
enforces that structurally as well as behaviourally.

## Identity is permanent, the ticker is an attribute

The durable key is the vendor permanent identifier plus its effective interval
(``PERMATICKER_EFFECTIVE_INTERVAL_V1``, owner ruling 2026-07-29, see
``app/validation/security_lineage.py``). A ticker that is renamed within one lineage is
the *same* security and must resolve to one owned entry; a ticker reused across lineages
is *different* securities and must not be merged.

Identity resolution is injected rather than imported. That keeps this module free of any
factor-store dependency, makes the lineage rule substitutable, and confines the
research-plane coupling to whichever concrete resolver the engine wires in. A security
whose identity cannot be resolved **fails closed** (``identity_unresolved``) rather than
silently falling back to ticker-as-identity — that fallback is precisely the defect the
identity contract exists to prevent.

## Ambiguity is an outcome, not an error

Ownership is *unambiguous* only when this strategy is the sole acquirer of the security on
the account. Competing acquisition — another strategy, or a non-strategy BUY — means the
current broker quantity may contain shares this strategy did not acquire, and no rule
exists to apportion them. The security is then ``AMBIGUOUS`` and every attribution-dependent
automated operation must decline to act on it (v0.3 §5.4.1). Never guess; never default to
"probably ours"; never drop it silently.

A MANUAL **SELL** is not ambiguity. It disposes of shares rather than creating a competing
claim. It is exactly why quantity cannot be reconstructed, and exactly not a reason to
disown the security.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.enums import OrderSide, OrderSourceType
from app.db.models.fill import Fill
from app.db.models.order import Order
from app.db.models.symbol import Symbol

#: The governed security-identity contract this resolver keys on (owner ruling 2026-07-29).
#: Re-exported from the lineage module so a future change to the rule cannot leave this
#: module silently asserting the old one.
from app.validation.security_lineage import SECURITY_IDENTITY_CONTRACT

__all__ = [
    "SECURITY_IDENTITY_CONTRACT",
    "AmbiguityReason",
    "OwnedSecurity",
    "OwnershipResolution",
    "OwnershipStatus",
    "SecurityIdentityResolver",
    "StrategyOwnedSecurityResolver",
]


class OwnershipStatus(StrEnum):
    """This strategy's claim on a security that was acquired on the account."""

    #: This strategy is the sole acquirer. Safe for attribution-dependent automation.
    OWNED = "owned"
    #: This strategy acquired it, but so did someone else. Fail closed.
    AMBIGUOUS = "ambiguous"
    #: Acquired on this account, but not by this strategy. Not ours; not an error.
    UNCLAIMED = "unclaimed"


class AmbiguityReason(StrEnum):
    """Why a security this strategy acquired cannot be attributed to it cleanly."""

    #: Another strategy_id also has qualifying acquisition provenance here.
    COMPETING_STRATEGY_ACQUISITION = "competing_strategy_acquisition"
    #: A MANUAL / AGENT / PINE BUY filled on this account+security, so the live
    #: quantity may contain shares this strategy did not acquire.
    NON_STRATEGY_ACQUISITION = "non_strategy_acquisition"
    #: The permanent security identity could not be established. Never guess from the
    #: ticker — reuse across lineages is exactly what the identity contract prevents.
    IDENTITY_UNRESOLVED = "identity_unresolved"


class SecurityIdentityResolver(Protocol):
    """Maps an observed ticker to its permanent security identity.

    Returns ``None`` when the identity cannot be established (unknown ticker, a lineage
    gap, a reuse boundary inside the relevant interval). ``None`` must fail closed at the
    call site — it is never an invitation to fall back to the ticker.
    """

    def resolve(self, ticker: str) -> str | None:  # pragma: no cover - protocol
        ...


@dataclass(frozen=True)
class OwnedSecurity:
    """One security acquired on the account, and this strategy's claim on it.

    Deliberately carries **no quantity field**. There is nothing to put in one: the
    ledger cannot supply it (§4.8) and the broker position is the authority. A caller
    that wants a quantity must read the position.
    """

    #: Permanent security identity — the durable key. ``None`` only when unresolved,
    #: in which case ``status`` is AMBIGUOUS / IDENTITY_UNRESOLVED.
    security_id: str | None
    #: The identity contract this ``security_id`` was minted under.
    identity_contract: str
    #: Observed tickers for this identity, sorted. An *attribute* of the identity — a
    #: rename within one lineage yields one entry here with two tickers, not two entries.
    tickers: tuple[str, ...]
    status: OwnershipStatus
    #: Set when ``status`` is AMBIGUOUS; ``None`` otherwise.
    reason: AmbiguityReason | None
    #: Filled BUY orders by THIS strategy that establish the claim, oldest first.
    acquisition_order_ids: tuple[int, ...]
    #: Distinct ``"<source_type>:<source_id>"`` acquirers seen on this security, sorted.
    #: Includes this strategy. Present on every status so an operator can see the basis.
    acquiring_sources: tuple[str, ...]
    first_acquired_at: datetime | None
    last_acquired_at: datetime | None

    @property
    def is_claimable(self) -> bool:
        """True only for an unambiguous claim by this strategy."""
        return self.status is OwnershipStatus.OWNED


@dataclass(frozen=True)
class OwnershipResolution:
    """Every security acquired on the account, classified for one strategy."""

    account_id: int
    strategy_id: int
    securities: tuple[OwnedSecurity, ...]

    @property
    def owned(self) -> tuple[OwnedSecurity, ...]:
        return tuple(s for s in self.securities if s.status is OwnershipStatus.OWNED)

    @property
    def ambiguous(self) -> tuple[OwnedSecurity, ...]:
        return tuple(s for s in self.securities if s.status is OwnershipStatus.AMBIGUOUS)

    @property
    def unclaimed(self) -> tuple[OwnedSecurity, ...]:
        return tuple(s for s in self.securities if s.status is OwnershipStatus.UNCLAIMED)

    @property
    def owned_tickers(self) -> frozenset[str]:
        """Uppercased tickers of unambiguously owned securities.

        A convenience for callers that still key on ticker at the execution boundary
        (``symbols.ticker`` is the broker-plane key). The *ownership decision* was made on
        permanent identity; this only projects it back down.
        """
        return frozenset(t for s in self.owned for t in s.tickers)


class StrategyOwnedSecurityResolver:
    """Read-only resolver over the order/fill ledger. Writes nothing, sums nothing.

    A **qualifying acquisition** is an order that is all of:

    * ``account_id`` == the target account;
    * ``source_type`` == ``STRATEGY`` and ``source_id`` == ``str(strategy_id)``;
    * ``side`` == ``BUY``;
    * has at least one fill.

    The fill requirement is a deliberate strictness the bare provenance rule does not
    state. A REJECTED buy acquired nothing — Account 6 has exactly such a HON order — and
    treating it as provenance would over-claim. Requiring a fill can only ever
    *under*-claim, which surfaces as UNCLAIMED and fails closed; over-claiming would
    silently attribute someone else's shares. Note this is an EXISTENCE test, not a sum:
    §4.8 forbids deriving quantity, not observing that an acquisition occurred.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        identity_resolver: SecurityIdentityResolver,
    ) -> None:
        self._session_factory = session_factory
        self._identity = identity_resolver

    async def resolve(self, *, account_id: int, strategy_id: int) -> OwnershipResolution:
        """Classify every security acquired on ``account_id`` for ``strategy_id``.

        Securities never acquired on this account do not appear at all. Securities
        acquired only by others appear as UNCLAIMED — a positive statement that they are
        not ours, which is more useful downstream than an absence.
        """
        rows = await self._acquisitions(account_id)

        # Group by permanent identity, NOT by ticker: a rename inside one lineage must
        # collapse to a single security. Unresolvable tickers are grouped under their own
        # sentinel key so two unrelated unresolved names never merge into one entry.
        by_identity: dict[tuple[bool, str], list[_Acquisition]] = {}
        for row in rows:
            sid = self._identity.resolve(row.ticker)
            key = (sid is not None, sid if sid is not None else f"\0unresolved:{row.ticker}")
            by_identity.setdefault(key, []).append(row)

        mine = f"{OrderSourceType.STRATEGY.value}:{strategy_id}"
        securities = [
            self._classify(strategy_id, resolved, key, acqs, mine)
            for (resolved, key), acqs in by_identity.items()
        ]
        securities.sort(key=lambda s: (s.tickers, s.security_id or ""))
        return OwnershipResolution(
            account_id=account_id,
            strategy_id=strategy_id,
            securities=tuple(securities),
        )

    # ---- internals ----

    def _classify(
        self,
        strategy_id: int,
        identity_resolved: bool,
        identity_key: str,
        acqs: list[_Acquisition],
        mine: str,
    ) -> OwnedSecurity:
        tickers = tuple(sorted({a.ticker for a in acqs}))
        sources = tuple(sorted({a.source for a in acqs}))
        ours = [a for a in acqs if a.source == mine]
        order_ids = tuple(
            a.order_id for a in sorted(ours, key=lambda a: (a.created_at, a.order_id))
        )
        firsts = [a.created_at for a in ours]

        def build(
            security_id: str | None,
            status: OwnershipStatus,
            reason: AmbiguityReason | None,
        ) -> OwnedSecurity:
            return OwnedSecurity(
                security_id=security_id,
                identity_contract=SECURITY_IDENTITY_CONTRACT,
                tickers=tickers,
                status=status,
                reason=reason,
                acquisition_order_ids=order_ids,
                acquiring_sources=sources,
                first_acquired_at=min(firsts) if firsts else None,
                last_acquired_at=max(firsts) if firsts else None,
            )

        if not ours:
            # Acquired here, but not by us. Not an error and not ambiguity — ambiguity
            # only arises for a claim we actually hold (v0.3 §5.4.1).
            return build(
                identity_key if identity_resolved else None,
                OwnershipStatus.UNCLAIMED,
                None,
            )

        if not identity_resolved:
            # We have a claim but cannot name the security durably. Fail closed rather
            # than key it on a ticker that may denote a different issuer.
            return build(None, OwnershipStatus.AMBIGUOUS, AmbiguityReason.IDENTITY_UNRESOLVED)

        competing_strategy = any(
            a.source != mine and a.source_type is OrderSourceType.STRATEGY for a in acqs
        )
        non_strategy = any(a.source_type is not OrderSourceType.STRATEGY for a in acqs)
        if competing_strategy or non_strategy:
            return build(
                identity_key,
                OwnershipStatus.AMBIGUOUS,
                (
                    AmbiguityReason.COMPETING_STRATEGY_ACQUISITION
                    if competing_strategy
                    else AmbiguityReason.NON_STRATEGY_ACQUISITION
                ),
            )

        return build(identity_key, OwnershipStatus.OWNED, None)

    async def _acquisitions(self, account_id: int) -> list[_Acquisition]:
        """Every FILLED BUY on the account, from any source, newest-agnostic.

        Selects identity columns only. ``Order.qty`` and ``Fill.qty`` are deliberately
        absent from the projection so no quantity is even in scope here.
        """
        stmt = (
            select(
                Order.id,
                Order.source_type,
                Order.source_id,
                Order.created_at,
                Symbol.ticker,
            )
            .join(Symbol, Symbol.id == Order.symbol_id)
            .where(
                Order.account_id == account_id,
                Order.side == OrderSide.BUY,
                select(Fill.id).where(Fill.order_id == Order.id).exists(),
            )
        )
        async with self._session_factory() as session:
            rows = (await session.execute(stmt)).all()
        return [
            _Acquisition(
                order_id=oid,
                source_type=stype,
                source=f"{stype.value}:{sid if sid is not None else ''}",
                created_at=created,
                ticker=ticker.upper(),
            )
            for oid, stype, sid, created, ticker in rows
        ]


@dataclass(frozen=True)
class _Acquisition:
    """One filled BUY. Carries no quantity — see the module docstring."""

    order_id: int
    source_type: OrderSourceType
    source: str
    created_at: datetime
    ticker: str
