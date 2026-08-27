"""The security->CIK binding, assembled over its full evidence chain.

The frozen design requires

    permanent security identity  ->  effective-dated class identity
        ->  SEC-declared {symbol, title, exchange}  ->  registrant CIK

and says explicitly that ticker equality cannot close any hop. A cover page supplies only
the last two: what it proves is ``declared class tuple -> CIK``, which is why the object
built from observations is named ``DeclaredClassCikEpisode``. It is *admissible input* to a
binding, never the binding. Two unrelated issuers can reuse a symbol/title/exchange tuple at
non-overlapping dates, and keying a "security" on that tuple would stitch them into
successive episodes of one identity — the V3 failure shape in new clothes.

**Admission is positive.** An earlier revision decided admissibility by rejecting a short
list of bad basis strings, so anything else was admitted and a well-chosen constant could
conjure a governed-looking first hop out of nothing. A ``ClassIdentityLink`` is now
admissible only when its ``FirstHopSource`` names a source class in the frozen O-9 set, its
artifact digest is verified, its permanent-identity match is independent of the ticker, and
the source actually covers the link's effective interval.

``O9_APPROVED_FIRST_HOP_SOURCE_CLASSES`` is **still empty by construction**. The cover-page
class ``SEC_PERIODIC_COVER_IDENTITY_V1`` was O-9 approved once the first observation was
sealed, but it is approved for ``declared class -> CIK`` and lives in a *separate* registry:
it proves what a registrant declared, not which permanent security that declaration belongs
to. The first hop still has no qualifying source, so the default state of this module remains
DISPUTED and ``bindings`` remains 0.

⭐ The split is **enforced at both boundaries, not merely named**. ``FirstHopAdmissionPolicy``
reads ``O9_APPROVED_FIRST_HOP_SOURCE_CLASSES``; ``DeclaredClassAdmissionPolicy`` reads
``O9_APPROVED_DECLARED_CLASS_SOURCE_CLASSES``; the two frozensets are asserted disjoint at
import. Approving a class for one hop therefore cannot approve it for the other in either
direction -- a future first-hop ruling does not silently authorize that source to mint
declared-class episodes, and the cover-page class can never close the first hop.

``NO_COMPETING_SECURITY_CIK_BINDING`` is evaluated between two *admissible bindings* keyed by
permanent security, never against an index CIK: index metadata is not a binding, and
treating it as one would let filing metadata masquerade as identity evidence (that conflict
is ``INDEX_COVER_CIK_MISMATCH``, in ``acquire``).
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


@dataclass(frozen=True)
class SourceClass:
    """A governed evidence class, with the hop it is approved for stated explicitly."""

    name: str
    hop: str
    admissible_fields: tuple[str, ...]
    semantics: str


#: ⭐ O-9 APPROVED 2026-08-26, after the first sealed cover-page observation.
#:
#: It is approved for the LAST TWO hops -- ``declared class tuple -> registrant CIK`` at a
#: known accepted timestamp -- and for nothing else.
SEC_PERIODIC_COVER_IDENTITY_V1: Final = SourceClass(
    name="SEC_PERIODIC_COVER_IDENTITY_V1",
    hop="DECLARED_CLASS_TO_CIK",
    admissible_fields=(
        "EntityCentralIndexKey",
        "TradingSymbol",
        "Security12bTitle",
        "SecurityExchangeName",
    ),
    semantics=(
        "At accepted_at, this SEC registrant declared this listed security/class tuple on "
        "the filing cover page."
    ),
)

#: Source classes approved for ``declared class -> CIK``. The cover-page class lives here.
O9_APPROVED_DECLARED_CLASS_SOURCE_CLASSES: Final[frozenset[str]] = frozenset(
    {SEC_PERIODIC_COVER_IDENTITY_V1.name}
)

#: ⛔ STILL EMPTY BY CONSTRUCTION. Source classes approved for the FIRST hop,
#: ``permanent security identity -> effective-dated declared class``.
#:
#: ⚠ Renamed from ``O9_APPROVED_SOURCE_CLASSES``, which was dangerously ambiguous: it reads
#: like a general registry but gates only ``FirstHopAdmissionPolicy``. Putting the cover-page
#: class in it would have made a ``ClassIdentityLink`` citing that class admissible as a first
#: hop -- manufacturing exactly the ``permaticker -> CIK`` binding the O-9 ruling says the
#: cover page does NOT establish. Two registries, because there are two different questions.
O9_APPROVED_FIRST_HOP_SOURCE_CLASSES: Final[frozenset[str]] = frozenset()

assert not (O9_APPROVED_FIRST_HOP_SOURCE_CLASSES & O9_APPROVED_DECLARED_CLASS_SOURCE_CLASSES), (
    "a source class approved for one hop is not thereby approved for the other"
)

FIRST_HOP_OK: Final = "ADMISSIBLE"
FIRST_HOP_SOURCE_CLASS_NOT_APPROVED: Final = "SOURCE_CLASS_NOT_O9_APPROVED"
FIRST_HOP_ARTIFACT_UNVERIFIED: Final = "SOURCE_ARTIFACT_DIGEST_UNVERIFIED"
FIRST_HOP_IDENTITY_NOT_INDEPENDENT: Final = "PERMANENT_IDENTITY_NOT_INDEPENDENTLY_MATCHED"
FIRST_HOP_INTERVAL_UNSUPPORTED: Final = "EFFECTIVE_INTERVAL_NOT_SUPPORTED_BY_SOURCE"

DECLARED_CLASS_OK: Final = "ADMISSIBLE"
DECLARED_CLASS_SOURCE_NOT_APPROVED: Final = "SOURCE_CLASS_NOT_O9_APPROVED_FOR_DECLARED_CLASS"
DECLARED_CLASS_ARTIFACT_UNVERIFIED: Final = "DECLARED_CLASS_ARTIFACT_UNVERIFIED"

#: Identity-match methods that are not independent of the ticker. Named so a rejection can be
#: precise; admission never depends on this list.
TICKER_DEPENDENT_MATCHES: Final[frozenset[str]] = frozenset(
    {"TICKER_EQUALITY", "TICKER_EQUALITY_ONLY", "CURRENT_TICKER_MAP", "SYMBOL_MATCH", ""}
)


def declared_class(obs: Observation) -> DeclaredClass:
    """The declared class tuple. Never a security identity on its own."""
    return (obs.security_12b_title, obs.trading_symbol, obs.security_exchange_name)


@dataclass(frozen=True)
class FirstHopSource:
    """The governed artifact a ``ClassIdentityLink`` rests on."""

    source_class: str
    artifact_sha256: str
    artifact_verified: bool
    identity_match_method: str
    covers_from: datetime
    covers_to: datetime


@dataclass(frozen=True)
class ClassIdentityLink:
    """The FIRST HOP: a governed permanent security identity tied to a declared class.

    This module does not manufacture links — it consumes governed ones, and there are
    currently **none in custody**. Admissibility is decided by a
    ``FirstHopAdmissionPolicy`` against ``source``, never by the shape of a free-text label.
    """

    permaticker: int
    declared: DeclaredClass
    valid_from: datetime
    valid_to: datetime
    source: FirstHopSource | None = None

    def covers(self, when: datetime) -> bool:
        return self.valid_from <= when <= self.valid_to

    def admissibility(self, policy: FirstHopAdmissionPolicy) -> tuple[bool, str]:
        return policy.admit(self)


@dataclass(frozen=True)
class FirstHopAdmissionPolicy:
    """Which source classes may close the first hop. Frozen; empty until an owner ruling."""

    approved_source_classes: frozenset[str] = O9_APPROVED_FIRST_HOP_SOURCE_CLASSES

    def admit(self, link: ClassIdentityLink) -> tuple[bool, str]:
        src = link.source
        if src is None or src.source_class not in self.approved_source_classes:
            return False, FIRST_HOP_SOURCE_CLASS_NOT_APPROVED
        if not src.artifact_verified or len(src.artifact_sha256) != 64:
            return False, FIRST_HOP_ARTIFACT_UNVERIFIED
        if src.identity_match_method.upper() in TICKER_DEPENDENT_MATCHES:
            return False, FIRST_HOP_IDENTITY_NOT_INDEPENDENT
        if link.valid_from < src.covers_from or link.valid_to > src.covers_to:
            return False, FIRST_HOP_INTERVAL_UNSUPPORTED
        return True, FIRST_HOP_OK


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
class SecurityCikBinding:
    """``permanent security -> CIK`` over an interval, with the whole chain evidenced."""

    permaticker: int
    cik: int
    declared: DeclaredClass
    valid_from: datetime
    valid_to: datetime
    first_hop_source_class: str
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


class DeclaredClassInadmissible(RuntimeError):
    """Episode construction was attempted from a source O-9 has not approved for this hop."""


@dataclass(frozen=True)
class DeclaredClassAdmissionPolicy:
    """Which source classes may close ``declared class -> CIK``.

    ⭐ This exists because ``Observation.build`` proves only **provenance** -- that the tuple
    came off a cover page through ``INLINE_XBRL_COVER``. Provenance is not the owner's
    separate decision that the provenance class is O-9 admissible for this hop, and
    conflating the two would let any future cover-shaped parser mint episodes without a
    ruling. The registry is consulted at the boundary, not inferred from the payload.

    ⛔ Deliberately reads a *different* frozenset from ``FirstHopAdmissionPolicy``. Approving
    a class for one hop must never approve it for the other, in either direction.
    """

    approved_source_classes: frozenset[str] = O9_APPROVED_DECLARED_CLASS_SOURCE_CLASSES

    def admit(self, source_class: str, artifact_verified: bool) -> tuple[bool, str]:
        if source_class not in self.approved_source_classes:
            return False, DECLARED_CLASS_SOURCE_NOT_APPROVED
        if not artifact_verified:
            return False, DECLARED_CLASS_ARTIFACT_UNVERIFIED
        return True, DECLARED_CLASS_OK


def build_declared_class_episodes(
    observations: list[Observation],
    *,
    to_utc,
    source_class: str,
    artifact_verified: bool,
    policy: DeclaredClassAdmissionPolicy | None = None,
) -> list[DeclaredClassCikEpisode]:
    """Group admissible observations into inward-bounded (declared class, CIK) episodes.

    ``source_class`` and ``artifact_verified`` are REQUIRED keywords: the caller must state
    which governed source class it is building from, and a refusal raises rather than
    returning an empty list, so an unapproved source can never be mistaken for one that
    simply produced no episodes.
    """
    admitted, reason = (policy or DeclaredClassAdmissionPolicy()).admit(
        source_class, artifact_verified
    )
    if not admitted:
        raise DeclaredClassInadmissible(
            f"cannot build declared-class episodes from {source_class!r}: {reason}"
        )

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
    episodes: list[DeclaredClassCikEpisode],
    links: list[ClassIdentityLink],
    policy: FirstHopAdmissionPolicy | None = None,
) -> list[SecurityCikBinding]:
    """Compose the full chain. Only an ADMISSIBLE first hop can produce a binding.

    The binding's interval is the **intersection** of the link's validity and the episode's
    inward-bounded evidence: neither hop may extend the other.
    """
    pol = policy or FirstHopAdmissionPolicy()
    out: list[SecurityCikBinding] = []
    for link in links:
        admitted, _reason = link.admissibility(pol)
        if not admitted:
            continue
        for ep in episodes:
            if ep.declared != link.declared:
                continue
            if not ep.overlaps_interval(link.valid_from, link.valid_to):
                continue
            assert link.source is not None  # admitted implies a source
            out.append(
                SecurityCikBinding(
                    permaticker=link.permaticker,
                    cik=ep.cik,
                    declared=ep.declared,
                    valid_from=max(ep.first_accepted, link.valid_from),
                    valid_to=min(ep.last_accepted, link.valid_to),
                    first_hop_source_class=link.source.source_class,
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
    policy: FirstHopAdmissionPolicy | None = None,
) -> tuple[bool, str]:
    """Evaluate the middle and third conjuncts of ``LINEAGE_STABLE`` for one security/week.

    Every negative answer is a DISPUTED-producing status, never a manufactured binding —
    including the case where the only available first hop is not governed evidence.
    """
    pol = policy or FirstHopAdmissionPolicy()
    covering = [b for b in bindings if b.permaticker == permaticker and b.covers(week)]
    if not covering:
        relevant = [link for link in links if link.permaticker == permaticker and link.covers(week)]
        if not relevant:
            return False, NO_FIRST_HOP
        verdicts = [link.admissibility(pol) for link in relevant]
        if not any(ok for ok, _ in verdicts):
            return False, f"DISPUTED_FIRST_HOP_{verdicts[0][1]}"
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
    inadmissible_first_hops: list[tuple[ClassIdentityLink, str]] = field(default_factory=list)

    @classmethod
    def build(
        cls,
        observations: list[Observation],
        links: list[ClassIdentityLink],
        *,
        to_utc,
        source_class: str,
        artifact_verified: bool,
        policy: FirstHopAdmissionPolicy | None = None,
        declared_policy: DeclaredClassAdmissionPolicy | None = None,
    ) -> BindingReport:
        pol = policy or FirstHopAdmissionPolicy()
        eps = build_declared_class_episodes(
            observations,
            to_utc=to_utc,
            source_class=source_class,
            artifact_verified=artifact_verified,
            policy=declared_policy,
        )
        bindings = build_security_cik_bindings(eps, links, pol)
        rejected: list[tuple[ClassIdentityLink, str]] = []
        for link in links:
            ok, reason = link.admissibility(pol)
            if not ok:
                rejected.append((link, reason))
        return cls(
            episodes=eps,
            bindings=bindings,
            conflicts=detect_competing_bindings(bindings),
            inadmissible_first_hops=rejected,
        )
