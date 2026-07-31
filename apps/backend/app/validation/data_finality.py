"""Forward-validation DATA-FINALITY gate — prove the session's data is final before it is evaluated.

A forward observation is a claim about what the frozen instrument decided on a specific market session.
That claim is only as good as the data the decision was computed from, so before an eligible session may
be evaluated the runner must PROVE — not assume — that every input the registered construction reads is
present, complete and final for that exact date.

The registered construction is the census one and is not negotiable here (owner ruling 2026-07-24):
scores from `FactorDataStore` → `_CachedPriceStore` → `backtest_momentum_stage2.compute_day` (which is
`universe_asof(n=200)` → `compute_momentum_batch(252/21)`); regime from `stage4.build_market_proxy` /
`gross_series` over the BROAD EQUAL-WEIGHT proxy — the month-end union of `universe_asof(n=500)`, not
SPY and not any convenience benchmark — with a 200-session MA; prices from the same store's `closeadj`.

This module computes no factor value, return, ranking or portfolio result. It calls the SAME universe
construction the decision will call, so coverage is measured against the exact set of names the frozen
computation consumes, and it records what it found next to what the construction required.

## Verdicts

  READY                             every registered input is present, complete and final
  NOT_READY_DATA_STALE              the store's finalized cutoff precedes the session
  NOT_READY_CURRENT_SESSION_MISSING a name the construction admits has no usable mark on the session
  NOT_READY_LOOKBACK_INCOMPLETE     a scoring candidate lacks the exact 252+21-session history
  NOT_READY_PROXY_INCOMPLETE        a proxy constituent cannot contribute its return, on this session
                                    or on any of the 200 MA sessions
  NOT_READY_INGEST_IN_PROGRESS      an ingest is running, or the last one did not finish clean
  NOT_READY_ADJUSTMENT_UNVERIFIED   corporate-action reflection over the consumed window is not proven
                                    (including: no verifier configured, or the declared set is
                                    incomplete)
  INTEGRITY_STOP_DATA_CONFLICT      the data contradicts itself (duplicates, or the store moved
                                    underneath a run)

A NOT_READY_* verdict is the system working. The known stale-SEP condition on the box is exactly what
this gate is for: surfaced accurately, never bypassed.

## Coverage is construction-derived, not threshold-derived

There are no coverage minima. A name is either supplied to the frozen computation or it is not, and if
it is not, the reason must be a frozen eligibility RULE (listed after the window began, delisted before
the session) rather than a hole in the data. Every count is reported as a numerator over the
construction's own denominator, so "how much data was missing" is never a matter of interpretation.

## Corporate actions gate the session until reflection is PROVEN

The schema cannot show that an action is already baked into `closeadj`, and — critically — an EMPTY
`actions` table is not evidence that no action occurred. The governed store holds zero action rows while
`closeadj` departs from `close` on ~48% of its 39M rows, so a row count would let a session pass
vacuously. Reflection must therefore be proven by an `adjustment_verifier` (R5b) whose evidence object
the gate reads; the gate derives `adjustment_reflection_proven` from that verdict and never accepts an
independently supplied boolean. No verifier configured means nothing is proven, which means the session
does not run (owner ruling 2026-07-24).

## The store identity is value-level

`ingest_runs` carries no batch id and `sep` rows carry no version, so "all reads resolve from one
immutable ingest version" is CONSTRUCTED: a streaming SHA-256 over the deterministically ordered ROWS
the decision will consume — every `sep` field, the `tickers` PIT-eligibility fields, the window's
actions, and the ingest history. Aggregate counts would let a single changed `closeadj` slip through
unnoticed; hashing the values themselves does not. `verify_store_unchanged` re-streams it after the
session's reads, and any difference is `INTEGRITY_STOP_DATA_CONFLICT`.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

# The ONE production bound on what lands in an immutable observation. Imported rather than restated:
# a narrow-readiness clause that pins the cap must pin the SAME cap the verifier enforces, and a second
# copy of the number is a pin that can drift silently. `adjustment_verifier` imports nothing from here,
# so this direction carries no cycle; the rest of the coupling stays behind `AdjustmentEvidence`.
from app.validation.adjustment_verifier import MAX_EVIDENCE_ACTIONS
from app.validation.forward_window import IntegrityStop
from app.validation.security_lineage import (
    LINEAGE_BRIDGE_HOLE_MIN_SESSIONS,
    SessionLineageFilter,
    assess_bridge_risk,
)

# The registered construction constants (§2 / stage2 / stage4 frozen controls).
MOMENTUM_LOOKBACK_SESSIONS = 252
MOMENTUM_SKIP_SESSIONS = 21
REGIME_MA_SESSIONS = 200
SCORING_UNIVERSE_N = 200                  # stage2 UNIVERSE_N
PROXY_UNIVERSE_N = 500                    # stage4 build_market_proxy basket

# Datasets a forward session reads. An unclean ingest in any of them blocks the session.
REQUIRED_DATASETS = ("sep", "actions")

_ROW_SEP = "\x1e"
_FIELD_SEP = "\x1f"


class DataReadiness(StrEnum):
    READY = "READY"
    #: A NARROWER readiness claim than `READY`, and deliberately a distinct verdict rather than a flag
    #: on it: the session's DECISION is proven valid while some corporate actions remain economically
    #: unproven.
    #:
    #: ⚠ This is NOT a waiver and NOT an operator override. It is reachable only through
    #: `NarrowReadinessAttestation`, every clause of which is machine-checked against the measured
    #: adjustment evidence, and it NEVER sets `adjustment_reflection_proven` — the broad claim "every
    #: corporate action is economically reconciled" stays FALSE and visible.
    #:
    #: ⚠⚠ It is SESSION-SCOPED BY CONSTRUCTION. The attestation names one `session_date` and is refused
    #: for any other, so it cannot silently persist into a later observation; a future session must
    #: recompute its own relevance assessment or fall back to `NOT_READY_ADJUSTMENT_UNVERIFIED`.
    READY_DECISION_VALID_WITH_DISCLOSED_NONDECISION_LIMITATIONS = (
        "READY_DECISION_VALID_WITH_DISCLOSED_NONDECISION_LIMITATIONS")
    NOT_READY_DATA_STALE = "NOT_READY_DATA_STALE"
    NOT_READY_CURRENT_SESSION_MISSING = "NOT_READY_CURRENT_SESSION_MISSING"
    NOT_READY_LOOKBACK_INCOMPLETE = "NOT_READY_LOOKBACK_INCOMPLETE"
    NOT_READY_PROXY_INCOMPLETE = "NOT_READY_PROXY_INCOMPLETE"
    NOT_READY_LINEAGE_BRIDGE_RISK = "NOT_READY_LINEAGE_BRIDGE_RISK"
    NOT_READY_INGEST_IN_PROGRESS = "NOT_READY_INGEST_IN_PROGRESS"
    NOT_READY_ADJUSTMENT_UNVERIFIED = "NOT_READY_ADJUSTMENT_UNVERIFIED"
    INTEGRITY_STOP_DATA_CONFLICT = "INTEGRITY_STOP_DATA_CONFLICT"


#: The verdicts under which a session may be EVALUATED. The narrow one is included DELIBERATELY — it is
#: the outcome that says "this decision is valid" — but it stays a SEPARATE verdict so nothing can
#: mistake it for the broad proof, and `adjustment_reflection_proven` remains False under it.
#:
#: ⚠ Exported so consumers test membership instead of hard-coding `== "READY"`. A literal comparison is
#: how the narrow status silently flattens into a plain READY downstream — which is precisely what the
#: separate verdict exists to prevent.
READINESS_PERMITS_EVALUATION = frozenset({
    DataReadiness.READY,
    DataReadiness.READY_DECISION_VALID_WITH_DISCLOSED_NONDECISION_LIMITATIONS,
})


@dataclass(frozen=True)
class NarrowReadinessAttestation:
    """The ONE route to `READY_DECISION_VALID_WITH_DISCLOSED_NONDECISION_LIMITATIONS`.

    It carries no authority of its own. Every clause below is RE-DERIVED from the measured adjustment
    evidence and refused on mismatch, so the attestation can only ever confirm what the data already
    shows — it can never assert something into being true. In particular it cannot mark an action
    proven, cannot suppress a conflict, and cannot admit an unassessed action.

    ⚠⚠ `session_date` is what stops this becoming a standing exception. The attestation is refused for
    any session other than the one it names, so the narrow status must be re-earned — with a freshly
    computed relevance assessment — for every future observation.

    The three digests bind the claim to the artifacts that measured it: the complete reconciliation, the
    decision-relevance assessment, and the quarantine. A reader holding this evidence can fetch all
    three and re-derive the verdict rather than trusting it.
    """
    session_date: date
    reconciliation_artifact_sha256: str
    relevance_artifact_sha256: str
    quarantine_artifact_sha256: str
    #: The digest of the EXACT relevance set the readiness construction builds — `relevance_digest`
    #: over (store identity, window start, session date, sorted names).
    #:
    #: ⚠⚠ REQUIRED, and the reason this field exists at all. On 2026-07-27 the attestation's census was
    #: copied from a DIAGNOSTIC runner that assembled its own relevance set (689 identities) while the
    #: readiness path assembles a different one (670). Every count downstream of that divergence was
    #: wrong, and nothing in the contract could see it, because the two sets were never compared. Now
    #: they are: a census can only be checked against the set it was measured over.
    relevance_set_sha256: str = ""
    #: PERMANENT identities whose price history this vintage withholds. Unexplained factor movements
    #: are tolerated only on these, and only because they are excluded from the decision path.
    quarantined_identities: frozenset[str] = frozenset()
    #: The per-status census this attestation was written against. If the measurement has moved, the
    #: attestation is stale and is refused rather than reinterpreted.
    #:
    #: ⚠ Must be DERIVED from the readiness construction — see `build_narrow_readiness_attestation`.
    #: Hand-entered or diagnostic-sourced counts are what the `relevance_set_sha256` clause exists to
    #: catch.
    expected_status_counts: dict[str, int] = field(default_factory=dict)


#: Per-action statuses that a narrow-readiness session may still carry. Exactly one, and it is the
#: DISCLOSED limitation — never the default-deny bucket, never a conflict, never insufficiency.
_NARROW_TOLERATED_STATUS = "UNRESOLVED_NONDECISION_MA_SEMANTICS"
_NARROW_DISCLOSURE_REASON = "ACQUIRED_SIDE_ECONOMICALLY_TERMINAL_AND_MEASURED_NON_DECISION_RELEVANT"


def _narrow_readiness_refusals(
    adjustment: dict[str, Any], attestation: NarrowReadinessAttestation, session_date: date,
) -> list[str]:
    """Every reason the narrow claim does NOT hold. Empty list == the claim is supported.

    Written as a refusal list rather than a boolean so the evidence can state precisely WHICH clause
    failed; a bare False would make an operator guess.
    """
    out: list[str] = []
    if attestation.session_date != session_date:
        out.append(f"the attestation names session {attestation.session_date.isoformat()} but this "
                   f"assessment describes {session_date.isoformat()}; the narrow status is "
                   f"session-scoped and is never inherited by another observation")
        return out          # nothing else is meaningful once the session does not match

    counts = dict(adjustment.get("checks_by_status") or {})
    if not counts:
        out.append("the adjustment evidence carries no per-status census to check")
        return out

    # (1) every canonical action assessed — the default-deny bucket must be EMPTY.
    never = counts.get("NOT_PROVEN_UNSUPPORTED_SEMANTICS", 0)
    if never:
        out.append(f"{never} action(s) were never assessed and remain at the default-deny status")

    # (2) nothing conflicting or insufficient may hide behind the disclosure.
    for bad in ("PROVEN_NOT_REFLECTED", "SOURCE_CONFLICT", "NOT_PROVEN_INSUFFICIENT_DATA"):
        if counts.get(bad, 0):
            out.append(f"{counts[bad]} action(s) are {bad}")

    # (3) the ONLY non-proven status permitted is the disclosed limitation.
    permitted = {"PROVEN_REFLECTED", "PROVEN_NO_PRICE_ADJUSTMENT_APPLICABLE",
                 "PROVEN_LINEAGE_EVENT_NO_ADDITIONAL_PRICE_ADJUSTMENT", _NARROW_TOLERATED_STATUS}
    for status, n in counts.items():
        if status not in permitted:
            out.append(f"{n} action(s) carry {status}, which the narrow claim does not admit")

    # (4) every disclosed action must carry SESSION-BOUND relevance evidence, bound by digest.
    disclosed = counts.get(_NARROW_TOLERATED_STATUS, 0)
    reasons = dict(adjustment.get("checks_by_reason_code") or {})
    if disclosed and reasons.get(_NARROW_DISCLOSURE_REASON, 0) != disclosed:
        out.append(f"{disclosed} disclosed action(s) but "
                   f"{reasons.get(_NARROW_DISCLOSURE_REASON, 0)} carry the named relevance reason "
                   f"code; a disclosure without its measured basis is not admissible")
    bound = adjustment.get("ma_disclosure_sha256")
    if disclosed and bound != attestation.relevance_artifact_sha256:
        out.append(f"the disclosure is bound to assessment {str(bound)[:16]}… but the attestation "
                   f"names {attestation.relevance_artifact_sha256[:16]}…")

    # (5) every relevant action must be CLASSIFIED — CENSUS completeness, not PAYLOAD completeness.
    #
    # ⚠ This clause previously required `truncated == False`, which made the narrow status UNREACHABLE
    # in production and was only ever satisfied by a diagnostic that raised the cap in its own process.
    # `truncated` describes the bounded per-action DETAIL carried in the immutable observation; the
    # census is computed over EVERY check before bounding (`evidence()` in R5b), so truncation says
    # nothing whatever about whether an action was assessed. Against 1,764 relevant actions and a
    # 200-action receipt cap, the old clause could not pass however clean the data was.
    #
    # The property actually worth proving is that the census accounts for every action, and that the
    # bounding arithmetic is internally consistent — a receipt cannot claim 200 of 1,764 while the
    # census sums to something else. The production cap stays exactly where it is.
    action_evidence = dict(adjustment.get("action_evidence") or {})
    if not action_evidence:
        out.append("the adjustment evidence carries no bounded-evidence record, so the per-action "
                   "census cannot be reconciled against what was serialized")
    else:
        total = int(action_evidence.get("total_action_count") or 0)
        omitted = int(action_evidence.get("omitted_action_count") or 0)
        cap = int(action_evidence.get("max_actions") or 0)
        # Measured on the list actually carried, not on the count the record claims for it.
        serialized = len(list(adjustment.get("checks") or ()))
        census = sum(int(n) for n in counts.values())
        if census != total:
            out.append(f"the per-status census sums to {census} but {total} action(s) were assessed; "
                       f"'every action classified' is exactly the claim that does not hold")
        if omitted != total - serialized:
            out.append(f"the bounded-evidence arithmetic is inconsistent: {total} assessed, "
                       f"{serialized} serialized, {omitted} recorded as omitted")
        if bool(action_evidence.get("truncated")) is not (omitted > 0):
            out.append(f"truncated={action_evidence.get('truncated')} contradicts "
                       f"{omitted} omitted action(s)")
        # The cap is a PRODUCTION control. An evidence object built with a raised cap is a diagnostic
        # one, and a diagnostic must not be able to satisfy a production readiness contract.
        if cap <= 0 or cap > MAX_EVIDENCE_ACTIONS:
            out.append(f"the evidence was bounded at {cap} action(s), not the production cap of "
                       f"{MAX_EVIDENCE_ACTIONS}; a raised cap makes this a diagnostic record")
        elif serialized > cap:
            out.append(f"{serialized} action(s) serialized against a cap of {cap}")

    # (6) every unexplained factor movement must sit on a QUARANTINED identity.
    #
    # The examples list is bounded, so it can only discharge this if it is complete; otherwise a
    # movement could exist on a non-quarantined name and simply not be shown.
    total = int(adjustment.get("unexplained_adjustment_count") or 0)
    examples = list(adjustment.get("unexplained_examples") or [])
    if total != len(examples):
        out.append(f"{total} unexplained factor movement(s) but only {len(examples)} recorded; the "
                   f"census cannot be checked against the quarantine")
    else:
        stray = sorted({str(e.get("permaticker")) for e in examples
                        if str(e.get("permaticker")) not in attestation.quarantined_identities})
        if stray:
            out.append(f"unexplained factor movement(s) on non-quarantined identities {stray}")

    # (7) the census must have been measured over THIS session's relevance set.
    #
    # ⚠ Checked BEFORE the counts, because it is the clause that explains them. Two runs over different
    # identity sets produce different censuses for the same data, and comparing counts alone reports a
    # stale attestation without saying why. This binds the census to the set it was measured over.
    measured_set = str(adjustment.get("relevance_set_sha256") or "")
    if not attestation.relevance_set_sha256:
        out.append("the attestation names no relevance set, so its census cannot be attributed to any "
                   "particular construction; derive it with build_narrow_readiness_attestation")
    elif attestation.relevance_set_sha256 != measured_set:
        out.append(f"the attestation was written over relevance set "
                   f"{attestation.relevance_set_sha256[:16]}… but this assessment constructed "
                   f"{(measured_set or '<none>')[:16]}…; the census describes a different set of "
                   f"securities and is not evidence about this one")

    # (8) the measured census must match what the attestation was written against.
    if not attestation.expected_status_counts:
        out.append("the attestation carries no expected census, so there is nothing to re-derive the "
                   "measurement against")
    elif dict(attestation.expected_status_counts) != counts:
        out.append(f"the attestation was written against {dict(attestation.expected_status_counts)} "
                   f"but the measurement is {counts}; the attestation is stale")
    return out


class DataFinalityError(IntegrityStop):
    """The store could not be interrogated at all (unreadable / wrong shape), or it moved underneath a
    run. Fails closed: a session whose data cannot be examined is never evaluated."""


@dataclass(frozen=True)
class ConstructionSpec:
    """The frozen construction the gate measures against. These are the registered values the decision
    itself uses — not tunable admission thresholds."""
    momentum_lookback_sessions: int = MOMENTUM_LOOKBACK_SESSIONS
    momentum_skip_sessions: int = MOMENTUM_SKIP_SESSIONS
    regime_ma_sessions: int = REGIME_MA_SESSIONS
    scoring_universe_n: int = SCORING_UNIVERSE_N
    proxy_universe_n: int = PROXY_UNIVERSE_N

    @property
    def required_history_sessions(self) -> int:
        return max(self.momentum_lookback_sessions + self.momentum_skip_sessions,
                   self.regime_ma_sessions)


@dataclass(frozen=True)
class DataFinalityEvidence:
    """OPEN operational provenance for one readiness assessment. Counts, dates, digests and verdicts
    only — no factor values, no returns, no rankings, no portfolio results."""
    session_date: str
    verdict: DataReadiness
    detail: str
    # store + ingest identity
    store_path: str
    store_identity_sha256: str                 # STREAMING value-level digest of the consumed rows
    ingest_identity_sha256: str
    ingest_runs_observed: int
    ingest_unclean_datasets: tuple[str, ...]
    # finality
    max_finalized_session: str | None
    finality_basis: str
    # session coverage — numerator over the construction's own denominator
    session_eligible_universe: int
    session_complete: int
    session_excluded_by_rule: int
    session_missing: int
    session_row_count: int
    session_max_lastupdated: str | None
    # lookback coverage
    lookback_sessions_available: int
    lookback_sessions_required: int
    lookback_earliest: str | None
    lookback_latest: str | None
    momentum_candidates: int
    full_lookback_candidates: int
    # market-proxy coverage
    proxy_expected_constituents: int
    proxy_contributing_constituents: int
    proxy_sessions_checked: int
    proxy_sessions_incomplete: int
    # conflicts
    duplicate_row_count: int
    # corporate actions
    corporate_actions_in_window: int
    corporate_actions_max_date: str | None
    adjustment_reflection_proven: bool
    adjustment_evidence: dict[str, Any] | None
    # what the construction required
    construction: dict[str, int] = field(default_factory=dict)
    missing_examples: tuple[str, ...] = ()     # a few names, for operational diagnosis
    # Security-identity resolution (PERMATICKER_EFFECTIVE_INTERVAL_V1). Carries the contract version,
    # the raw and lineage-eligible counts, and every exclusion with its reason and permanent ids.
    # Recorded so the 691 → 672 → 664 path reads as three named steps rather than one unexplained
    # reduction: raw → lineage-eligible (here) → rule-eligible (`proxy_expected_constituents`) →
    # contributing (`proxy_contributing_constituents`).
    lineage: dict[str, Any] | None = None
    # Kept SEPARATE from the exclusion counts on purpose: a name may be lineage-excluded without
    # threatening the frozen proxy, and only the bridge shape stops the session.
    lineage_proxy_bridge_check: dict[str, Any] | None = None

    @property
    def ready(self) -> bool:
        """Whether the session may be evaluated. ⚠ NOT the same question as whether every corporate
        action is economically reconciled — read `adjustment_reflection_proven` for that, and
        `fully_proven` for both together."""
        return self.verdict in READINESS_PERMITS_EVALUATION

    @property
    def fully_proven(self) -> bool:
        """The BROAD claim: evaluable AND every corporate action economically reconciled."""
        return self.verdict is DataReadiness.READY and self.adjustment_reflection_proven

    @property
    def has_disclosed_limitations(self) -> bool:
        return (self.verdict
                is DataReadiness.READY_DECISION_VALID_WITH_DISCLOSED_NONDECISION_LIMITATIONS)

    def to_open_provenance(self) -> dict[str, Any]:
        d = asdict(self)
        d["verdict"] = str(self.verdict)
        d["ingest_unclean_datasets"] = list(self.ingest_unclean_datasets)
        d["missing_examples"] = list(self.missing_examples)

        # ── the readiness CLAIM, stated at the top level ────────────────────────────────────────────
        #
        # `ready` alone is not a faithful summary once a second ready verdict exists: a receipt saying
        # only `ready: true` would read identically for a fully proven session and for one carrying
        # disclosed limitations. `fully_proven` and `has_disclosed_limitations` are PROPERTIES, so
        # `asdict` drops them — they are added explicitly, and the limitation detail is lifted out of
        # `adjustment_evidence` rather than left for a reader to go digging for.
        # ⚠ ALL THREE are @property, so `asdict` drops every one of them. `ready` in particular is the
        # field a downstream reader is most likely to look for, and its absence would be silent.
        d["readiness_verdict"] = str(self.verdict)
        d["ready"] = self.ready
        d["fully_proven"] = self.fully_proven
        d["has_disclosed_limitations"] = self.has_disclosed_limitations
        # Stated at the top level, not only inside the limitation block: a receipt must answer "were
        # all action semantics proven?" without the reader having to know that the answer hides one
        # level down, and it must answer it on EVERY path — including the fully proven one.
        d["full_action_semantics_proven"] = self.fully_proven
        d["disclosed_limitations"] = self._disclosed_limitations()
        return d

    def _disclosed_limitations(self) -> dict[str, Any] | None:
        """The limitation block a downstream receipt must carry, or None when there is none.

        ⚠ Deliberately built even if `narrow_readiness` is absent from the adjustment evidence, so a
        narrow verdict can never be serialized without SOME statement of what was limited.
        """
        if not self.has_disclosed_limitations:
            return None
        adj = self.adjustment_evidence or {}
        narrow = adj.get("narrow_readiness") or {}
        counts = adj.get("checks_by_status") or {}
        reasons = adj.get("checks_by_reason_code") or {}
        tolerated = counts.get(_NARROW_TOLERATED_STATUS, 0)
        unexplained = int(adj.get("unexplained_adjustment_count") or 0)
        return {
            "session_date": narrow.get("attested_session", self.session_date),
            "limitation_status": _NARROW_TOLERATED_STATUS,
            # ⚠ The ACTIVE limitation for this session, measured over this session's relevance set.
            # It is legitimately 0 when the adjudicated events lie outside that set — see below.
            "limitation_count": tolerated,
            # ⚠ Filtered on the COUNT, not merely on the key's presence. The census carries a key for
            # every reason code the verifier knows about, so a presence test lists a reason that fired
            # zero times — which reads as a finding.
            "limitation_reason_codes": sorted(
                code for code, n in reasons.items() if code == _NARROW_DISCLOSURE_REASON and n),
            # ⚠⚠ The two figures a reader needs in order NOT to be misled. A corpus-wide adjudication
            # is not a session finding: an event the relevance set never contains cannot limit a
            # decision the relevance set produced. Stated side by side so neither can be read as the
            # other.
            "known_corpus_wide_unsupported_semantics": adj.get("ma_disclosure_entry_count"),
            "present_in_readiness_relevance_set": tolerated,
            "readiness_relevance_set_sha256": adj.get("relevance_set_sha256"),
            "relevant_ticker_count": adj.get("relevant_ticker_count"),
            "unexplained_movements_on_quarantined_identities": unexplained,
            "reconciliation_artifact_sha256": narrow.get("reconciliation_artifact_sha256"),
            "relevance_artifact_sha256": narrow.get("relevance_artifact_sha256"),
            "quarantine_artifact_sha256": narrow.get("quarantine_artifact_sha256"),
            "quarantined_identities": narrow.get("quarantined_identities", []),
            "full_action_semantics_proven": False,
            "claim": "the decision this session makes is valid; the broad proof that EVERY corporate "
                     "action is economically reconciled does not hold, and each condition that "
                     "remains was measured over this session's own relevance set to have no part in "
                     "the decision",
        }


UniverseFn = Callable[[date, int], list[str]]


class AdjustmentEvidence(Protocol):
    """What an adjustment verifier returns. The gate DERIVES `adjustment_reflection_proven` from this
    evidence — it never accepts an independently supplied boolean."""
    proven: bool

    def to_open_provenance(self) -> dict[str, Any]: ...


# (window_start, session_date, relevant_tickers, store_identity_sha256) -> evidence.
#
# The relevance set is the union of the scoring candidates and the whole market-proxy basket, so a
# security that left the universe mid-window but priced into the consumed history is still covered.
# The STORE IDENTITY is passed IN rather than recomputed: the adjustment verdict must be bound to the
# same identified store this assessment describes, and a separately recomputed value could differ.
AdjustmentVerifier = Callable[[date, date, list[str], str], AdjustmentEvidence]


class _Store:
    """Thin read-only SQL surface over the factor store. Accepts a `FactorDataStore` (its `.con`) or a
    duckdb connection, so the gate can be exercised without importing the ingest path."""

    def __init__(self, store: Any) -> None:
        con = getattr(store, "con", store)
        if not hasattr(con, "execute"):
            raise DataFinalityError(f"not a queryable store: {type(store).__name__}")
        self.con = con
        self.raw = store
        self.path = str(getattr(store, "db_path", "") or getattr(con, "database", "") or "unknown")

    def one(self, sql: str, params: list | None = None) -> tuple:
        try:
            row = self.con.execute(sql, params or []).fetchone()
        except Exception as exc:
            raise DataFinalityError(f"store query failed: {exc}") from exc
        return tuple(row) if row is not None else ()

    def all(self, sql: str, params: list | None = None) -> list[tuple]:
        try:
            return [tuple(r) for r in self.con.execute(sql, params or []).fetchall()]
        except Exception as exc:
            raise DataFinalityError(f"store query failed: {exc}") from exc

    def stream_into(self, digest: Any, sql: str, params: list | None = None,
                    *, batch: int = 10_000) -> None:
        """Feed a query's deterministically ordered rows into `digest` without materializing them."""
        digest.update(sql.encode("utf-8"))
        try:
            cur = self.con.execute(sql, params or [])
            while True:
                rows = cur.fetchmany(batch)
                if not rows:
                    break
                for r in rows:
                    digest.update(
                        (_FIELD_SEP.join("" if v is None else str(v) for v in r) + _ROW_SEP)
                        .encode("utf-8"))
        except DataFinalityError:
            raise
        except Exception as exc:
            raise DataFinalityError(f"store query failed: {exc}") from exc


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime | date):
        return value.isoformat()
    return str(value)


