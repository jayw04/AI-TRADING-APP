"""MDQ-001 §7.1 admissibility adjudication — offline, strictly read-only.

``CaptureStore.verify`` proves **integrity**: the manifested bytes are the
frozen bytes and no stray file was added. Registration §4 "Admissible corpus"
(and plan v0.8 §7.1) additionally require **sufficiency** — that the partition
contains the observations it was supposed to contain. The two are not the same
question, and nothing else in the repo computes the second: at the frozen
60-second cadence the abort-after-30-consecutive-failed-cycles rule permits a
~30-minute hole in a partition that freezes normally and passes ``verify``
(the GAPPER v1 failure mode — records present, sufficiency absent; plan §4.9).

This module evaluates each §7.1 condition mechanically and emits
PASS / FAIL / NOT_EVALUABLE per condition, with the observed value beside the
frozen expected value and the document each frozen value came from.

Discipline:

  * **Read-only.** Nothing here opens a file for writing, creates a directory,
    or mutates a byte under the capture root. The corpus is immutable governed
    evidence; an adjudicator that can write is an adjudicator that can launder.
    There is deliberately no ``--repair``/``--fix`` affordance.
  * **Offline.** No network, no Alpaca SDK, no credentials. MDQ-001 is an
    offline read-only consumer of frozen partitions (registration §7, control 1
    of the adopted Option 2A).
  * **Fail closed.** NOT_EVALUABLE is a first-class outcome and is never
    coerced to PASS or to FAIL. A partition is ADMISSIBLE only when every
    condition PASSes; anything else is not admissible, with the reason stated.

**Owner ruling 2026-08-18 (denominator).** The registration froze
``expected_cycles`` as a FORMULA over an unbound ``session_scope``; this module
previously reported both defensible readings and returned NOT_EVALUABLE. The
owner has now ruled, and the ruling is implemented here verbatim: the
04:00-16:00 ET interval is the EOD one-minute BAR CENSUS scope, **not** the
sampler denominator (using the bar window as the sampler denominator would
mechanically fail every otherwise healthy sampler partition). The sampler
denominator is the HALF-OPEN grid ``09:25 ET <= t < official NYSE close`` at the
frozen 60s cadence — 395 slots on a normal 16:00 close, 215 on a 13:00 early
close, 0 on a non-session. The 98% floor and the 10-minute maximum contiguous
gap are UNCHANGED. See :data:`OWNER_RULING_DENOMINATOR`.

The ruling removes exactly ONE source of NOT_EVALUABLE — the denominator (and
the scope ambiguity that hung off it). Every other unresolved value keeps its
honest status; see :data:`UNRATIFIED_AFTER_RULING`.

Every frozen value used is listed in :data:`THRESHOLD_SOURCES` and echoed into
the report, so the output can be pasted into the governing program-start record
without a reader having to trust this module's memory of the registration.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app.research.capture.collector import (
    CAPTURE_MODE_EOD_BARS,
    CAPTURE_MODE_SAMPLER,
)
from app.research.capture.identity import AcquisitionPins
from app.research.capture.store import (
    FEEDS,
    MANIFEST_SCHEMA,
    CaptureStore,
    PartitionRef,
)

ET = ZoneInfo("America/New_York")

ADMISSIBILITY_SCHEMA = "mdq-admissibility-report/1"
ADMISSIBILITY_VERSION = "mdq-admissibility/0.1.0"

REGISTRATION_DOC = "docs/design/MDQ-001_Registration_v1_0_DRAFT.md"
PLAN_DOC = "docs/Strategies/AlgoTraderPlus_v1_4_1_ImplementationPlan_v0_8.md"

# --- frozen values -----------------------------------------------------------
#
# Taken from the SIGNED registration §8 block (and its ratified §8.1 addendum).
# Where a value is NOT ratified anywhere, it is labelled as a tool default here
# and in THRESHOLD_SOURCES — never silently promoted to a frozen threshold.

MIN_COMPLETENESS = 0.98
MAX_CONTIGUOUS_GAP_MINUTES = 10.0
CADENCE_SECONDS = 60
MAX_CONSECUTIVE_FAILED_CYCLES = 30
REGISTRATION_SIGNOFF_DATE = date(2026, 8, 17)
BAR_WINDOW_ET: tuple[time, time] = (time(4, 0), time(16, 0))

# RULED 2026-08-18. The sampler window's start is now a frozen definition, not
# a deployment fact: `sampler_start = 09:25 America/New_York`. The END is the
# official NYSE close for that session, EXCLUSIVE, and remains an input because
# the market calendar — not this module — controls early closes and non-trading
# days (see THRESHOLD_SOURCES['session_close']: no calendar is importable from
# inside this package).
SAMPLER_START_ET = time(9, 25)

# The ruled grid is HALF-OPEN: slots are `sampler_start + k*cadence` for every k
# with `sampler_start <= slot < sampler_end`. The endpoint is EXCLUDED — the
# close itself is not a slot. On a normal session that is 395 slots, not 396;
# the off-by-one is worth a percentage point of completeness, which is why the
# boundary is spelled out here and asserted in the tests.
SLOT_GRID_IS_HALF_OPEN = True

OWNER_RULING_DATE = date(2026, 8, 18)
OWNER_RULING_DENOMINATOR = (
    "OWNER RULING 2026-08-18 (MDQ-001 expected_cycles denominator). Verbatim: "
    "'The 04:00-16:00 interval is the EOD one-minute bar census scope, not the "
    "sampler denominator. Using the bar window as the sampler denominator would "
    "mechanically make every otherwise healthy sampler partition fail "
    "completeness.' Frozen definition: sampler_start = 09:25 America/New_York; "
    "sampler_end = official NYSE close for that session, EXCLUSIVE; cadence = 60 "
    "seconds; expected_cycles = count of scheduled cadence slots t such that "
    "sampler_start <= t < sampler_end. => 395 on a normal 16:00 ET close, 215 on "
    "a 13:00 ET early close, 0 on holidays/non-sessions. The market calendar "
    "controls early closes and non-trading days. The 98% completeness floor and "
    "the 10-minute maximum contiguous gap are UNCHANGED and are not weakened."
)

# The ruled scheduling model. The collector is being moved to FIXED-RATE
# scheduling (absolute monotonic deadline per slot, no burst/catch-up, close
# checked BEFORE the cycle, and a persisted scheduled_slot_ts/slot_index per
# cycle) under a separate owner ruling. Under fixed-rate the close is tested
# before a cycle fires, so no cycle can legitimately land past the close and no
# grace is owed. Legacy fixed-DELAY partitions (the sleep came AFTER the sample,
# so `now >= close` was tested only after taking one more sample) are owed
# exactly one cadence period. Grace is loop semantics, never a relaxed
# threshold, and which one applies is decided by evidence in the partition
# itself: a partition carrying the fixed-rate slot fields gets no grace.
FIXED_RATE_CLOSE_GRACE_PERIODS = 0
LEGACY_FIXED_DELAY_CLOSE_GRACE_PERIODS = 1
SCOPE_GRACE_PERIODS = LEGACY_FIXED_DELAY_CLOSE_GRACE_PERIODS

# Field names the fixed-rate collector persists per cycle. Counting observed
# cycles against the frozen slot grid via these is the faithful measure (owner
# ruling); wall-clock spacing is the fallback for partitions that predate them.
SLOT_TS_FIELD = "scheduled_slot_ts"
SLOT_INDEX_FIELD = "slot_index"

# --- review disposition + holdout arithmetic (owner rulings 2026-08-18) ------
#
# Ratified §8.1 supersedes the registration's stale §4 'keep if ANY K criterion
# is met': the GO floor is >=2 of K1-K6 both EVALUABLE and PASS. The owner also
# closed the hole the ratified text left open (>=2 evaluable, exactly 1 PASS).
GO_FLOOR_PASSES = 2
GO_FLOOR_EVALUABLE = 2
CRITERIA = ("K1", "K2", "K3", "K4", "K5", "K6")

# Half-open, date-based, no weekend/holiday sliding.
REVIEW_WINDOW_DAYS = 60
PERIOD_HOLDOUT_OFFSET_DAYS = 48
PERIOD_HOLDOUT_DAYS = REVIEW_WINDOW_DAYS - PERIOD_HOLDOUT_OFFSET_DAYS  # 12
HOLDOUT_SYMBOL_COUNT = 10

# sha256 of the LF-normalised bytes of the frozen universe-symbols file. The
# registration §8 block freezes the LF sha (the box checks out LF); a Windows
# working copy stores CRLF, so hashing raw bytes there would spuriously fail.
# Normalising line endings — and only line endings — keeps the frozen value
# reproducible on both hosts (cf. the .gitattributes byte-custody rule).
UNIVERSE_SYMBOLS_FILE_SHA256_LF = "0c57bd71c0b73565328ec27036c6573f11b87594acb49ca461458a7d947f88d4"

# Derived from that file by the collector's own rule
# (sha256(json.dumps(sorted(universe)))); cross-checked against the file at
# runtime rather than trusted, so a tampered config cannot pass by matching
# only itself.
EXPECTED_UNIVERSE_SHA256 = "a022e399e216f16328eaecd809126951f6658cb09351281fa02187a0a6faf563"

# NOT RATIFIED — see THRESHOLD_SOURCES. Used only to judge whether the observed
# inter-cycle spacing is consistent with the frozen 60s cadence.
CADENCE_TOLERANCE_SECONDS = 5.0

THRESHOLD_SOURCES: dict[str, str] = {
    "min_completeness": (
        f"{REGISTRATION_DOC} §8 sign-off block, line 'Partition completeness: "
        f"[X] >= 98% observed/expected cycles per partition per feed' "
        f"(proposed in {PLAN_DOC} §4.9; ACCEPTED as proposed, signed 2026-08-17)"
    ),
    "max_contiguous_gap_minutes": (
        f"{REGISTRATION_DOC} §8 sign-off block, same line: "
        f"'max contiguous gap 10 min' ({PLAN_DOC} §4.9)"
    ),
    "feed_error_denominator_only": (
        f"{REGISTRATION_DOC} §8 'feed_error counts toward the denominator only'; "
        f"also §4 'Admissible corpus' and {PLAN_DOC} §4.9"
    ),
    "cadence_seconds": (
        f"{REGISTRATION_DOC} §8 'Sampler cadence/retry: [X] 60s cadence ...'; "
        f"§4 K6 note: 'The sampling cadence is frozen identity (§8)'"
    ),
    "max_consecutive_failed_cycles": (
        f"{REGISTRATION_DOC} §8 'abort after 30 consecutive failed cycles' "
        f"(reported here as a diagnostic; the abort is collector behaviour, not a gate)"
    ),
    "bar_window_et": (
        f"{REGISTRATION_DOC} §7 Phase A ('04:00-16:00 ET - premarket + RTH'); "
        f"{PLAN_DOC} §4.1 'bar session_scope = 04:00-16:00 ET' (RESOLVED, committed)"
    ),
    "sampler_start_et": (
        "RULED 2026-08-18 — no longer an open question. The owner ruling freezes "
        "'sampler_start = 09:25 America/New_York' as the denominator's left edge. "
        "It agrees with the deployment fact it supersedes (systemd "
        "OnCalendar=Mon..Fri 09:25:00 America/New_York for mdq-sample, "
        "AlgoTraderPlus_v1_4_1_ImplementationPlan_v0_9.md §3.3). Still overridable "
        "as an input so an adjudication can be re-run against a differently-ruled "
        "start, but the default is now the ruled value, not a tool guess. "
        f"{OWNER_RULING_DENOMINATOR}"
    ),
    "expected_cycles_denominator": (
        "RESOLVED BY OWNER RULING 2026-08-18. Registration §4 'Admissible corpus' "
        "defined 'expected_cycles = f(session_scope, cadence, market calendar)' "
        "and §8 froze only the threshold ('[X] >= 98% observed/expected cycles "
        "per partition per feed, max contiguous gap 10 min') without ever binding "
        "session_scope. The ruling binds it to the sampler window and explicitly "
        "rejects the 04:00-16:00 ET bar-census window as the sampler "
        f"denominator. {OWNER_RULING_DENOMINATOR}"
    ),
    "expected_cycles_grid": (
        "OWNER RULING 2026-08-18, HALF-OPEN grid: expected_cycles is the number "
        "of slots sampler_start + k*cadence lying in [sampler_start, "
        "sampler_end). Equivalently ceil(span / cadence): a 395-minute span at "
        "60s is 395 slots, NOT 396 — the close is not itself a slot. The 396 "
        "figure in this tool's earlier arithmetic was the inclusive-endpoint "
        "reading and is superseded; it inflated the denominator by one slot."
    ),
    "census_window_diagnostic": (
        "OWNER RULING 2026-08-18: the 04:00-16:00 ET interval is the EOD "
        "one-minute BAR CENSUS scope (registration §7 Phase A; plan §4.1) and is "
        "NOT the sampler denominator. It remains computable as an explicitly "
        "requested DIAGNOSTIC only, is labelled as such in every record, and is "
        "never scored against the completeness floor or the gap rule."
    ),
    "close_grace_periods": (
        "Loop semantics, not a threshold. Under the ruled FIXED-RATE collector "
        "the close is checked BEFORE each cycle, so no cycle may land at or past "
        "the close and the grace is 0. Legacy fixed-DELAY partitions slept AFTER "
        "sampling and are owed exactly one cadence period. Which applies is "
        "decided by evidence in the partition (presence of the fixed-rate slot "
        "fields), never by a flag."
    ),
    "observed_cycle_method": (
        "OWNER RULING 2026-08-18 (fixed-rate collector): where the collector "
        f"persists {SLOT_TS_FIELD!r}/{SLOT_INDEX_FIELD!r} per cycle, observed "
        "cycles are counted against the frozen slot grid rather than inferred "
        "from wall-clock spacing — the more faithful measure. Partitions that "
        "predate the field fall back to distinct-cycle_ts counting, and the "
        "report SAYS SO; the two methods are never silently mixed within one "
        "partition."
    ),
    "session_close": (
        "EXPLICIT REQUIRED INPUT — resolved per session from the NYSE calendar by "
        "the CALLER (scripts/mdq_collector.py _session_close_utc, "
        "pandas_market_calendars), the same source the collector itself stops "
        "sampling on. This module deliberately holds NO holiday or early-close "
        "table of its own and imports no calendar: app/market/session.py exists "
        "and would otherwise serve, but the capture package is structurally "
        "forbidden from importing any foreign app.* module (plan v0.3 §4.5, "
        "enforced by tests/research/test_mdq_capture.py), and a third-party "
        "calendar import would break this module's stdlib-only posture. When the "
        "close is absent the cycle-count conditions are NOT_EVALUABLE — a "
        "non-session and an unavailable calendar are indistinguishable from "
        "inside a partition, so both fail closed. The provenance the caller "
        "states is echoed into the record as inputs.session_close_source."
    ),
    "registration_signoff_date": (
        f"{REGISTRATION_DOC} §8 'Registered by / date: Jay Wang (owner) - 2026-08-17'. "
        f"§4 'Admissible corpus': a partition enters the corpus only if 'captured "
        f"after §8 sign-off'. Only the DATE is frozen, not a time of day."
    ),
    "credential_fingerprint": (
        "app/research/capture/identity.py AcquisitionPins.key_fingerprint "
        f"('b56421a28128', owner-authorized re-pin 2026-08-18 superseding "
        f"'5b6f39e5198d' -- key rotated on the box 2026-08-17 21:32 EDT, same "
        f"broker account); corroborated by {REGISTRATION_DOC} §7 probe table "
        f"(ALPACA_PAPER_6 = workbench account 7) and §2 P-2"
    ),
    "account_number": (
        "app/research/capture/identity.py AcquisitionPins.account_number "
        f"('PA3BGKRLH2AP'); corroborated by {REGISTRATION_DOC} §7 probe table "
        f"and the Entitlement-date row of the header table"
    ),
    "universe_symbols_file_sha256": (
        f"{REGISTRATION_DOC} §8 'Phase-A capture universe' block: "
        f"apps/backend/config/mdq_phase_a_universe_symbols.json "
        f"sha256 {UNIVERSE_SYMBOLS_FILE_SHA256_LF} (LF bytes)"
    ),
    "universe_sha256": (
        "DERIVED at runtime from the frozen symbols file by the collector's own "
        "rule, scripts/mdq_collector.py _universe_sha = "
        "sha256(json.dumps(sorted(universe))); the recorded expectation "
        f"{EXPECTED_UNIVERSE_SHA256} is cross-checked against that derivation"
    ),
    "no_provenance_label": (
        f"{REGISTRATION_DOC} §4 'Pre-registration quarantine' — any capture made "
        f"before §8 sign-off carries the manifest label PRE_REGISTRATION_SMOKE and "
        f"is INADMISSIBLE; {PLAN_DOC} §7.2 first bullet. A governed partition "
        f"carries NO label at all (scripts/mdq_collector.py emits 'label' only "
        f"when --label is passed)."
    ),
    "capture_modes": (
        f"{REGISTRATION_DOC} §7 Phase A: 'paired latest-quote sampling + "
        f"end-of-session 1-minute bars'; mode literals from "
        f"app/research/capture/collector.py"
    ),
    "manifest_schema": "app/research/capture/store.py MANIFEST_SCHEMA",
    "verdict_table": (
        "OWNER RULING 2026-08-18. The registration's stale §4 wording ('keep if "
        "ANY K criterion is met') is SUPERSEDED by the ratified §8.1 floor (at "
        "least 2 of K1-K6 both EVALUABLE and PASS), and the ruling additionally "
        "closes the hole §8.1 left open (2+ evaluable, exactly 1 PASS was "
        "undefined). Ruled table: 2+ evaluable and 2+ PASS => GO; 2+ evaluable "
        "and 0 PASS => STOP; fewer than 2 evaluable => HOLD with one stated "
        "extension; 2+ evaluable and exactly 1 PASS => HOLD with one stated "
        "extension. A NOT_EVALUABLE criterion neither passes nor fails and never "
        "contributes to the GO floor."
    ),
    "holdout_window": (
        "OWNER RULING 2026-08-18, half-open and date-based: review_start_date = "
        "session_date of the first admissible governed capture; "
        "review_end_exclusive = review_start_date + 60 calendar days; "
        "period_holdout_start = review_start_date + 48 calendar days; the period "
        "holdout is session_date >= period_holdout_start AND session_date < "
        "review_end_exclusive. Review window = offsets 0-59; holdout = offsets "
        "48-59, exactly 12 CALENDAR dates. The boundary is NOT slid for weekends "
        "or holidays — those simply contain no trading partition. Sliding would "
        "turn 'final 20%' into 'final 12 trading sessions', a different rule."
    ),
    "exploration_embargo": (
        "OWNER RULING 2026-08-18: exploratory_access_allowed = symbol NOT IN "
        "holdout_symbols AND session_date < period_holdout_start. The 10 holdout "
        "symbols are quarantined for the WHOLE window; every symbol is "
        "quarantined during the final 12 calendar dates. Evaluated as a pure "
        "predicate — no filesystem, no network, no corpus access."
    ),
    "cadence_tolerance_seconds": (
        "TOOL DEFAULT — NOT RATIFIED ANYWHERE. The registration freezes the 60s "
        "cadence as identity but freezes no tolerance for observed inter-cycle "
        "spacing (REST latency plus sleep(60) make exact 60.000s spacing "
        "impossible). 5.0s is this tool's default and is reported as such. "
        "OWNER QUESTION."
    ),
    "collector_code_identity": (
        f"{PLAN_DOC} §7.1 'collector code identity is approved for the period' — "
        f"NO approved version/sha is frozen in the registration or in any "
        f"program-start record that exists yet, so this condition is "
        f"NOT_EVALUABLE unless an approved version is supplied explicitly. "
        f"OWNER QUESTION."
    ),
}


# Values this tool must still not present as frozen thresholds. The 2026-08-18
# ruling closed the first two entries of the previous list (the sampler start and
# the expected_cycles denominator); the rest keep their honest status, and one
# new item is surfaced BY the ruling rather than settled by it.
UNRATIFIED_AFTER_RULING: dict[str, str] = {
    "cadence_tolerance_seconds": (
        "STILL UNRATIFIED. The registration freezes the 60s cadence as identity "
        "but no tolerance for observed inter-cycle spacing. 5.0s is this tool's "
        "default. The move to fixed-rate scheduling changes what the measurement "
        "MEANS (spacing becomes grid-anchored rather than work-dependent) without "
        "ratifying a number, so this stays an owner question."
    ),
    "approved_collector_code_identity": (
        "STILL UNRATIFIED. Plan §7.1 requires 'collector code identity is "
        "approved for the period' but no approved version/sha is frozen in the "
        "registration or in any program-start record that exists yet. The "
        "condition is NOT_EVALUABLE unless an approved version is supplied. The "
        "pending fixed-rate collector change makes pinning this MORE urgent, not "
        "less: partitions either side of it are not the same instrument."
    ),
    "session_close_calendar_artifact": (
        "SURFACED BY THE RULING, NOT SETTLED BY IT. The ruling says 'official "
        "NYSE close' and 'the market calendar controls early closes and "
        "non-trading days' without pinning WHICH calendar artifact is "
        "authoritative or how its version is recorded. This module holds no "
        "calendar and takes the close as an explicit input; the caller's source "
        "is echoed into the record but is not verified against anything."
    ),
}


class Denominator(StrEnum):
    """Which ``session_scope`` binds ``expected_cycles`` — RULED 2026-08-18.

    The registration froze a FORMULA over an unbound ``session_scope``:

        "Define ``expected_cycles = f(session_scope, cadence, market calendar)``"
        — registration §4 "Admissible corpus"

    and §8 froze only the THRESHOLD. This module used to report both defensible
    readings and refuse to pick. The owner has ruled:

    * :attr:`SAMPLER_WINDOW` — ``09:25 ET <= t < official NYSE close`` at the
      frozen 60s cadence. **This is the admissibility denominator.** It is the
      only value :data:`RULED_DENOMINATOR` may take.
    * :attr:`CENSUS_WINDOW` — 04:00-16:00 ET, the EOD one-minute BAR CENSUS
      scope (registration §7 Phase A; plan §4.1). The ruling states plainly that
      this is *not* the sampler denominator, because using the bar window as the
      sampler denominator "would mechanically make every otherwise healthy
      sampler partition fail completeness". It survives only as an explicitly
      requested DIAGNOSTIC, labelled as such wherever it appears, never scored.

    Asking for :attr:`CENSUS_WINDOW` as the governing denominator is therefore
    not a choice this module honours; it is served as the diagnostic it now is,
    with the reinterpretation stated in the record.
    """

    CENSUS_WINDOW = "census_window"
    SAMPLER_WINDOW = "sampler_window"


# The single admissible denominator (owner ruling 2026-08-18). Not a default a
# caller may override into the census window — see :func:`resolve_denominator`.
RULED_DENOMINATOR = Denominator.SAMPLER_WINDOW

DENOMINATOR_ROLE_GOVERNING = (
    "ADMISSIBILITY DENOMINATOR (owner ruling 2026-08-18) — scored against the "
    "98% completeness floor and the 10-minute maximum contiguous gap"
)
DENOMINATOR_ROLE_DIAGNOSTIC = (
    "DIAGNOSTIC ONLY — NOT the admissibility denominator. The owner ruling "
    "2026-08-18 assigns the 04:00-16:00 ET window to the EOD bar census and "
    "excludes it from the sampler denominator. Reported on explicit request so "
    "the bar-census arithmetic is visible; never scored."
)


def resolve_denominator(
    requested: Denominator | None, *, census_diagnostic: bool = False
) -> tuple[Denominator, bool, str]:
    """Apply the ruling to whatever a caller asked for.

    Returns ``(governing, include_census_diagnostic, note)``. The governing
    denominator is always :data:`RULED_DENOMINATOR`; a request for the census
    window is reinterpreted as a request for the census DIAGNOSTIC, and the
    reinterpretation is returned so it can be recorded rather than hidden.
    """
    if requested is Denominator.CENSUS_WINDOW:
        return (
            RULED_DENOMINATOR,
            True,
            "census_window was requested as the governing denominator; the owner "
            "ruling 2026-08-18 assigns that window to the EOD bar census and "
            "forbids it as the sampler denominator, so it is served as an "
            "explicitly-requested DIAGNOSTIC and the sampler window governs",
        )
    if requested is None:
        return (
            RULED_DENOMINATOR,
            census_diagnostic,
            "no denominator supplied; the ruled sampler-window denominator "
            "applies by default (owner ruling 2026-08-18)",
        )
    return (
        RULED_DENOMINATOR,
        census_diagnostic,
        "sampler_window requested and ruled — the two agree",
    )


class Outcome(StrEnum):
    """A condition's disposition.

    NOT_EVALUABLE is first class: it is neither a pass nor a failure, and is
    never coerced into either (registration §4 applies exactly this language to
    K2/K4/K5/K6; it is applied here to the §7.1 conditions).
    """

    PASS = "PASS"
    FAIL = "FAIL"
    NOT_EVALUABLE = "NOT_EVALUABLE"


class Verdict(StrEnum):
    ADMISSIBLE = "ADMISSIBLE"
    NOT_ADMISSIBLE = "NOT_ADMISSIBLE"
    UNDETERMINED = "UNDETERMINED"


EXIT_ADMISSIBLE = 0
EXIT_NOT_ADMISSIBLE = 1
EXIT_UNDETERMINED = 2


@dataclass(frozen=True)
class ConditionResult:
    """One §7.1 condition: observed value, frozen expectation, and provenance."""

    condition: str
    outcome: Outcome
    observed: Any
    expected: Any
    detail: str
    source: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "condition": self.condition,
            "outcome": str(self.outcome),
            "observed": self.observed,
            "expected": self.expected,
            "detail": self.detail,
            "source": self.source,
        }


@dataclass(frozen=True)
class CycleStats:
    """What the quote sampler actually left behind in ``quotes/samples.jsonl``."""

    observed_cycles: int = 0
    error_cycles: int = 0
    empty_cycles: int = 0
    partial_cycles: int = 0
    total_cycle_slots_seen: int = 0
    max_consecutive_error_cycles: int = 0
    malformed_lines: int = 0
    torn_tail: bool = False
    unparsable_cycle_ts: int = 0
    symbols_seen: tuple[str, ...] = ()
    first_ts: datetime | None = None
    last_ts: datetime | None = None
    median_spacing_seconds: float | None = None
    observed_ts: tuple[datetime, ...] = ()
    present: bool = False
    # Fixed-rate scheduling evidence, parallel to ``observed_ts``. ``None`` in a
    # position means that cycle carried no such field — the pre-fixed-rate
    # collector wrote neither, so both tuples are all-None for legacy partitions.
    observed_slot_ts: tuple[datetime | None, ...] = ()
    observed_slot_index: tuple[int | None, ...] = ()
    slot_field_cycles: int = 0
    slot_field_names: tuple[str, ...] = ()
    slot_field_conflicts: int = 0


@dataclass(frozen=True)
class ReadingResult:
    """Completeness and gap over ONE session-scope window.

    Exactly one reading per feed is ever SCORED — the ruled sampler window. A
    census-window reading is produced only on explicit request and carries
    :data:`DENOMINATOR_ROLE_DIAGNOSTIC` in :attr:`role` so it cannot be mistaken
    for an admissibility number by anyone reading the record.
    """

    denominator: Denominator
    role: str
    window_start: datetime
    window_end: datetime
    expected_cycles: int
    observed_cycles: int
    completeness: float
    max_gap_minutes: float
    meets_min_completeness: bool
    meets_max_gap: bool
    scope_note: str
    count: ObservedCount

    @property
    def is_governing(self) -> bool:
        return self.denominator is RULED_DENOMINATOR

    def as_dict(self) -> dict[str, Any]:
        return {
            "denominator": str(self.denominator),
            "role": self.role,
            "window_start_et": self.window_start.astimezone(ET).isoformat(),
            "window_end_et_exclusive": self.window_end.astimezone(ET).isoformat(),
            "window_span_seconds": (self.window_end - self.window_start).total_seconds(),
            "expected_cycles": self.expected_cycles,
            "observed_cycles": self.observed_cycles,
            "observed_cycle_method": str(self.count.method),
            "observed_cycle_method_note": self.count.note,
            "numerator_diagnostics": self.count.as_dict(),
            "completeness": self.completeness,
            "max_contiguous_gap_minutes": round(self.max_gap_minutes, 3),
            "meets_min_completeness": self.meets_min_completeness,
            "meets_max_contiguous_gap": self.meets_max_gap,
            "scope_note": self.scope_note,
        }


@dataclass
class FeedAssessment:
    feed: str
    session: date
    conditions: list[ConditionResult] = field(default_factory=list)
    stats: CycleStats = field(default_factory=CycleStats)
    readings: dict[str, ReadingResult] = field(default_factory=dict)
    governing_denominator: Denominator | None = None
    derivation: dict[str, Any] = field(default_factory=dict)

    @property
    def governing_reading(self) -> ReadingResult | None:
        if self.governing_denominator is None:
            return None
        return self.readings.get(str(self.governing_denominator))

    @property
    def outcome(self) -> Verdict:
        return roll_up(self.conditions)

    def as_dict(self) -> dict[str, Any]:
        return {
            "feed": self.feed,
            "session": self.session.isoformat(),
            "verdict": str(self.outcome),
            "observed_cycles": self.stats.observed_cycles,
            "governing_denominator": (
                str(self.governing_denominator) if self.governing_denominator else None
            ),
            "governing_denominator_role": DENOMINATOR_ROLE_GOVERNING,
            "observed_cycle_method": (
                str(self.governing_reading.count.method) if self.governing_reading else None
            ),
            "completeness_by_reading": {k: v.as_dict() for k, v in sorted(self.readings.items())},
            "expected_cycles_derivation": self.derivation,
            "cycle_diagnostics": {
                "error_cycles": self.stats.error_cycles,
                "empty_cycles": self.stats.empty_cycles,
                "partial_cycles": self.stats.partial_cycles,
                "cycle_slots_seen": self.stats.total_cycle_slots_seen,
                "max_consecutive_error_cycles": self.stats.max_consecutive_error_cycles,
                "malformed_lines": self.stats.malformed_lines,
                "torn_tail_tolerated": self.stats.torn_tail,
                "unparsable_cycle_ts": self.stats.unparsable_cycle_ts,
                "median_spacing_seconds": self.stats.median_spacing_seconds,
                "first_cycle_ts": _iso(self.stats.first_ts),
                "last_cycle_ts": _iso(self.stats.last_ts),
                "distinct_symbols_seen": len(self.stats.symbols_seen),
            },
            "conditions": [c.as_dict() for c in self.conditions],
        }


@dataclass
class AdmissibilityReport:
    root: Path
    session: date
    feeds: dict[str, FeedAssessment] = field(default_factory=dict)
    joint: list[ConditionResult] = field(default_factory=list)
    thresholds: dict[str, Any] = field(default_factory=dict)
    inputs: dict[str, Any] = field(default_factory=dict)
    generated_at: str = ""

    def all_conditions(self) -> list[ConditionResult]:
        return [c for _, c in self.labelled_conditions()]

    def labelled_conditions(self) -> list[tuple[str, ConditionResult]]:
        """Every condition paired with the scope it was evaluated in."""
        out: list[tuple[str, ConditionResult]] = [("joint", c) for c in self.joint]
        for feed in sorted(self.feeds):
            out.extend((feed, c) for c in self.feeds[feed].conditions)
        return out

    @property
    def verdict(self) -> Verdict:
        return roll_up(self.all_conditions())

    @property
    def exit_code(self) -> int:
        return {
            Verdict.ADMISSIBLE: EXIT_ADMISSIBLE,
            Verdict.NOT_ADMISSIBLE: EXIT_NOT_ADMISSIBLE,
            Verdict.UNDETERMINED: EXIT_UNDETERMINED,
        }[self.verdict]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": ADMISSIBILITY_SCHEMA,
            "tool": ADMISSIBILITY_VERSION,
            "generated_at": self.generated_at,
            "governing_documents": {
                "registration": REGISTRATION_DOC,
                "plan": PLAN_DOC,
            },
            "inputs": self.inputs,
            "thresholds": self.thresholds,
            "threshold_sources": THRESHOLD_SOURCES,
            "owner_ruling": OWNER_RULING_DENOMINATOR,
            "unratified_after_ruling": UNRATIFIED_AFTER_RULING,
            "joint_conditions": [c.as_dict() for c in self.joint],
            "per_feed": {f: self.feeds[f].as_dict() for f in sorted(self.feeds)},
            "verdict": str(self.verdict),
            "exit_code": self.exit_code,
            "not_passing": [
                {
                    "scope": scope,
                    "condition": c.condition,
                    "outcome": str(c.outcome),
                    "detail": c.detail,
                }
                for scope, c in self.labelled_conditions()
                if c.outcome is not Outcome.PASS
            ],
        }


def roll_up(conditions: list[ConditionResult]) -> Verdict:
    """Fail closed: every condition must PASS.

    A single FAIL makes the partition NOT_ADMISSIBLE. Otherwise any
    NOT_EVALUABLE leaves it UNDETERMINED — also not admissible, but a different
    fact that must not be reported as a failure. An empty condition list is
    UNDETERMINED, never a vacuous pass.
    """
    if not conditions:
        return Verdict.UNDETERMINED
    if any(c.outcome is Outcome.FAIL for c in conditions):
        return Verdict.NOT_ADMISSIBLE
    if any(c.outcome is Outcome.NOT_EVALUABLE for c in conditions):
        return Verdict.UNDETERMINED
    return Verdict.ADMISSIBLE


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt is not None else None


# --- frozen universe ---------------------------------------------------------


def default_universe_file() -> Path:
    """apps/backend/config/mdq_phase_a_universe_symbols.json — the deployable
    ``--universe-file`` array frozen at registration §8."""
    return Path(__file__).resolve().parents[3] / "config" / "mdq_phase_a_universe_symbols.json"


def _sha256_lf(path: Path) -> str:
    """sha256 of a file's LF-normalised bytes (read-only)."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def universe_sha256(symbols: list[str] | tuple[str, ...]) -> str:
    """The collector's own universe hash (scripts/mdq_collector.py _universe_sha)."""
    return hashlib.sha256(json.dumps(sorted(symbols)).encode()).hexdigest()


