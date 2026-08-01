"""Corporate-action adjustment verifier (R5b) — prove the adjusted series reflects the declared actions.

The frozen computation reads `closeadj`. If a split or distribution is not reflected in that series the
way the declared action says it should be, the momentum window is computed over a price path that never
existed. R5a therefore refuses a session whose corporate-action reflection is unproven; this module is
what can prove it.

## TWO factor systems, not one — and each is verified on its own terms

SHARADAR carries three price columns, and the arithmetic only works once their semantics are stated:

    closeunadj   the price actually traded that day
    close        the SPLIT-ADJUSTED price
    closeadj     the split-AND-distribution adjusted (total-return) price

so the corpus expresses exactly two adjustment factors, and they are INDEPENDENT:

    SPLIT factor      S_t = close_t / closeunadj_t
    DIVIDEND factor   D_t = closeadj_t / close_t

A declared split with multiplier `m` moves the SPLIT factor and CANNOT appear in the dividend factor:
`S_t / S_{t-1} == m`. Measured: NFLX 10:1 on 2025-11-17 has `close/closeunadj` 0.1000 before and 1.0000
from the split while `closeadj/close` stays 1.0000 throughout; DD 1-for-3 on 2026-06-24 goes 3.0000 →
1.0000. The earlier model assumed `close` was unadjusted and multiplied the adjusted-ratio expectation
by `m`, which demanded the factor somewhere it structurally cannot be and turned every declared split
into a false conflict.

A declared cash distribution moves the DIVIDEND factor, through the platform's documented total-return
formulation (`app/factor_data/total_return.py`):

    expected_ratio = (raw_close_t + cash_per_share) / raw_close_{t-1}
    observed_ratio = closeadj_t / closeadj_{t-1}

`split_multiplier` is deliberately ABSENT from that leg: `close` already carries split semantics, so
`close_t/close_{t-1}` contains no split jump and re-applying the multiplier double-counts it. Confirmed
on the one split-plus-cash case in the window — TRI 2026-05-04, observed 1.01271475 vs expected
1.01271235, a 3e-6 match the old formula reported as a conflict.

## Both directions are checked, and the second is the load-bearing one

  (a) DECLARED → SERIES: every relevant declared action must be reflected within tolerance.
  (b) SERIES → DECLARED: every adjustment EVENT visible in the data must be explained by a declared
      action — and it is checked SEPARATELY ON EACH FACTOR.

Direction (b) exists because the absence of action rows is not evidence that no action occurred. The
governed store can hold ZERO rows in `actions` while `closeadj` differs from `close` on ~48% of its 39M
rows: without (b), "no actions in the window" would read as "nothing to prove" and the session would
pass vacuously.

### ⚠ Why direction (b) needs TWO legs — the defect this module was blind to

Direction (b) originally flagged a session when `closeadj/prev_closeadj` departed from
`close/prev_close`. But that quantity is exactly `D_t / D_{t-1}`, and **a split never changes D**
(`closeadj = close × D`, and `close` already carries the split). So the single-leg test could only ever
detect dividend-like adjustments: **an UNDECLARED SPLIT in the vintage would pass undetected.**

So direction (b) now runs one leg per factor:

    dividend leg   D_t / D_{t-1} != 1   with no reconciled dividend on that (identity, session)
    split leg      S_t / S_{t-1} != 1   with no reconciled split    on that (identity, session)

and the census reports `undeclared_dividend_factor_changes`, `undeclared_split_factor_changes` and
`combined_or_ambiguous_changes` separately, because a count that merges them cannot be read.

### ⚠⚠ The `explained` set is FACTOR-SPECIFIC, and this is a CORRECTNESS REQUIREMENT

The rule "*any* declared action on (ticker, date) ⇒ that session is explained" is REJECTED. Under it, a
declared dividend would suppress an undeclared split on the same session, and an unsupported action
would suppress everything — silently. Everything still passes; the series→declared direction just
quietly stops catching a whole defect class. There is no failing test to notice, which is precisely why
this is called out here rather than left to read as a refactor.

A session enters `explained_<factor>_sessions` only when an action on it is

    1. classified `PRICE_ADJUSTMENT_EXPECTED`,  AND
    2. applicable to THAT SPECIFIC factor,      AND
    3. successfully reconciled (`PROVEN_REFLECTED`).

so: a PROVEN dividend explains the dividend factor only · a PROVEN split explains the split factor only
· a PROVEN split-and-cash explains both, independently · and a bare `acquisitionof`, an unsupported
action, an insufficient one and a `PROVEN_NOT_REFLECTED` one explain **NEITHER**.

Sessions are keyed by **permanent identity + session**, never by ticker text — a symbol is reused
across issuers, so a ticker-keyed suppression can silence a different company's adjustment.

## Default-deny action applicability

Every action is pre-classified `PRICE_ADJUSTMENT_EXPECTED` / `NO_SINGLE_SECURITY_PRICE_ADJUSTMENT_EXPECTED`
/ `INSUFFICIENT_TO_CLASSIFY`, then resolved to one of six TERMINAL statuses. The default is
`NOT_PROVEN_UNSUPPORTED_SEMANTICS`, and an action leaves it only via a NAMED, TESTED rule whose reason
code is recorded in the evidence. There is no blanket acceptance of acquisitions, delistings, spinoffs
or contraticker rows, and a broad M&A valuation engine is explicitly not in scope.

Only `PROVEN_REFLECTED` and `PROVEN_NO_PRICE_ADJUSTMENT_APPLICABLE` satisfy readiness.

## What this can and cannot prove

It proves CONSISTENCY between `closeadj`, `close`, `closeunadj` and the declared action rows. It does
NOT prove that the declared cash amount, ratio, ex-date or classification is itself correct — that is a
property of the source, not of the arithmetic. The evidence therefore reports two separate facts:

    adjustment_series_consistent_with_declared_actions   (what the arithmetic shows)
    declared_action_source_authoritative                 (whether the source is frozen and identified)

`proven` requires BOTH. A source that has not been explicitly declared authoritative can never yield a
PROVEN verdict, however clean the arithmetic looks.

## Tolerance is derived from the stored precision and a MEASURED noise/signal separation

Prices are stored to four decimals, so the ratio noise scales with 1/price and a one-day comparison
rounds four of them. The band is therefore `safety × quantum × Σ(1/price)`, with a fixed relative floor.

⚠ The safety factor's plateau (150,115 flagged at 1x → 7,362 at 5x → 7,302 at 20x) was measured on the
SEAM-CONTAMINATED predecessor store, so that plateau included vintage-seam artifacts. The factor is
carried forward UNCHANGED and is treated as PROVISIONAL until re-measured on the rebuilt corpus; the
re-measurement is a separate, evidence-backed amendment and is NOT a licence to tune until the gate
passes. Every check records the absolute and relative residual, both tolerances, and the basis.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field, replace
from datetime import date
from enum import StrEnum
from typing import Any

from app.validation.forward_window import IntegrityStop

# ── vendor action labels ─────────────────────────────────────────────────────────────────────────────
#
# Grouped by what the arithmetic can verify. Labels absent from every set fall to UNSUPPORTED, which is
# the intended default: an unrecognised label must never be assumed harmless.
_CASH_LABELS = frozenset({"dividend", "cash dividend", "dividends", "distribution"})
_SPLIT_LABELS = frozenset({"split", "stocksplit", "stock split", "reverse split", "reversesplit"})
_SPINOFF_LABELS = frozenset({"spinoff", "spin-off", "stockdividend", "stock dividend"})
_MERGER_LABELS = frozenset({"merger", "acquisition", "conversion", "exchange"})
_SYMBOL_LABELS = frozenset({"tickerchange", "ticker change", "namechange", "name change",
                            "symbolchange", "listed", "delisted", "relisted"})

# Labels whose `value` column IS consumed by the adjustment arithmetic. Only for these can two rows
# sharing a label but declaring different values contradict each other — see `_partition_duplicates`.
_ARITHMETIC_VALUE_LABELS = _CASH_LABELS | _SPLIT_LABELS

# ── named, testable applicability rules (the ONLY exits from the default-deny status) ────────────────
#
# Each constant is a reason code that appears in the evidence. An action that matches no rule keeps the
# default `NOT_PROVEN_UNSUPPORTED_SEMANTICS`.
REASON_DIVIDEND_REFLECTED = "DECLARED_CASH_DISTRIBUTION_REFLECTED_IN_DIVIDEND_FACTOR"
REASON_SPLIT_REFLECTED = "DECLARED_SPLIT_REFLECTED_IN_SPLIT_FACTOR"
REASON_SPLIT_AND_CASH_REFLECTED = "DECLARED_SPLIT_AND_CASH_REFLECTED_IN_BOTH_FACTORS"
REASON_ACQUIRER_CONTINUES = "ACQUIRER_CONTINUES_NO_SIBLING_ACTION_AND_NO_FACTOR_MOVEMENT"
REASON_RELATIONSHIP_METADATA = "RELATIONSHIP_METADATA_ONLY_NO_FACTOR_MOVEMENT"
REASON_INITIAL_LISTING_METADATA = "INITIAL_LISTING_METADATA_ONLY_NO_FACTOR_MOVEMENT"
REASON_INITIAL_LISTING_NO_HISTORY = "INITIAL_LISTING_NO_PRIOR_GOVERNED_HISTORY_TO_ADJUST"
REASON_TICKER_CHANGE_SAME_LINEAGE = "TICKER_CHANGE_WITHIN_SAME_PERMANENT_LINEAGE_NO_FACTOR_MOVEMENT"
REASON_SPINOFF_REFLECTED = "SPINOFF_DISTRIBUTION_REFLECTED_IN_DIVIDEND_FACTOR"
REASON_SPINOFF_AND_SPLIT_REFLECTED = "SPINOFF_DISTRIBUTION_AND_SPLIT_REFLECTED_IN_BOTH_FACTORS"
REASON_ADR_RATIO_REFLECTED = "ADR_RATIO_CHANGE_REFLECTED_IN_SPLIT_FACTOR"
REASON_LINEAGE_EVENT_NO_ADJUSTMENT = (
    "CHILD_LINEAGE_BEGINS_AT_EFFECTIVE_BOUNDARY_WITH_PARENT_DISTRIBUTION_ALREADY_RECONCILED")
REASON_MA_DISCLOSED_NONDECISION = (
    "ACQUIRED_SIDE_ECONOMICALLY_TERMINAL_AND_MEASURED_NON_DECISION_RELEVANT")

#: Every reason code a check may carry. Bound so a new exit cannot be added without being named here.
NAMED_APPLICABILITY_RULES = frozenset({
    REASON_DIVIDEND_REFLECTED, REASON_SPLIT_REFLECTED, REASON_SPLIT_AND_CASH_REFLECTED,
    REASON_ACQUIRER_CONTINUES, REASON_RELATIONSHIP_METADATA, REASON_INITIAL_LISTING_METADATA,
    REASON_INITIAL_LISTING_NO_HISTORY, REASON_TICKER_CHANGE_SAME_LINEAGE,
    REASON_SPINOFF_REFLECTED, REASON_SPINOFF_AND_SPLIT_REFLECTED, REASON_ADR_RATIO_REFLECTED,
    REASON_LINEAGE_EVENT_NO_ADJUSTMENT, REASON_MA_DISCLOSED_NONDECISION,
})

# ── the bounded spinoff / ADR-ratio increment (owner ruling 2026-07-30) ──────────────────────────────
#
# NARROW AND FIELD-DRIVEN. This is NOT a general M&A valuation engine and must never grow into one: it
# admits exactly two additional shapes, each only when the AUTHORITATIVE RECORD supplies the mechanical
# term, and it fails closed otherwise.
#
# `SPINOFF_DISTRIBUTION`: value leaves the parent and is distributed through another security, so a
# price adjustment IS expected. The mechanical term is `spinoffdividend.value` — MEASURED to be the
# distributed value PER PARENT SHARE, which composes through the ordinary total-return relation
# unchanged. Verified on all 14 in-window spinoff groups at 8e-08..1.3e-05 relative residual (FTV/RAL,
# LBRDK/GLIBK, LBRDA/GLIBA, HON/SOLS, DD/Q, GLIBK/GLIBR, UL/MICC, CMCSA/VSNT, APTV/VGNT, ANAB/TRAX,
# FDX/FDXF, HON/HONA, SPGI/MBGL, MIDD/MFP) — the same precision as an ordinary cash dividend.
#
# ⚠ `spinoff.value` is the SHARE-COUNT RATIO and is NOT the price term. Do not multiply it by the
# spun-off security's price to derive the distribution: measured, `spinoffdividend / spinoff` equals the
# contra security's close for only some groups (LBRDK 31.00 == GLIBK 31.0) and diverges materially for
# others (HON 98.50 vs SOLS 48.74; DD 285.00 vs Q 97.0), because the term references a when-issued or
# reference price rather than the first regular close. The declared field is the term; a reconstruction
# from ratio x price is NOT equivalent and must never be substituted for it.
#
# ⚠⚠ A `spinoff` row carrying only a label and a contraticker, with NO `spinoffdividend` value, has NO
# mechanical term and stays NOT_PROVEN_UNSUPPORTED_SEMANTICS. The ratio must never be inferred from the
# observed price movement, from relative market values, from the ticker relationship, or from whatever
# factor would make the series reconcile.
_SPINOFF_VALUE_LABEL = "spinoffdividend"
_SPINOFF_RATIO_LABEL = "spinoff"
_SPINOFF_SHAPE_LABELS = frozenset({_SPINOFF_RATIO_LABEL, _SPINOFF_VALUE_LABEL, "split"})

# `adrratiosplit` is mechanically a share-ratio transformation, so it belongs to the SPLIT factor. But
# its DIRECTION is not self-evident and the corpus proves it: of 383 groups, 303 carry a same-date
# `split` row (282 exact reciprocals, 3 equal, 18 neither) and 80 carry `adrratiosplit` ALONE.
#
# ⚠ Therefore the multiplier is taken from the `split` row — whose direction convention is already
# governed and proven on the window's 11 declared splits — and the `adrratiosplit` row is admitted only
# as a NON-CONFLICTING CO-DECLARATION when the two are exact reciprocals. Reading a factor out of
# `adrratiosplit` alone would require choosing its direction, and the only available tiebreak would be
# the observed price movement, which is precisely the inference the ruling forbids. Alone, ambiguous,
# or conflicting ⇒ fail closed.
_ADR_RATIO_LABEL = "adrratiosplit"
_ADR_SHAPE_LABELS = frozenset({_ADR_RATIO_LABEL, "split"})

# ── lineage-construction events for the CHILD of a spinoff ───────────────────────────────────────────
#
# `listed | spunofffrom | tickerchangefrom | tickerchangeto` on the SPUN-OFF security is not a
# one-security price adjustment at all — it is the construction of a new lineage. It clears only on
# POSITIVE permanent-identity evidence, and only when the PARENT's distribution has already been
# reconciled in the same run; otherwise the child's listing would silently stand in for a parent
# adjustment nobody verified.
_SPUNOFF_FROM_LABEL = "spunofffrom"
_LINEAGE_EVENT_LABELS = frozenset({"listed", _SPUNOFF_FROM_LABEL,
                                   "tickerchangefrom", "tickerchangeto"})
#: Reciprocity band for `adrratiosplit x split == 1`. Deliberately tight: it tests agreement between two
#: DECLARED terms, not a price observation, so it needs no price-quantum allowance.
_ADR_RECIPROCAL_TOLERANCE = 1e-6

# Labels that the named metadata rules recognise. Kept narrow ON PURPOSE — the owner's ruling admits
# only relationship metadata, initial-listing metadata, ticker changes inside one permanent lineage,
# and acquisition-reference rows that merely identify another security.
_RELATIONSHIP_LABELS = frozenset({"relation", "initiated"})
_LISTING_LABELS = frozenset({"listed"})
_TICKER_CHANGE_LABELS = frozenset({"tickerchangeto", "tickerchangefrom"})
_ACQUIRER_REFERENCE_LABEL = "acquisitionof"

# The stored price quantum (four decimals across `sep`) and the resulting ratio-noise model.
#
# A one-day comparison rounds FOUR prices — two series, this session and the previous — and each
# contributes a relative error of about `quantum / price`, so the band is the SUM of the four
# reciprocals rather than a single term.
#
# ── why NOISE_SAFETY_FACTOR is 5.0 (corrected 2026-07-30) ───────────────────────────────────────────
#
# ⚠ THE EARLIER JUSTIFICATION WAS WRONG AND IS RETRACTED. It claimed a single universal knee-then-
# plateau (150,115 flagged at 1x -> 7,362 at 5x -> 7,302 at 20x) measured on the predecessor store.
# That store SPLICED TWO ADJUSTMENT VINTAGES at 2026-06-15, so most of what the "plateau" counted as
# real adjustment events were SEAM ARTIFACTS. Re-measured on the single-vintage rebuild over
# 1,551,867 session pairs / 6,221 names, the ordinary no-action noise at 5x is 205, not 7,362.
#
# The rebuilt-corpus curve does NOT show one universal plateau. It shows two different shapes:
#
#   SPLIT leg     20,818 (1x) -> 7,997 (2x) -> 1,950 (3x) -> 438 (4x) -> 7 (5x) -> 2 (6x..100x)
#                 a clean knee and a stable floor of 2, reached by 6x.
#   DIVIDEND leg  161,974 -> 20,595 -> 368 -> 237 -> 216 (5x) -> 163 (10x) -> 104 (20x) -> 65 (100x)
#                 NO plateau: a slow tail that never flattens.
#
# and raising the factor to chase that tail starts DESTROYING TRUE SIGNAL — declared dividends still
# flagged fall 8,220/8,229 at 5x to 8,155 at 20x and 7,977 at 50x.
#
# So 5.0 is retained NOT because corpus-v2 produced a universal plateau — it did not — but because:
#   * split-factor noise is stable at that level;
#   * lowering it increases noise sharply (655 at 4x, 2,282 at 3x);
#   * raising it destroys genuine declared-dividend sensitivity.
# It is the most conservative previously governed value that preserves known real events. This is
# evidence that the measurement does not support a LARGER tolerance; it is not a proof that 5x is
# globally optimal.
#
# ⚠ ONE COMMON TOLERANCE IS DELIBERATELY KEPT for both legs. Splitting it per factor is not authorised
# without a FAILING FIXTURE proving a single band is technically invalid.
PRICE_QUANTUM = 1e-4
NOISE_SAFETY_FACTOR = 5.0
RELATIVE_FLOOR = 1e-6             # floating-point/representation floor
ABSOLUTE_TOLERANCE = 0.0          # the model is relative; kept explicit and recorded


class AdjustmentVerdict(StrEnum):
    """The WINDOW-level verdict. `data_finality` consumes `proven`, derived from this."""
    PROVEN = "PROVEN"
    NO_RELEVANT_ACTIONS = "NO_RELEVANT_ACTIONS"
    NOT_PROVEN_INSUFFICIENT_DATA = "NOT_PROVEN_INSUFFICIENT_DATA"
    NOT_PROVEN_UNSUPPORTED_ACTION = "NOT_PROVEN_UNSUPPORTED_ACTION"
    INTEGRITY_STOP_CONFLICT = "INTEGRITY_STOP_CONFLICT"


class ActionClass(StrEnum):
    CASH_DIVIDEND = "CASH_DIVIDEND"
    SPLIT = "SPLIT"
    SPLIT_AND_CASH = "SPLIT_AND_CASH"
    SPINOFF_DISTRIBUTION = "SPINOFF_DISTRIBUTION"
    MERGER_CONVERSION = "MERGER_CONVERSION"
    SYMBOL_TRANSITION = "SYMBOL_TRANSITION"
    ACQUIRER_REFERENCE = "ACQUIRER_REFERENCE"
    RELATIONSHIP_METADATA = "RELATIONSHIP_METADATA"
    UNSUPPORTED = "UNSUPPORTED"


class ActionApplicability(StrEnum):
    """Does this action imply a single-security historical price adjustment? Pre-classification only —
    it never by itself proves anything."""
    PRICE_ADJUSTMENT_EXPECTED = "PRICE_ADJUSTMENT_EXPECTED"
    NO_SINGLE_SECURITY_PRICE_ADJUSTMENT_EXPECTED = "NO_SINGLE_SECURITY_PRICE_ADJUSTMENT_EXPECTED"
    INSUFFICIENT_TO_CLASSIFY = "INSUFFICIENT_TO_CLASSIFY"


class ActionStatus(StrEnum):
    """The TERMINAL per-action statuses. Only the entries in `SATISFIES_READINESS` allow a session to
    run; everything else blocks, including the default."""
    PROVEN_REFLECTED = "PROVEN_REFLECTED"
    PROVEN_NO_PRICE_ADJUSTMENT_APPLICABLE = "PROVEN_NO_PRICE_ADJUSTMENT_APPLICABLE"
    #: A CHILD security's listing out of an already-reconciled parent distribution. It is a
    #: lineage-construction event, not a one-security price adjustment, and it clears only on positive
    #: permanent-identity evidence — see `_lineage_event_rule`.
    PROVEN_LINEAGE_EVENT_NO_ADDITIONAL_PRICE_ADJUSTMENT = (
        "PROVEN_LINEAGE_EVENT_NO_ADDITIONAL_PRICE_ADJUSTMENT")
    PROVEN_NOT_REFLECTED = "PROVEN_NOT_REFLECTED"
    NOT_PROVEN_INSUFFICIENT_DATA = "NOT_PROVEN_INSUFFICIENT_DATA"
    NOT_PROVEN_UNSUPPORTED_SEMANTICS = "NOT_PROVEN_UNSUPPORTED_SEMANTICS"
    #: ⚠⚠ A DISCLOSED LIMITATION, **NOT A PROOF**. An economically terminal acquired-side event whose
    #: final economic treatment the vendor schema cannot establish (no per-share consideration, no
    #: exchange ratio, no successor conversion term; `value` is AGGREGATE TRANSACTION VALUE IN
    #: MILLIONS), and which has been MEASURED to have zero impact on the governed decision.
    #:
    #: It is deliberately NOT in `SATISFIES_READINESS`: it does not convert unsupported M&A semantics
    #: into proven reflection, and it must never be read as `PROVEN_NO_PRICE_ADJUSTMENT_APPLICABLE`.
    #: It exists so the limitation can be stated and bound into a countersignature EXPLICITLY rather
    #: than disappearing into the default-deny bucket alongside genuinely unassessed actions.
    UNRESOLVED_NONDECISION_MA_SEMANTICS = "UNRESOLVED_NONDECISION_MA_SEMANTICS"
    SOURCE_CONFLICT = "SOURCE_CONFLICT"
    #: ⚠⚠ A GOVERNED DISCLOSURE, **NOT A PROOF**, and the only status here that describes a FACTOR
    #: MOVEMENT rather than a declared action. It says exactly this and nothing more:
    #:
    #:   * a movement was observed in the adjusted series;
    #:   * no reconciled authoritative action explains it;
    #:   * the identity, the session AND the factor are covered by the countersigned quarantine;
    #:   * the movement is therefore excluded from trusted adjustment evidence;
    #:   * a session may proceed over it ONLY under disclosed-limitation readiness.
    #:
    #: It does NOT mean the action semantics are proven, the movement is reconciled, a price
    #: adjustment was verified, or that the identity is decision-irrelevant — the countersigned block
    #: states in as many words that these identities ARE decision-relevant in the raw construction.
    #: It lives in this enum rather than one of its own so that every existing consumer which decides
    #: "is this proven?" by testing membership of `SATISFIES_READINESS` gets the right answer without
    #: being taught about a second vocabulary.
    GOVERNED_QUARANTINED_UNEXPLAINED_MOVEMENT = "GOVERNED_QUARANTINED_UNEXPLAINED_MOVEMENT"


#: The default. An action is unsupported until a NAMED rule moves it, never the other way round.
DEFAULT_ACTION_STATUS = ActionStatus.NOT_PROVEN_UNSUPPORTED_SEMANTICS

#: Exactly the statuses that satisfy readiness. ⚠ Neither `UNRESOLVED_NONDECISION_MA_SEMANTICS` nor
#: `GOVERNED_QUARANTINED_UNEXPLAINED_MOVEMENT` is among them — a disclosed limitation is not a proof,
#: and adding either would relax the gate rather than describe the evidence.
SATISFIES_READINESS = frozenset({
    ActionStatus.PROVEN_REFLECTED,
    ActionStatus.PROVEN_NO_PRICE_ADJUSTMENT_APPLICABLE,
    ActionStatus.PROVEN_LINEAGE_EVENT_NO_ADDITIONAL_PRICE_ADJUSTMENT,
})


class FactorKind(StrEnum):
    """The two independent adjustment factor systems the corpus expresses."""
    DIVIDEND = "DIVIDEND_FACTOR"          # closeadj / close
    SPLIT = "SPLIT_FACTOR"                # close / closeunadj
    COMBINED = "COMBINED_OR_AMBIGUOUS"    # both moved on one session and at least one is undeclared


class DuplicateDisposition(StrEnum):
    SINGLE_SOURCE_ROW = "SINGLE_SOURCE_ROW"
    CANONICALIZED_IDENTICAL_DUPLICATES = "CANONICALIZED_IDENTICAL_DUPLICATES"
    SOURCE_CONFLICT_INCOMPATIBLE_DUPLICATES = "SOURCE_CONFLICT_INCOMPATIBLE_DUPLICATES"


class AdjustmentVerificationError(IntegrityStop):
    """The store could not be interrogated. Fails closed — an unverifiable window is never proven."""


@dataclass(frozen=True)
class ActionSourceDeclaration:
    """The corporate-action source, as REGISTERED. `authoritative` is an explicit declaration that the
    source is frozen and identified; it is never inferred from the presence of rows."""
    identity: str
    authoritative: bool = False
    coverage_start: date | None = None
    coverage_end: date | None = None

    def covers(self, start: date, end: date) -> bool:
        return (self.coverage_start is not None and self.coverage_end is not None
                and self.coverage_start <= start and self.coverage_end >= end)


def source_row_key(ticker: str, when: Any, action: str, value: Any, contraticker: Any) -> str:
    """The canonical identity of ONE source row, used to look up its line numbers in the sealed export.

    Derived only from the vendor's own field values, so the same row keys identically whether it is read
    from the sealed CSV or from the normalized store.
    """
    parts = [str(ticker), str(when), str(action),
             "" if value is None else format(float(value), ".10g"),
             "" if contraticker is None else str(contraticker)]
    return "|".join(parts)


@dataclass(frozen=True)
class SourceRowIndex:
    """Line numbers in the SEALED source export, supplied by the caller.

    ⚠⚠ DuckDB `rowid` is PROHIBITED as provenance. It is a PHYSICAL address: unstable across a rebuild,
    not derived from the source, and meaningless to anyone holding the export. Duplicate provenance must
    point at the sealed artifact, bound by `row_set_identity_sha256`, so a reader can go and look at the
    actual lines. The index is OPTIONAL because the product store does not carry line numbers — when it
    is absent the multiplicity is still recorded, only the line references are omitted.
    """
    sealed_actions_artifact_sha256: str
    row_set_identity_sha256: str
    lines: dict[str, tuple[int, ...]] = field(default_factory=dict)

    def for_row(self, key: str) -> tuple[int, ...]:
        return tuple(self.lines.get(key, ()))


@dataclass(frozen=True)
class NonDecisionMADisclosure:
    """An EXTERNAL adjudication that named acquired-side events are decision-irrelevant.

    ⚠⚠ THIS IS A DISCLOSURE, NOT A PROOF, and it is deliberately not something this module can decide
    for itself. Whether an action affects the governed decision is a SESSION-LEVEL property — it
    depends on the scoring universe, the month-end proxy draws, the final contributor set and the
    selection — none of which a corporate-action verifier can see. Letting the verifier infer it would
    be inventing authority it does not have.

    So the finding is supplied from outside, bound by the digest of the artifact that measured it, and
    this module then CROSS-CHECKS the one clause it CAN observe: that the security is economically
    terminal, i.e. carries no price row after the effective date. A disclosure whose subject still has
    price history is REFUSED rather than reconciled — a security whose series continues past its own
    delisting needs successor linkage nobody has proven.

    `entries` is keyed by `(permaticker, effective_date)`. Keying by permanent identity, never ticker
    text, so a reused symbol cannot inherit another issuer's disclosure.
    """
    assessment_artifact_sha256: str
    entries: frozenset[tuple[str, date]] = frozenset()

    def covers(self, permaticker: str | None, when: date) -> bool:
        return permaticker is not None and (permaticker, when) in self.entries


@dataclass(frozen=True)
class Tolerance:
    """Price-quantum derived comparison band: `safety × quantum × Σ(1/price)` over the prices a
    comparison rounds, floored at `relative_floor`. A fixed 1e-4 quantum is a far larger relative error
    on a $1 name than on a $100 one, so the band is computed per observation rather than fixed."""
    price_quantum: float = PRICE_QUANTUM
    noise_safety_factor: float = NOISE_SAFETY_FACTOR
    relative_floor: float = RELATIVE_FLOOR
    absolute: float = ABSOLUTE_TOLERANCE

    def for_prices(self, *prices: float) -> float:
        """The relative band for a comparison involving `prices` — the summed reciprocal-price
        rounding contribution, scaled by the measured noise/signal separation factor."""
        usable = [p for p in prices if p and p > 0]
        if not usable:
            return self.relative_floor
        summed = sum(1.0 / p for p in usable)
        return max(self.relative_floor,
                   self.noise_safety_factor * self.price_quantum * summed)

    def basis(self) -> dict[str, float | str]:
        return {"price_quantum": self.price_quantum,
                "noise_safety_factor": self.noise_safety_factor,
                "relative_floor": self.relative_floor, "absolute_tolerance": self.absolute,
                "noise_safety_factor_status": "RETAINED_ON_FACTOR_SPECIFIC_EVIDENCE",
                "precision_basis": "sep prices stored to 4 decimals; a one-day ratio comparison rounds "
                                   "four prices (two series, this session and the previous), so the "
                                   "band sums their reciprocal-price contributions",
                "noise_safety_factor_basis":
                    "5x is retained NOT because the rebuilt corpus produced a universal plateau — it "
                    "did not — but because split-factor noise is stable at that level (floor 2 from "
                    "6x), lowering it increases noise sharply (655 at 4x, 2,282 at 3x), and raising "
                    "it destroys true dividend sensitivity (declared dividends flagged fall "
                    "8,220/8,229 at 5x to 8,155 at 20x and 7,977 at 50x). The dividend leg has NO "
                    "clean plateau. The earlier single-universal-plateau claim was measured on the "
                    "SEAM-CONTAMINATED predecessor store and is RETRACTED; one common tolerance is "
                    "kept for both legs pending a failing fixture that proves it technically invalid"}


@dataclass(frozen=True)
class ActionCheck:
    """One (identity, ex-date) group's verification, with everything needed to re-derive the verdict."""
    ticker: str
    permaticker: str | None
    action_date: str
    action_types: tuple[str, ...]
    action_class: ActionClass
    applicability: ActionApplicability
    status: ActionStatus
    reason_code: str | None
    declared_split_multiplier: float | None
    declared_cash_per_share: float | None
    prev_close: float | None
    close: float | None
    prev_closeadj: float | None
    closeadj: float | None
    expected_ratio: float | None
    observed_ratio: float | None
    absolute_residual: float | None
    relative_residual: float | None
    absolute_tolerance: float
    relative_tolerance: float
    verdict: AdjustmentVerdict
    detail: str
    # Which FACTOR(s) this check reconciled. The factor-specific `explained` sets are built from these
    # and from nothing else — see the module docstring.
    proves_dividend_factor: bool = False
    proves_split_factor: bool = False
    # Duplicate canonicalization provenance (items 7/8).
    canonical_action_id: str = ""
    raw_source_row_count: int = 0
    canonical_row_count: int = 0
    duplicate_disposition: DuplicateDisposition = DuplicateDisposition.SINGLE_SOURCE_ROW
    source_csv_line_numbers: tuple[int, ...] = ()
    sealed_actions_artifact_sha256: str | None = None

    @property
    def satisfies_readiness(self) -> bool:
        return self.status in SATISFIES_READINESS