def _digest(parts: list[Any]) -> str:
    return hashlib.sha256("|".join("" if p is None else str(p) for p in parts).encode()).hexdigest()


def store_identity(st: _Store, earliest: Any, session_date: date) -> str:
    """A STREAMING value-level digest over exactly the rows a session's construction consumes.

    Aggregates (counts, dates, coverage) cannot serve here: changing one `closeadj` leaves every
    aggregate intact while changing what the strategy decides. The digest therefore covers each `sep`
    field in the window, the `tickers` rows that drive PIT eligibility, the window's corporate actions,
    and the ingest history — each streamed in a deterministic order.
    """
    h = hashlib.sha256()
    lo = earliest if earliest is not None else session_date
    st.stream_into(h,
                   "SELECT ticker, date, open, high, low, close, volume, closeadj, closeunadj, "
                   "lastupdated FROM sep WHERE date BETWEEN ? AND ? ORDER BY ticker, date",
                   [lo, session_date])
    st.stream_into(h,
                   "SELECT ticker, sector, isdelisted, firstpricedate, lastpricedate, lastupdated "
                   "FROM tickers ORDER BY ticker")
    st.stream_into(h,
                   "SELECT date, action, ticker, value, contraticker FROM actions "
                   "WHERE date BETWEEN ? AND ? ORDER BY date, ticker, action, value",
                   [lo, session_date])
    st.stream_into(h,
                   "SELECT dataset, started_at, finished_at, rows, status FROM ingest_runs "
                   "ORDER BY dataset, started_at, finished_at, status")
    return h.hexdigest()


