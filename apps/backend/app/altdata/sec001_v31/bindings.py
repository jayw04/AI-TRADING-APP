"""Cross-filing security->CIK binding episodes and the competing-binding conjunct.

This module exists to keep the identity layers from blurring. ``LINEAGE_STABLE`` has three
conjuncts, and two of them are about different things:

``SECURITY_CIK_BINDING_COVERS_WEEK``
    An admissible, effective-dated security->CIK binding spans the week. Built here from
    cover-page observations by inward bounding: an episode runs from the *first* accepted
    observation of a class under a CIK to the *last*, and qualifies cells inside that
    interval only. No outward extrapolation, no "same company throughout".

``NO_COMPETING_SECURITY_CIK_BINDING``
    No *other* admissible binding claims the same permanent security over an overlapping
    interval. That is a relation between **two admissible bindings** — which is why an
    index/cover CIK mismatch is emphatically *not* evaluated here. A CIK read from an index
    record is acquisition metadata; it is not itself an admissible security->CIK binding, and
    treating it as one would let filing metadata masquerade as identity evidence. That
    conflict is ``INDEX_COVER_CIK_MISMATCH`` and it lives in ``acquire``.

A security is keyed by its declared class tuple, not by ticker. Two classes of one registrant
are two securities here, which is what makes the GOOG/GOOGL case resolvable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Final

from app.altdata.sec001_v31.layers import Observation

#: A security's identity for binding purposes: the Section 12(b) class tuple. Ticker alone is
#: never the key -- that is the equality the whole design rejects.
SecurityKey = tuple[str, str, str]

COMPETING: Final = "COMPETING_SECURITY_CIK_BINDING"
UNIQUE: Final = "NO_COMPETING_SECURITY_CIK_BINDING"


def security_key(obs: Observation) -> SecurityKey:
    return (obs.security_12b_title, obs.trading_symbol, obs.security_exchange_name)


@dataclass
class BindingEpisode:
    """An inward-bounded security->CIK binding. Qualifies cells within [first, last] only."""

    security: SecurityKey
    cik: int
    first_accepted: datetime
    last_accepted: datetime
    observation_count: int = 0
    accessions: list[str] = field(default_factory=list)

    def covers(self, when: datetime) -> bool:
        """Inward bounding: no outward extrapolation beyond observed evidence."""
        return self.first_accepted <= when <= self.last_accepted

    def overlaps(self, other: BindingEpisode) -> bool:
        return (
            self.first_accepted <= other.last_accepted
            and other.first_accepted <= self.last_accepted
        )


@dataclass
class CompetingBinding:
    security: SecurityKey
    left: BindingEpisode
    right: BindingEpisode

    def describe(self) -> str:
        return (
            f"security {self.security} claimed by CIK {self.left.cik} "
            f"[{self.left.first_accepted.date()}..{self.left.last_accepted.date()}] and CIK "
            f"{self.right.cik} [{self.right.first_accepted.date()}..{self.right.last_accepted.date()}]"
        )


def build_binding_episodes(observations: list[Observation], *, to_utc) -> list[BindingEpisode]:
    """Group admissible observations into inward-bounded (security, CIK) episodes."""
    grouped: dict[tuple[SecurityKey, int], list[Observation]] = {}
    for obs in observations:
        grouped.setdefault((security_key(obs), obs.cik), []).append(obs)

    episodes: list[BindingEpisode] = []
    for (sec, cik), obs_list in grouped.items():
        stamps = sorted(to_utc(o.accepted_at) for o in obs_list)
        episodes.append(
            BindingEpisode(
                security=sec,
                cik=cik,
                first_accepted=stamps[0],
                last_accepted=stamps[-1],
                observation_count=len(obs_list),
                accessions=sorted({o.accession for o in obs_list}),
            )
        )
    return sorted(episodes, key=lambda e: (e.security, e.cik, e.first_accepted))


def detect_competing_bindings(episodes: list[BindingEpisode]) -> list[CompetingBinding]:
    """Two admissible bindings claiming the same security over overlapping intervals."""
    conflicts: list[CompetingBinding] = []
    by_security: dict[SecurityKey, list[BindingEpisode]] = {}
    for ep in episodes:
        by_security.setdefault(ep.security, []).append(ep)

    for sec, eps in by_security.items():
        for i in range(len(eps)):
            for j in range(i + 1, len(eps)):
                if eps[i].cik != eps[j].cik and eps[i].overlaps(eps[j]):
                    conflicts.append(CompetingBinding(sec, eps[i], eps[j]))
    return conflicts


def binding_covers_week(
    episodes: list[BindingEpisode], security: SecurityKey, week: datetime
) -> tuple[bool, str]:
    """Evaluate the two binding conjuncts for one security/week.

    Returns ``(covered, status)``. A week covered by two disagreeing CIKs is **not** covered:
    the competing conjunct fails and the cell stays DISPUTED.
    """
    covering = [e for e in episodes if e.security == security and e.covers(week)]
    if not covering:
        return False, "NO_BINDING_COVERS_WEEK"
    if len({e.cik for e in covering}) > 1:
        return False, COMPETING
    return True, UNIQUE