@dataclass(frozen=True)
class FrozenUniverse:
    path: Path
    symbols: tuple[str, ...]
    file_sha256_lf: str
    universe_sha256: str


def load_frozen_universe(path: Path | None = None) -> FrozenUniverse:
    p = (path or default_universe_file()).resolve()
    symbols = tuple(str(s).upper() for s in json.loads(p.read_text(encoding="utf-8")))
    return FrozenUniverse(
        path=p,
        symbols=symbols,
        file_sha256_lf=_sha256_lf(p),
        universe_sha256=universe_sha256(symbols),
    )


# --- expected cycles ---------------------------------------------------------


def sampler_window(
    session: date,
    session_close_utc: datetime,
    *,
    start_et: time = SAMPLER_START_ET,
) -> tuple[datetime, datetime]:
    """The ruled HALF-OPEN sampler window ``[start, end)`` in UTC.

    ``start`` is 09:25 America/New_York for the session; ``end`` is the official
    NYSE close and is EXCLUSIVE — the close is not itself a scheduled slot
    (owner ruling 2026-08-18). Both are returned as instants, so a DST-shifted
    session or an early close needs no special case.
    """
    start = datetime.combine(session, start_et, tzinfo=ET).astimezone(UTC)
    return start, session_close_utc.astimezone(UTC)