def _ingest_identity(st: _Store) -> tuple[str, int, tuple[str, ...]]:
    rows = st.all("SELECT dataset, started_at, finished_at, rows, status FROM ingest_runs "
                  "ORDER BY dataset, started_at, finished_at")
    digest = _digest([f"{d}~{_iso(s)}~{_iso(f)}~{r}~{stat}" for d, s, f, r, stat in rows])
    unclean: list[str] = []
    for dataset in REQUIRED_DATASETS:
        runs = [r for r in rows if r[0] == dataset]
        if not runs:
            continue                 # no bookkeeping is not evidence of a partial ingest; finality and
            # the adjustment rule below still have to be established on their own evidence.
        if any(str(r[4]).lower() == "running" for r in runs):
            unclean.append(f"{dataset}:running")
            continue
        latest = max(runs, key=lambda r: (r[2] or r[1] or datetime.min))
        if str(latest[4]).lower() != "ok":
            unclean.append(f"{dataset}:{latest[4]}")
    return digest, len(rows), tuple(unclean)


def _session_close_utc(session_date: date) -> datetime | None:
    try:
        import pandas_market_calendars as mcal
        schedule = mcal.get_calendar("XNYS").schedule(start_date=session_date, end_date=session_date)
        if schedule.empty:
            return None
        return schedule.iloc[0]["market_close"].tz_convert("UTC").to_pydatetime()
    except Exception:                                      # pragma: no cover
        return None