# ── bounded per-action evidence (A3) ─────────────────────────────────────────────────────────────────
#
# `checks` was unbounded: one `ActionCheck` per relevant (ticker, ex-date) group, all of them carried
# into the committed observation. Over a 200-session MA window across ~200 names that is thousands of
# entries, and the observation is immutable — an unbounded payload is not merely large, it is a size no
# one chose.
#
# ⚠ This cap bounds what lands in an IMMUTABLE OBSERVATION. It is a legitimate production control and is
# NOT the same thing as the completeness of a diagnostic reconciliation; a diagnostic that needs every
# relevant action rebinds these constants in its own process and restores them, rather than editing them.

MAX_EVIDENCE_ACTIONS = 200
MAX_EVIDENCE_SERIALIZED_BYTES = 256 * 1024

SELECTION_RULE = (
    "longest deterministic prefix of the relevant actions ordered by "
    "(action_date, action_types, ticker, action_digest) whose FINAL canonical serialization fits "
    "both max_actions and max_serialized_bytes; an entry that would breach either cap ends the prefix"
)


def _check_payload(check: ActionCheck) -> dict[str, Any]:
    """Exactly the representation that lands in the record — what the byte cap must be measured on."""
    return {**asdict(check), "verdict": str(check.verdict), "action_class": str(check.action_class),
            "applicability": str(check.applicability), "status": str(check.status),
            "duplicate_disposition": str(check.duplicate_disposition)}


