"""The security->CIK binding, assembled over its full evidence chain.

Review finding (P0, conceptual): the previous module defined a "security" as the SEC-declared
tuple ``(Security12bTitle, TradingSymbol, SecurityExchangeName)`` and built CIK episodes
straight from it. That proves

    SEC-declared class tuple  ->  CIK

which is only the *last two hops*. The frozen design requires

    permanent security identity  ->  effective-dated class identity
        ->  SEC-declared {symbol, title, exchange}  ->  registrant CIK

and says explicitly that ticker equality cannot close any hop. Skipping the first hop is not
a formality: two unrelated issuers can reuse a symbol/title/exchange tuple at non-overlapping
dates, and the old code would have stitched them into successive episodes of one "security".
That is the V3 failure shape wearing new clothes.

So the object built from cover pages is now named for what it actually is — a
``DeclaredClassCikEpisode``. It is *admissible input* to a binding, never the binding. A
``SecurityCikBinding`` exists only where a governed ``ClassIdentityLink`` independently ties
a permanent security identity to that declared class over an interval. Where the first hop
cannot be made without relying on ticker equality, the candidate is **DISPUTED** — the
design's answer, and not one this module may soften.

``NO_COMPETING_SECURITY_CIK_BINDING`` is likewise evaluated between two *admissible
bindings* keyed by permanent security, never against an index CIK: index metadata is not a
binding, and treating it as one would let filing metadata masquerade as identity evidence
(that conflict is ``INDEX_COVER_CIK_MISMATCH``, in ``acquire``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Final

from app.altdata.sec001_v31.layers import Observation

#: The SEC-declared Section 12(b) class tuple. The *last* hop's key, not a security identity.
DeclaredClass = tuple[str, str, str]  # (security_12b_title, trading_symbol, exchange)

COMPETING: Final = "COMPETING_SECURITY_CIK_BINDING"
UNIQUE: Final = "NO_COMPETING_SECURITY_CIK_BINDING"
NO_BINDING: Final = "NO_BINDING_COVERS_WEEK"
NO_FIRST_HOP: Final = "DISPUTED_NO_PERMANENT_SECURITY_LINK"
FIRST_HOP_TICKER_ONLY: Final = "DISPUTED_FIRST_HOP_TICKER_EQUALITY_ONLY"

#: Bases that cannot close the first hop. Named so a reviewer can see what is rejected.
INADMISSIBLE_FIRST_HOP_BASES: Final[frozenset[str]] = frozenset(
    {"TICKER_EQUALITY", "TICKER_EQUALITY_ONLY", "CURRENT_TICKER_MAP", "SYMBOL_MATCH", ""}
)


def declared_class(obs: Observation) -> DeclaredClass:
    """The declared class tuple. Never a security identity on its own."""
    return (obs.security_12b_title, obs.trading_symbol, obs.security_exchange_name)


@dataclass(frozen=True)
class DeclaredClassCikEpisode:
    """An inward-bounded ``declared class -> CIK`` episode from cover-page observations.

    Admissible **input** to a security->CIK binding. Not a binding: it says nothing about
    which permanent security the declared class belonged to.
    """

    declared: DeclaredClass
    cik: int
    first_accepted: datetime
    last_accepted: datetime
    observation_count: int = 0
    accessions: tuple[str, ...] = ()

    def covers(self, when: datetime) -> bool:
        """Inward bounding: no outward extrapolation beyond observed evidence."""
        return self.first_accepted <= when <= self.last_accepted

    def overlaps_interval(self, start: datetime, end: datetime) -> bool:
        return self.first_accepted <= end and start <= self.last_accepted


@dataclass(frozen=True)
class ClassIdentityLink:
    """The FIRST HOP: a governed permanent security identity tied to a declared class.

    ``basis`` records how the link was established. It must come from an O-9-approved
    source; a basis of ticker equality is inadmissible and yields DISPUTED rather than a
    binding. This module does not manufacture links — it consumes governed ones, and there
    are currently **none in custody**, which is exactly why WP0A-Q exists.
    """

    permaticker: int
    declared: DeclaredClass
    valid_from: datetime
    valid_to: datetime
    basis: str

    @property
    def is_admissible(self) -> bool:
        return self.basis.upper() not in INADMISSIBLE_FIRST_HOP_BASES

    def covers(self, when: datetime) -> bool:
        return self.valid_from <= when <= self.valid_to


@dataclass(frozen=True)
class SecurityCikBinding:
    """``permanent security -> CIK`` over an interval, with the whole chain evidenced."""

    permaticker: int
    cik: int
    declared: DeclaredClass
    valid_from: datetime
    valid_to: datetime
    first_hop_basis: str
    episode_accessions: tuple[str, ...] = ()

    def covers(self, when: datetime) -> bool:
        return self.valid_from <= when <= self.valid_to

    def overlaps(self, other: SecurityCikBinding) -> bool:
        return self.valid_from <= other.valid_to and other.valid_from <= self.valid_to


@dataclass
class CompetingBinding:
    permaticker: int
    left: SecurityCikBinding
    right: SecurityCikBinding

    def describe(self) -> str:
        return (
            f"permanent security {self.permaticker} claimed by CIK {self.left.cik} "
            f"[{self.left.valid_from.date()}..{self.left.valid_to.date()}] and CIK "
            f"{self.right.cik} [{self.right.valid_from.date()}..{self.right.valid_to.date()}]"
        )


def build_declared_class_episodes(
    observations: list[Observation], *, to_utc
) -> list[DeclaredClassCikEpisode]:
    """Group admissible observations into inward-bounded (declared class, CIK) episodes."""
    grouped: dict[tuple[DeclaredClass, int], list[Observation]] = {}
    for obs in observations:
        grouped.setdefault((declared_class(obs), obs.cik), []).append(obs)

    episodes: list[DeclaredClassCikEpisode] = []
    for (dc, cik), obs_list in grouped.items():
        stamps = sorted(to_utc(o.accepted_at) for o in obs_list)
        episodes.append(
            DeclaredClassCikEpisode(
                declared=dc,
                cik=cik,
                first_accepted=stamps[0],
                last_accepted=stamps[-1],
                observation_count=len(obs_list),
                accessions=tuple(sorted({o.accession for o in obs_list})),
            )
        )
    return sorted(episodes, key=lambda e: (e.declared, e.cik, e.first_accepted))


def build_security_cik_bindings(
    episodes: list[DeclaredClassCikEpisode], links: list[ClassIdentityLink]
) -> list[SecurityCikBinding]:
    """Compose the full chain. Only an ADMISSIBLE first hop can produce a binding.

    The binding's interval is the **intersection** of the link's validity and the episode's
    inward-bounded evidence: neither hop may extend the other.
    """
    out: list[SecurityCikBinding] = []
    for link in links:
        if not link.is_admissible:
            continue
        for ep in episodes:
            if ep.declared != link.declared:
                continue
            if not ep.overlaps_interval(link.valid_from, link.valid_to):
                continue
            start = max(ep.first_accepted, link.valid_from)
            end = min(ep.last_accepted, link.valid_to)
            out.append(
                SecurityCikBinding(
                    permaticker=link.permaticker,
                    cik=ep.cik,
                    declared=ep.declared,
                    valid_from=start,
                    valid_to=end,
                    first_hop_basis=link.basis,
                    episode_accessions=ep.accessions,
                )
            )
    return sorted(out, key=lambda b: (b.permaticker, b.cik, b.valid_from))


def detect_competing_bindings(bindings: list[SecurityCikBinding]) -> list[CompetingBinding]:
    """Two admissible bindings claiming one PERMANENT security over overlapping intervals."""
    conflicts: list[CompetingBinding] = []
    by_security: dict[int, list[SecurityCikBinding]] = {}
    for b in bindings:
        by_security.setdefault(b.permaticker, []).append(b)

    for pt, bs in by_security.items():
        for i in range(len(bs)):
            for j in range(i + 1, len(bs)):
                if bs[i].cik != bs[j].cik and bs[i].overlaps(bs[j]):
                    conflicts.append(CompetingBinding(pt, bs[i], bs[j]))
    return conflicts


def security_cik_binding_covers_week(
    bindings: list[SecurityCikBinding],
    links: list[ClassIdentityLink],
    permaticker: int,
    week: datetime,
) -> tuple[bool, str]:
    """Evaluate the middle and third conjuncts of ``LINEAGE_STABLE`` for one security/week.

    Returns ``(covered, status)``. Every negative answer is a DISPUTED-producing status, not
    a manufactured binding — including the case where the only available first hop rests on
    ticker equality.
    """
    covering = [b for b in bindings if b.permaticker == permaticker and b.covers(week)]
    if not covering:
        relevant = [link for link in links if link.permaticker == permaticker and link.covers(week)]
        if not relevant:
            return False, NO_FIRST_HOP
        if not any(link.is_admissible for link in relevant):
            return False, FIRST_HOP_TICKER_ONLY
        return False, NO_BINDING
    if len({b.cik for b in covering}) > 1:
        return False, COMPETING
    return True, UNIQUE


@dataclass
class BindingReport:
    """What a Gate-0a input looks like. Deliberately carries no economic quantity."""

    episodes: list[DeclaredClassCikEpisode] = field(default_factory=list)
    bindings: list[SecurityCikBinding] = field(default_factory=list)
    conflicts: list[CompetingBinding] = field(default_factory=list)
    inadmissible_first_hops: list[ClassIdentityLink] = field(default_factory=list)

    @classmethod
    def build(
        cls, observations: list[Observation], links: list[ClassIdentityLink], *, to_utc
    ) -> BindingReport:
        eps = build_declared_class_episodes(observations, to_utc=to_utc)
        bindings = build_security_cik_bindings(eps, links)
        return cls(
            episodes=eps,
            bindings=bindings,
            conflicts=detect_competing_bindings(bindings),
            inadmissible_first_hops=[link for link in links if not link.is_admissible],
        )