def _default_universe_fn(store: Any) -> UniverseFn:
    """Bind to the REAL registered universe construction — the same call the decision makes."""
    from app.factor_data.universe import universe_asof

    def fn(as_of: date, n: int) -> list[str]:
        return list(universe_asof(store, as_of, n=n))

    return fn


@dataclass(frozen=True)
class _TickerFacts:
    first_price: date | None
    last_price: date | None
    delisted: bool


def _ticker_facts(st: _Store, tickers: list[str]) -> dict[str, _TickerFacts]:
    if not tickers:
        return {}
    ph = ",".join("?" * len(tickers))
    rows = st.all(f"SELECT ticker, firstpricedate, lastpricedate, isdelisted FROM tickers "
                  f"WHERE ticker IN ({ph})", list(tickers))
    return {r[0]: _TickerFacts(first_price=r[1], last_price=r[2], delisted=bool(r[3])) for r in rows}


def _excluded_by_rule(facts: _TickerFacts | None, window_start: date, session_date: date) -> bool:
    """True when a frozen eligibility RULE — not a data hole — explains an absent mark: the name was
    listed after the window began (it cannot carry the history the computation consumes), or it was
    delisted before the session."""
    if facts is None:
        return False                                  # unknown name: not excused by any rule
    if facts.first_price is not None and facts.first_price > window_start:
        return True
    return bool(facts.delisted and facts.last_price is not None and facts.last_price < session_date)