def expected_cycles(
    window_start: datetime,
    window_end: datetime,
    *,
    cadence_seconds: int = CADENCE_SECONDS,
) -> int:
    """Number of scheduled cadence slots in the HALF-OPEN window ``[start, end)``.

    Owner ruling 2026-08-18::

        expected_cycles = count of scheduled cadence slots t such that
                          sampler_start <= t < sampler_end

    The slots are ``window_start + k*cadence`` for ``k >= 0``, counted while the
    slot is strictly BEFORE ``window_end``. That is ``ceil(span / cadence)``,
    computed here with :func:`divmod` so an exactly-divisible span cannot be
    pushed over by float error. A 395-minute span at 60s is **395** slots — the
    earlier ``floor(span/cadence) + 1`` reading counted the endpoint and gave
    396, inflating the denominator by one slot and costing a quarter of a
    percentage point of completeness.

    A degenerate (zero-length) window has no slots, which is how the ruling's
    "0 on holidays/non-sessions" falls out of the same arithmetic.
    """
    span = (window_end - window_start).total_seconds()
    if span < 0:
        raise ValueError("sampler window ends before it starts")
    whole, remainder = divmod(span, cadence_seconds)
    return int(whole) + (1 if remainder > 0 else 0)


def slot_grid(
    window_start: datetime,
    window_end: datetime,
    *,
    cadence_seconds: int = CADENCE_SECONDS,
) -> tuple[datetime, ...]:
    """The frozen grid itself: every scheduled slot in ``[start, end)``."""
    return tuple(
        window_start + timedelta(seconds=k * cadence_seconds)
        for k in range(expected_cycles(window_start, window_end, cadence_seconds=cadence_seconds))
    )


def expected_cycles_for_session(
    session: date,
    session_close_utc: datetime | None,
    *,
    start_et: time = SAMPLER_START_ET,
    cadence_seconds: int = CADENCE_SECONDS,
) -> int:
    """The ruled denominator for one session; ``0`` when it is not a session.

    The market calendar — supplied by the caller as ``session_close_utc`` —
    controls early closes and non-trading days. ``None`` means the calendar
    yielded no close for the date, and the ruling's answer for that case is
    zero expected cycles. (Adjudication does NOT read zero as "vacuously
    complete": a partition whose close is unknown is NOT_EVALUABLE, because from
    inside a partition a holiday and an unavailable calendar look identical.)
    """
    if session_close_utc is None:
        return 0
    start, end = sampler_window(session, session_close_utc, start_et=start_et)
    return expected_cycles(start, end, cadence_seconds=cadence_seconds)


def max_contiguous_gap_minutes(
    observed: tuple[datetime, ...],
    window_start: datetime,
    window_end: datetime,
) -> float:
    """Longest stretch of the window with no observation, in minutes.

    Measured on the timestamps themselves rather than on slot indices, so that
    normal cadence drift cannot manufacture a phantom gap, and including both
    window edges so an outage at the open or into the close counts. A healthy
    60-second cadence therefore yields ~1.0.
    """
    if not observed:
        return (window_end - window_start).total_seconds() / 60.0
    marks = [window_start, *observed, window_end]
    return max((b - a).total_seconds() for a, b in zip(marks, marks[1:], strict=False)) / 60.0


# --- quote-stream parsing ----------------------------------------------------