def _canonical_bytes(payloads: list[dict[str, Any]]) -> bytes:
    import json

    return json.dumps(payloads, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def action_digest(check: ActionCheck) -> str:
    """A canonical digest of one check — the final tie-breaker, so ordering never depends on incidental
    database order or on dict iteration."""
    return hashlib.sha256(_canonical_bytes([_check_payload(check)])).hexdigest()


def _selection_key(check: ActionCheck) -> tuple[str, str, str, str]:
    return (check.action_date, "|".join(check.action_types), check.ticker, action_digest(check))


@dataclass(frozen=True)
class BoundedActionEvidence:
    """What was included, what was left out, and the rule that decided."""
    total_action_count: int
    included_action_count: int
    omitted_action_count: int
    serialized_bytes: int
    max_actions: int
    max_serialized_bytes: int
    truncated: bool
    selection_rule: str


def bound_action_evidence(
    checks: tuple[ActionCheck, ...], *, max_actions: int | None = None,
    max_serialized_bytes: int | None = None,
) -> tuple[tuple[ActionCheck, ...], BoundedActionEvidence]:
    """Select the longest deterministic prefix of `checks` that fits both caps.

    The byte cap is enforced on the FINAL canonical serialization, re-measured after each candidate is
    added — not estimated from Python object sizes, which bear no relation to the bytes actually
    recorded.

    A single oversized action cannot slip past the cap: it simply fails to fit, which ends the prefix.
    If the very first entry does not fit, none are included and `truncated` is True — a prefix rule
    keeps the selection reproducible, whereas skipping-and-continuing would make inclusion depend on
    the sizes of entries around it.
    """
    # Resolved from the module constants at CALL time, not captured as default arguments. A default
    # argument binds at definition time, which would make the caps look configurable while being frozen
    # at import — the constants would silently stop being the source of truth.
    max_actions = MAX_EVIDENCE_ACTIONS if max_actions is None else max_actions
    max_serialized_bytes = (MAX_EVIDENCE_SERIALIZED_BYTES if max_serialized_bytes is None
                            else max_serialized_bytes)

    ordered = sorted(checks, key=_selection_key)
    included: list[ActionCheck] = []
    payloads: list[dict[str, Any]] = []
    size = len(_canonical_bytes([]))

    for check in ordered:
        if len(included) >= max_actions:
            break
        candidate = [*payloads, _check_payload(check)]
        candidate_size = len(_canonical_bytes(candidate))
        if candidate_size > max_serialized_bytes:
            break
        included.append(check)
        payloads = candidate
        size = candidate_size

    omitted = len(ordered) - len(included)
    return tuple(included), BoundedActionEvidence(
        total_action_count=len(ordered), included_action_count=len(included),
        omitted_action_count=omitted, serialized_bytes=size, max_actions=max_actions,
        max_serialized_bytes=max_serialized_bytes, truncated=bool(omitted),
        selection_rule=SELECTION_RULE)


@dataclass(frozen=True)
class UnexplainedAdjustment:
    """A factor movement visible in the series with no reconciled action to explain it."""
    ticker: str
    permaticker: str | None
    session_date: str
    factor: FactorKind
    observed_ratio: float
    raw_ratio: float
    absolute_residual: float
    relative_tolerance: float
    dividend_factor_ratio: float | None = None
    split_factor_ratio: float | None = None


@dataclass(frozen=True)
class FactorMovementCensus:
    """Direction (b), reported PER FACTOR. A merged count cannot be read: an undeclared split and an
    undeclared dividend are different defects with different causes."""
    undeclared_dividend_factor_changes: int = 0
    undeclared_split_factor_changes: int = 0
    combined_or_ambiguous_changes: int = 0
    explained_dividend_factor_sessions: int = 0
    explained_split_factor_sessions: int = 0
    session_pairs_examined: int = 0
    identities_examined: int = 0
    unresolved_identity_count: int = 0

    @property
    def total_undeclared(self) -> int:
        return (self.undeclared_dividend_factor_changes + self.undeclared_split_factor_changes
                + self.combined_or_ambiguous_changes)


@dataclass(frozen=True)
class AdjustmentVerificationEvidence:
    """OPEN provenance for one window's verification — actions, prices and arithmetic only. No factor
    values, rankings, returns or portfolio results."""
    session_date: str
    window_start: str
    verdict: AdjustmentVerdict
    proven: bool
    adjustment_series_consistent_with_declared_actions: bool
    declared_action_source_authoritative: bool
    source_identity: str
    source_coverage_start: str | None
    source_coverage_end: str | None
    total_actions_in_window: int
    relevant_actions_in_window: int
    irrelevant_actions_in_window: int
    relevant_ticker_count: int
    relevance_set_sha256: str
    store_identity_sha256: str
    checks_by_verdict: dict[str, int]
    unexplained_adjustment_count: int
    detail: str
    tolerance: dict[str, float | str] = field(default_factory=dict)
    checks_by_status: dict[str, int] = field(default_factory=dict)
    checks_by_applicability: dict[str, int] = field(default_factory=dict)
    checks_by_reason_code: dict[str, int] = field(default_factory=dict)
    factor_census: FactorMovementCensus | None = None
    #: The digest of the EXTERNAL decision-relevance assessment, when one was supplied. Recorded so a
    #: downstream gate can bind the disclosure to the artifact that measured it instead of parsing it
    #: out of prose.
    ma_disclosure_sha256: str | None = None
    #: How many events the supplied disclosure covers CORPUS-WIDE. Recorded separately from
    #: `checks_by_status` because the two answer different questions and conflating them is exactly how
    #: the 2026-07-27 attestation went stale: a disclosure adjudicated over a BROADER identity set lists
    #: events that this session's relevance set may not contain at all. A reader must be able to see
    #: "18 known corpus-wide, 0 present in this session" rather than infer one number from the other.
    ma_disclosure_entry_count: int | None = None
    # A3: `checks` is a BOUNDED selection; `action_evidence` says how bounded and by what rule, so a
    # reader never has to guess whether a short list means "few actions" or "many, truncated".
    action_evidence: BoundedActionEvidence | None = None
    checks: tuple[ActionCheck, ...] = ()
    unexplained_examples: tuple[UnexplainedAdjustment, ...] = ()

    def to_open_provenance(self) -> dict[str, Any]:
        d = asdict(self)
        d["verdict"] = str(self.verdict)
        d["checks"] = [_check_payload(c) for c in self.checks]
        d["unexplained_examples"] = [{**asdict(u), "factor": str(u.factor)}
                                     for u in self.unexplained_examples]
        return d


def relevance_digest(tickers: list[str], window_start: date, session_date: date,
                     store_identity_sha256: str) -> str:
    """Bind the relevance SET to the same value-level store identity R5a records, so the set a
    verification ran over cannot be reinterpreted later against different data."""
    payload = "|".join([store_identity_sha256, window_start.isoformat(), session_date.isoformat(),
                        *sorted(tickers)])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


#: The vendor's EXPLICIT "no contra security" sentinel, matched exactly after stripping.
#:
#: ⚠ Deliberately NOT a loose null-token rule. `NA` is a LIVE TICKER in this very corpus (Nordic
#: American Tankers) — a case-folded "na" test, or adding "na" to a null set, would classify its
#: dividends as contraticker events and make them unverifiable. This is the THIRD instance of that
#: defect class here (issue #527's `NA` ticker; a `"nat"` null token that emptied ticker `NAT`), so
#: missingness is decided by the documented sentinel, never by resemblance to one.
#:
#: Every dividend (216,756) and split (10,136) row in the governed corpus carries `'N/A'`. Reading it
#: as a real contraticker sent all of them down the "another security is involved" branch, where the
#: correct cash-dividend and split paths are unreachable — the paths existed and were right, but no
#: input could ever arrive at them.
_NO_CONTRA_SENTINELS = frozenset({"N/A"})


def _involves_contra_security(contraticker: Any) -> bool:
    """Whether the action names ANOTHER security, which a one-security ratio cannot express."""
    if contraticker is None:
        return False
    text = str(contraticker).strip()
    # "nan" is the pandas float-NaN artifact of a missing cell, not a symbol.
    return bool(text) and text.lower() != "nan" and text not in _NO_CONTRA_SENTINELS


def classify_action(label: str, contraticker: Any) -> ActionClass:
    """Classify a raw action label. A contraticker means another security is involved, which the
    one-security ratio relationship cannot express — those stay unsupported."""
    text = str(label or "").strip().lower()
    if _involves_contra_security(contraticker):
        if text in _MERGER_LABELS:
            return ActionClass.MERGER_CONVERSION
        if text in _SPINOFF_LABELS:
            return ActionClass.SPINOFF_DISTRIBUTION
        if text == _ACQUIRER_REFERENCE_LABEL:
            # An `acquisitionof` row NAMES the acquired security in `contraticker`; that reference is
            # what the row is for, and it does not by itself make the acquirer's own price history
            # adjustable. Whether it clears is decided empirically by the named rule, never here.
            return ActionClass.ACQUIRER_REFERENCE
        if text in _RELATIONSHIP_LABELS:
            return ActionClass.RELATIONSHIP_METADATA
        return ActionClass.UNSUPPORTED
    if text in _CASH_LABELS:
        return ActionClass.CASH_DIVIDEND
    if text in _SPLIT_LABELS:
        return ActionClass.SPLIT
    if text in _SPINOFF_LABELS:
        return ActionClass.SPINOFF_DISTRIBUTION
    if text in _MERGER_LABELS:
        return ActionClass.MERGER_CONVERSION
    if text == _ACQUIRER_REFERENCE_LABEL:
        return ActionClass.ACQUIRER_REFERENCE
    if text in _RELATIONSHIP_LABELS:
        return ActionClass.RELATIONSHIP_METADATA
    if text in _SYMBOL_LABELS:
        return ActionClass.SYMBOL_TRANSITION
    return ActionClass.UNSUPPORTED


def _query(store: Any, sql: str, params: list) -> list[tuple]:
    con = getattr(store, "con", store)
    if not hasattr(con, "execute"):
        raise AdjustmentVerificationError(f"not a queryable store: {type(store).__name__}")
    try:
        return [tuple(r) for r in con.execute(sql, params).fetchall()]
    except Exception as exc:
        raise AdjustmentVerificationError(f"store query failed: {exc}") from exc


# ── permanent identity resolution ────────────────────────────────────────────────────────────────────

def _resolve_permatickers(store: Any, names: list[str]) -> dict[str, str]:
    """ticker → the vendor PERMANENT identifier, from the governed TICKERS table.

    The factor-specific `explained` sets are keyed by this, never by ticker text: a symbol is reused
    across issuers (EchoStar vs Echo Global under `ECHO`), so a ticker-keyed suppression can silence a
    DIFFERENT company's adjustment on the same session. A ticker that does not resolve is left out and
    fails closed at the point of use rather than falling back to its symbol.
    """
    cols = {str(r[1]).lower()
            for r in _query(store, "PRAGMA table_info('tickers')", [])}
    if not cols:
        raise AdjustmentVerificationError("the store has no `tickers` table, so securities cannot be "
                                          "resolved to permanent identities")
    if "permaticker" not in cols:
        raise AdjustmentVerificationError(
            "the governed TICKERS table carries no `permaticker` column; the adjustment verifier "
            "resolves securities by permanent identity and never falls back to ticker identity")
    if not names:
        return {}
    ph = ",".join("?" * len(names))
    rows = _query(store,
                  f"SELECT ticker, permaticker FROM tickers "
                  f"WHERE ticker IN ({ph}) AND permaticker IS NOT NULL", list(names))
    out: dict[str, str] = {}
    ambiguous: set[str] = set()
    for ticker, perma in rows:
        text = str(perma).strip()
        if not text:
            continue
        if ticker in out and out[ticker] != text:
            ambiguous.add(str(ticker))
        out[str(ticker)] = text
    if ambiguous:
        raise AdjustmentVerificationError(
            f"{len(ambiguous)} ticker(s) resolve to MORE THAN ONE permanent identity "
            f"(e.g. {sorted(ambiguous)[:3]}); the identity contract requires exactly one")
    return out


def _mark_bounds(store: Any, names: list[str]) -> dict[str, tuple[date, date]]:
    """ticker → (first, last) governed session carrying a usable mark, over the WHOLE store.

    Used by the named applicability rules: "this listing has no prior governed history to adjust" and
    "the acquirer's lineage continues past the action" are both statements about the security's whole
    life, not about the verification window.
    """
    if not names:
        return {}
    ph = ",".join("?" * len(names))
    rows = _query(store,
                  f"SELECT ticker, min(date), max(date) FROM sep "
                  f"WHERE ticker IN ({ph}) AND closeadj IS NOT NULL GROUP BY ticker", list(names))
    return {str(r[0]): (r[1], r[2]) for r in rows}


def verify_adjustments(
    store: Any,
    *,
    window_start: date,
    session_date: date,
    relevant_tickers: list[str],
    source: ActionSourceDeclaration,
    store_identity_sha256: str = "",
    tolerance: Tolerance | None = None,
    max_examples: int = 25,
    source_row_index: SourceRowIndex | None = None,
    ma_disclosure: NonDecisionMADisclosure | None = None,
) -> AdjustmentVerificationEvidence:
    """Verify that the adjusted series over `[window_start, session_date]` reflects every relevant
    declared action, and that no FACTOR MOVEMENT in the series is unexplained.

    `relevant_tickers` is the union of the securities whose adjusted observations can influence the
    session — the scoring candidates plus the proxy's expected constituents across the whole MA window,
    including names that left the universe before the session but priced into it earlier.
    """
    tol = tolerance or Tolerance()
    names = sorted(set(relevant_tickers))
    digest = relevance_digest(names, window_start, session_date, store_identity_sha256)

    total_actions = _query(store, "SELECT COUNT(*) FROM actions WHERE date BETWEEN ? AND ?",
                           [window_start, session_date])[0][0]
    rows: list[tuple] = []
    if names:
        ph = ",".join("?" * len(names))
        rows = _query(store,
                      f"SELECT ticker, date, action, value, contraticker FROM actions "
                      f"WHERE date BETWEEN ? AND ? AND ticker IN ({ph}) "
                      f"ORDER BY ticker, date, action, value",
                      [window_start, session_date, *names])
    relevant = len(rows)

    def evidence(verdict: AdjustmentVerdict, detail: str, *, consistent: bool,
                 checks: tuple[ActionCheck, ...] = (),
                 unexplained: tuple[UnexplainedAdjustment, ...] = (),
                 unexplained_count: int = 0,
                 census: FactorMovementCensus | None = None) -> AdjustmentVerificationEvidence:
        # Counted over EVERY check, before bounding. Truncating the payload must not distort the
        # verdict census — the counts are how a reader knows what the omitted entries were.
        by_verdict: dict[str, int] = {}
        by_status: dict[str, int] = {}
        by_applicability: dict[str, int] = {}
        by_reason: dict[str, int] = {}
        for c in checks:
            by_verdict[str(c.verdict)] = by_verdict.get(str(c.verdict), 0) + 1
            by_status[str(c.status)] = by_status.get(str(c.status), 0) + 1
            by_applicability[str(c.applicability)] = by_applicability.get(str(c.applicability), 0) + 1
            if c.reason_code:
                by_reason[c.reason_code] = by_reason.get(c.reason_code, 0) + 1
        bounded_checks, bounded = bound_action_evidence(checks)
        proven = verdict in (AdjustmentVerdict.PROVEN, AdjustmentVerdict.NO_RELEVANT_ACTIONS)
        return AdjustmentVerificationEvidence(
            session_date=session_date.isoformat(), window_start=window_start.isoformat(),
            verdict=verdict, proven=proven,
            adjustment_series_consistent_with_declared_actions=consistent,
            declared_action_source_authoritative=source.authoritative,
            source_identity=source.identity,
            source_coverage_start=source.coverage_start.isoformat() if source.coverage_start else None,
            source_coverage_end=source.coverage_end.isoformat() if source.coverage_end else None,
            total_actions_in_window=int(total_actions), relevant_actions_in_window=relevant,
            irrelevant_actions_in_window=int(total_actions) - relevant,
            relevant_ticker_count=len(names), relevance_set_sha256=digest,
            store_identity_sha256=store_identity_sha256, checks_by_verdict=by_verdict,
            checks_by_status=by_status, checks_by_applicability=by_applicability,
            checks_by_reason_code=by_reason, factor_census=census,
            ma_disclosure_sha256=(ma_disclosure.assessment_artifact_sha256
                                  if ma_disclosure else None),
            ma_disclosure_entry_count=(len(ma_disclosure.entries) if ma_disclosure else None),
            unexplained_adjustment_count=unexplained_count, detail=detail,
            tolerance=tol.basis(), action_evidence=bounded, checks=bounded_checks,
            unexplained_examples=unexplained)

    if not names:
        return evidence(AdjustmentVerdict.NOT_PROVEN_INSUFFICIENT_DATA,
                        "no relevant securities were supplied — nothing could be verified",
                        consistent=False)

    # The source must be declared authoritative and cover the window BEFORE any arithmetic counts.
    if not source.authoritative:
        return evidence(
            AdjustmentVerdict.NOT_PROVEN_INSUFFICIENT_DATA,
            f"the corporate-action source {source.identity!r} is not declared authoritative — an "
            f"unfrozen or unidentified source cannot evidence reflection", consistent=False)
    if not source.covers(window_start, session_date):
        return evidence(
            AdjustmentVerdict.NOT_PROVEN_INSUFFICIENT_DATA,
            f"the declared source coverage ({source.coverage_start}..{source.coverage_end}) does not "
            f"span the consumed window {window_start}..{session_date}", consistent=False)

    permatickers = _resolve_permatickers(store, names)
    bounds = _mark_bounds(store, names)

    # ── direction (a): every relevant declared action must be reflected ──
    groups: dict[tuple[str, date], list[tuple]] = {}
    for ticker, when, label, value, contra in rows:
        groups.setdefault((ticker, when), []).append((label, value, contra))

    marks = _marks(store, names, window_start, session_date)
    checks: list[ActionCheck] = []
    for (ticker, when), items in sorted(groups.items(), key=lambda kv: (kv[0][0], str(kv[0][1]))):
        checks.append(_check_group(ticker, when, items, marks, tol,
                                   permaticker=permatickers.get(ticker), bounds=bounds.get(ticker),
                                   source_row_index=source_row_index))

    # ── direction (b): every FACTOR MOVEMENT in the series must be explained, per factor ──
    #
    # ⚠ The `explained` sets are built ONLY from checks that reached PROVEN_REFLECTED on that specific
    # factor. A declared-but-unreconciled action, an unsupported one, and a bare `acquisitionof` all
    # explain NOTHING — otherwise a failed reconciliation would suppress the very series signal that
    # exists to catch it.
    explained_dividend: set[tuple[str, date]] = set()
    explained_split: set[tuple[str, date]] = set()
    for c in checks:
        if c.status is not ActionStatus.PROVEN_REFLECTED or c.permaticker is None:
            continue
        key = (c.permaticker, date.fromisoformat(c.action_date))
        if c.proves_dividend_factor:
            explained_dividend.add(key)
        if c.proves_split_factor:
            explained_split.add(key)

    census, examples, flagged = _unexplained_factor_movements(
        store, names, window_start, session_date, tol,
        permatickers=permatickers, explained_dividend=explained_dividend,
        explained_split=explained_split, limit=max_examples)
    unexplained_total = census.total_undeclared

    # ── post-pass: the two rulings that need context a single group cannot see ──────────────────────
    #
    # Both run AFTER the census, and NEITHER touches the explained sets — a lineage event and a
    # disclosed acquisition reconcile no factor, so nothing they do can suppress a series signal.
    # Running them here rather than inside `_check_group` is what lets them depend on (a) whether the
    # PARENT's distribution was proven in this same pass and (b) whether the session showed an
    # unexplained movement at all.
    checks = _apply_context_rulings(store, checks, groups=groups, permatickers=permatickers,
                                    bounds=bounds, flagged=flagged, disclosure=ma_disclosure)

    conflict = [c for c in checks if c.status in (ActionStatus.PROVEN_NOT_REFLECTED,
                                                  ActionStatus.SOURCE_CONFLICT)]
    unsupported = [c for c in checks if c.status is ActionStatus.NOT_PROVEN_UNSUPPORTED_SEMANTICS]
    insufficient = [c for c in checks if c.status is ActionStatus.NOT_PROVEN_INSUFFICIENT_DATA]
    disclosed = [c for c in checks
                 if c.status is ActionStatus.UNRESOLVED_NONDECISION_MA_SEMANTICS]
    consistent = not conflict

    if conflict:
        return evidence(AdjustmentVerdict.INTEGRITY_STOP_CONFLICT,
                        f"{len(conflict)} relevant action(s) contradict the adjusted series or each "
                        f"other (e.g. {conflict[0].ticker} {conflict[0].action_date}: "
                        f"{conflict[0].detail})", consistent=False, checks=tuple(checks),
                        unexplained=examples, unexplained_count=unexplained_total, census=census)
    if unsupported:
        return evidence(AdjustmentVerdict.NOT_PROVEN_UNSUPPORTED_ACTION,
                        f"{len(unsupported)} relevant action(s) have no named rule that establishes "
                        f"how they affect a single security's price history (e.g. "
                        f"{unsupported[0].ticker} {unsupported[0].action_date}: "
                        f"{unsupported[0].action_types}); the default is to refuse, not to assume "
                        f"no adjustment was required",
                        consistent=consistent, checks=tuple(checks), unexplained=examples,
                        unexplained_count=unexplained_total, census=census)
    if insufficient:
        return evidence(AdjustmentVerdict.NOT_PROVEN_INSUFFICIENT_DATA,
                        f"{len(insufficient)} relevant action(s) lack the marks the relationship needs "
                        f"(e.g. {insufficient[0].ticker} {insufficient[0].action_date})",
                        consistent=consistent, checks=tuple(checks), unexplained=examples,
                        unexplained_count=unexplained_total, census=census)
    if disclosed:
        # Reported with its own wording so the record cannot be misread as a clean pass. The claim
        # this supports is NARROWER than "every corporate action is economically reconciled".
        return evidence(
            AdjustmentVerdict.NOT_PROVEN_UNSUPPORTED_ACTION,
            f"{len(disclosed)} economically terminal acquired-side action(s) remain UNVERIFIABLE from "
            f"the vendor schema and are recorded as a DISCLOSED LIMITATION "
            f"({ActionStatus.UNRESOLVED_NONDECISION_MA_SEMANTICS}); each was measured to have no "
            f"effect on the governed decision, but a disclosure is not proven reflection and does not "
            f"satisfy readiness (e.g. {disclosed[0].ticker} {disclosed[0].action_date})",
            consistent=consistent, checks=tuple(checks), unexplained=examples,
            unexplained_count=unexplained_total, census=census)
    if unexplained_total:
        return evidence(
            AdjustmentVerdict.NOT_PROVEN_INSUFFICIENT_DATA,
            f"{unexplained_total} factor movement(s) in the consumed window have no reconciled action "
            f"to explain them ({census.undeclared_dividend_factor_changes} dividend-factor, "
            f"{census.undeclared_split_factor_changes} split-factor, "
            f"{census.combined_or_ambiguous_changes} combined; e.g. {examples[0].ticker} "
            f"{examples[0].session_date} {examples[0].factor}) — the declared set is incomplete, and "
            f"an empty action table is not evidence that none occurred",
            consistent=consistent, checks=tuple(checks), unexplained=examples,
            unexplained_count=unexplained_total, census=census)

    if not checks:
        return evidence(AdjustmentVerdict.NO_RELEVANT_ACTIONS,
                        "an authoritative source covering the window declares no action on any "
                        "relevant security, and neither factor shows an unexplained movement",
                        consistent=True, census=census)
    return evidence(AdjustmentVerdict.PROVEN,
                    f"all {len(checks)} relevant action(s) reached a terminal proven status within the "
                    f"price-quantum tolerance, and neither factor shows an unexplained movement",
                    consistent=True, checks=tuple(checks), census=census)


def _marks(store: Any, names: list[str], window_start: date, session_date: date
           ) -> dict[tuple[str, date], tuple]:
    """(ticker, date) → (prev_close, close, prev_closeadj, closeadj, prev_unadj, unadj).

    ⚠ The scan starts ONE GOVERNED SESSION BEFORE `window_start` (owner authorization 2026-07-30).
    An action effective on the FIRST in-window session has no prior mark inside the window, so its
    ratio is uncomputable and it fails closed for a reason that is an artifact of where the window
    begins rather than a property of the data (measured: NXPI and STX on 2025-06-25). The extra mark is
    used for VERIFICATION CONTEXT ONLY — it does not enlarge the strategy lookback, and no ranking or
    scoring input reads it. If the preceding authoritative mark does not exist, the case still fails
    closed.
    """
    ph = ",".join("?" * len(names))
    rows = _query(store,
                  f"WITH prior AS (SELECT max(date) AS d FROM sep WHERE date < ?), "
                  f"scan AS (SELECT ticker, date, close, closeadj, closeunadj, "
                  f"  lag(close) OVER (PARTITION BY ticker ORDER BY date) AS pclose, "
                  f"  lag(closeadj) OVER (PARTITION BY ticker ORDER BY date) AS padj, "
                  f"  lag(closeunadj) OVER (PARTITION BY ticker ORDER BY date) AS punadj "
                  f"  FROM sep WHERE ticker IN ({ph}) "
                  f"  AND date BETWEEN coalesce((SELECT d FROM prior), ?) AND ?) "
                  f"SELECT ticker, date, close, closeadj, pclose, padj, closeunadj, punadj "
                  f"FROM scan WHERE date BETWEEN ? AND ? ORDER BY ticker, date",
                  [window_start, *names, window_start, session_date, window_start, session_date])
    return {(r[0], r[1]): (r[4], r[2], r[5], r[3], r[7], r[6]) for r in rows}


# ── duplicate canonicalization (items 7/8) ───────────────────────────────────────────────────────────

def _partition_duplicates(items: list[tuple]) -> tuple[list[tuple], int, bool]:
    """Collapse byte-identical source rows; detect duplicates that CONTRADICT one another.

    Returns `(canonical_rows, raw_row_count, incompatible)`.

    Identical duplicates are a SOURCE ARTIFACT, not a contradiction: the vendor emitting the same
    dividend twice says the same thing twice. Treating that as a conflict blocked 260 measured groups
    that assert nothing inconsistent. They are canonicalized to one row and the multiplicity is retained
    in the evidence rather than discarded.

    ⚠⚠ Incompatibility is scoped to labels whose `value` the arithmetic actually CONSUMES — cash
    distributions and splits. This is not a nicety, it follows from a measured fact about the source:
    `ACTIONS.value` is TYPE-DEPENDENT. For `acquisitionof`/`acquisitionby` it is the REPORTED
    TRANSACTION VALUE IN MILLIONS (measured: BRK.B→TMHC 6768.8, GSK→NUVL 9792.6, PSA→NSA 3351.8) — never
    a per-share consideration, never an exchange ratio, never a split multiplier. Two `acquisitionof`
    rows on one date declaring different values mean the acquirer bought two companies that day; they
    contradict NOTHING about price adjustment, and calling that a source conflict would manufacture a
    blocker out of a field the arithmetic never reads.
    """
    raw = len(items)
    seen: set[tuple[str, float | None, str | None]] = set()
    canonical: list[tuple] = []
    for label, value, contra in items:
        key = (str(label), float(value) if value is not None else None,
               None if contra is None else str(contra))
        if key in seen:
            continue
        seen.add(key)
        canonical.append((label, value, contra))

    # A contradiction is the SAME arithmetic label declaring DIFFERENT values on one (ticker, date).
    by_label: dict[str, set[float | None]] = {}
    for label, value, _contra in canonical:
        text = str(label or "").strip().lower()
        if text in _ARITHMETIC_VALUE_LABELS:
            by_label.setdefault(text, set()).add(
                round(float(value), 10) if value is not None else None)
    incompatible = any(len(v) > 1 for v in by_label.values())
    return canonical, raw, incompatible


def _canonical_action_id(ticker: str, permaticker: str | None, when: date,
                         canonical: list[tuple]) -> str:
    """A SOURCE-DERIVED identity for one canonicalized action group.

    ⚠ Never a DuckDB `rowid`: that is a physical address, unstable across a rebuild and meaningless
    outside the file it came from.
    """
    payload = "|".join([str(permaticker or ""), str(ticker), when.isoformat(),
                        *sorted(source_row_key(ticker, when, label, value, contra)
                                for label, value, contra in canonical)])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _factor_unchanged(prev_a: float, a: float, prev_b: float, b: float, tol: Tolerance) -> bool:
    """Whether the factor `a/b` is unchanged across the session pair, within the rounding band."""
    if not all(x and x > 0 for x in (prev_a, a, prev_b, b)):
        return False
    ratio = (a / b) / (prev_a / prev_b)
    return abs(ratio - 1.0) <= tol.absolute + tol.for_prices(prev_a, a, prev_b, b)


def _check_group(ticker: str, when: date, items: list[tuple], marks: dict, tol: Tolerance, *,
                 permaticker: str | None, bounds: tuple[date, date] | None,
                 source_row_index: SourceRowIndex | None) -> ActionCheck:
    """Verify one (identity, ex-date) group and resolve it to ONE of the six terminal statuses.

    Default-deny: the status starts at `NOT_PROVEN_UNSUPPORTED_SEMANTICS` and only a named rule moves
    it. Every exit records the reason code that authorised it.
    """
    types = tuple(str(i[0]) for i in items)
    canonical, raw_count, incompatible = _partition_duplicates(items)
    disposition = (DuplicateDisposition.SINGLE_SOURCE_ROW if raw_count == len(canonical)
                   else DuplicateDisposition.CANONICALIZED_IDENTICAL_DUPLICATES)
    action_id = _canonical_action_id(ticker, permaticker, when, canonical)
    lines: tuple[int, ...] = ()
    if source_row_index is not None:
        collected: list[int] = []
        for label, value, contra in canonical:
            collected.extend(source_row_index.for_row(
                source_row_key(ticker, when, label, value, contra)))
        lines = tuple(sorted(set(collected)))

    classes = [classify_action(label, contra) for label, _v, contra in canonical]
    labels = {str(label or "").strip().lower() for label, _v, _c in canonical}

    def result(status: ActionStatus, klass: ActionClass, detail: str, *,
               applicability: ActionApplicability, reason: str | None = None,
               split=None, cash=None, expected=None, observed=None, abs_res=None, rel_res=None,
               rel_tol=0.0, prices=(None, None, None, None),
               proves_dividend: bool = False, proves_split: bool = False,
               dispo: DuplicateDisposition | None = None) -> ActionCheck:
        assert reason is None or reason in NAMED_APPLICABILITY_RULES, (
            f"reason code {reason!r} is not a NAMED applicability rule")
        return ActionCheck(
            ticker=ticker, permaticker=permaticker, action_date=when.isoformat(),
            action_types=types, action_class=klass, applicability=applicability, status=status,
            reason_code=reason,
            declared_split_multiplier=split, declared_cash_per_share=cash,
            prev_close=prices[0], close=prices[1], prev_closeadj=prices[2], closeadj=prices[3],
            expected_ratio=expected, observed_ratio=observed, absolute_residual=abs_res,
            relative_residual=rel_res, absolute_tolerance=tol.absolute, relative_tolerance=rel_tol,
            verdict=_WINDOW_VERDICT_FOR[status], detail=detail,
            proves_dividend_factor=proves_dividend, proves_split_factor=proves_split,
            canonical_action_id=action_id, raw_source_row_count=raw_count,
            canonical_row_count=len(canonical),
            duplicate_disposition=dispo or disposition, source_csv_line_numbers=lines,
            sealed_actions_artifact_sha256=(
                source_row_index.sealed_actions_artifact_sha256 if source_row_index else None))

    if permaticker is None:
        return result(ActionStatus.NOT_PROVEN_INSUFFICIENT_DATA, ActionClass.UNSUPPORTED,
                      "the security does not resolve to a permanent identity, so an adjustment cannot "
                      "be attributed to a lineage",
                      applicability=ActionApplicability.INSUFFICIENT_TO_CLASSIFY)

    if incompatible:
        return result(ActionStatus.SOURCE_CONFLICT, ActionClass.UNSUPPORTED,
                      f"duplicate source rows declare incompatible values for the same arithmetic "
                      f"action on this date: {sorted(types)}",
                      applicability=ActionApplicability.INSUFFICIENT_TO_CLASSIFY,
                      dispo=DuplicateDisposition.SOURCE_CONFLICT_INCOMPATIBLE_DUPLICATES)

    marks_row = marks.get((ticker, when))
    have_marks = marks_row is not None and not any(p is None or p <= 0 for p in marks_row)
    prices = marks_row[:4] if marks_row else (None, None, None, None)

    # ── the NO-ADJUSTMENT-EXPECTED rules ────────────────────────────────────────────────────────────
    #
    # Each is NAMED, narrow and EMPIRICAL. None of them asserts anything about the economics of the
    # event; each proves only that the two governed factor systems express no historical price
    # adjustment across the session. Anything that matches no rule keeps the default and blocks.
    no_adjust = _no_adjustment_rule(labels, marks_row, have_marks, bounds, when, tol)
    if no_adjust is not None:
        klass, reason, detail = no_adjust
        if reason is None:
            return result(ActionStatus.NOT_PROVEN_INSUFFICIENT_DATA, klass, detail,
                          applicability=ActionApplicability.INSUFFICIENT_TO_CLASSIFY, prices=prices)
        return result(ActionStatus.PROVEN_NO_PRICE_ADJUSTMENT_APPLICABLE, klass, detail,
                      applicability=ActionApplicability.NO_SINGLE_SECURITY_PRICE_ADJUSTMENT_EXPECTED,
                      reason=reason, prices=prices)

    # ── the bounded extended shapes: spinoff distribution and ADR-ratio change ──────────────────────
    extended = _extended_shape_terms(labels, canonical)
    override_reason: str | None = None
    if extended is not None:
        ok, splits, cash, klass, override_reason, why = extended
        if not ok:
            return result(DEFAULT_ACTION_STATUS, klass, why,
                          applicability=ActionApplicability.INSUFFICIENT_TO_CLASSIFY, prices=prices)
    else:
        # ── everything that is not an arithmetic action keeps the DEFAULT ──────────────────────────
        arithmetic = {ActionClass.CASH_DIVIDEND, ActionClass.SPLIT}
        if any(k not in arithmetic for k in classes):
            offending = next(k for k in classes if k not in arithmetic)
            return result(DEFAULT_ACTION_STATUS, offending,
                          f"action class {offending} has no named rule establishing how it affects "
                          f"this security's price history; it may involve another security or a "
                          f"non-price event, and the default is to refuse rather than assume",
                          applicability=ActionApplicability.INSUFFICIENT_TO_CLASSIFY, prices=prices)

        splits = [float(v) for (label, v, _c), k in zip(canonical, classes, strict=True)
                  if k is ActionClass.SPLIT and v is not None]
        cash = [float(v) for (label, v, _c), k in zip(canonical, classes, strict=True)
                if k is ActionClass.CASH_DIVIDEND and v is not None]
        if any(v is None for _l, v, _c in canonical):
            return result(ActionStatus.NOT_PROVEN_INSUFFICIENT_DATA, ActionClass.UNSUPPORTED,
                          "an action row carries no declared value",
                          applicability=ActionApplicability.PRICE_ADJUSTMENT_EXPECTED, prices=prices)
        klass = (ActionClass.SPLIT_AND_CASH if splits and cash
                 else ActionClass.SPLIT if splits else ActionClass.CASH_DIVIDEND)

    if len(splits) > 1 and len({round(s, 10) for s in splits}) > 1:
        return result(ActionStatus.SOURCE_CONFLICT, ActionClass.SPLIT,
                      f"incompatible split multipliers declared on the same date: {splits}",
                      applicability=ActionApplicability.PRICE_ADJUSTMENT_EXPECTED, prices=prices,
                      dispo=DuplicateDisposition.SOURCE_CONFLICT_INCOMPATIBLE_DUPLICATES)

    split_mult = splits[0] if splits else 1.0
    cash_total = sum(cash)                     # additive: recognized cash distributions compose

    if not have_marks:
        return result(ActionStatus.NOT_PROVEN_INSUFFICIENT_DATA, klass,
                      "the prior and current raw and adjusted marks are not all available",
                      applicability=ActionApplicability.PRICE_ADJUSTMENT_EXPECTED,
                      split=split_mult, cash=cash_total, prices=prices)

    # `have_marks` has already established the row exists and every mark is present and positive, so
    # these are floats. Bound EXPLICITLY rather than unpacked: the guard is an `any(... is None ...)`
    # test, which a type checker cannot narrow through, and leaving them optional would let a genuine
    # None slip into the arithmetic under a later edit with only a type error to show for it.
    assert marks_row is not None, "have_marks implies the mark row exists"
    prev_close, close, prev_adj, adj = (float(marks_row[0]), float(marks_row[1]),
                                        float(marks_row[2]), float(marks_row[3]))
    prev_unadj, unadj = float(marks_row[4]), float(marks_row[5])

    proves_split = False
    split_obs: float | None = None
    split_res: float | None = None
    split_tol: float | None = None

    # ── the SPLIT leg: proved on the SPLIT factor `close/closeunadj` ────────────────────────────────
    # SHARADAR's `close` is ALREADY SPLIT-ADJUSTED; `closeunadj` is the traded price, so the split
    # factor lives here and CANNOT appear in `closeadj/close`. Measured: NFLX 10:1 0.1000 → 1.0000;
    # DD 1-for-3 3.0000 → 1.0000, with `closeadj/close` flat across both.
    if splits:
        split_factor_prev = prev_close / prev_unadj
        split_factor = close / unadj
        split_obs = split_factor / split_factor_prev
        split_res = abs(split_obs - split_mult)
        split_tol = tol.for_prices(prev_close, close, prev_unadj, unadj)
        if split_res > tol.absolute + split_tol * abs(split_mult):
            return result(ActionStatus.PROVEN_NOT_REFLECTED, klass,
                          f"the cumulative split factor moves {split_obs:.8f} where the declared "
                          f"split implies {split_mult:.8f} (residual {split_res:.3e} > tolerance)",
                          applicability=ActionApplicability.PRICE_ADJUSTMENT_EXPECTED,
                          split=split_mult, cash=cash_total, expected=split_mult,
                          observed=split_obs, abs_res=split_res,
                          rel_res=split_res / abs(split_mult) if split_mult else float("inf"),
                          rel_tol=split_tol, prices=prices)
        proves_split = True

    # ── the CASH leg: proved on the DIVIDEND factor, via the total-return relation ───────────────────
    # `split_mult` is deliberately ABSENT: `close` already carries split semantics, so
    # close_t/close_{t-1} contains no split jump and re-applying the multiplier double-counts it.
    #
    # ⚠ For a PURE split this leg is NOT evaluated as a conflict condition. A declared split says
    # nothing about the dividend factor, so a dividend-factor movement on that session is an UNDECLARED
    # DIVIDEND — a direction (b) finding against the dividend factor, not evidence that the split was
    # misapplied. Reporting it here would mislabel a correctly reflected split as unreflected, and
    # (worse) would let the split's own reconciliation stand in for a dividend that was never declared.
    if cash:
        expected = (close + cash_total) / prev_close
        observed = adj / prev_adj
        abs_res = abs(observed - expected)
        rel_res = abs_res / abs(expected) if expected else float("inf")
        rel_tol = tol.for_prices(prev_close, close, prev_adj, adj)
        if abs_res > tol.absolute + rel_tol * abs(expected):
            return result(ActionStatus.PROVEN_NOT_REFLECTED, klass,
                          f"the dividend factor moves {observed:.8f} where the declared distribution "
                          f"implies {expected:.8f} (residual {abs_res:.3e} > tolerance)",
                          applicability=ActionApplicability.PRICE_ADJUSTMENT_EXPECTED,
                          split=split_mult, cash=cash_total, expected=expected, observed=observed,
                          abs_res=abs_res, rel_res=rel_res, rel_tol=rel_tol, prices=prices)
        reason = override_reason or (REASON_SPLIT_AND_CASH_REFLECTED if splits
                                     else REASON_DIVIDEND_REFLECTED)
        return result(ActionStatus.PROVEN_REFLECTED, klass,
                      "the adjusted series matches the declared action within tolerance",
                      applicability=ActionApplicability.PRICE_ADJUSTMENT_EXPECTED, reason=reason,
                      split=split_mult, cash=cash_total, expected=expected, observed=observed,
                      abs_res=abs_res, rel_res=rel_res, rel_tol=rel_tol, prices=prices,
                      proves_dividend=True, proves_split=proves_split)

    # Reached only with a declared split and no cash leg: a group carrying neither would have been
    # refused earlier (no declared value, or a non-arithmetic class), so the split measurements exist.
    # Asserted rather than assumed — an unreachable branch that silently produced None residuals would
    # publish a PROVEN_REFLECTED check with no evidence in it.
    assert split_obs is not None and split_res is not None and split_tol is not None, (
        "the pure-split path requires the split leg to have been measured")
    return result(ActionStatus.PROVEN_REFLECTED, klass,
                  "the split factor matches the declared multiplier within tolerance",
                  applicability=ActionApplicability.PRICE_ADJUSTMENT_EXPECTED,
                  reason=override_reason or REASON_SPLIT_REFLECTED,
                  split=split_mult, cash=cash_total,
                  expected=split_mult, observed=split_obs, abs_res=split_res,
                  rel_res=(split_res / abs(split_mult)) if split_mult else None,
                  rel_tol=split_tol, prices=prices, proves_split=True)


def _apply_context_rulings(
    store: Any, checks: list[ActionCheck], *, groups: dict[tuple[str, date], list[tuple]],
    permatickers: dict[str, str], bounds: dict[str, tuple[date, date]],
    flagged: set[tuple[str, date]], disclosure: NonDecisionMADisclosure | None,
) -> list[ActionCheck]:
    """Re-resolve the two statuses that need whole-pass context, leaving every other check untouched.

    Only a check currently sitting at the DEFAULT may be moved: this pass can promote an unassessed
    action, never rescue one that was actively disproven or that conflicts.
    """
    #: (ticker, date) of every spinoff distribution PROVEN in this same pass — the parent condition.
    proven_spinoffs = {(c.ticker, c.action_date) for c in checks
                       if c.status is ActionStatus.PROVEN_REFLECTED
                       and c.reason_code in (REASON_SPINOFF_REFLECTED,
                                             REASON_SPINOFF_AND_SPLIT_REFLECTED)}
    out: list[ActionCheck] = []
    for c in checks:
        if c.status is not DEFAULT_ACTION_STATUS or c.permaticker is None:
            out.append(c)
            continue
        when = date.fromisoformat(c.action_date)
        items = groups.get((c.ticker, when), [])
        labels = {str(lb or "").strip().lower() for lb, _v, _cc in items}
        moved = (c.permaticker, when) in flagged

        # ── lineage-construction event for the CHILD of an already-reconciled distribution ─────────
        if _SPUNOFF_FROM_LABEL in labels and labels <= _LINEAGE_EVENT_LABELS:
            parent = [str(cc) for lb, _v, cc in items
                      if str(lb or "").strip().lower() == _SPUNOFF_FROM_LABEL and cc]
            span = bounds.get(c.ticker)
            # Every clause must hold, and each is POSITIVE evidence rather than an absence:
            #  * the child's series BEGINS exactly at the effective boundary (so no predecessor
            #    history was inherited and none is missing);
            #  * the declaring parent's distribution was PROVEN in this same pass;
            #  * the session shows no unexplained factor movement.
            begins_at_boundary = span is not None and span[0] == when
            parent_proven = bool(parent) and all((p, c.action_date) in proven_spinoffs
                                                 for p in parent)
            if begins_at_boundary and parent_proven and not moved:
                out.append(replace(
                    c, status=ActionStatus.PROVEN_LINEAGE_EVENT_NO_ADDITIONAL_PRICE_ADJUSTMENT,
                    verdict=AdjustmentVerdict.PROVEN,
                    applicability=ActionApplicability.NO_SINGLE_SECURITY_PRICE_ADJUSTMENT_EXPECTED,
                    reason_code=REASON_LINEAGE_EVENT_NO_ADJUSTMENT,
                    detail=(f"the child lineage begins exactly at the effective boundary "
                            f"{when.isoformat()} with no inherited predecessor history, the "
                            f"declaring parent {parent} had its distribution reconciled in this same "
                            f"verification, and neither governed factor shows an unexplained "
                            f"movement; the listing requires no additional price adjustment")))
                continue

        # ── acquired-side event disclosed as decision-irrelevant ───────────────────────────────────
        #
        # ⚠ A DISCLOSURE, NOT A PROOF. The decision-irrelevance finding is supplied from outside; the
        # ONE clause verifiable here is cross-checked and refused on mismatch.
        if disclosure is not None and disclosure.covers(c.permaticker, when):
            span = bounds.get(c.ticker)
            terminal = span is not None and span[1] <= when
            if not terminal:
                out.append(replace(
                    c, detail=(f"{c.detail} — a non-decision disclosure was supplied for this action "
                               f"but is REFUSED: the security still carries price history after "
                               f"{when.isoformat()}, so it is not economically terminal and would "
                               f"need successor linkage that has not been proven")))
                continue
            if moved:
                out.append(replace(
                    c, detail=(f"{c.detail} — a non-decision disclosure was supplied for this action "
                               f"but is REFUSED: the session carries an unexplained factor movement")))
                continue
            out.append(replace(
                c, status=ActionStatus.UNRESOLVED_NONDECISION_MA_SEMANTICS,
                reason_code=REASON_MA_DISCLOSED_NONDECISION,
                detail=(f"the acquired security's final economic treatment is NOT established by the "
                        f"vendor schema (no per-share consideration, exchange ratio or successor "
                        f"conversion term; `value` is aggregate transaction value in millions). It is "
                        f"economically terminal at {when.isoformat()} and was MEASURED to have no "
                        f"effect on the governed decision (assessment "
                        f"{disclosure.assessment_artifact_sha256[:16]}…). DISCLOSED LIMITATION, not "
                        f"proven reflection — this status does not satisfy readiness")))
            continue

        out.append(c)
    return out


def _extended_shape_terms(
    labels: set[str], canonical: list[tuple],
) -> tuple[bool, list[float], list[float], ActionClass, str | None, str] | None:
    """The bounded spinoff / ADR-ratio increment: turn a recognised extended shape into the SAME
    mechanical terms the ordinary legs already verify.

    Returns `None` when the group is not one of the two admitted shapes (so the ordinary path runs
    unchanged), or `(ok, splits, cash, action_class, reason_code, detail)`. `ok=False` means the shape
    was recognised but the authoritative record does NOT supply the mechanical term, which is a
    fail-closed refusal — never a licence to reconstruct the term from the series.

    ⚠ Nothing here reads a price. Every term comes from a declared field; whether the series agrees is
    decided afterwards by the unchanged dividend- and split-factor legs, at the governed tolerance.
    """
    def _values(label: str) -> list[float]:
        return [float(v) for lb, v, _c in canonical
                if str(lb or "").strip().lower() == label and v is not None]

    # ── ADR-ratio change ───────────────────────────────────────────────────────────────────────────
    if _ADR_RATIO_LABEL in labels and labels <= _ADR_SHAPE_LABELS:
        adr, spl = _values(_ADR_RATIO_LABEL), _values("split")
        if not spl:
            return (False, [], [], ActionClass.SPLIT, None,
                    "an ADR ratio change is declared with no same-date split multiplier, so the "
                    "direction of the ratio is not established by the record; deriving it from the "
                    "observed price movement is exactly the inference this rule refuses")
        if not adr:
            return (False, [], [], ActionClass.SPLIT, None,
                    "the ADR ratio row carries no declared value")
        if len({round(s, 10) for s in spl}) > 1:
            return (False, [], [], ActionClass.SPLIT, None,
                    f"multiple same-date split multipliers conflict: {spl}")
        # The two terms must agree. They are reciprocal statements of one transformation, so their
        # product is 1; anything else is a conflict between declared terms and is refused.
        if any(abs(a * spl[0] - 1.0) > _ADR_RECIPROCAL_TOLERANCE for a in adr):
            return (False, [], [], ActionClass.SPLIT, None,
                    f"the declared ADR ratio {adr} and split multiplier {spl[0]} are not reciprocal, "
                    f"so the same-date terms conflict and the transformation is not uniquely "
                    f"determined")
        return (True, [spl[0]], [], ActionClass.SPLIT, REASON_ADR_RATIO_REFLECTED,
                "ADR ratio change corroborated by a reciprocal same-date split multiplier")

    # ── spinoff distribution ───────────────────────────────────────────────────────────────────────
    if _SPINOFF_RATIO_LABEL in labels and labels <= _SPINOFF_SHAPE_LABELS:
        distributed = _values(_SPINOFF_VALUE_LABEL)
        if not distributed:
            return (False, [], [], ActionClass.SPINOFF_DISTRIBUTION, None,
                    "a spinoff is declared with no distribution value, so the record supplies only an "
                    "event label and a contraticker; the mechanical term is absent and must not be "
                    "inferred from price movements, relative market values or ticker relationships")
        spl = _values("split")
        if "split" in labels and not spl:
            return (False, [], [], ActionClass.SPINOFF_DISTRIBUTION, None,
                    "a same-date split is declared with no multiplier")
        klass = ActionClass.SPLIT_AND_CASH if spl else ActionClass.SPINOFF_DISTRIBUTION
        reason = REASON_SPINOFF_AND_SPLIT_REFLECTED if spl else REASON_SPINOFF_REFLECTED
        # `spinoffdividend.value` is the distributed value PER PARENT SHARE and composes through the
        # total-return relation exactly as a cash distribution does. `spinoff.value` is the SHARE-COUNT
        # ratio and is deliberately NOT consumed — see the note at the label constants.
        return (True, spl, distributed, klass, reason,
                "spinoff distribution value declared per parent share")

    return None


def _no_adjustment_rule(labels: set[str], marks_row: tuple | None, have_marks: bool,
                        bounds: tuple[date, date] | None, when: date, tol: Tolerance
                        ) -> tuple[ActionClass, str | None, str] | None:
    """The NAMED rules that establish `NO_SINGLE_SECURITY_PRICE_ADJUSTMENT_EXPECTED`.

    Returns `(action_class, reason_code, detail)`, a `reason_code` of None meaning "this rule applies
    but could not be CONFIRMED, so fail closed as insufficient", or None meaning "no rule applies".

    ⚠ Every rule that can be confirmed requires BOTH governed factors to be unchanged across the
    session. That is what turns an untestable claim about an event's economics into a measured property
    of the data: had a hidden consideration required a historical adjustment, a factor would have moved
    and the rule would not fire.
    """
    def factors_unchanged() -> bool:
        if not have_marks or marks_row is None:
            return False
        prev_close, close, prev_adj, adj, prev_unadj, unadj = marks_row
        return (_factor_unchanged(prev_adj, adj, prev_close, close, tol)          # dividend factor
                and _factor_unchanged(prev_close, close, prev_unadj, unadj, tol))  # split factor

    # ── bare `acquisitionof` — the acquirer's own row ───────────────────────────────────────────────
    #
    # ⚠⚠ `ACTIONS.value` ON THIS ROW IS THE REPORTED TRANSACTION VALUE IN MILLIONS. It is NOT a
    # per-share consideration, NOT an exchange ratio and NOT a split multiplier, and `value IS NULL` /
    # `IS NOT NULL` MUST NEVER determine whether an adjustment applies: 4,565 of 4,569 `acquisitionof`
    # rows carry a non-null value, so a null-check reads as meaningful and is not. The field-based
    # formulation of this rule was WITHDRAWN for exactly that reason — SHARADAR/ACTIONS has no
    # consideration or exchange-ratio field at all (its columns are only date, action, ticker, name,
    # value, contraticker, contraname), so the condition "no stock distribution or exchange ratio was
    # applied to the subject security" HAS NO FIELD TO TEST.
    #
    # ⚠ What this rule proves is NARROW and must not be overstated: it does NOT establish that no
    # consideration existed, that there was no stock consideration, or that the event had no economic
    # effect. The dataset cannot support any of those. It proves only that no mechanical historical-
    # price adjustment is expressed or required by the two governed factor systems.
    if labels == {_ACQUIRER_REFERENCE_LABEL}:
        if bounds is None or not (bounds[0] < when < bounds[1]):
            return (ActionClass.ACQUIRER_REFERENCE, None,
                    "the acquirer's permanent lineage is not observed both before and after the "
                    "action date, so continuation cannot be confirmed")
        if not factors_unchanged():
            return None          # a factor moved (or is unmeasurable) — fall through to the default
        return (ActionClass.ACQUIRER_REFERENCE, REASON_ACQUIRER_CONTINUES,
                "the subject is the ACQUIRER, no economically distinct sibling action is declared on "
                "this date, the permanent lineage continues across it, and NEITHER governed factor "
                "moves; no mechanical historical-price adjustment is expressed or required (this does "
                "NOT assert that no consideration existed)")

    # ── relationship metadata only ─────────────────────────────────────────────────────────────────
    if labels and labels <= _RELATIONSHIP_LABELS:
        if not factors_unchanged():
            return None
        return (ActionClass.RELATIONSHIP_METADATA, REASON_RELATIONSHIP_METADATA,
                "the group declares only relationship metadata identifying another security, and "
                "neither governed factor moves across the session")

    # ── initial-listing metadata only ──────────────────────────────────────────────────────────────
    if labels and labels <= _LISTING_LABELS:
        # A listing on the security's FIRST governed session has no prior history to adjust, and that
        # is a measurable fact rather than an exemption: the absence of a prior mark is CONFIRMED from
        # the store, not merely encountered.
        if bounds is not None and bounds[0] >= when:
            return (ActionClass.SYMBOL_TRANSITION, REASON_INITIAL_LISTING_NO_HISTORY,
                    "the listing is the security's first governed session, so no prior price history "
                    "exists that an adjustment could apply to")
        if not factors_unchanged():
            return None
        return (ActionClass.SYMBOL_TRANSITION, REASON_INITIAL_LISTING_METADATA,
                "the group declares only listing metadata, and neither governed factor moves across "
                "the session")

    # ── ticker change inside ONE permanent lineage ─────────────────────────────────────────────────
    #
    # The subject security keeps its permanent identity; only the symbol moves. A change that crosses
    # identities is NOT covered here — it never reaches this rule, because the group is resolved
    # against a single permaticker and a cross-identity change appears as a different lineage.
    if labels and labels <= _TICKER_CHANGE_LABELS:
        if not factors_unchanged():
            return None
        return (ActionClass.SYMBOL_TRANSITION, REASON_TICKER_CHANGE_SAME_LINEAGE,
                "the group declares only a ticker change within the same permanent lineage, and "
                "neither governed factor moves across the session")

    return None


#: How a terminal per-action status maps onto the WINDOW verdict `data_finality` consumes.
_WINDOW_VERDICT_FOR: dict[ActionStatus, AdjustmentVerdict] = {
    ActionStatus.PROVEN_REFLECTED: AdjustmentVerdict.PROVEN,
    ActionStatus.PROVEN_NO_PRICE_ADJUSTMENT_APPLICABLE: AdjustmentVerdict.PROVEN,
    ActionStatus.PROVEN_LINEAGE_EVENT_NO_ADDITIONAL_PRICE_ADJUSTMENT: AdjustmentVerdict.PROVEN,
    ActionStatus.PROVEN_NOT_REFLECTED: AdjustmentVerdict.INTEGRITY_STOP_CONFLICT,
    ActionStatus.SOURCE_CONFLICT: AdjustmentVerdict.INTEGRITY_STOP_CONFLICT,
    ActionStatus.NOT_PROVEN_INSUFFICIENT_DATA: AdjustmentVerdict.NOT_PROVEN_INSUFFICIENT_DATA,
    ActionStatus.NOT_PROVEN_UNSUPPORTED_SEMANTICS: AdjustmentVerdict.NOT_PROVEN_UNSUPPORTED_ACTION,
    # ⚠ A disclosed limitation still BLOCKS. It is separated from the default only so a reader can
    # tell "measured, disclosed and bounded" from "never assessed" — not so it can pass.
    ActionStatus.UNRESOLVED_NONDECISION_MA_SEMANTICS:
        AdjustmentVerdict.NOT_PROVEN_UNSUPPORTED_ACTION,
}


def _unexplained_factor_movements(
    store: Any, names: list[str], window_start: date, session_date: date, tol: Tolerance, *,
    permatickers: dict[str, str], explained_dividend: set[tuple[str, date]],
    explained_split: set[tuple[str, date]], limit: int,
) -> tuple[FactorMovementCensus, tuple[UnexplainedAdjustment, ...], set[tuple[str, date]]]:
    """Direction (b), run SEPARATELY on each governed factor.

        dividend factor   D = closeadj / close
        split factor      S = close / closeunadj

    A movement in D with no reconciled cash distribution on that (identity, session) is an undeclared
    distribution; a movement in S with no reconciled split is an UNDECLARED SPLIT — which the previous
    single-leg formulation could not detect at all, because `closeadj/prev_closeadj` divided by
    `close/prev_close` is exactly `D_t/D_{t-1}`, and a split never changes D.

    Suppression is FACTOR-SPECIFIC and keyed by PERMANENT IDENTITY: a reconciled dividend suppresses
    only the dividend leg, on that lineage, on that session.
    """
    ph = ",".join("?" * len(names))
    rows = _query(store,
                  f"WITH s AS (SELECT ticker, date, close, closeadj, closeunadj, "
                  f"  lag(close) OVER (PARTITION BY ticker ORDER BY date) AS pclose, "
                  f"  lag(closeadj) OVER (PARTITION BY ticker ORDER BY date) AS padj, "
                  f"  lag(closeunadj) OVER (PARTITION BY ticker ORDER BY date) AS punadj "
                  f"  FROM sep WHERE ticker IN ({ph}) AND date BETWEEN ? AND ?) "
                  f"SELECT ticker, date, close, closeadj, closeunadj, pclose, padj, punadj FROM s "
                  f"WHERE pclose > 0 AND padj > 0 AND close > 0 AND closeadj > 0 "
                  f"ORDER BY ticker, date",
                  [*names, window_start, session_date])

    div_count = split_count = combined = 0
    pairs = 0
    unresolved = 0
    identities: set[str] = set()
    examples: list[UnexplainedAdjustment] = []
    #: Every (identity, session) carrying an unexplained movement — the full set, not just the bounded
    #: examples, because downstream rules must be able to ask "did THIS session move?" for any session.
    flagged: set[tuple[str, date]] = set()

    for ticker, when, close, adj, unadj, pclose, padj, punadj in rows:
        pairs += 1
        perma = permatickers.get(ticker)
        if perma is None:
            # Fails closed: an unresolvable identity cannot be suppressed by anything, because a
            # suppression keyed on its symbol could belong to a different issuer entirely.
            unresolved += 1
        else:
            identities.add(perma)

        # dividend factor D = closeadj/close, expressed as the departure of the adjusted one-day ratio
        # from the raw one-day ratio (algebraically D_t/D_{t-1}); kept in this form because it is the
        # formulation the existing evidence and the measured tolerance plateau were built on.
        observed = adj / padj
        raw = close / pclose
        div_residual = abs(observed - raw)
        div_tol = tol.for_prices(pclose, close, padj, adj)
        div_moved = div_residual > tol.absolute + div_tol * abs(raw)

        # split factor S = close/closeunadj
        split_moved = False
        split_ratio = None
        split_residual = 0.0
        split_tol = tol.for_prices(pclose, close, punadj, unadj)
        if all(x and x > 0 for x in (punadj, unadj)):
            split_ratio = (close / unadj) / (pclose / punadj)
            split_residual = abs(split_ratio - 1.0)
            split_moved = split_residual > tol.absolute + split_tol

        key = (perma, when) if perma is not None else None
        div_unexplained = div_moved and (key is None or key not in explained_dividend)
        split_unexplained = split_moved and (key is None or key not in explained_split)
        if not (div_unexplained or split_unexplained):
            continue

        if perma is not None:
            flagged.add((perma, when))
        div_ratio = observed / raw if raw else None
        if div_unexplained and split_unexplained:
            combined += 1
            kind, residual, rel_tol = FactorKind.COMBINED, max(div_residual, split_residual), div_tol
        elif div_unexplained:
            div_count += 1
            kind, residual, rel_tol = FactorKind.DIVIDEND, div_residual, div_tol
        else:
            split_count += 1
            kind, residual, rel_tol = FactorKind.SPLIT, split_residual, split_tol

        if len(examples) < limit:
            examples.append(UnexplainedAdjustment(
                ticker=ticker, permaticker=perma, session_date=when.isoformat(), factor=kind,
                observed_ratio=observed, raw_ratio=raw, absolute_residual=residual,
                relative_tolerance=rel_tol, dividend_factor_ratio=div_ratio,
                split_factor_ratio=split_ratio))

    census = FactorMovementCensus(
        undeclared_dividend_factor_changes=div_count,
        undeclared_split_factor_changes=split_count,
        combined_or_ambiguous_changes=combined,
        explained_dividend_factor_sessions=len(explained_dividend),
        explained_split_factor_sessions=len(explained_split),
        session_pairs_examined=pairs, identities_examined=len(identities),
        unresolved_identity_count=unresolved)
    return census, tuple(examples), flagged