def build_narrow_readiness_attestation(
    store: Any,
    session_date: date,
    *,
    construction: ConstructionSpec | None = None,
    universe_fn: UniverseFn | None = None,
    adjustment_verifier: AdjustmentVerifier,
    reconciliation_artifact_sha256: str,
    relevance_artifact_sha256: str,
    quarantine_artifact_sha256: str,
    quarantined_identities: frozenset[str] = frozenset(),
) -> tuple[NarrowReadinessAttestation, dict[str, Any]]:
    """Derive an attestation MECHANICALLY from the readiness construction, and record what it was
    derived from.

    ⚠⚠ THIS IS A SEPARATE, PRE-PRODUCTION STEP AND IS DELIBERATELY NOT REACHABLE FROM
    `assess_data_finality`. The readiness path must never learn its own expectations: an assessment
    that derived `expected_status_counts` from the run it is checking would agree with itself by
    construction, and clause (8) would prove nothing. What makes the derivation honest is that its
    OUTPUT is an artifact — reviewed, published and bound by digest — consumed by a later, independent
    run that re-derives every clause and refuses on any divergence.

    ⚠ Why this exists at all: on 2026-07-27 the attestation's census was copied from a DIAGNOSTIC
    runner that assembled its own relevance set (689 identities) rather than the one the readiness path
    builds (670). The counts were internally consistent and completely inapplicable, and the deployed
    runtime correctly refused them. Nothing here may be hand-entered; the relevance set, its digest and
    the census all come from ONE run of the identical production construction.

    Returns the attestation and an OPEN construction record naming the session, the relevance set it
    was measured over, that set's digest, the resulting census and every bound artifact digest.
    """
    seen: dict[str, Any] = {}

    def capturing(window_start: date, when: date, tickers: list[str],
                  store_identity: str) -> AdjustmentEvidence:
        # The relevance set is assembled INSIDE the assessment; capturing it at the one boundary it
        # crosses is what guarantees the attestation describes the production set and not a rebuild of
        # it. A second reconstruction here would reintroduce exactly the divergence this repairs.
        seen["relevant_tickers"] = sorted(set(tickers))
        seen["window_start"] = window_start
        return adjustment_verifier(window_start, when, tickers, store_identity)

    ev = assess_data_finality(store, session_date, construction=construction,
                              universe_fn=universe_fn, adjustment_verifier=capturing)
    adjustment = ev.adjustment_evidence or {}
    if not adjustment:
        raise DataFinalityError(
            f"the assessment stopped at {ev.verdict} before corporate-action verification, so no "
            f"relevance set or census exists to attest to: {ev.detail}")

    captured_start = seen.get("window_start")
    counts = {str(k): int(v) for k, v in (adjustment.get("checks_by_status") or {}).items()}
    attestation = NarrowReadinessAttestation(
        session_date=session_date,
        reconciliation_artifact_sha256=reconciliation_artifact_sha256,
        relevance_artifact_sha256=relevance_artifact_sha256,
        quarantine_artifact_sha256=quarantine_artifact_sha256,
        relevance_set_sha256=str(adjustment.get("relevance_set_sha256") or ""),
        quarantined_identities=frozenset(quarantined_identities),
        expected_status_counts=counts)
    record = {
        "derived_by": "build_narrow_readiness_attestation",
        "session_date": session_date.isoformat(),
        "window_start": captured_start.isoformat() if isinstance(captured_start, date) else None,
        "readiness_verdict_without_attestation": str(ev.verdict),
        "scoring_universe_n": ev.construction.get("scoring_universe_n"),
        "proxy_universe_n": ev.construction.get("proxy_universe_n"),
        "session_eligible_universe": ev.session_eligible_universe,
        "proxy_expected_constituents": ev.proxy_expected_constituents,
        "relevance_set_sha256": attestation.relevance_set_sha256,
        "relevant_ticker_count": len(seen.get("relevant_tickers") or ()),
        "relevant_identities": list(seen.get("relevant_tickers") or ()),
        "expected_status_counts": dict(counts),
        "store_identity_sha256": ev.store_identity_sha256,
        "reconciliation_artifact_sha256": reconciliation_artifact_sha256,
        "relevance_artifact_sha256": relevance_artifact_sha256,
        "quarantine_artifact_sha256": quarantine_artifact_sha256,
        "quarantined_identities": sorted(quarantined_identities),
        "ma_disclosure_sha256": adjustment.get("ma_disclosure_sha256"),
        "ma_disclosure_entry_count": adjustment.get("ma_disclosure_entry_count"),
        "unexplained_adjustment_count": adjustment.get("unexplained_adjustment_count"),
    }
    return attestation, record