def read_cycle_stats(samples_path: Path) -> CycleStats:
    """Parse ``quotes/samples.jsonl`` read-only and summarise the cycles.

    A cycle counts as OBSERVED when it carries at least one real quote. Cycles
    carrying only a ``feed_error`` record, or only ``missing`` markers, count
    toward the denominator but never the numerator (registration §8:
    "feed_error counts toward the denominator only").

    Where the fixed-rate collector persists ``scheduled_slot_ts`` / ``slot_index``
    on its records, those are carried out alongside the cycle timestamps so
    :func:`count_observed_cycles` can count against the frozen grid instead of
    inferring from wall-clock spacing (owner ruling 2026-08-18). Records that
    predate the fields simply carry ``None``, which is what makes the fallback
    detectable rather than invisible.
    """
    if not samples_path.exists():
        return CycleStats(present=False)

    lines = samples_path.read_text(encoding="utf-8").splitlines()
    order: list[str] = []
    cycles: dict[str, dict[str, int]] = {}
    slot_ts_seen: dict[str, set[str]] = {}
    slot_idx_seen: dict[str, set[int]] = {}
    slot_field_names: set[str] = set()
    symbols: set[str] = set()
    malformed = 0
    torn_tail = False

    for idx, raw in enumerate(lines):
        if not raw.strip():
            continue
        try:
            rec = json.loads(raw)
        except json.JSONDecodeError:
            # The store tolerates exactly one torn FINAL line (append is its
            # single non-atomic operation); anything earlier is corruption.
            if idx == len(lines) - 1:
                torn_tail = True
            else:
                malformed += 1
            continue
        if not isinstance(rec, dict):
            malformed += 1
            continue
        key = str(rec.get("cycle_ts", ""))
        if key not in cycles:
            cycles[key] = {"quotes": 0, "missing": 0, "errors": 0}
            slot_ts_seen[key] = set()
            slot_idx_seen[key] = set()
            order.append(key)
        raw_slot_ts = rec.get(SLOT_TS_FIELD)
        if isinstance(raw_slot_ts, str) and raw_slot_ts:
            slot_ts_seen[key].add(raw_slot_ts)
            slot_field_names.add(SLOT_TS_FIELD)
        raw_slot_idx = rec.get(SLOT_INDEX_FIELD)
        if isinstance(raw_slot_idx, int) and not isinstance(raw_slot_idx, bool):
            slot_idx_seen[key].add(raw_slot_idx)
            slot_field_names.add(SLOT_INDEX_FIELD)
        bucket = cycles[key]
        if "feed_error" in rec:
            bucket["errors"] += 1
        elif rec.get("missing"):
            bucket["missing"] += 1
            symbols.add(str(rec.get("symbol", "")))
        elif "bid" in rec or "quote_ts" in rec:
            bucket["quotes"] += 1
            symbols.add(str(rec.get("symbol", "")))
        else:
            malformed += 1

    entries: list[tuple[datetime, datetime | None, int | None]] = []
    unparsable = 0
    error_cycles = 0
    empty_cycles = 0
    partial = 0
    max_consecutive_errors = 0
    slot_field_cycles = 0
    slot_field_conflicts = 0
    run = 0
    for key in order:
        bucket = cycles[key]
        is_observed = bucket["quotes"] > 0
        if bucket["errors"] > 0 and not is_observed:
            error_cycles += 1
            run += 1
            max_consecutive_errors = max(max_consecutive_errors, run)
        else:
            run = 0
        if not is_observed and bucket["errors"] == 0:
            empty_cycles += 1
        if is_observed and bucket["missing"] > 0:
            partial += 1
        if not is_observed:
            continue
        try:
            cycle_ts = datetime.fromisoformat(key)
        except ValueError:
            unparsable += 1
            continue
        ts_values = slot_ts_seen[key]
        idx_values = slot_idx_seen[key]
        if len(ts_values) > 1 or len(idx_values) > 1:
            # One cycle must carry ONE scheduled slot. Disagreement inside a
            # cycle is recorded, and the cycle contributes no slot evidence.
            slot_field_conflicts += 1
            entries.append((cycle_ts, None, None))
            continue
        slot_ts: datetime | None = None
        if ts_values:
            try:
                slot_ts = datetime.fromisoformat(next(iter(ts_values)))
            except ValueError:
                slot_field_conflicts += 1
        slot_index = next(iter(idx_values)) if idx_values else None
        if slot_ts is not None or slot_index is not None:
            slot_field_cycles += 1
        entries.append((cycle_ts, slot_ts, slot_index))

    entries.sort(key=lambda e: e[0])
    observed_ts = tuple(e[0] for e in entries)
    spacings = [(b - a).total_seconds() for a, b in zip(observed_ts, observed_ts[1:], strict=False)]
    symbols.discard("")

    return CycleStats(
        observed_cycles=len(observed_ts) + unparsable,
        error_cycles=error_cycles,
        empty_cycles=empty_cycles,
        partial_cycles=partial,
        total_cycle_slots_seen=len(order),
        max_consecutive_error_cycles=max_consecutive_errors,
        malformed_lines=malformed,
        torn_tail=torn_tail,
        unparsable_cycle_ts=unparsable,
        symbols_seen=tuple(sorted(symbols)),
        first_ts=observed_ts[0] if observed_ts else None,
        last_ts=observed_ts[-1] if observed_ts else None,
        median_spacing_seconds=_median(spacings) if spacings else None,
        observed_ts=observed_ts,
        present=True,
        observed_slot_ts=tuple(e[1] for e in entries),
        observed_slot_index=tuple(e[2] for e in entries),
        slot_field_cycles=slot_field_cycles,
        slot_field_names=tuple(sorted(slot_field_names)),
        slot_field_conflicts=slot_field_conflicts,
    )


class CountMethod(StrEnum):
    """How the NUMERATOR was obtained.

    The owner ruled that where the collector persists a scheduled slot, observed
    cycles are counted against the frozen slot grid — that is the more faithful
    measure than inferring occupancy from wall-clock spacing. Partitions written
    before the field exists must still be adjudicable, so the fallback stays,
    but which one was used is stated in the record every time. The two are never
    mixed inside one partition: a partially-instrumented partition is counted
    entirely by the fallback, because a half-and-half numerator is neither
    measure and cannot be reasoned about.
    """

    SLOT_GRID = "slot_grid"
    CYCLE_TS_FALLBACK = "cycle_ts_fallback"


@dataclass(frozen=True)
class ObservedCount:
    """The numerator, how it was obtained, and what it had to discard."""

    method: CountMethod
    observed_cycles: int
    marks: tuple[datetime, ...]
    slots_filled: tuple[int, ...]
    off_grid_cycles: int
    duplicate_slot_cycles: int
    slot_index_disagreements: int
    note: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "method": str(self.method),
            "observed_cycles": self.observed_cycles,
            "off_grid_cycles": self.off_grid_cycles,
            "duplicate_slot_cycles": self.duplicate_slot_cycles,
            "slot_index_disagreements": self.slot_index_disagreements,
            "note": self.note,
        }


def count_observed_cycles(
    stats: CycleStats,
    window_start: datetime,
    window_end: datetime,
    *,
    cadence_seconds: int = CADENCE_SECONDS,
) -> ObservedCount:
    """Count observed cycles against the ruled grid, or say why it could not.

    Preference order (owner ruling 2026-08-18):

    1. ``scheduled_slot_ts`` — absolute, so it maps onto the ruled grid without
       assuming the collector's slot 0 is the ruled slot 0.
    2. ``slot_index`` — used when no slot timestamp is present, and otherwise
       cross-checked against the timestamp with any disagreement reported.
    3. ``cycle_ts`` — the legacy fallback, for partitions written before the
       fields existed. Reported as such, never silently substituted.
    """
    expected = expected_cycles(window_start, window_end, cadence_seconds=cadence_seconds)
    n_observed = len(stats.observed_ts)

    if stats.slot_field_cycles == 0:
        return ObservedCount(
            method=CountMethod.CYCLE_TS_FALLBACK,
            observed_cycles=stats.observed_cycles,
            marks=stats.observed_ts,
            slots_filled=(),
            off_grid_cycles=0,
            duplicate_slot_cycles=0,
            slot_index_disagreements=0,
            note=(
                f"FALLBACK: no cycle carries {SLOT_TS_FIELD} or {SLOT_INDEX_FIELD}, "
                "so this partition predates the fixed-rate collector. Observed "
                "cycles are counted as distinct quote-bearing cycle_ts values and "
                "the gap is measured on those wall-clock timestamps. This is the "
                "legacy measure, not the ruled slot-grid measure."
            ),
        )
    if stats.slot_field_cycles < n_observed:
        return ObservedCount(
            method=CountMethod.CYCLE_TS_FALLBACK,
            observed_cycles=stats.observed_cycles,
            marks=stats.observed_ts,
            slots_filled=(),
            off_grid_cycles=0,
            duplicate_slot_cycles=0,
            slot_index_disagreements=0,
            note=(
                f"FALLBACK (MIXED PARTITION): {stats.slot_field_cycles} of "
                f"{n_observed} observed cycles carry the scheduled-slot field. "
                "Counting methods are never mixed inside one partition, so the "
                "whole partition is counted from cycle_ts. A partition that "
                "straddles the fixed-rate collector change is worth an owner look "
                "in its own right — it is two instruments in one file."
            ),
        )

    filled: set[int] = set()
    off_grid = 0
    duplicates = 0
    disagreements = 0
    for slot_ts, slot_index in zip(stats.observed_slot_ts, stats.observed_slot_index, strict=False):
        index: int | None = None
        on_grid = True
        if slot_ts is not None:
            whole, remainder = divmod((slot_ts - window_start).total_seconds(), cadence_seconds)
            if remainder == 0:
                index = int(whole)
            else:
                on_grid = False
        if slot_index is not None:
            if index is None:
                if on_grid:
                    index = slot_index
            elif index != slot_index:
                disagreements += 1
        if not on_grid or index is None or not (0 <= index < expected):
            off_grid += 1
            continue
        if index in filled:
            duplicates += 1
            continue
        filled.add(index)

    slots = tuple(sorted(filled))
    note = (
        f"SLOT GRID: every observed cycle carries the collector's scheduled slot "
        f"({', '.join(stats.slot_field_names)}), so occupancy is counted directly "
        f"against the {expected}-slot ruled grid rather than inferred from "
        "wall-clock spacing (owner ruling 2026-08-18)."
    )
    if off_grid:
        note += (
            f" {off_grid} cycle(s) carried a slot that is not on the ruled grid or "
            "lies outside the window; they are excluded from the numerator and "
            "surface in session_scope_match."
        )
    if duplicates:
        note += f" {duplicates} cycle(s) claimed an already-filled slot."
    if disagreements:
        note += (
            f" {disagreements} cycle(s) carried a {SLOT_INDEX_FIELD} disagreeing with "
            f"their {SLOT_TS_FIELD}; the timestamp governs and the disagreement is "
            "reported rather than reconciled."
        )
    return ObservedCount(
        method=CountMethod.SLOT_GRID,
        observed_cycles=len(slots),
        marks=tuple(window_start + timedelta(seconds=index * cadence_seconds) for index in slots),
        slots_filled=slots,
        off_grid_cycles=off_grid,
        duplicate_slot_cycles=duplicates,
        slot_index_disagreements=disagreements,
        note=note,
    )


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    return ordered[mid] if n % 2 else (ordered[mid - 1] + ordered[mid]) / 2.0


# --- the §7.1 conditions -----------------------------------------------------


