"""Issuer identity over effective intervals: permanent id <-> vendor ticker (WP1.5, L-9).

Pure and return-blind: it takes plain interval records and reads no store, no price and no
return. The intraday fetch must be keyed to the point-in-time issuer, never to a ticker string,
because a reused ticker would otherwise pull another issuer's bars.

What this module does NOT establish. A rename candidate (one permanent id carried by several
vendor tickers over NON-overlapping intervals) and a reuse candidate (one ticker carried by
several permanent ids over NON-overlapping intervals) have passed the temporal check only; that
is necessary, not sufficient. Whether the vendor retro-mapped history onto the new symbol, and
whether the TICKERS intervals are themselves point-in-time, are unverified (Backlog 7.2) and
must be established against the real corpus. Overlapping intervals are conflicts and are never
resolved by guessing: a lookup that lands in one returns ``AMBIGUOUS_OVERLAP``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date

PURE_FUNCTIONS = ("build_identity_map", "ticker_on", "permaticker_on", "audit_identity")

RESOLVED = "RESOLVED"
NO_MAPPING = "NO_MAPPING"
AMBIGUOUS_OVERLAP = "AMBIGUOUS_OVERLAP"
RESOLUTION_STATUSES = (RESOLVED, NO_MAPPING, AMBIGUOUS_OVERLAP)


class IdentityDataError(ValueError):
    """The interval records themselves are defective (blank id, inverted or duplicated)."""


@dataclass(frozen=True)
class IdentityRecord:
    """One vendor ticker carried by one issuer over the inclusive interval [first, last].

    ``last`` None means the interval is still open on the corpus date.
    """

    permaticker: str
    ticker: str
    first: date
    last: date | None


@dataclass(frozen=True)
class Resolution:
    status: str
    value: str | None
    detail: str


@dataclass(frozen=True)
class IdentityMap:
    by_permaticker: Mapping[str, tuple[IdentityRecord, ...]]
    by_ticker: Mapping[str, tuple[IdentityRecord, ...]]
    record_count: int


@dataclass(frozen=True)
class IdentityAudit:
    """Temporal classification of every multi-valued identifier. Candidates, not verdicts."""

    rename_candidates: tuple[tuple[str, tuple[str, ...]], ...]  # permaticker -> tickers in order
    reuse_candidates: tuple[tuple[str, tuple[str, ...]], ...]  # ticker -> permatickers in order
    permaticker_overlaps: tuple[tuple[str, tuple[str, ...]], ...]  # conflict
    ticker_overlaps: tuple[tuple[str, tuple[str, ...]], ...]  # conflict
    open_ended: int


def _contains(rec: IdentityRecord, day: date) -> bool:
    return rec.first <= day and (rec.last is None or day <= rec.last)


def _overlap(a: IdentityRecord, b: IdentityRecord) -> bool:
    a_before_b_end = b.last is None or a.first <= b.last
    b_before_a_end = a.last is None or b.first <= a.last
    return a_before_b_end and b_before_a_end


def build_identity_map(records: Iterable[IdentityRecord]) -> IdentityMap:
    rows = sorted(records, key=lambda r: (r.permaticker, r.ticker, r.first))
    seen: set[IdentityRecord] = set()
    for r in rows:
        if not r.permaticker.strip() or not r.ticker.strip():
            raise IdentityDataError(f"blank identifier in record {r!r}")
        if r.last is not None and r.first > r.last:
            raise IdentityDataError(f"inverted interval {r.first}..{r.last} for {r.ticker}")
        if r in seen:
            raise IdentityDataError(f"duplicate record {r!r}")
        seen.add(r)
    by_p: dict[str, list[IdentityRecord]] = {}
    by_t: dict[str, list[IdentityRecord]] = {}
    for r in rows:
        by_p.setdefault(r.permaticker, []).append(r)
        by_t.setdefault(r.ticker, []).append(r)
    return IdentityMap(
        {k: tuple(sorted(v, key=lambda r: r.first)) for k, v in by_p.items()},
        {k: tuple(sorted(v, key=lambda r: r.first)) for k, v in by_t.items()},
        len(rows),
    )


def ticker_on(idmap: IdentityMap, permaticker: str, day: date) -> Resolution:
    """The vendor ticker to use in a request for this issuer on ``day``."""
    active = [r for r in idmap.by_permaticker.get(permaticker, ()) if _contains(r, day)]
    if not active:
        return Resolution(NO_MAPPING, None, f"{permaticker}: no ticker interval contains {day}")
    if len(active) > 1:
        names = sorted(r.ticker for r in active)
        return Resolution(AMBIGUOUS_OVERLAP, None, f"{permaticker} carries {names} on {day}")
    return Resolution(RESOLVED, active[0].ticker, "single active interval")


def permaticker_on(idmap: IdentityMap, ticker: str, day: date) -> Resolution:
    """The issuer a vendor ticker string denotes on ``day`` (reverse of :func:`ticker_on`)."""
    active = [r for r in idmap.by_ticker.get(ticker, ()) if _contains(r, day)]
    if not active:
        return Resolution(NO_MAPPING, None, f"{ticker}: no issuer interval contains {day}")
    if len({r.permaticker for r in active}) > 1:
        ids = sorted({r.permaticker for r in active})
        return Resolution(AMBIGUOUS_OVERLAP, None, f"{ticker} denotes {ids} on {day}")
    return Resolution(RESOLVED, active[0].permaticker, "single active interval")


def _classify(
    groups: Mapping[str, tuple[IdentityRecord, ...]], other: str
) -> tuple[list[tuple[str, tuple[str, ...]]], list[tuple[str, tuple[str, ...]]]]:
    sequential: list[tuple[str, tuple[str, ...]]] = []
    conflicts: list[tuple[str, tuple[str, ...]]] = []
    for key in sorted(groups):
        recs = groups[key]
        ids = tuple(dict.fromkeys(getattr(r, other) for r in recs))
        if len(ids) < 2:
            continue
        clash = any(
            getattr(a, other) != getattr(b, other) and _overlap(a, b)
            for i, a in enumerate(recs)
            for b in recs[i + 1 :]
        )
        (conflicts if clash else sequential).append((key, ids))
    return sequential, conflicts


def audit_identity(idmap: IdentityMap) -> IdentityAudit:
    renames, perma_overlaps = _classify(idmap.by_permaticker, "ticker")
    reuses, ticker_overlaps = _classify(idmap.by_ticker, "permaticker")
    open_ended = sum(1 for recs in idmap.by_permaticker.values() for r in recs if r.last is None)
    return IdentityAudit(
        tuple(renames), tuple(reuses), tuple(perma_overlaps), tuple(ticker_overlaps), open_ended
    )