def assess_data_finality(
    store: Any,
    session_date: date,
    *,
    construction: ConstructionSpec | None = None,
    universe_fn: UniverseFn | None = None,
    adjustment_verifier: AdjustmentVerifier | None = None,
    narrow_readiness: NarrowReadinessAttestation | None = None,
) -> DataFinalityEvidence:
    """Assess whether `session_date` may be evaluated, and return the evidence either way.

    Checks run root-condition first: unclean ingest → staleness and the finality basis → the session's
    own coverage against the registered universe → self-contradiction → the exact lookback the scoring
    candidates consume → the market proxy's own constituent set across the session and the MA window →
    corporate-action reflection.
    """
    spec = construction or ConstructionSpec()
    st = _Store(store)
    uni = universe_fn or _default_universe_fn(store)
    iso = session_date.isoformat()

    ingest_digest, ingest_count, unclean = _ingest_identity(st)

    window = st.all("SELECT DISTINCT date FROM sep WHERE date <= ? ORDER BY date DESC LIMIT ?",
                    [session_date, spec.required_history_sessions])
    window_dates = [r[0] for r in window]
    earliest = window_dates[-1] if window_dates else None
    latest = window_dates[0] if window_dates else None

    # ── security-identity resolution, applied at the ONE seam every consumer draws from ──
    # Wrapping the universe callable — rather than filtering inside each consumer — is what makes it
    # impossible for ranking, the proxy basket, the completeness numerator or the decision itself to
    # see a pre-filter candidate. A name whose lookback crosses a permanent-lineage boundary is not
    # merely excused from a denominator; it never reaches the computation at all.
    lineage_filter: SessionLineageFilter | None = None
    if earliest is not None:
        lineage_filter = SessionLineageFilter(store, session_date=session_date,
                                              lookback_start=earliest)
        uni = lineage_filter.wrap(uni)

    max_row = st.one("SELECT MAX(date) FROM sep")
    max_finalized = max_row[0] if max_row else None

    sess = st.one("SELECT COUNT(*), MAX(lastupdated) FROM sep WHERE date = ? AND closeadj IS NOT NULL",
                  [session_date])
    session_rows, session_lastupdated = (sess or (0, None))

    dup_row = st.one(
        "SELECT COUNT(*) FROM (SELECT ticker, date FROM sep WHERE date BETWEEN ? AND ? "
        "GROUP BY ticker, date HAVING COUNT(*) > 1)", [earliest or session_date, session_date])
    duplicates = int(dup_row[0]) if dup_row else 0

    act_row = st.one("SELECT COUNT(*), MAX(date) FROM actions WHERE date BETWEEN ? AND ?",
                     [earliest or session_date, session_date])
    actions_count, actions_max = (act_row or (0, None))

    identity = store_identity(st, earliest, session_date)

    state: dict[str, Any] = {
        "session_eligible_universe": 0, "session_complete": 0, "session_excluded_by_rule": 0,
        "session_missing": 0, "momentum_candidates": 0, "full_lookback_candidates": 0,
        "proxy_expected": 0, "proxy_contributing": 0, "proxy_sessions_checked": 0,
        "proxy_sessions_incomplete": 0, "missing_examples": (), "relevance_tickers": (),
        "bridge_check": None,
    }

    def evidence(verdict: DataReadiness, detail: str, basis: str = "", proven: bool = False,
                 adjustment: dict[str, Any] | None = None) -> DataFinalityEvidence:
        return DataFinalityEvidence(
            session_date=iso, verdict=verdict, detail=detail, store_path=st.path,
            store_identity_sha256=identity, ingest_identity_sha256=ingest_digest,
            ingest_runs_observed=ingest_count, ingest_unclean_datasets=unclean,
            max_finalized_session=_iso(max_finalized), finality_basis=basis,
            session_eligible_universe=state["session_eligible_universe"],
            session_complete=state["session_complete"],
            session_excluded_by_rule=state["session_excluded_by_rule"],
            session_missing=state["session_missing"],
            session_row_count=int(session_rows or 0),
            session_max_lastupdated=_iso(session_lastupdated),
            lookback_sessions_available=len(window_dates),
            lookback_sessions_required=spec.required_history_sessions,
            lookback_earliest=_iso(earliest), lookback_latest=_iso(latest),
            momentum_candidates=state["momentum_candidates"],
            full_lookback_candidates=state["full_lookback_candidates"],
            proxy_expected_constituents=state["proxy_expected"],
            proxy_contributing_constituents=state["proxy_contributing"],
            proxy_sessions_checked=state["proxy_sessions_checked"],
            proxy_sessions_incomplete=state["proxy_sessions_incomplete"],
            duplicate_row_count=duplicates,
            corporate_actions_in_window=int(actions_count or 0),
            corporate_actions_max_date=_iso(actions_max),
            adjustment_reflection_proven=proven, adjustment_evidence=adjustment,
            construction=asdict(spec), missing_examples=state["missing_examples"],
            lineage=(lineage_filter.assessment().to_evidence() if lineage_filter else None),
            lineage_proxy_bridge_check=state["bridge_check"])

    # (1) mid-flight or unclean ingest
    if unclean:
        return evidence(DataReadiness.NOT_READY_INGEST_IN_PROGRESS,
                        f"ingest not clean for {list(unclean)} — the session's data may be partial")

    # (2) staleness / finality basis
    if max_finalized is None:
        return evidence(DataReadiness.NOT_READY_DATA_STALE, "the store holds no price data at all")
    if max_finalized < session_date:
        return evidence(DataReadiness.NOT_READY_DATA_STALE,
                        f"the store's finalized cutoff {_iso(max_finalized)} precedes session {iso}")
    if max_finalized > session_date:
        basis = f"a later session ({_iso(max_finalized)}) is present, so {iso} is settled"
    else:
        close = _session_close_utc(session_date)
        fin_row = st.one("SELECT MAX(finished_at) FROM ingest_runs WHERE dataset = 'sep' "
                         "AND LOWER(status) = 'ok'")
        finished_at = fin_row[0] if fin_row else None
        if close is None or finished_at is None:
            return evidence(DataReadiness.NOT_READY_DATA_STALE,
                            f"{iso} is the store's last session and no clean sep ingest completing "
                            f"after its close can be evidenced — it cannot be shown to be final")
        stamp = finished_at.replace(tzinfo=None) if isinstance(finished_at, datetime) else None
        if stamp is None or stamp < close.replace(tzinfo=None):
            return evidence(DataReadiness.NOT_READY_DATA_STALE,
                            f"the last clean sep ingest finished {_iso(finished_at)}, before the {iso} "
                            f"close {_iso(close)} — the session's data is not established as final")
        basis = (f"{iso} is the store's last session; a clean sep ingest finished {_iso(finished_at)}, "
                 f"after the {_iso(close)} close")

    # (3) the session's coverage, measured against the REGISTERED universe construction
    try:
        universe = uni(session_date, spec.scoring_universe_n)
    except Exception as exc:
        return evidence(DataReadiness.NOT_READY_CURRENT_SESSION_MISSING,
                        f"the registered universe could not be constructed for {iso}: {exc}", basis)
    state["session_eligible_universe"] = len(universe)
    if not universe:
        return evidence(DataReadiness.NOT_READY_CURRENT_SESSION_MISSING,
                        f"the registered universe for {iso} is empty", basis)

    window_start = earliest or session_date
    facts = _ticker_facts(st, universe)
    priced_today = {r[0] for r in st.all(
        "SELECT DISTINCT ticker FROM sep WHERE date = ? AND closeadj IS NOT NULL", [session_date])}

    complete, excluded, missing = [], [], []
    for t in universe:
        if t in priced_today:
            complete.append(t)
        elif _excluded_by_rule(facts.get(t), window_start, session_date):
            excluded.append(t)
        else:
            missing.append(t)
    state.update(session_complete=len(complete), session_excluded_by_rule=len(excluded),
                 session_missing=len(missing), missing_examples=tuple(sorted(missing)[:10]))
    if missing:
        return evidence(
            DataReadiness.NOT_READY_CURRENT_SESSION_MISSING,
            f"{len(missing)} of {len(universe)} registered universe name(s) have no usable mark on "
            f"{iso} and no frozen rule explains the absence (e.g. {sorted(missing)[:5]})", basis)

    # (4) self-contradiction
    if duplicates:
        return evidence(DataReadiness.INTEGRITY_STOP_DATA_CONFLICT,
                        f"{duplicates} duplicate (ticker, date) row(s) in the consumed window", basis)

    # (5) the exact history the scoring candidates consume
    if len(window_dates) < spec.required_history_sessions:
        return evidence(
            DataReadiness.NOT_READY_LOOKBACK_INCOMPLETE,
            f"{len(window_dates)} session(s) of history available, {spec.required_history_sessions} "
            f"required ({spec.momentum_lookback_sessions}+{spec.momentum_skip_sessions} momentum / "
            f"{spec.regime_ma_sessions} regime MA)", basis)

    candidates = [t for t in universe if not _excluded_by_rule(facts.get(t), window_start, session_date)]
    state["momentum_candidates"] = len(candidates)
    state["relevance_tickers"] = tuple(sorted(set(state["relevance_tickers"]) | set(candidates)))
    full = _names_with_full_history(st, candidates, window_start, session_date,
                                    len(window_dates))
    state["full_lookback_candidates"] = len(full)
    short = sorted(set(candidates) - full)
    if short:
        state["missing_examples"] = tuple(short[:10])
        return evidence(
            DataReadiness.NOT_READY_LOOKBACK_INCOMPLETE,
            f"{len(short)} of {len(candidates)} scoring candidate(s) lack the exact "
            f"{spec.required_history_sessions}-session history the computation consumes "
            f"(e.g. {short[:5]})", basis)

    # (6) the market proxy's OWN constituent set
    proxy_verdict = _assess_proxy(st, uni, spec, window_dates, session_date, state)

    # (6b) could a lineage-excluded symbol FABRICATE a return inside the frozen proxy?
    #
    # `build_market_proxy` is a frozen validated artifact that calls `universe_asof` directly, so its
    # basket cannot be filtered — an excluded name is still in its panel. Almost always that is
    # harmless: `pct_change` across a one-sided hole is NaN and `skipna` drops it. The exception is
    # marks on BOTH sides of a long hole, where two disconnected segments get bridged into one
    # enormous fabricated return that flows into the index and the regime it drives.
    #
    # Since the replica may not be modified, eligibility upstream is the control point: the session
    # refuses BEFORE the proxy is used, rather than the caveat being carried forward as a standing
    # assumption. This can only ever add a refusal — it never restores a name to eligibility.
    if lineage_filter is not None:
        ma_window = sorted(window_dates[:spec.regime_ma_sessions])
        risks = assess_bridge_risk(store, lineage_filter.assessment().excluded, window=ma_window)
        state["bridge_check"] = {
            "examined_exclusions": lineage_filter.assessment().excluded_count,
            "risky_exclusions": len(risks),
            "min_hole_sessions": LINEAGE_BRIDGE_HOLE_MIN_SESSIONS,
            "window_start": ma_window[0].isoformat() if ma_window else None,
            "window_end": ma_window[-1].isoformat() if ma_window else None,
            "window_sessions": len(ma_window),
            "verdict": "PASS" if not risks else "REFUSE",
            "risks": [r.to_evidence() for r in risks],
        }
        if risks:
            names = ", ".join(
                f"{r.ticker} (perma {r.permaticker}, {r.hole_sessions} session hole "
                f"{r.hole_start}..{r.hole_end}, last mark before {r.last_mark_before}, first after "
                f"{r.first_mark_after})" for r in risks)
            return evidence(
                DataReadiness.NOT_READY_LINEAGE_BRIDGE_RISK,
                f"{len(risks)} lineage-excluded symbol(s) hold marks on BOTH sides of a hole of at "
                f"least {LINEAGE_BRIDGE_HOLE_MIN_SESSIONS} governed sessions inside the proxy window: "
                f"{names}. The frozen market-proxy construction would bridge those disconnected "
                f"segments into a fabricated return", basis)

    if proxy_verdict is not None:
        return evidence(DataReadiness.NOT_READY_PROXY_INCOMPLETE, proxy_verdict, basis)

    # (7) corporate-action reflection — PROVEN by a verifier, or the session does not run.
    #
    # An empty `actions` table is NOT evidence that no action occurred: the governed store holds zero
    # action rows while `closeadj` departs from `close` on ~48% of its 39M rows. Counting rows would let
    # a session pass vacuously, so reflection must be proven by a verifier that also detects adjustment
    # events the declared set does not explain. With no verifier configured, nothing is proven.
    if adjustment_verifier is None:
        return evidence(
            DataReadiness.NOT_READY_ADJUSTMENT_UNVERIFIED,
            f"no adjustment verifier is configured, so corporate-action reflection over the consumed "
            f"window cannot be proven ({actions_count} declared action row(s), latest "
            f"{_iso(actions_max)}); an absent action table is not evidence that none occurred", basis)
    result = adjustment_verifier(window_start, session_date, list(state["relevance_tickers"]), identity)
    adjustment = result.to_open_provenance()
    bound = str(adjustment.get("store_identity_sha256", ""))
    if bound != identity:
        return evidence(
            DataReadiness.INTEGRITY_STOP_DATA_CONFLICT,
            f"the adjustment verification is bound to store identity {bound[:16] or '<empty>'}… but "
            f"this assessment describes {identity[:16]}… — the two do not describe the same data",
            basis, False, adjustment)
    if not result.proven:
        # ── the NARROW, session-scoped readiness claim ──────────────────────────────────────────────
        #
        # Reached only when the broad proof fails, and only through an attestation whose every clause is
        # re-derived from the measurement above. `proven` STAYS FALSE in the evidence: the claim being
        # made is not "every corporate action is reconciled" but the strictly narrower "the decision
        # this session makes is valid, and the actions that remain unproven were measured to have no
        # part in it".
        if narrow_readiness is not None:
            refusals = _narrow_readiness_refusals(adjustment, narrow_readiness, session_date)
            counts = dict(adjustment.get("checks_by_status") or {})
            # ⚠ Two DIFFERENT numbers, reported separately and never collapsed. The disclosure is
            # adjudicated corpus-wide; how many of its events this session's relevance set actually
            # contains is a measurement, and on 2026-07-27 the answer is zero. Reporting only the
            # corpus-wide figure would state a limitation this session does not carry; reporting only
            # the session figure would hide that the adjudication exists at all.
            disclosed = counts.get(_NARROW_TOLERATED_STATUS, 0)
            corpus_wide = adjustment.get("ma_disclosure_entry_count")
            narrow = {
                "attested_session": narrow_readiness.session_date.isoformat(),
                "reconciliation_artifact_sha256": narrow_readiness.reconciliation_artifact_sha256,
                "relevance_artifact_sha256": narrow_readiness.relevance_artifact_sha256,
                "quarantine_artifact_sha256": narrow_readiness.quarantine_artifact_sha256,
                "attested_relevance_set_sha256": narrow_readiness.relevance_set_sha256,
                "measured_relevance_set_sha256": adjustment.get("relevance_set_sha256"),
                "quarantined_identities": sorted(narrow_readiness.quarantined_identities),
                "full_action_semantics_proven": False,
                "decision_validity_proven": not refusals,
                # Derived from the MEASUREMENT, never asserted to preserve an expected shape.
                "nondecision_limitations_present": bool(disclosed),
                "corpus_wide_unsupported_semantics_count": corpus_wide,
                "unsupported_semantics_in_readiness_relevance_set": disclosed,
                "unexplained_movements_on_quarantined_identities": int(
                    adjustment.get("unexplained_adjustment_count") or 0),
                "refusals": refusals,
            }
            adjustment = {**adjustment, "narrow_readiness": narrow}
            if not refusals:
                # The detail must describe WHAT was limited on THIS session. A fixed sentence about
                # economically terminal actions reads as a finding even when the count is zero.
                unexplained = int(adjustment.get("unexplained_adjustment_count") or 0)
                limits = []
                if disclosed:
                    limits.append(f"{disclosed} economically terminal corporate action(s) remain "
                                  f"economically unproven, each machine-verified as outside the "
                                  f"scoring universe, the proxy contributors, the top five and the "
                                  f"regime inputs")
                if unexplained:
                    limits.append(f"{unexplained} unexplained factor movement(s) sit on quarantined "
                                  f"identities excluded from the decision path")
                if corpus_wide:
                    limits.append(f"the supplied relevance assessment adjudicates {corpus_wide} "
                                  f"event(s) corpus-wide, of which {disclosed} fall inside this "
                                  f"session's relevance set")
                return evidence(
                    DataReadiness.READY_DECISION_VALID_WITH_DISCLOSED_NONDECISION_LIMITATIONS,
                    f"the {session_date.isoformat()} decision path is proven valid while "
                    + "; ".join(limits or ["the broad reflection proof does not hold"])
                    + ". FULL ACTION SEMANTICS ARE NOT PROVEN — this is a narrower claim bound to "
                      "this session, to the relevance set it constructed, and to the reconciliation, "
                      "relevance and quarantine artifacts named in the evidence",
                    basis, False, adjustment)
        return evidence(
            DataReadiness.NOT_READY_ADJUSTMENT_UNVERIFIED,
            "corporate-action reflection over the consumed window is not proven: "
            f"{adjustment.get('detail', '')}",
            basis, False, adjustment)

    return evidence(DataReadiness.READY, "all registered inputs are present, complete and final",
                    basis, True, adjustment)


