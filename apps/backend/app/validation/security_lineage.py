"""Security identity resolution: a permanent lineage, not a ticker (owner ruling, 2026-07-29).

A ticker symbol is not a durable security identity. Vendors reuse symbols across unrelated issuers and
retro-map a security's whole price history onto its current symbol when it is renamed, so a key that
looks stable across a lookback can silently denote two different companies.

The governed identity is therefore::

    security identity = vendor permanent identifier + effective-date interval

with the ticker demoted to an attribute of that identity. `permaticker` is Sharadar's permanent
identifier; it is non-null across the governed TICKERS slice, and the vendor itself disambiguates
reuse by suffixing superseded lineages (`ECHO` = EchoStar today, `ECHO2` = Echo Global Logistics,
`ECHO1` = Electronic Clearing House).

## Why detection cannot stop at the session

The ruling is explicit that eligibility spans the **whole required lookback**, not just session S. A
252-session momentum score computed across a symbol-reuse boundary is not a degraded number, it is a
number for no company at all — so such a candidate is REFUSED and removed *before ranking and target
construction*, never merely exempted from a completeness denominator while its score still flows
through.

## The detection problem this module actually solves

SEP carries no permanent identifier — it is keyed by ticker alone. So a lineage break inside the
lookback has to be established from the two sources that DO carry identity:

  * TICKERS gives the active lineage's `permaticker` and its effective price interval;
  * ACTIONS gives `tickerchangeto` / `tickerchangefrom` events, i.e. the dates a symbol began
    denoting a different lineage.

A rename *within* one lineage is legitimate and must stay eligible; a rename that hands the symbol to
a different `permaticker` inside the lookback is a refusal. Where neither source explains a structural
hole in the price series, metadata and prices disagree and the candidate is refused rather than
guessed at.

## What this module does NOT do

It does not repair the corpus. A store whose SEP conflates two issuers under one key stays defective;
this makes the affected names INELIGIBLE until a Layer-2 corpus rebuild reconstructs history under
permanent identities and issues a new whole-corpus countersignature (ADR 0048 (4) — a historical
correction is never a delta). Nothing here substitutes ticker continuity for permanent lineage.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Any

#: Version of the identity rule itself. Bound into the governed construction identity so that a later
#: resolver change cannot silently reinterpret the same artifacts as meaning something else.
SECURITY_IDENTITY_CONTRACT = "PERMATICKER_EFFECTIVE_INTERVAL_V1"

#: A run of consecutive governed sessions with no mark, inside the span where the active lineage's own
#: metadata says the security was trading. Short holes are ordinary illiquidity; a run this long is a
#: structural discontinuity — the signature of history that belongs to another lineage.
LINEAGE_GAP_SESSIONS = 20

#: How late the first mark inside the window may fall behind the span the metadata claims, before
#: metadata and prices are treated as disagreeing.
LATE_START_SESSIONS = 20

#: Governed parameter (owner-approved 2026-07-29 as an INITIAL value, not an eternal truth): the
#: shortest in-window hole that separates two price segments far enough apart to be treated as
#: disconnected rather than as a data blemish. Changing it changes what the construction accepts, so
#: it is recorded in the evidence and moving it requires review.
LINEAGE_BRIDGE_HOLE_MIN_SESSIONS = 20


class LineageRefusal(StrEnum):
    """Why a candidate cannot be resolved to exactly one permanent lineage over its lookback.

    Every member is a REFUSAL. There is deliberately no "degraded" or "partial" state: the ruling
    forbids computing a score across a lineage boundary, and a value that cannot be attributed to one
    issuer has no meaning to degrade from.
    """

    NO_ACTIVE_LINEAGE = "NO_ACTIVE_LINEAGE"
    MULTIPLE_ACTIVE_LINEAGES = "MULTIPLE_ACTIVE_LINEAGES"
    MISSING_PERMANENT_ID = "MISSING_PERMANENT_ID"
    LOOKBACK_CROSSES_LINEAGE = "LOOKBACK_CROSSES_LINEAGE"
    METADATA_PRICE_DISAGREE = "METADATA_PRICE_DISAGREE"
    UNRESOLVED_REMAP_GAP = "UNRESOLVED_REMAP_GAP"
    AMBIGUOUS_EFFECTIVE_INTERVAL = "AMBIGUOUS_EFFECTIVE_INTERVAL"


class SecurityIdentityUnavailable(Exception):
    """The store cannot support identity resolution at all — e.g. TICKERS carries no permanent
    identifier column. A construction that cannot name its securities fails closed; it does not fall
    back to ticker identity."""


@dataclass(frozen=True)
class LineageDecision:
    """One candidate's resolution. `eligible` is true only when a single lineage covers the lookback.

    `predecessor_permaticker` and `boundary_date` are structured rather than left inside `detail`
    because a boundary is the unit of the eventual Layer-2 repair: recording BOTH permanent ids and
    the date the symbol changed hands makes the corpus correction measurable, instead of something a
    later reader has to parse back out of prose.
    """

    ticker: str
    eligible: bool
    permaticker: str | None = None
    refusal: LineageRefusal | None = None
    detail: str = ""
    predecessor_permaticker: str | None = None
    boundary_date: date | None = None

    def to_evidence(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "ticker": self.ticker, "permaticker": self.permaticker,
            "refusal": str(self.refusal) if self.refusal else None, "detail": self.detail}
        if self.predecessor_permaticker is not None:
            out["predecessor_permaticker"] = self.predecessor_permaticker
        if self.boundary_date is not None:
            out["boundary_date"] = self.boundary_date.isoformat()
        return out


@dataclass(frozen=True)
class LineageAssessment:
    """The eligible set plus the full refusal record for one session.

    Exclusions are counted and attributed because the ruling makes them observable evidence: an
    observation must record how many candidates were dropped and why, so a shrinking universe is
    visible rather than silently absorbed.
    """

    session_date: date
    lookback_start: date
    contract: str
    considered: int
    eligible_tickers: tuple[str, ...]
    excluded: tuple[LineageDecision, ...]

    @property
    def excluded_count(self) -> int:
        return len(self.excluded)

    def counts_by_refusal(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for d in self.excluded:
            key = str(d.refusal) if d.refusal else "UNSPECIFIED"
            out[key] = out.get(key, 0) + 1
        return dict(sorted(out.items()))

    def to_evidence(self) -> dict[str, Any]:
        """Open provenance for the observation record.

        The two counts are reported SEPARATELY and named unambiguously: a later reader must be able
        to tell a universe that was small from one that was filtered, and the preregistered minimum
        is evaluated against the eligible count, never the raw one.

        Every excluded name is listed — not a sample. The exclusions are the whole point of the
        record, and a truncated list would let a growing exclusion set hide behind a fixed-size window.
        """
        return {
            "security_identity_contract": self.contract,
            "session_date": self.session_date.isoformat(),
            "lookback_start": self.lookback_start.isoformat(),
            "raw_universe_count": self.considered,
            "lineage_eligible_universe_count": len(self.eligible_tickers),
            "excluded_count": self.excluded_count,
            "excluded_by_reason": self.counts_by_refusal(),
            "excluded": [d.to_evidence() for d in self.excluded],
        }


def _con(store: Any) -> Any:
    """The query surface, whether a `FactorDataStore` or a bare connection.

    `data_finality` already accepts both, so resolution must too — otherwise the identity contract
    would apply to production stores and silently not apply wherever a connection is passed directly.
    """
    con = getattr(store, "con", None)
    if con is not None:
        return con
    if hasattr(store, "execute"):
        return store
    raise SecurityIdentityUnavailable("the store exposes no connection for identity resolution")


def require_permanent_identifier(store: Any) -> None:
    """Refuse a store whose TICKERS carries no permanent identifier.

    This is the "source lacks a stable permanent identifier" refusal, checked once at construction
    rather than degrading per name — a corpus that cannot name securities permanently cannot support
    the identity contract at all.
    """
    cols = {str(r[1]).lower() for r in _con(store).execute("PRAGMA table_info('tickers')").fetchall()}
    if not cols:
        raise SecurityIdentityUnavailable("the store has no `tickers` table")
    if "permaticker" not in cols:
        raise SecurityIdentityUnavailable(
            f"the governed TICKERS table carries no `permaticker` column (has {sorted(cols)}); "
            f"{SECURITY_IDENTITY_CONTRACT} requires a vendor permanent identifier and never falls "
            f"back to ticker identity")


def _sessions_between(con: Any, start: date, end: date) -> list[date]:
    return [r[0] for r in con.execute(
        "SELECT DISTINCT date FROM sep WHERE date BETWEEN ? AND ? ORDER BY date",
        [start, end]).fetchall()]


def resolve_lineage(store: Any, ticker: str, *, session_date: date,
                    lookback_start: date, sessions: list[date] | None = None) -> LineageDecision:
    """Resolve one candidate to a single permanent lineage covering the whole lookback, or refuse."""
    con = _con(store)

    rows = con.execute(
        "SELECT permaticker, firstpricedate, lastpricedate FROM tickers WHERE ticker = ?",
        [ticker]).fetchall()
    if not rows:
        return LineageDecision(ticker, False, refusal=LineageRefusal.NO_ACTIVE_LINEAGE,
                               detail="no TICKERS record for this symbol")

    active = [r for r in rows
              if r[1] is not None and r[2] is not None and r[1] <= session_date <= r[2]]
    if not active:
        return LineageDecision(
            ticker, False, refusal=LineageRefusal.NO_ACTIVE_LINEAGE,
            detail=f"no lineage's effective interval contains {session_date}")
    if len(active) > 1:
        return LineageDecision(
            ticker, False, refusal=LineageRefusal.MULTIPLE_ACTIVE_LINEAGES,
            detail=f"{len(active)} lineages are simultaneously active at {session_date}: "
                   f"{sorted(str(r[0]) for r in active)}")

    perma, first_price, last_price = active[0]
    if perma is None or not str(perma).strip():
        return LineageDecision(ticker, False, refusal=LineageRefusal.MISSING_PERMANENT_ID,
                               detail="the active lineage carries no permanent identifier")
    perma = str(perma).strip()

    if first_price > last_price:
        return LineageDecision(ticker, False, perma,
                               refusal=LineageRefusal.AMBIGUOUS_EFFECTIVE_INTERVAL,
                               detail=f"effective interval is inverted: {first_price}..{last_price}")

    # ── a symbol handed to a DIFFERENT lineage inside the lookback ──
    changes = con.execute(
        "SELECT date, contraticker FROM actions WHERE action = 'tickerchangefrom' "
        "AND ticker = ? AND date > ? AND date <= ? ORDER BY date",
        [ticker, lookback_start, session_date]).fetchall()
    for changed_on, predecessor in changes:
        prior = con.execute(
            "SELECT permaticker FROM tickers WHERE ticker = ?", [str(predecessor)]).fetchone()
        prior_perma = str(prior[0]).strip() if prior is not None and prior[0] is not None else None
        # ⚠ An ABSENT predecessor row is NOT evidence of a lineage change, and treating it as one
        # rejects the ordinary case. On an intra-lineage rename the vendor retro-maps the security's
        # whole history onto the new symbol and RETIRES the old key, so the predecessor legitimately
        # disappears — measured on 2026-07-27, that pattern covers BNY←BK, FISV←FI, MRSH←MMC and
        # KEEL←BITF, all of which carry a complete 273/273-session history and must stay eligible.
        # Only a predecessor that still resolves to a DIFFERENT permanent id is decisive here; where
        # the old key is simply gone, the price/metadata continuity test below is what distinguishes
        # a retro-mapped rename from a symbol handed to another issuer.
        if prior_perma is not None and prior_perma != perma:
            return LineageDecision(
                ticker, False, perma, refusal=LineageRefusal.LOOKBACK_CROSSES_LINEAGE,
                detail=f"symbol was renamed from {predecessor!r} on {changed_on}, inside the lookback "
                       f"beginning {lookback_start}; predecessor resolves to {prior_perma!r}, not "
                       f"{perma!r}",
                predecessor_permaticker=prior_perma, boundary_date=changed_on)

    # ── prices must agree with the interval the metadata claims ──
    span_start = max(lookback_start, first_price)
    span_end = min(session_date, last_price)
    if span_start > span_end:
        return LineageDecision(ticker, False, perma,
                               refusal=LineageRefusal.AMBIGUOUS_EFFECTIVE_INTERVAL,
                               detail=f"effective interval {first_price}..{last_price} does not "
                                      f"intersect the lookback {lookback_start}..{session_date}")

    governed = sessions if sessions is not None else _sessions_between(con, span_start, span_end)
    window = [d for d in governed if span_start <= d <= span_end]
    if not window:
        return LineageDecision(ticker, False, perma, refusal=LineageRefusal.METADATA_PRICE_DISAGREE,
                               detail="no governed session falls inside the claimed interval")

    marks = {r[0] for r in con.execute(
        "SELECT date FROM sep WHERE ticker = ? AND date BETWEEN ? AND ? AND closeadj IS NOT NULL",
        [ticker, span_start, span_end]).fetchall()}
    if not marks:
        return LineageDecision(
            ticker, False, perma, refusal=LineageRefusal.METADATA_PRICE_DISAGREE,
            detail=f"metadata claims the lineage traded {span_start}..{span_end} but SEP holds no "
                   f"mark for the symbol in that span")

    present = [d in marks for d in window]

    # a first mark materially later than the metadata's own start
    late = 0
    for ok in present:
        if ok:
            break
        late += 1
    if late >= LATE_START_SESSIONS:
        return LineageDecision(
            ticker, False, perma, refusal=LineageRefusal.METADATA_PRICE_DISAGREE,
            detail=f"metadata claims trading from {span_start} but the first mark is {late} governed "
                   f"session(s) later; the earlier history belongs to another lineage")

    # a structural hole with no rename to explain it
    run = worst = 0
    for ok in present:
        run = 0 if ok else run + 1
        worst = max(worst, run)
    if worst >= LINEAGE_GAP_SESSIONS:
        return LineageDecision(
            ticker, False, perma, refusal=LineageRefusal.UNRESOLVED_REMAP_GAP,
            detail=f"{worst} consecutive governed sessions have no mark inside the interval the "
                   f"metadata claims ({span_start}..{span_end}); a vendor remap this leaves cannot be "
                   f"resolved without a historical corpus correction")

    return LineageDecision(ticker, True, perma,
                           detail=f"single lineage {perma} spans {span_start}..{span_end}")


def assess_universe(store: Any, candidates: list[str], *, session_date: date,
                    lookback_start: date) -> LineageAssessment:
    """Resolve every candidate, returning the eligible set and the full refusal record.

    Order is preserved for the eligible set: callers rank on it, and a resolver must not perturb the
    ordering the universe construction produced.
    """
    require_permanent_identifier(store)
    con = _con(store)
    sessions = _sessions_between(con, lookback_start, session_date)

    kept: list[str] = []
    dropped: list[LineageDecision] = []
    for t in candidates:
        decision = resolve_lineage(store, t, session_date=session_date,
                                   lookback_start=lookback_start, sessions=sessions)
        if decision.eligible:
            kept.append(t)
        else:
            dropped.append(decision)

    return LineageAssessment(
        session_date=session_date, lookback_start=lookback_start,
        contract=SECURITY_IDENTITY_CONTRACT, considered=len(candidates),
        eligible_tickers=tuple(kept), excluded=tuple(dropped))


@dataclass(frozen=True)
class BridgeRisk:
    """A lineage-excluded symbol whose in-window history could FABRICATE a return.

    The frozen market-proxy replica builds its own basket by calling `universe_asof` directly, so an
    excluded name is still present in its panel. That is harmless in every ordinary shape: a name that
    stopped trading has marks only before its hole, a name that started mid-window has marks only
    after, and `pct_change` yields NaN across the boundary either way — dropped by `skipna`.

    The one shape that is NOT harmless is marks on BOTH sides of a long hole: `pct_change` then bridges
    two disconnected segments and manufactures a single enormous return that flows straight into the
    equal-weighted index and the regime it drives. Since the replica may not be modified, the session
    refuses upstream instead.
    """

    ticker: str
    permaticker: str | None
    hole_sessions: int
    hole_start: date
    hole_end: date
    last_mark_before: date
    first_mark_after: date

    def to_evidence(self) -> dict[str, Any]:
        return {
            "symbol": self.ticker, "permaticker": self.permaticker,
            "reason": "LINEAGE_BRIDGE_RISK", "marks_before": True, "marks_after": True,
            "hole_sessions": self.hole_sessions,
            "hole_start": self.hole_start.isoformat(), "hole_end": self.hole_end.isoformat(),
            "last_mark_before": self.last_mark_before.isoformat(),
            "first_mark_after": self.first_mark_after.isoformat(),
        }


def assess_bridge_risk(store: Any, excluded: tuple[LineageDecision, ...], *, window: list[date],
                       min_hole_sessions: int = LINEAGE_BRIDGE_HOLE_MIN_SESSIONS,
                       ) -> tuple[BridgeRisk, ...]:
    """Find lineage-excluded symbols that could bridge a fabricated return across the proxy window.

    Measured in GOVERNED SESSIONS, not calendar days — a fortnight of holidays is not a hole — and
    deliberately narrow: only names already excluded by the identity contract are examined, and only
    the both-sides shape qualifies. A long one-sided gap is the ordinary delisting/new-listing case and
    must stay non-blocking; generalising this into "any long gap fails" would refuse most of a normal
    month-end basket.

    This can only ever ADD a refusal. It never returns a name to eligibility.
    """
    if not excluded or not window:
        return ()
    con = _con(store)
    ordered = sorted(window)
    start, end = ordered[0], ordered[-1]

    risks: list[BridgeRisk] = []
    for decision in excluded:
        marks = {r[0] for r in con.execute(
            "SELECT date FROM sep WHERE ticker = ? AND date BETWEEN ? AND ? "
            "AND closeadj IS NOT NULL", [decision.ticker, start, end]).fetchall()}
        if not marks:
            continue
        present = [d in marks for d in ordered]

        run = 0
        run_end = -1
        worst = 0
        worst_end = -1
        for i, ok in enumerate(present):
            if ok:
                run = 0
                continue
            run += 1
            run_end = i
            if run > worst:
                worst, worst_end = run, run_end
        if worst < min_hole_sessions or worst_end < 0:
            continue
        worst_start = worst_end - worst + 1
        before = [d for d, ok in zip(ordered[:worst_start], present[:worst_start], strict=True) if ok]
        after = [d for d, ok in zip(ordered[worst_end + 1:], present[worst_end + 1:], strict=True)
                 if ok]
        if not before or not after:
            continue                    # one-sided: ordinary delisting or new listing
        risks.append(BridgeRisk(
            ticker=decision.ticker, permaticker=decision.permaticker, hole_sessions=worst,
            hole_start=ordered[worst_start], hole_end=ordered[worst_end],
            last_mark_before=before[-1], first_mark_after=after[0]))
    return tuple(risks)


class SessionLineageFilter:
    """Applies the identity contract to EVERY universe call made for one session.

    This is the containment point, and it is deliberately the `UniverseFn` rather than any individual
    consumer. Ranking, proxy-basket construction, score computation, target sizing and the
    completeness numerator all obtain their candidates from that one callable, so filtering it once
    means no downstream consumer can accidentally see the pre-filter set — which is the actual
    implementation risk here, not the resolver's own sophistication.

    The lookback is the SESSION's, not the `as_of` of the individual call: the proxy basket is a union
    of month-end universes, but every name in it is used to compute values over the session's window,
    so that is the window its lineage must be consistent across.

    Decisions are memoized because the basket calls the universe once per month-end and names repeat
    heavily; resolution is pure with respect to a fixed store and session.
    """

    def __init__(self, store: Any, *, session_date: date, lookback_start: date) -> None:
        require_permanent_identifier(store)
        self._store = store
        self.session_date = session_date
        self.lookback_start = lookback_start
        self._decisions: dict[str, LineageDecision] = {}
        self._raw_seen: set[str] = set()
        self._sessions = _sessions_between(_con(store), lookback_start, session_date)

    def _decide(self, ticker: str) -> LineageDecision:
        cached = self._decisions.get(ticker)
        if cached is None:
            cached = resolve_lineage(self._store, ticker, session_date=self.session_date,
                                     lookback_start=self.lookback_start, sessions=self._sessions)
            self._decisions[ticker] = cached
        return cached

    def filter(self, candidates: list[str]) -> list[str]:
        """Return only the lineage-eligible candidates, order preserved."""
        self._raw_seen.update(candidates)
        return [t for t in candidates if self._decide(t).eligible]

    def wrap(self, universe_fn: Any) -> Any:
        """Wrap a `UniverseFn`, so every consumer of it inherits the filter."""

        def fn(as_of: date, n: int) -> list[str]:
            return self.filter(list(universe_fn(as_of, n)))

        return fn

    @property
    def raw_seen_count(self) -> int:
        return len(self._raw_seen)

    def assessment(self) -> LineageAssessment:
        """Everything resolved for this session, across every universe call made."""
        excluded = tuple(d for t, d in sorted(self._decisions.items()) if not d.eligible)
        eligible = tuple(sorted(t for t, d in self._decisions.items() if d.eligible))
        return LineageAssessment(
            session_date=self.session_date, lookback_start=self.lookback_start,
            contract=SECURITY_IDENTITY_CONTRACT, considered=len(self._decisions),
            eligible_tickers=eligible, excluded=excluded)


__all__ = [
    "LATE_START_SESSIONS",
    "LINEAGE_BRIDGE_HOLE_MIN_SESSIONS",
    "LINEAGE_GAP_SESSIONS",
    "SECURITY_IDENTITY_CONTRACT",
    "BridgeRisk",
    "LineageAssessment",
    "LineageDecision",
    "LineageRefusal",
    "SecurityIdentityUnavailable",
    "SessionLineageFilter",
    "assess_bridge_risk",
    "assess_universe",
    "require_permanent_identifier",
    "resolve_lineage",
]