def assess_feed(
    store: CaptureStore,
    ref: PartitionRef,
    *,
    frozen_universe: FrozenUniverse,
    session_close_utc: datetime | None,
    pins: AcquisitionPins | None = None,
    sampler_start_et: time = SAMPLER_START_ET,
    cadence_seconds: int = CADENCE_SECONDS,
    min_completeness: float = MIN_COMPLETENESS,
    max_gap_minutes: float = MAX_CONTIGUOUS_GAP_MINUTES,
    cadence_tolerance_seconds: float = CADENCE_TOLERANCE_SECONDS,
    approved_collector_versions: tuple[str, ...] = (),
    signoff_date: date = REGISTRATION_SIGNOFF_DATE,
    governing_denominator: Denominator | None = None,
    include_census_diagnostic: bool = False,
) -> FeedAssessment:
    """Evaluate every §7.1 condition for one feed's partition. Strictly read-only.

    The denominator is no longer a caller's choice: the owner ruling 2026-08-18
    binds it to the half-open sampler grid, and :func:`resolve_denominator`
    applies that ruling to whatever was requested. ``include_census_diagnostic``
    additionally computes the 04:00-16:00 ET bar-census arithmetic, clearly
    labelled as a diagnostic that is never scored.
    """
    latch = pins or AcquisitionPins()
    fa = FeedAssessment(feed=ref.feed, session=ref.session)
    add = fa.conditions.append
    src = THRESHOLD_SOURCES
    pdir = store.partition_dir(ref)
    mpath = store.manifest_path(ref)

    # 1. freeze completed ----------------------------------------------------
    if not pdir.exists():
        add(
            ConditionResult(
                "freeze_completed",
                Outcome.FAIL,
                "partition directory absent",
                "manifest.json present",
                f"no partition at {pdir}",
                src["manifest_schema"],
            )
        )
        return fa
    if not mpath.exists():
        add(
            ConditionResult(
                "freeze_completed",
                Outcome.FAIL,
                "no manifest.json",
                "manifest.json present",
                "partition is UNFROZEN — inadmissible (plan §7.2)",
                src["manifest_schema"],
            )
        )
        return fa
    add(
        ConditionResult(
            "freeze_completed",
            Outcome.PASS,
            "manifest.json present",
            "manifest.json present",
            "freeze completed (manifest presence == FROZEN)",
            src["manifest_schema"],
        )
    )

    # 2. manifest well-formed ------------------------------------------------
    try:
        manifest = json.loads(mpath.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        add(
            ConditionResult(
                "manifest_well_formed",
                Outcome.FAIL,
                f"{type(exc).__name__}: {exc}",
                f"schema {MANIFEST_SCHEMA} with files[]",
                "manifest unreadable — nothing downstream can be adjudicated",
                src["manifest_schema"],
            )
        )
        return fa
    required = ("schema", "feed", "session", "collector_version", "frozen_at", "files")
    missing_keys = [k for k in required if k not in manifest]
    if not isinstance(manifest, dict) or missing_keys or manifest.get("schema") != MANIFEST_SCHEMA:
        add(
            ConditionResult(
                "manifest_well_formed",
                Outcome.FAIL,
                {"schema": manifest.get("schema"), "missing_keys": missing_keys},
                {"schema": MANIFEST_SCHEMA, "missing_keys": []},
                "manifest is not a well-formed capture manifest",
                src["manifest_schema"],
            )
        )
        return fa
    add(
        ConditionResult(
            "manifest_well_formed",
            Outcome.PASS,
            {"schema": manifest["schema"], "files": len(manifest["files"])},
            {"schema": MANIFEST_SCHEMA},
            "manifest carries schema, feed, session, collector_version, frozen_at, files[]",
            src["manifest_schema"],
        )
    )

    # 3. integrity — reuse CaptureStore.verify, do not re-implement -----------
    problems = store.verify(ref)
    add(
        ConditionResult(
            "integrity_verify",
            Outcome.PASS if not problems else Outcome.FAIL,
            problems or "all manifested files re-hash; no unmanifested strays",
            "CaptureStore.verify() == []",
            "re-hash of every manifested file plus stray rejection; this is also "
            "how §7.1 'no post-freeze mutation' is evidenced (mutated bytes change "
            "the recorded sha256)",
            "app/research/capture/store.py CaptureStore.verify",
        )
    )

    # 4. label — hard exclusion ----------------------------------------------
    label = manifest.get("label")
    add(
        ConditionResult(
            "no_provenance_label",
            Outcome.PASS if label is None else Outcome.FAIL,
            label,
            None,
            "an admissible governed partition carries NO label; any label "
            "(PRE_REGISTRATION_SMOKE or otherwise) quarantines the partition",
            src["no_provenance_label"],
        )
    )

    # 5. captured after §8 sign-off ------------------------------------------
    add(_assess_signoff(ref.session, manifest, signoff_date, src["registration_signoff_date"]))

    # 6. identity provenance --------------------------------------------------
    got_fp = manifest.get("credential_fingerprint")
    got_acct = manifest.get("account_number")
    ok_identity = got_fp == latch.key_fingerprint and got_acct == latch.account_number
    add(
        ConditionResult(
            "identity_latch_recorded",
            Outcome.PASS if ok_identity else Outcome.FAIL,
            {"credential_fingerprint": got_fp, "account_number": got_acct},
            {
                "credential_fingerprint": latch.key_fingerprint,
                "account_number": latch.account_number,
            },
            "manifest records the pinned acquisition identity; an unpinned-credential "
            "partition is inadmissible (plan §7.2)",
            f"{src['credential_fingerprint']} || {src['account_number']}",
        )
    )

    # 7. explicit feed identity ------------------------------------------------
    manifest_feed = manifest.get("feed")
    feed_ok = manifest_feed == ref.feed and manifest_feed in FEEDS
    add(
        ConditionResult(
            "feed_identity_explicit",
            Outcome.PASS if feed_ok else Outcome.FAIL,
            {"manifest_feed": manifest_feed, "partition_path_feed": ref.feed},
            {"manifest_feed": ref.feed},
            "explicit feed literal present and consistent with the partition path",
            f"{REGISTRATION_DOC} §7 control 2; {PLAN_DOC} §7.3",
        )
    )

    # 8. declared universe ----------------------------------------------------
    declared = manifest.get("universe")
    declared_sha = manifest.get("universe_sha256")
    universe_ok = (
        isinstance(declared, list)
        and [str(s) for s in declared] == sorted(frozen_universe.symbols)
        and declared_sha == frozen_universe.universe_sha256
    )
    add(
        ConditionResult(
            "universe_match",
            Outcome.PASS if universe_ok else Outcome.FAIL,
            {
                "universe_sha256": declared_sha,
                "symbols": len(declared) if isinstance(declared, list) else None,
            },
            {
                "universe_sha256": frozen_universe.universe_sha256,
                "symbols": len(frozen_universe.symbols),
            },
            "the manifest's declared universe equals the frozen Phase-A universe",
            src["universe_sha256"],
        )
    )

    # 9. session recorded ------------------------------------------------------
    add(
        ConditionResult(
            "session_recorded",
            Outcome.PASS if manifest.get("session") == ref.session.isoformat() else Outcome.FAIL,
            manifest.get("session"),
            ref.session.isoformat(),
            "manifest session matches the adjudicated session date",
            src["manifest_schema"],
        )
    )

    # 10. capture modes --------------------------------------------------------
    modes = manifest.get("capture_modes") or []
    want_modes = {CAPTURE_MODE_SAMPLER, CAPTURE_MODE_EOD_BARS}
    add(
        ConditionResult(
            "capture_modes_complete",
            Outcome.PASS if want_modes.issubset(set(modes)) else Outcome.FAIL,
            sorted(modes),
            sorted(want_modes),
            "Phase A is quote sampling AND end-of-session 1-minute bars; a partition "
            "missing either mode is scope-mismatched",
            src["capture_modes"],
        )
    )

    # 11. expected files -------------------------------------------------------
    listed = {f["path"] for f in manifest["files"] if isinstance(f, dict) and "path" in f}
    want_files = {"quotes/samples.jsonl", "bars/bars_1min.parquet"}
    add(
        ConditionResult(
            "expected_files_present",
            Outcome.PASS if want_files.issubset(listed) else Outcome.FAIL,
            sorted(listed),
            sorted(want_files),
            "the manifest lists the quote stream and the session bar file",
            src["capture_modes"],
        )
    )

    # 12. collector code identity ----------------------------------------------
    collector_version = manifest.get("collector_version")
    if not approved_collector_versions:
        add(
            ConditionResult(
                "collector_code_identity",
                Outcome.NOT_EVALUABLE,
                collector_version,
                "an approved collector version/sha for the period",
                "no approved collector identity is frozen anywhere this tool can "
                "read; supply --approved-collector-version to evaluate it",
                src["collector_code_identity"],
            )
        )
    else:
        add(
            ConditionResult(
                "collector_code_identity",
                Outcome.PASS if collector_version in approved_collector_versions else Outcome.FAIL,
                collector_version,
                list(approved_collector_versions),
                "collector code identity approved for the period",
                src["collector_code_identity"],
            )
        )

    # --- sufficiency (§4.9) ----------------------------------------------------
    stats = read_cycle_stats(pdir / "quotes" / "samples.jsonl")
    fa.stats = stats

    add(
        ConditionResult(
            "quote_records_parseable",
            Outcome.PASS
            if stats.present and stats.malformed_lines == 0 and stats.unparsable_cycle_ts == 0
            else Outcome.FAIL,
            {
                "present": stats.present,
                "malformed_lines": stats.malformed_lines,
                "unparsable_cycle_ts": stats.unparsable_cycle_ts,
                "torn_tail_tolerated": stats.torn_tail,
            },
            {"present": True, "malformed_lines": 0, "unparsable_cycle_ts": 0},
            "every quote record parses; one torn FINAL line is tolerated by the "
            "store's own append contract, anything earlier is corruption",
            "app/research/capture/store.py append_jsonl docstring",
        )
    )

    observed_symbols = set(stats.symbols_seen)
    frozen_symbols = set(frozen_universe.symbols)
    if not stats.present:
        add(
            ConditionResult(
                "observed_symbols_match",
                Outcome.NOT_EVALUABLE,
                None,
                {"count": len(frozen_symbols)},
                "no quote stream in the partition — nothing to compare",
                src["universe_symbols_file_sha256"],
            )
        )
    else:
        add(
            ConditionResult(
                "observed_symbols_match",
                Outcome.PASS if observed_symbols == frozen_symbols else Outcome.FAIL,
                {
                    "count": len(observed_symbols),
                    "unexpected": sorted(observed_symbols - frozen_symbols),
                    "absent": sorted(frozen_symbols - observed_symbols),
                },
                {"count": len(frozen_symbols)},
                "symbols observed in the quote stream equal the frozen universe",
                src["universe_symbols_file_sha256"],
            )
        )

    if session_close_utc is None:
        for cond in (
            "session_scope_match",
            "cadence_match",
            "completeness_ratio",
            "max_contiguous_gap",
        ):
            add(
                ConditionResult(
                    cond,
                    Outcome.NOT_EVALUABLE,
                    None,
                    None,
                    "no session close supplied — expected_cycles = f(session_scope, "
                    "cadence, market calendar) cannot be evaluated (not a trading "
                    "session, or the calendar was unavailable)",
                    src["session_close"],
                )
            )
        return fa

    governing, want_census, ruling_note = resolve_denominator(
        governing_denominator, census_diagnostic=include_census_diagnostic
    )
    fa.governing_denominator = governing
    wanted = [Denominator.SAMPLER_WINDOW]
    if want_census:
        wanted.append(Denominator.CENSUS_WINDOW)
    fa.readings = {
        str(d): _reading(
            d,
            ref.session,
            session_close_utc,
            stats,
            sampler_start_et=sampler_start_et,
            cadence_seconds=cadence_seconds,
            min_completeness=min_completeness,
            max_gap_minutes=max_gap_minutes,
        )
        for d in wanted
    }
    sampler_reading = fa.readings[str(Denominator.SAMPLER_WINDOW)]
    census_reading = fa.readings.get(str(Denominator.CENSUS_WINDOW))
    by_reading = {k: v.as_dict() for k, v in sorted(fa.readings.items())}
    fa.derivation = {
        "formula": (
            "expected_cycles = #{k >= 0 : sampler_start + k*cadence < sampler_end} "
            "= ceil((sampler_end - sampler_start) / cadence)"
        ),
        "grid": "HALF-OPEN: sampler_start <= t < sampler_end (the close is not a slot)",
        "cadence_seconds": cadence_seconds,
        "ruling": OWNER_RULING_DENOMINATOR,
        "ruling_applied": ruling_note,
        "readings": by_reading,
        "numerator": sampler_reading.count.as_dict(),
        "sampler_timing_semantics": _timing_semantics(
            sampler_reading,
            stats,
            cadence_seconds=cadence_seconds,
            min_completeness=min_completeness,
        ),
        "governing_denominator": str(governing),
    }

    # 13. session scope ------------------------------------------------------
    add(
        _assess_scope(
            stats,
            sampler_reading,
            census_reading,
            cadence_seconds=cadence_seconds,
            source=src["sampler_start_et"],
        )
    )

    # 14. cadence ------------------------------------------------------------
    cadence_source = f"{src['cadence_seconds']} || tolerance: {src['cadence_tolerance_seconds']}"
    if stats.median_spacing_seconds is None:
        add(
            ConditionResult(
                "cadence_match",
                Outcome.NOT_EVALUABLE,
                None,
                {"cadence_seconds": cadence_seconds},
                "fewer than two observed cycles — no spacing to measure",
                cadence_source,
            )
        )
    else:
        delta = abs(stats.median_spacing_seconds - cadence_seconds)
        add(
            ConditionResult(
                "cadence_match",
                Outcome.PASS if delta <= cadence_tolerance_seconds else Outcome.FAIL,
                {
                    "median_spacing_seconds": stats.median_spacing_seconds,
                    "abs_deviation_seconds": delta,
                    "note": (
                        "cmd_sample is FIXED-DELAY (the sleep is AFTER the requests), "
                        "so the true period is cadence + per-cycle work, never exactly "
                        "the cadence"
                    ),
                },
                {
                    "cadence_seconds": cadence_seconds,
                    "tolerance_seconds": cadence_tolerance_seconds,
                    "tolerance_status": "TOOL DEFAULT — NOT RATIFIED",
                },
                "observed inter-cycle spacing is consistent with the frozen 60s cadence",
                cadence_source,
            )
        )

    # 15/16. completeness + max contiguous gap -------------------------------
    #
    # RULED 2026-08-18. These two conditions used to return NOT_EVALUABLE because
    # the registration froze expected_cycles as a formula over an unbound
    # session_scope. The owner has bound it, so they are now scored — against the
    # half-open sampler grid, and against nothing else.
    ruling = sampler_reading
    add(
        ConditionResult(
            "completeness_ratio",
            Outcome.PASS if ruling.meets_min_completeness else Outcome.FAIL,
            {
                "governing_denominator": str(governing),
                "observed_cycles": ruling.observed_cycles,
                "expected_cycles": ruling.expected_cycles,
                "completeness": ruling.completeness,
                "observed_cycle_method": str(ruling.count.method),
                "error_cycles_excluded_from_numerator": stats.error_cycles,
                "empty_cycles_excluded_from_numerator": stats.empty_cycles,
                "all_readings": by_reading,
            },
            {
                "min_completeness": min_completeness,
                "denominator": str(governing),
                "expected_cycles": ruling.expected_cycles,
                "min_observed_cycles": _min_observed_for_floor(
                    ruling.expected_cycles, min_completeness
                ),
            },
            "observed / expected sampling cycles per partition per feed over the "
            "RULED half-open sampler grid (09:25 ET inclusive to the official NYSE "
            "close exclusive, 60s cadence); feed_error and all-missing cycles count "
            "toward the denominator only",
            f"{src['min_completeness']} || {src['expected_cycles_denominator']} || "
            f"{src['expected_cycles_grid']} || {src['feed_error_denominator_only']} || "
            f"{src['observed_cycle_method']}",
        )
    )
    add(
        ConditionResult(
            "max_contiguous_gap",
            Outcome.PASS if ruling.meets_max_gap else Outcome.FAIL,
            {
                "governing_denominator": str(governing),
                "max_contiguous_gap_minutes": round(ruling.max_gap_minutes, 3),
                "implied_missing_consecutive_cycles": max(
                    0, int(round(ruling.max_gap_minutes * 60.0 / cadence_seconds)) - 1
                ),
                "observed_cycle_method": str(ruling.count.method),
                "all_readings": by_reading,
            },
            {"max_contiguous_gap_minutes": max_gap_minutes},
            "longest stretch of the ruled half-open sampler window with no "
            "observation, measured on the slot grid where the collector recorded "
            "one and on the observed cycle timestamps otherwise, and including "
            "both window edges",
            f"{src['max_contiguous_gap_minutes']} || {src['observed_cycle_method']}",
        )
    )

    return fa


def _min_observed_for_floor(expected: int, min_completeness: float) -> int:
    """Smallest integer cycle count that clears the floor over ``expected`` slots.

    Stated in the record so a reader does not have to re-derive it: over the
    ruled 395-slot grid the 98% floor admits at most 7 missing cycles, because
    387/395 = 97.97% fails and 388/395 = 98.23% passes.
    """
    for observed in range(expected + 1):
        if observed >= min_completeness * expected:
            return observed
    return expected


def _reading(
    denominator: Denominator,
    session: date,
    session_close_utc: datetime,
    stats: CycleStats,
    *,
    sampler_start_et: time,
    cadence_seconds: int,
    min_completeness: float,
    max_gap_minutes: float,
) -> ReadingResult:
    """Completeness and gap over one session-scope window."""
    if denominator is Denominator.CENSUS_WINDOW:
        start = datetime.combine(session, BAR_WINDOW_ET[0], tzinfo=ET).astimezone(UTC)
        end = datetime.combine(session, BAR_WINDOW_ET[1], tzinfo=ET).astimezone(UTC)
        role = DENOMINATOR_ROLE_DIAGNOSTIC
        note = (
            "EOD one-minute BAR CENSUS scope 04:00-16:00 ET (registration §7 Phase "
            "A; plan §4.1). The owner ruling 2026-08-18 states this is the bar "
            "census scope and NOT the sampler denominator: scoring a 09:25-start "
            "sampler against it would mechanically fail every healthy partition."
        )
    else:
        start, end = sampler_window(session, session_close_utc, start_et=sampler_start_et)
        role = DENOMINATOR_ROLE_GOVERNING
        note = (
            "RULED sampler window: 09:25 America/New_York (inclusive) to the "
            "official NYSE close (EXCLUSIVE) at the frozen 60s cadence — 395 slots "
            "on a normal 16:00 close, 215 on a 13:00 early close, 0 on a "
            "non-session (owner ruling 2026-08-18)."
        )
    exp = expected_cycles(start, end, cadence_seconds=cadence_seconds)
    count = count_observed_cycles(stats, start, end, cadence_seconds=cadence_seconds)
    completeness = count.observed_cycles / exp if exp else 0.0
    gap = max_contiguous_gap_minutes(count.marks, start, end)
    return ReadingResult(
        denominator=denominator,
        role=role,
        window_start=start,
        window_end=end,
        expected_cycles=exp,
        observed_cycles=count.observed_cycles,
        completeness=completeness,
        max_gap_minutes=gap,
        meets_min_completeness=completeness >= min_completeness,
        meets_max_gap=gap <= max_gap_minutes,
        scope_note=note,
        count=count,
    )


def _simulate_fixed_delay_cycles(span_seconds: float, cadence_seconds: int, overhead: float) -> int:
    """Cycle count ``cmd_sample``'s loop produces at a given per-cycle overhead."""
    elapsed = 0.0
    cycles = 0
    while True:
        cycles += 1
        if elapsed + overhead >= span_seconds:
            return cycles
        elapsed += overhead + cadence_seconds


def _simulate_fixed_rate_cycles(expected: int, cadence_seconds: int, overhead: float) -> int:
    """Cycle count a FIXED-RATE loop produces at a given per-cycle overhead.

    Absolute monotonic deadline per slot, no burst and no catch-up: a cycle
    whose work takes ``overhead`` seconds occupies ``ceil(overhead / cadence)``
    slots (at least one), and the loop resumes at the next slot that has not yet
    passed. Overhead therefore costs nothing at all until it exceeds one full
    cadence period, at which point the achievable count halves in one step.
    """
    whole, remainder = divmod(max(0.0, overhead), cadence_seconds)
    step = max(1, int(whole) + (1 if remainder > 0 else 0))
    return -(-expected // step)


def _max_overhead_meeting_floor(
    simulate: Any, needed: float, *, ceiling_seconds: float
) -> float | None:
    """Largest per-cycle overhead (0.01s resolution) that still clears the floor."""
    tolerable: float | None = None
    for step in range(int(ceiling_seconds * 100) + 1):
        overhead = step / 100.0
        if simulate(overhead) >= needed:
            tolerable = overhead
        else:
            break
    return tolerable


def _timing_semantics(
    sampler_reading: ReadingResult,
    stats: CycleStats,
    *,
    cadence_seconds: int,
    min_completeness: float,
) -> dict[str, Any]:
    """How much per-cycle overhead each scheduling model survives.

    The frozen 98% floor is a fact about the DENOMINATOR; whether a healthy
    capture can reach it is a fact about the LOOP. Both models are reported so
    the owner can see the difference the fixed-rate change makes rather than
    discovering it at adjudication:

    * fixed DELAY (the legacy loop: sample, append, test ``now >= close``, only
      THEN sleep ``cadence``) has a true period of ``cadence + per-cycle work``,
      so a partition drifts short of the scheduled slot count with a perfectly
      healthy feed. Its headroom is on the order of a second.
    * fixed RATE (the ruled loop: absolute monotonic deadline per slot, no
      burst/catch-up, close checked BEFORE the cycle) fires every slot for as
      long as the work fits inside one cadence period, so the floor is robust
      until per-cycle work reaches the cadence itself — and then collapses in a
      single step rather than degrading gently.
    """
    span = (sampler_reading.window_end - sampler_reading.window_start).total_seconds()
    expected = sampler_reading.expected_cycles
    needed = min_completeness * expected
    fixed_delay_headroom = _max_overhead_meeting_floor(
        lambda overhead: _simulate_fixed_delay_cycles(span, cadence_seconds, overhead),
        needed,
        ceiling_seconds=10.0,
    )
    fixed_rate_headroom = _max_overhead_meeting_floor(
        lambda overhead: _simulate_fixed_rate_cycles(expected, cadence_seconds, overhead),
        needed,
        ceiling_seconds=2.0 * cadence_seconds,
    )
    observed_overhead: float | None = None
    achievable: int | None = None
    vs_achievable: float | None = None
    if stats.median_spacing_seconds is not None:
        observed_overhead = round(stats.median_spacing_seconds - cadence_seconds, 3)
        achievable = _simulate_fixed_delay_cycles(
            span, cadence_seconds, max(0.0, observed_overhead)
        )
        vs_achievable = stats.observed_cycles / achievable if achievable else None
    return {
        "loop_observed_in_this_partition": (
            "fixed-rate (the partition carries the collector's scheduled slot)"
            if sampler_reading.count.method is CountMethod.SLOT_GRID
            else "fixed-delay or unknown (no scheduled slot recorded on the cycles)"
        ),
        "legacy_loop": "fixed-delay (the sleep is AFTER the requests and the append)",
        "ruled_loop": (
            "fixed-rate (absolute monotonic deadline per slot, no burst/catch-up, "
            "close checked BEFORE the cycle)"
        ),
        "true_period_seconds_fixed_delay": f"{cadence_seconds} + per-cycle work",
        "true_period_seconds_fixed_rate": f"{cadence_seconds} exactly, while work < cadence",
        "expected_cycles_half_open_grid": expected,
        "max_per_cycle_overhead_seconds_meeting_min_completeness": fixed_delay_headroom,
        "max_per_cycle_overhead_seconds_meeting_min_completeness_fixed_delay": (
            fixed_delay_headroom
        ),
        "max_per_cycle_overhead_seconds_meeting_min_completeness_fixed_rate": (fixed_rate_headroom),
        "note": (
            "under fixed DELAY, above that per-cycle overhead a perfectly healthy "
            "capture still fails the frozen completeness floor. Under fixed RATE "
            "the floor is unaffected by overhead until the work reaches a full "
            "cadence period, so the frozen 98% is robust rather than marginal — "
            "which is the point of the scheduling change, not a relaxation of it."
        ),
        "observed_per_cycle_overhead_seconds": observed_overhead,
        "achievable_cycles_at_observed_overhead": achievable,
        "ratio_vs_achievable_cycles": vs_achievable,
        "achievable_ratio_status": (
            "DIAGNOSTIC ONLY, NOT AN ADMISSIBLE DENOMINATOR. An 'elapsed-time-derived "
            "achievable cycles' denominator has been floated as a fix for scheduler "
            "drift, but it is (a) absent from the frozen text, (b) excluded by the "
            "owner ruling 2026-08-18, which binds the denominator to the half-open "
            "sampler grid, and (c) partly self-referential — it derives the "
            "denominator from the partition's own observed spacing, so it cannot "
            "detect a capture that ran slow. Reported so the owner can see the "
            "number, never scored."
        ),
    }


def _close_grace_periods(stats: CycleStats) -> int:
    """Grace owed at the close, decided by evidence rather than by a flag.

    A partition whose every observed cycle carries the fixed-rate collector's
    scheduled slot was produced by a loop that checks the close BEFORE the
    cycle, so no cycle may legitimately land at or past the close: grace 0.
    Anything else is (or may be) the legacy fixed-DELAY loop, which tested
    ``now >= close`` only after taking one more sample: grace one cadence period.
    """
    if stats.observed_ts and stats.slot_field_cycles == len(stats.observed_ts):
        return FIXED_RATE_CLOSE_GRACE_PERIODS
    return LEGACY_FIXED_DELAY_CLOSE_GRACE_PERIODS


def _assess_scope(
    stats: CycleStats,
    sampler_reading: ReadingResult,
    census_reading: ReadingResult | None,
    *,
    cadence_seconds: int,
    source: str,
) -> ConditionResult:
    """Every observed cycle must fall inside the RULED sampler window.

    Before the ruling this condition had to return NOT_EVALUABLE for cycles
    lying between the two candidate windows (inside 04:00-16:00 ET but outside
    the sampler window), because scope conformance turned on the unresolved
    denominator. The ruling resolves it: the sampler window is the scope, so a
    04:00 cycle is now unambiguously out of scope and FAILs. That is the same
    ambiguity being closed, not a new strictness.
    """
    grace_periods = _close_grace_periods(stats)
    windows: dict[str, Any] = {
        "ruled_sampler_window_et": [
            sampler_reading.window_start.astimezone(ET).isoformat(),
            sampler_reading.window_end.astimezone(ET).isoformat() + " (exclusive)",
        ],
        "close_grace_periods": grace_periods,
    }
    if census_reading is not None:
        windows["census_window_et_DIAGNOSTIC_ONLY"] = [
            census_reading.window_start.astimezone(ET).isoformat(),
            census_reading.window_end.astimezone(ET).isoformat(),
        ]
    if not stats.observed_ts:
        return ConditionResult(
            "session_scope_match",
            Outcome.NOT_EVALUABLE,
            None,
            windows,
            "no observed cycles to place inside the ruled window",
            source,
        )
    grace = timedelta(seconds=grace_periods * cadence_seconds)
    outside = [
        t
        for t in stats.observed_ts
        if t < sampler_reading.window_start or t >= sampler_reading.window_end + grace
    ]
    observed = {
        "first_cycle_et": stats.observed_ts[0].astimezone(ET).isoformat(),
        "last_cycle_et": stats.observed_ts[-1].astimezone(ET).isoformat(),
        "cycles_outside_ruled_sampler_window": len(outside),
        "close_grace_seconds": grace_periods * cadence_seconds,
        "off_grid_cycles": sampler_reading.count.off_grid_cycles,
        "scheduling_evidence": (
            "fixed-rate (scheduled slot recorded on every observed cycle)"
            if grace_periods == FIXED_RATE_CLOSE_GRACE_PERIODS
            else "legacy/unknown (no scheduled slot on every cycle) — one cadence "
            "period of close grace applies"
        ),
    }
    if outside or sampler_reading.count.off_grid_cycles:
        return ConditionResult(
            "session_scope_match",
            Outcome.FAIL,
            observed,
            windows,
            "cycles fall outside the ruled half-open sampler window (09:25 ET "
            "inclusive to the official NYSE close exclusive). Under the owner "
            "ruling 2026-08-18 the 04:00-16:00 ET interval is the EOD bar census "
            "scope, not the sampler scope, so a cycle in that band is out of scope "
            "rather than undecidable",
            source,
        )
    return ConditionResult(
        "session_scope_match",
        Outcome.PASS,
        observed,
        windows,
        "every observed cycle falls inside the ruled sampler window",
        source,
    )


def _assess_signoff(
    session: date,
    manifest: dict[str, Any],
    signoff_date: date,
    source: str,
) -> ConditionResult:
    frozen_at = manifest.get("frozen_at")
    frozen_date: date | None = None
    if isinstance(frozen_at, str):
        try:
            frozen_date = datetime.fromisoformat(frozen_at).date()
        except ValueError:
            frozen_date = None
    observed = {"session": session.isoformat(), "frozen_at": frozen_at}
    expected = {"session": f"> {signoff_date.isoformat()}"}
    if session < signoff_date or (frozen_date is not None and frozen_date < signoff_date):
        return ConditionResult(
            "captured_after_signoff",
            Outcome.FAIL,
            observed,
            expected,
            "capture predates the §8 registration sign-off — inadmissible",
            source,
        )
    if session == signoff_date:
        return ConditionResult(
            "captured_after_signoff",
            Outcome.NOT_EVALUABLE,
            observed,
            expected,
            "the session IS the sign-off date; §8 freezes a date, not a time of day, "
            "so 'captured after sign-off' cannot be established from the partition "
            "alone (fail closed)",
            source,
        )
    return ConditionResult(
        "captured_after_signoff",
        Outcome.PASS,
        observed,
        expected,
        "the whole session postdates the §8 sign-off date",
        source,
    )


def assess_partition(
    root: Path,
    session: date,
    *,
    session_close_utc: datetime | None,
    frozen_universe: FrozenUniverse | None = None,
    pins: AcquisitionPins | None = None,
    feeds: tuple[str, ...] = FEEDS,
    sampler_start_et: time = SAMPLER_START_ET,
    cadence_seconds: int = CADENCE_SECONDS,
    min_completeness: float = MIN_COMPLETENESS,
    max_gap_minutes: float = MAX_CONTIGUOUS_GAP_MINUTES,
    cadence_tolerance_seconds: float = CADENCE_TOLERANCE_SECONDS,
    approved_collector_versions: tuple[str, ...] = (),
    signoff_date: date = REGISTRATION_SIGNOFF_DATE,
    governing_denominator: Denominator | None = None,
    denominator_ruling: str | None = None,
    include_census_diagnostic: bool = False,
    session_close_source: str | None = None,
) -> AdmissibilityReport:
    """Adjudicate both feeds independently and jointly. Strictly read-only.

    The denominator is fixed by the owner ruling 2026-08-18 (the half-open
    09:25-to-close sampler grid) and is not a caller's choice; a request for the
    census window is served as a labelled diagnostic and the reinterpretation is
    recorded. ``denominator_ruling`` may add a caller-side citation on top of the
    ruling text this module already carries.

    ``session_close_utc`` remains an explicit input: this module holds no market
    calendar (see ``THRESHOLD_SOURCES['session_close']``). ``session_close_source``
    is the caller's statement of where the close came from, echoed into the
    record so a reader can see whether the close was authoritative.
    """
    fu = frozen_universe or load_frozen_universe()
    latch = pins or AcquisitionPins()
    store = CaptureStore(Path(root))
    governing, want_census, ruling_note = resolve_denominator(
        governing_denominator, census_diagnostic=include_census_diagnostic
    )

    report = AdmissibilityReport(
        root=Path(root).resolve(),
        session=session,
        generated_at=datetime.now(UTC).isoformat(),
    )
    report.inputs = {
        "capture_root": str(Path(root).resolve()),
        "session_date": session.isoformat(),
        "feeds": list(feeds),
        "session_close_utc": _iso(session_close_utc),
        "session_close_et": _iso(session_close_utc.astimezone(ET)) if session_close_utc else None,
        "universe_file": str(fu.path),
        "approved_collector_versions": list(approved_collector_versions),
        "governing_denominator": str(governing),
        "governing_denominator_requested": (
            str(governing_denominator) if governing_denominator else None
        ),
        "governing_denominator_ruling_applied": ruling_note,
        "denominator_ruling": denominator_ruling or OWNER_RULING_DENOMINATOR,
        "owner_ruling": OWNER_RULING_DENOMINATOR,
        "owner_ruling_date": OWNER_RULING_DATE.isoformat(),
        "census_diagnostic_included": want_census,
        "session_close_source": (
            session_close_source
            or "SUPPLIED BY CALLER, PROVENANCE UNSTATED — this module holds no "
            "market calendar; see threshold_sources.session_close"
        ),
        "unratified_after_ruling": sorted(UNRATIFIED_AFTER_RULING),
        "read_only": True,
    }
    report.thresholds = {
        "min_completeness": min_completeness,
        "max_contiguous_gap_minutes": max_gap_minutes,
        "cadence_seconds": cadence_seconds,
        "cadence_tolerance_seconds": cadence_tolerance_seconds,
        "sampler_start_et": sampler_start_et.isoformat(),
        "bar_window_et": [BAR_WINDOW_ET[0].isoformat(), BAR_WINDOW_ET[1].isoformat()],
        "registration_signoff_date": signoff_date.isoformat(),
        "expected_credential_fingerprint": latch.key_fingerprint,
        "expected_account_number": latch.account_number,
        "expected_universe_symbols": len(fu.symbols),
        "expected_universe_sha256": fu.universe_sha256,
        "expected_universe_file_sha256_lf": UNIVERSE_SYMBOLS_FILE_SHA256_LF,
        "collector_abort_after_consecutive_failed_cycles": MAX_CONSECUTIVE_FAILED_CYCLES,
        "expected_cycles_denominator": str(governing),
        "expected_cycles_grid": (
            "HALF-OPEN — sampler_start <= t < sampler_end (395 slots on a normal "
            "16:00 ET close, 215 on a 13:00 early close, 0 on a non-session)"
        ),
        "expected_cycles_for_this_session": expected_cycles_for_session(
            session,
            session_close_utc,
            start_et=sampler_start_et,
            cadence_seconds=cadence_seconds,
        ),
        "review_window_days": REVIEW_WINDOW_DAYS,
        "period_holdout_offset_days": PERIOD_HOLDOUT_OFFSET_DAYS,
        "period_holdout_days": PERIOD_HOLDOUT_DAYS,
        "holdout_symbol_count": HOLDOUT_SYMBOL_COUNT,
        "go_floor_evaluable": GO_FLOOR_EVALUABLE,
        "go_floor_passes": GO_FLOOR_PASSES,
    }

    report.joint.append(
        ConditionResult(
            "universe_config_integrity",
            Outcome.PASS if fu.file_sha256_lf == UNIVERSE_SYMBOLS_FILE_SHA256_LF else Outcome.FAIL,
            {"file": str(fu.path), "sha256_lf": fu.file_sha256_lf},
            {"sha256_lf": UNIVERSE_SYMBOLS_FILE_SHA256_LF},
            "the frozen universe file is the artifact signed at §8 (LF-normalised "
            "bytes, so a CRLF working copy does not spuriously fail)",
            THRESHOLD_SOURCES["universe_symbols_file_sha256"],
        )
    )
    report.joint.append(
        ConditionResult(
            "universe_sha_expectation",
            Outcome.PASS if fu.universe_sha256 == EXPECTED_UNIVERSE_SHA256 else Outcome.FAIL,
            fu.universe_sha256,
            EXPECTED_UNIVERSE_SHA256,
            "the universe hash derived from the frozen file equals the recorded "
            "expectation the manifests are supposed to carry",
            THRESHOLD_SOURCES["universe_sha256"],
        )
    )

    for feed in feeds:
        report.feeds[feed] = assess_feed(
            store,
            PartitionRef(feed=feed, session=session),
            frozen_universe=fu,
            session_close_utc=session_close_utc,
            pins=latch,
            sampler_start_et=sampler_start_et,
            cadence_seconds=cadence_seconds,
            min_completeness=min_completeness,
            max_gap_minutes=max_gap_minutes,
            cadence_tolerance_seconds=cadence_tolerance_seconds,
            approved_collector_versions=approved_collector_versions,
            signoff_date=signoff_date,
            governing_denominator=governing_denominator,
            include_census_diagnostic=include_census_diagnostic,
        )

    report.joint.extend(_joint_conditions(report, feeds))
    return report


def _joint_conditions(report: AdmissibilityReport, feeds: tuple[str, ...]) -> list[ConditionResult]:
    out: list[ConditionResult] = []
    present = {
        f: report.feeds[f] for f in feeds if f in report.feeds and report.feeds[f].stats.present
    }
    out.append(
        ConditionResult(
            "both_feeds_present",
            Outcome.PASS if set(present) == set(feeds) else Outcome.FAIL,
            sorted(present),
            sorted(feeds),
            "SIP and IEX are captured as paired partitions; a lone feed cannot "
            "support the IEX-vs-SIP census the corpus exists for",
            f"{REGISTRATION_DOC} §7 control 2 (paired IEX observations)",
        )
    )

    pair_source = (
        f"{REGISTRATION_DOC} §7 control 2; "
        "app/research/capture/collector.py sample_quotes_cycle shares one cycle_ts"
    )
    if len(present) < 2:
        out.append(
            ConditionResult(
                "paired_cycles",
                Outcome.NOT_EVALUABLE,
                sorted(present),
                "identical cycle_ts sets across feeds",
                "fewer than two feeds carry a quote stream",
                pair_source,
            )
        )
        return out

    keys = sorted(present)
    a = set(present[keys[0]].stats.observed_ts)
    b = set(present[keys[1]].stats.observed_ts)
    out.append(
        ConditionResult(
            "paired_cycles",
            Outcome.PASS if a == b else Outcome.FAIL,
            {
                keys[0]: len(a),
                keys[1]: len(b),
                f"only_in_{keys[0]}": len(a - b),
                f"only_in_{keys[1]}": len(b - a),
            },
            "identical cycle_ts sets across feeds",
            "the collector writes one cycle_ts per cycle to both feeds; a divergence "
            "means one feed lost observations the other kept",
            pair_source,
        )
    )
    return out


# --- program-review governance (owner rulings 2026-08-18) ---------------------
#
# NOTE ON PLACEMENT. The three helpers below are MDQ-001 PROGRAM-review
# arithmetic (the K1-K6 disposition, the 60/48-day holdout window, the
# exploration embargo), not PARTITION admissibility, which is what the rest of
# this module adjudicates. They live here because they are small, pure, share
# this module's frozen-value/provenance discipline, and MDQ-001 has no other
# governance module yet — a second file for three functions would be worse. If
# an `app/research/capture/review.py` (or an MDQ-001 review module elsewhere)
# is ever created for the K1-K6 verdict itself, these move there wholesale;
# nothing here depends on partition state, so the move is a cut and paste.


class Disposition(StrEnum):
    """The ruled review outcome. HOLD always carries ONE stated extension."""

    GO = "GO"
    STOP = "STOP"
    HOLD = "HOLD"


@dataclass(frozen=True)
class ReviewDisposition:
    """A disposition plus the counts and the rule that produced it."""

    disposition: Disposition
    evaluable: int
    passed: int
    extension_required: bool
    rule: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "disposition": str(self.disposition),
            "evaluable": self.evaluable,
            "passed": self.passed,
            "extension_required": self.extension_required,
            "rule": self.rule,
            "source": THRESHOLD_SOURCES["verdict_table"],
        }


def review_disposition(evaluable: int, passed: int) -> ReviewDisposition:
    """The ruled verdict table, in full.

    ===========================  ===============================
    Review result                Disposition
    ===========================  ===============================
    >=2 evaluable and >=2 PASS   GO
    >=2 evaluable and 0 PASS     STOP
    <2 evaluable                 HOLD, one stated extension
    >=2 evaluable, exactly 1     HOLD, one stated extension
    ===========================  ===============================

    The registration's stale §4 wording ("keep if ANY K criterion is met") is
    superseded by the ratified §8.1 floor, and the fourth row is the owner's
    closure of a genuine hole: §8.1 defined the floor and the failure case but
    left ">=2 evaluable, exactly 1 PASS" undefined.

    A NOT_EVALUABLE criterion neither passes nor fails: it is absent from both
    counts and can never contribute to the GO floor. That is why ``passed`` may
    not exceed ``evaluable`` — a criterion that passed was, by definition,
    evaluable.
    """
    if evaluable < 0 or passed < 0:
        raise ValueError("criterion counts cannot be negative")
    if passed > evaluable:
        raise ValueError(
            f"passed ({passed}) exceeds evaluable ({evaluable}): a criterion that "
            "PASSed was necessarily evaluable"
        )
    if evaluable < GO_FLOOR_EVALUABLE:
        return ReviewDisposition(
            Disposition.HOLD,
            evaluable,
            passed,
            True,
            f"fewer than {GO_FLOOR_EVALUABLE} criteria are evaluable — the GO floor "
            "cannot be tested at all, so the review HOLDs for one stated extension",
        )
    if passed >= GO_FLOOR_PASSES:
        return ReviewDisposition(
            Disposition.GO,
            evaluable,
            passed,
            False,
            f"{GO_FLOOR_EVALUABLE}+ criteria evaluable and {GO_FLOOR_PASSES}+ PASS "
            "— the ratified §8.1 floor is met",
        )
    if passed == 0:
        return ReviewDisposition(
            Disposition.STOP,
            evaluable,
            passed,
            False,
            f"{GO_FLOOR_EVALUABLE}+ criteria evaluable and none PASS — the program "
            "was testable and failed",
        )
    return ReviewDisposition(
        Disposition.HOLD,
        evaluable,
        passed,
        True,
        f"{GO_FLOOR_EVALUABLE}+ criteria evaluable and exactly 1 PASS — short of "
        "the GO floor but not a clean failure; the owner ruling assigns this to "
        "HOLD with one stated extension (the hole ratified §8.1 left open)",
    )


def review_disposition_from_outcomes(outcomes: dict[str, Outcome]) -> ReviewDisposition:
    """Apply the ruled table to per-criterion outcomes (K1-K6).

    NOT_EVALUABLE entries are dropped from both counts rather than being read as
    failures — the same first-class treatment the §7.1 conditions get.
    """
    evaluable = [o for o in outcomes.values() if o is not Outcome.NOT_EVALUABLE]
    return review_disposition(len(evaluable), sum(1 for o in evaluable if o is Outcome.PASS))


@dataclass(frozen=True)
class HoldoutWindow:
    """The ruled 60-day review window and its final-12-date period holdout.

    Half-open and date-based throughout. Offsets 0-59 are the review window;
    offsets 48-59 are the period holdout, exactly 12 CALENDAR dates. The
    boundary is never slid for weekends or holidays: those dates simply contain
    no trading partition. Sliding would silently convert "the final 20% of the
    window" into "the final 12 trading sessions", which is a different rule.
    """

    review_start_date: date
    review_end_exclusive: date
    period_holdout_start: date

    @property
    def review_dates(self) -> tuple[date, ...]:
        return tuple(
            self.review_start_date + timedelta(days=offset) for offset in range(REVIEW_WINDOW_DAYS)
        )

    @property
    def holdout_dates(self) -> tuple[date, ...]:
        return tuple(d for d in self.review_dates if d >= self.period_holdout_start)

    def in_review(self, session_date: date) -> bool:
        return self.review_start_date <= session_date < self.review_end_exclusive

    def in_period_holdout(self, session_date: date) -> bool:
        return self.period_holdout_start <= session_date < self.review_end_exclusive

    def as_dict(self) -> dict[str, Any]:
        return {
            "review_start_date": self.review_start_date.isoformat(),
            "review_end_exclusive": self.review_end_exclusive.isoformat(),
            "period_holdout_start": self.period_holdout_start.isoformat(),
            "review_window_days": REVIEW_WINDOW_DAYS,
            "period_holdout_days": len(self.holdout_dates),
            "boundary": "half-open, calendar dates, never slid for weekends or holidays",
            "source": THRESHOLD_SOURCES["holdout_window"],
        }


def holdout_window(review_start_date: date) -> HoldoutWindow:
    """Build the ruled window from the first admissible governed capture's date."""
    return HoldoutWindow(
        review_start_date=review_start_date,
        review_end_exclusive=review_start_date + timedelta(days=REVIEW_WINDOW_DAYS),
        period_holdout_start=review_start_date + timedelta(days=PERIOD_HOLDOUT_OFFSET_DAYS),
    )


def exploratory_access_allowed(
    symbol: str,
    session_date: date,
    *,
    holdout_symbols: frozenset[str] | set[str] | tuple[str, ...],
    window: HoldoutWindow,
) -> bool:
    """The ruled embargo predicate. Pure: no filesystem, no network, no corpus.

    ``exploratory_access_allowed = symbol NOT IN holdout_symbols
                                   AND session_date < period_holdout_start``

    The holdout symbols are quarantined for the whole window; every symbol is
    quarantined from ``period_holdout_start`` onward. Note the second clause is
    a bare ``<``, not "inside the window": a date after the window has ended is
    not thereby released, because nothing about the embargo says it should be.
    """
    return symbol.upper() not in {s.upper() for s in holdout_symbols} and (
        session_date < window.period_holdout_start
    )


# --- reporting ---------------------------------------------------------------

_MARK = {
    Outcome.PASS: "PASS",
    Outcome.FAIL: "FAIL",
    Outcome.NOT_EVALUABLE: "NOT-EVALUABLE",
}
_RULE = "=" * 78
_THIN = "-" * 78


_TEXT_VALUE_LIMIT = 220


def _abbrev(value: Any) -> str:
    text = repr(value)
    if len(text) <= _TEXT_VALUE_LIMIT:
        return text
    return f"{text[:_TEXT_VALUE_LIMIT]}... (full value in --json)"


def _render_condition(c: ConditionResult, out: list[str]) -> None:
    out.append(f"  [{_MARK[c.outcome]:^13}] {c.condition}")
    out.append(f"      observed : {_abbrev(c.observed)}")
    out.append(f"      expected : {_abbrev(c.expected)}")
    out.append(f"      meaning  : {c.detail}")


def render_text(report: AdmissibilityReport) -> str:
    """Human-readable report. Self-describing: every threshold used is printed."""
    out: list[str] = []
    out.append(_RULE)
    out.append("MDQ-001 PARTITION ADMISSIBILITY")
    out.append("registration §4 'Admissible corpus' / implementation plan §7.1")
    out.append(_RULE)
    out.append(f"tool           : {ADMISSIBILITY_VERSION}  (offline, strictly read-only)")
    out.append(f"generated at   : {report.generated_at}")
    out.append(f"capture root   : {report.inputs['capture_root']}")
    out.append(f"session date   : {report.inputs['session_date']}")
    out.append(
        f"session close  : {report.inputs['session_close_et']} ET "
        f"({report.inputs['session_close_utc']})"
    )
    out.append(f"universe file  : {report.inputs['universe_file']}")
    out.append(f"close source   : {report.inputs['session_close_source']}")
    out.append("")
    out.append("Owner ruling in force")
    out.append(_THIN)
    for line in _wrap(report.inputs["owner_ruling"], 74):
        out.append(f"  {line}")
    out.append(f"  applied: {report.inputs['governing_denominator_ruling_applied']}")
    out.append("")
    out.append("Still unratified after this ruling (never scored as frozen values)")
    out.append(_THIN)
    for key in report.inputs["unratified_after_ruling"]:
        out.append(f"  - {key}")
    out.append("")
    out.append("Frozen thresholds used (provenance in the --json output)")
    out.append(_THIN)
    for key, value in report.thresholds.items():
        out.append(f"  {key:<48} {value}")
    out.append("")
    out.append("Joint conditions (shared artifacts / both feeds)")
    out.append(_THIN)
    for c in report.joint:
        _render_condition(c, out)

    for feed in sorted(report.feeds):
        fa = report.feeds[feed]
        out.append("")
        out.append(f"Feed '{feed}' — {fa.outcome}")
        out.append(_THIN)
        if fa.derivation:
            d = fa.derivation
            out.append(f"  {d['formula']}")
            out.append(f"  {d['grid']}")
            numerator = d["numerator"]
            out.append(
                f"  observed_cycles = {numerator['observed_cycles']} "
                f"(method: {numerator['method']})"
            )
            out.append(f"  governing denominator: {d['governing_denominator']}")
            out.append("")
            out.append(
                f"    {'session_scope':<15} {'window (ET)':<13} {'expected':>8} "
                f"{'ratio':>8} {'>=98%':>6} {'max gap':>9} {'<=10m':>6}  role"
            )
            for name, r in sorted(d["readings"].items()):
                window = f"{r['window_start_et'][11:16]}-{r['window_end_et_exclusive'][11:16]}"
                role = "SCORED" if name == str(RULED_DENOMINATOR) else "diagnostic only"
                out.append(
                    f"    {name:<15} {window:<13} {r['expected_cycles']:>8} "
                    f"{r['completeness']:>7.2%} "
                    f"{'yes' if r['meets_min_completeness'] else 'NO':>6} "
                    f"{r['max_contiguous_gap_minutes']:>8.2f}m "
                    f"{'yes' if r['meets_max_contiguous_gap'] else 'NO':>6}  {role}"
                )
            timing = d["sampler_timing_semantics"]
            out.append(f"    loop seen here : {timing['loop_observed_in_this_partition']}")
            out.append(
                "    max per-cycle overhead still meeting the floor: "
                f"{timing['max_per_cycle_overhead_seconds_meeting_min_completeness_fixed_delay']}s"
                " under the legacy fixed-delay loop, "
                f"{timing['max_per_cycle_overhead_seconds_meeting_min_completeness_fixed_rate']}s"
                " under the ruled fixed-rate loop"
            )
            out.append("")
        for c in fa.conditions:
            _render_condition(c, out)

    out.append("")
    out.append(_RULE)
    out.append(f"VERDICT: {report.verdict}   (exit code {report.exit_code})")
    if report.verdict is not Verdict.ADMISSIBLE:
        out.append("Not passing:")
        for scope, c in report.labelled_conditions():
            if c.outcome is not Outcome.PASS:
                out.append(f"  - [{scope}] {c.condition}: {_MARK[c.outcome]}")
                out.append(f"      {c.detail}")
    out.append(_RULE)
    return "\n".join(out)


def _wrap(text: str, width: int) -> list[str]:
    """Greedy word wrap — stdlib-free so the report stays dependency-light."""
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if len(candidate) > width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def render_json(report: AdmissibilityReport) -> str:
    return json.dumps(report.as_dict(), indent=2, default=str)


__all__ = [
    "ADMISSIBILITY_SCHEMA",
    "ADMISSIBILITY_VERSION",
    "CADENCE_SECONDS",
    "CADENCE_TOLERANCE_SECONDS",
    "CRITERIA",
    "EXIT_ADMISSIBLE",
    "EXIT_NOT_ADMISSIBLE",
    "EXIT_UNDETERMINED",
    "EXPECTED_UNIVERSE_SHA256",
    "FIXED_RATE_CLOSE_GRACE_PERIODS",
    "GO_FLOOR_EVALUABLE",
    "GO_FLOOR_PASSES",
    "HOLDOUT_SYMBOL_COUNT",
    "LEGACY_FIXED_DELAY_CLOSE_GRACE_PERIODS",
    "MAX_CONTIGUOUS_GAP_MINUTES",
    "MIN_COMPLETENESS",
    "OWNER_RULING_DATE",
    "OWNER_RULING_DENOMINATOR",
    "PERIOD_HOLDOUT_DAYS",
    "PERIOD_HOLDOUT_OFFSET_DAYS",
    "REGISTRATION_SIGNOFF_DATE",
    "REVIEW_WINDOW_DAYS",
    "RULED_DENOMINATOR",
    "SAMPLER_START_ET",
    "SLOT_INDEX_FIELD",
    "SLOT_TS_FIELD",
    "THRESHOLD_SOURCES",
    "UNIVERSE_SYMBOLS_FILE_SHA256_LF",
    "UNRATIFIED_AFTER_RULING",
    "AdmissibilityReport",
    "ConditionResult",
    "CountMethod",
    "CycleStats",
    "Denominator",
    "Disposition",
    "FeedAssessment",
    "FrozenUniverse",
    "HoldoutWindow",
    "ObservedCount",
    "Outcome",
    "ReadingResult",
    "ReviewDisposition",
    "Verdict",
    "assess_feed",
    "assess_partition",
    "count_observed_cycles",
    "default_universe_file",
    "expected_cycles",
    "expected_cycles_for_session",
    "exploratory_access_allowed",
    "holdout_window",
    "load_frozen_universe",
    "max_contiguous_gap_minutes",
    "read_cycle_stats",
    "render_json",
    "render_text",
    "resolve_denominator",
    "review_disposition",
    "review_disposition_from_outcomes",
    "roll_up",
    "sampler_window",
    "slot_grid",
    "universe_sha256",
]