def _names_with_full_history(st: _Store, names: list[str], window_start: Any, session_date: date,
                             required_sessions: int) -> set[str]:
    """The subset of `names` carrying a usable mark on EVERY session of the consumed window."""
    if not names:
        return set()
    ph = ",".join("?" * len(names))
    rows = st.all(
        f"SELECT ticker FROM sep WHERE ticker IN ({ph}) AND date BETWEEN ? AND ? "
        f"AND closeadj IS NOT NULL GROUP BY ticker HAVING COUNT(DISTINCT date) >= ?",
        [*names, window_start, session_date, required_sessions])
    return {r[0] for r in rows}


def _assess_proxy(st: _Store, uni: UniverseFn, spec: ConstructionSpec, window_dates: list[date],
                  session_date: date, state: dict[str, Any]) -> str | None:
    """Measure the market proxy against ITS OWN construction: the month-end union of
    `universe_asof(n=500)` over the MA window, each constituent needing consecutive marks to contribute
    a return. Returns a failure detail, or None when the proxy is complete.

    `build_market_proxy` averages returns with `skipna=True`, so a missing constituent is silently
    dropped by the construction — which is exactly why completeness has to be proven here.
    """
    ma_dates = sorted(window_dates[:spec.regime_ma_sessions])
    if len(ma_dates) < 2:
        return f"only {len(ma_dates)} proxy session(s) available; the 200-session MA cannot be formed"

    month_ends = [d for i, d in enumerate(ma_dates)
                  if i + 1 == len(ma_dates) or (ma_dates[i + 1].year, ma_dates[i + 1].month)
                  != (d.year, d.month)]
    basket: set[str] = set()
    for d in month_ends:
        try:
            basket |= set(uni(d, spec.proxy_universe_n))
        except Exception:                     # the construction itself suppresses these (stage4 §)
            continue
    if not basket:
        return "the market-proxy basket is empty — no month-end universe could be constructed"

    names = sorted(basket)
    facts = _ticker_facts(st, names)
    window_start = ma_dates[0]
    expected = [t for t in names
                if not _excluded_by_rule(facts.get(t), window_start, session_date)]
    state["proxy_expected"] = len(expected)
    state["proxy_sessions_checked"] = len(ma_dates)
    # Relevance for adjustment verification is the WHOLE basket, not just today's expected set: a name
    # that left the universe mid-window still priced into the consumed history.
    state["relevance_tickers"] = tuple(sorted(set(state["relevance_tickers"]) | basket))

    ph = ",".join("?" * len(expected)) if expected else "''"
    rows = st.all(
        f"SELECT date, COUNT(DISTINCT ticker) FROM sep WHERE ticker IN ({ph}) "
        f"AND date BETWEEN ? AND ? AND closeadj IS NOT NULL GROUP BY date",
        [*expected, window_start, session_date])
    per_session = {r[0]: int(r[1]) for r in rows}
    state["proxy_contributing"] = per_session.get(session_date, 0)

    incomplete = [d for d in ma_dates if per_session.get(d, 0) != len(expected)]
    state["proxy_sessions_incomplete"] = len(incomplete)
    if state["proxy_contributing"] != len(expected):
        return (f"{state['proxy_contributing']} of {len(expected)} proxy constituent(s) are priced on "
                f"{session_date.isoformat()} — the equal-weight return would silently drop the rest")
    if incomplete:
        return (f"{len(incomplete)} of {len(ma_dates)} proxy session(s) in the MA window are missing a "
                f"constituent mark (e.g. {[d.isoformat() for d in incomplete[:3]]}) — the 200-session "
                f"MA would be computed over an incomplete basket")
    return None


def verify_store_unchanged(store: Any, session_date: date, expected: DataFinalityEvidence, *,
                           construction: ConstructionSpec | None = None) -> None:
    """Re-stream the value-level identity after the session's reads and require it to be unchanged.

    This is how "all data reads resolve from the same immutable ingest version" is established in a
    schema with no ingest-version column: not by trusting a field, but by proving the VALUES the reads
    resolved against did not move underneath them.
    """
    spec = construction or ConstructionSpec()
    st = _Store(store)
    window = st.all("SELECT DISTINCT date FROM sep WHERE date <= ? ORDER BY date DESC LIMIT ?",
                    [session_date, spec.required_history_sessions])
    earliest = window[-1][0] if window else None
    now = store_identity(st, earliest, session_date)
    if now != expected.store_identity_sha256:
        raise DataFinalityError(
            f"the factor store changed during session {session_date.isoformat()}: identity "
            f"{expected.store_identity_sha256[:16]}… → {now[:16]}… — the session's reads did not "
            f"resolve against one immutable state")


def whole_file_digest(path: Path, *, chunk: int = 1 << 20) -> str:
    """SHA-256 of the store file itself — the census-style pin. Optional additional evidence; the
    streaming value-level identity above is what every session records."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while block := fh.read(chunk):
            h.update(block)
    return h.hexdigest()
