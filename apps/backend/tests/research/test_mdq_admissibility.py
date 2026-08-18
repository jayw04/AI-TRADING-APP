"""MDQ-001 §7.1 admissibility unit tests.

Every fixture partition is built inside ``tmp_path``. Nothing here goes near a
real capture root, and one test proves byte-for-byte that adjudication leaves
the corpus untouched (owner rule: validating a write-capable path uses a
read-only or isolated copy, never a "benign" stub).

No network, no Alpaca SDK, no credentials — the module under test is offline by
construction (ADR 0051, registration §7 control 1).

These tests are written against the OWNER RULING 2026-08-18: the denominator is
the HALF-OPEN sampler grid ``09:25 ET <= t < official NYSE close`` at 60s — 395
slots on a normal close, 215 on a 13:00 early close, 0 on a non-session. The
04:00-16:00 ET window is the EOD bar census scope and appears here as a labelled
diagnostic, never as a scored denominator. The 98% floor and the 10-minute gap
rule are unchanged.
"""

from __future__ import annotations

import hashlib
import itertools
import json
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from app.research.capture.admissibility import (
    CADENCE_SECONDS,
    ET,
    EXIT_ADMISSIBLE,
    EXIT_NOT_ADMISSIBLE,
    EXIT_UNDETERMINED,
    EXPECTED_UNIVERSE_SHA256,
    GO_FLOOR_EVALUABLE,
    GO_FLOOR_PASSES,
    HOLDOUT_SYMBOL_COUNT,
    MAX_CONTIGUOUS_GAP_MINUTES,
    MIN_COMPLETENESS,
    OWNER_RULING_DENOMINATOR,
    PERIOD_HOLDOUT_DAYS,
    PERIOD_HOLDOUT_OFFSET_DAYS,
    REGISTRATION_SIGNOFF_DATE,
    REVIEW_WINDOW_DAYS,
    RULED_DENOMINATOR,
    SAMPLER_START_ET,
    SLOT_INDEX_FIELD,
    SLOT_TS_FIELD,
    THRESHOLD_SOURCES,
    UNIVERSE_SYMBOLS_FILE_SHA256_LF,
    UNRATIFIED_AFTER_RULING,
    ConditionResult,
    CountMethod,
    Denominator,
    Disposition,
    Outcome,
    Verdict,
    assess_partition,
    count_observed_cycles,
    expected_cycles,
    expected_cycles_for_session,
    exploratory_access_allowed,
    holdout_window,
    load_frozen_universe,
    max_contiguous_gap_minutes,
    read_cycle_stats,
    render_json,
    render_text,
    resolve_denominator,
    review_disposition,
    review_disposition_from_outcomes,
    roll_up,
    sampler_window,
    slot_grid,
    universe_sha256,
)
from app.research.capture.collector import CAPTURE_MODE_EOD_BARS, CAPTURE_MODE_SAMPLER
from app.research.capture.identity import AcquisitionPins
from app.research.capture.store import CaptureStore, PartitionRef

# The first scheduled governed session (the deployment's first timer fire).
SESSION = date(2026, 8, 18)
CLOSE = datetime.combine(SESSION, time(16, 0), tzinfo=ET).astimezone(UTC)
EARLY_CLOSE = datetime.combine(SESSION, time(13, 0), tzinfo=ET).astimezone(UTC)
WINDOW_START = datetime.combine(SESSION, SAMPLER_START_ET, tzinfo=ET).astimezone(UTC)

# RULED half-open grid: 09:25 <= t < 16:00 at 60s. 395 minutes => 395 slots.
# (The superseded inclusive-endpoint reading gave 396.)
EXPECTED_CYCLES = 395
EXPECTED_CYCLES_EARLY_CLOSE = 215
# 04:00 -> 16:00 ET, the EOD bar census scope. DIAGNOSTIC ONLY.
EXPECTED_CYCLES_CENSUS = 720
# 0.98 * 395 = 387.1, so the floor admits at most 7 missing cycles.
MIN_OBSERVED_FOR_FLOOR = 388
MAX_MISSING_UNDER_FLOOR = EXPECTED_CYCLES - MIN_OBSERVED_FOR_FLOOR

RULED_SAMPLER = Denominator.SAMPLER_WINDOW
CRITERION_KEYS = ("K1", "K2", "K3", "K4", "K5", "K6")

UNIVERSE = tuple(load_frozen_universe().symbols)


# --- fixture construction ------------------------------------------------------


def _quote_records(
    cycle_ts: str,
    symbols: tuple[str, ...],
    *,
    slot_ts: str | None = None,
    slot_index: int | None = None,
) -> list[dict[str, Any]]:
    extra: dict[str, Any] = {}
    if slot_ts is not None:
        extra[SLOT_TS_FIELD] = slot_ts
    if slot_index is not None:
        extra[SLOT_INDEX_FIELD] = slot_index
    return [
        {
            "cycle_ts": cycle_ts,
            "symbol": sym,
            "quote_ts": cycle_ts,
            "bid": 99.0,
            "ask": 101.0,
            "bid_size": 1.0,
            "ask_size": 2.0,
            **extra,
        }
        for sym in symbols
    ]


def build_partition(
    root: Path,
    feed: str,
    *,
    session: date = SESSION,
    cycles: int = EXPECTED_CYCLES,
    skip_slots: frozenset[int] = frozenset(),
    error_slots: frozenset[int] = frozenset(),
    universe: tuple[str, ...] = UNIVERSE,
    label: str | None = None,
    freeze: bool = True,
    with_bars: bool = True,
    provenance_overrides: dict[str, Any] | None = None,
    cadence_seconds: int = CADENCE_SECONDS,
    slot_fields: bool = False,
    slot_field_slots: frozenset[int] | None = None,
    cycle_ts_jitter_seconds: float = 0.0,
    slot_index_offset: int = 0,
    slot_ts_offset_seconds: float = 0.0,
) -> PartitionRef:
    """Build one capture partition in tmp_path exactly as the collector would.

    ``slot_fields`` emits the fixed-rate collector's ``scheduled_slot_ts`` /
    ``slot_index`` on every cycle; ``slot_field_slots`` emits them on a subset,
    which is how a partition straddling the collector change is simulated.
    """
    pins = AcquisitionPins()
    store = CaptureStore(root)
    ref = PartitionRef(feed=feed, session=session)
    window_start = datetime.combine(session, SAMPLER_START_ET, tzinfo=ET).astimezone(UTC)

    for slot in range(cycles):
        if slot in skip_slots:
            continue
        scheduled = window_start + timedelta(seconds=slot * cadence_seconds)
        cycle_ts = (scheduled + timedelta(seconds=cycle_ts_jitter_seconds)).isoformat()
        instrumented = slot_fields or (slot_field_slots is not None and slot in slot_field_slots)
        if slot in error_slots:
            records: list[dict[str, Any]] = [
                {"cycle_ts": cycle_ts, "feed_error": "ConnectionError: transient"}
            ]
        elif instrumented:
            records = _quote_records(
                cycle_ts,
                universe,
                slot_ts=(scheduled + timedelta(seconds=slot_ts_offset_seconds)).isoformat(),
                slot_index=slot + slot_index_offset,
            )
        else:
            records = _quote_records(cycle_ts, universe)
        store.append_jsonl(ref, "quotes", records)

    if with_bars:
        store.write_parquet(
            ref,
            "bars",
            "bars_1min",
            pd.DataFrame({"symbol": list(universe), "close": [1.0] * len(universe)}),
        )

    if freeze:
        provenance: dict[str, Any] = {
            **({"label": label} if label else {}),
            "provider": "alpaca",
            "entitlement": "algo_trader_plus (account-7 login)",
            "credential_fingerprint": pins.key_fingerprint,
            "account_number": pins.account_number,
            "alpaca_py_version": "0.42.0",
            "capture_modes": [CAPTURE_MODE_SAMPLER, CAPTURE_MODE_EOD_BARS],
            "universe": sorted(universe),
            "universe_sha256": universe_sha256(universe),
        }
        provenance.update(provenance_overrides or {})
        store.freeze(ref, provenance=provenance)
    return ref


def build_admissible_corpus(root: Path, **kwargs: Any) -> None:
    for feed in ("iex", "sip"):
        build_partition(root, feed, **kwargs)


def assess(root: Path, **kwargs: Any) -> Any:
    """Adjudicate with the module's default posture — i.e. under the ruling."""
    kwargs.setdefault("session_close_utc", CLOSE)
    return assess_partition(root, kwargs.pop("session", SESSION), **kwargs)


def assess_ruled(root: Path, **kwargs: Any) -> Any:
    """Adjudicate with the ruled denominator named explicitly (same result)."""
    kwargs.setdefault("governing_denominator", RULED_SAMPLER)
    kwargs.setdefault("denominator_ruling", "test fixture ruling")
    return assess(root, **kwargs)


def reading(report: Any, feed: str, denominator: Denominator) -> Any:
    return report.feeds[feed].readings[str(denominator)]


def outcome_of(report: Any, condition: str, feed: str | None = None) -> Outcome:
    pool = report.feeds[feed].conditions if feed else report.joint
    matches = [c for c in pool if c.condition == condition]
    assert matches, f"condition {condition!r} not evaluated"
    return matches[0].outcome


def condition_of(report: Any, condition: str, feed: str | None = None) -> ConditionResult:
    pool = report.feeds[feed].conditions if feed else report.joint
    return next(c for c in pool if c.condition == condition)


# --- the frozen values themselves ----------------------------------------------


def test_frozen_thresholds_are_the_signed_registration_values() -> None:
    """Registration §8 sign-off block, 'Partition completeness' and 'Sampler
    cadence/retry' lines (accepted as proposed, signed 2026-08-17). The
    2026-08-18 ruling bound the denominator and explicitly did NOT weaken these."""
    assert MIN_COMPLETENESS == 0.98
    assert MAX_CONTIGUOUS_GAP_MINUTES == 10.0
    assert CADENCE_SECONDS == 60
    assert date(2026, 8, 17) == REGISTRATION_SIGNOFF_DATE


def test_every_threshold_carries_a_documented_source() -> None:
    for key, source in THRESHOLD_SOURCES.items():
        assert source.strip(), f"{key} has no provenance string"
        assert len(source) > 40, f"{key}'s provenance is too thin to audit: {source!r}"


def test_the_ruling_is_quoted_verbatim_and_cited_by_the_thresholds_it_binds() -> None:
    """The record must carry the ruling itself, not a paraphrase of it."""
    assert "04:00-16:00 interval is the EOD one-minute bar census scope" in (
        OWNER_RULING_DENOMINATOR
    )
    assert "sampler_start <= t < sampler_end" in OWNER_RULING_DENOMINATOR
    assert "395" in OWNER_RULING_DENOMINATOR
    assert "215" in OWNER_RULING_DENOMINATOR
    for key in ("expected_cycles_denominator", "sampler_start_et"):
        assert "2026-08-18" in THRESHOLD_SOURCES[key]


def test_the_ruling_closed_exactly_two_of_the_open_questions() -> None:
    """The denominator and the sampler start are ruled; nothing else became
    silently ratified as a side effect."""
    assert "RESOLVED BY OWNER RULING" in THRESHOLD_SOURCES["expected_cycles_denominator"]
    assert "RULED 2026-08-18" in THRESHOLD_SOURCES["sampler_start_et"]
    assert set(UNRATIFIED_AFTER_RULING) == {
        "cadence_tolerance_seconds",
        "approved_collector_code_identity",
        "session_close_calendar_artifact",
    }
    for key, text in UNRATIFIED_AFTER_RULING.items():
        assert "UNRATIFIED" in text or "NOT SETTLED" in text, key
    assert "NOT RATIFIED" in THRESHOLD_SOURCES["cadence_tolerance_seconds"]
    assert "NOT_EVALUABLE" in THRESHOLD_SOURCES["collector_code_identity"]


def test_frozen_universe_matches_the_signed_artifact() -> None:
    """Registration §8 'Phase-A capture universe' block: the symbols file's LF
    sha256, and the universe hash the manifests must carry."""
    fu = load_frozen_universe()
    assert len(fu.symbols) == 50
    assert fu.file_sha256_lf == UNIVERSE_SYMBOLS_FILE_SHA256_LF
    assert fu.universe_sha256 == EXPECTED_UNIVERSE_SHA256
    assert fu.universe_sha256.startswith("a022e399")


# --- the ruled arithmetic ------------------------------------------------------


def test_the_ruled_grid_is_half_open_and_yields_395() -> None:
    """09:25 ET inclusive to 16:00 ET exclusive at 60s = 395 slots, NOT 396."""
    start, end = sampler_window(SESSION, CLOSE)
    assert (end - start).total_seconds() == 395 * 60
    assert expected_cycles(start, end) == 395
    grid = slot_grid(start, end)
    assert len(grid) == 395
    assert grid[0] == start
    assert grid[-1] == end - timedelta(seconds=60)
    assert grid[-1] < end, "the close is not itself a slot"


def test_the_ruled_grid_tracks_an_early_close() -> None:
    start, end = sampler_window(SESSION, EARLY_CLOSE)
    assert expected_cycles(start, end) == EXPECTED_CYCLES_EARLY_CLOSE
    assert (end - start).total_seconds() == 215 * 60


@pytest.mark.parametrize(
    ("close", "expected"),
    [(CLOSE, 395), (EARLY_CLOSE, 215), (None, 0)],
)
def test_the_three_ruled_denominators(close: datetime | None, expected: int) -> None:
    """395 on a normal 16:00 close, 215 on a 13:00 early close, 0 on a
    non-session — the market calendar (the caller) decides which applies."""
    assert expected_cycles_for_session(SESSION, close) == expected


def test_a_degenerate_window_has_no_slots() -> None:
    assert expected_cycles(WINDOW_START, WINDOW_START) == 0


def test_expected_cycles_is_a_ceiling_not_a_floor_plus_one() -> None:
    """A partial trailing period still schedules its slot; an exact fit does
    not schedule the endpoint. This is the whole off-by-one."""
    assert expected_cycles(WINDOW_START, WINDOW_START + timedelta(seconds=60)) == 1
    assert expected_cycles(WINDOW_START, WINDOW_START + timedelta(seconds=61)) == 2
    assert expected_cycles(WINDOW_START, WINDOW_START + timedelta(seconds=120)) == 2


def test_expected_cycles_rejects_an_inverted_window() -> None:
    with pytest.raises(ValueError):
        expected_cycles(CLOSE, WINDOW_START)


def test_the_floor_admits_exactly_seven_missing_cycles() -> None:
    """Recorded arithmetic, re-derived under the 395-slot grid: 387/395 =
    97.97% fails and 388/395 = 98.23% passes."""
    assert (MIN_OBSERVED_FOR_FLOOR - 1) / EXPECTED_CYCLES < MIN_COMPLETENESS
    assert MIN_OBSERVED_FOR_FLOOR / EXPECTED_CYCLES >= MIN_COMPLETENESS
    assert MAX_MISSING_UNDER_FLOOR == 7


def test_max_gap_includes_both_window_edges() -> None:
    mid = WINDOW_START + timedelta(minutes=30)
    assert max_contiguous_gap_minutes((mid,), WINDOW_START, CLOSE) == pytest.approx(365.0)
    assert max_contiguous_gap_minutes((), WINDOW_START, CLOSE) == pytest.approx(395.0)


def test_max_gap_is_measured_on_timestamps_not_slots() -> None:
    """Cadence drift must not manufacture a phantom gap."""
    drifted = tuple(WINDOW_START + timedelta(seconds=int(k * 60.4)) for k in range(EXPECTED_CYCLES))
    gap = max_contiguous_gap_minutes(drifted, WINDOW_START, CLOSE)
    assert gap < 3.0


# --- the ruling itself is not a caller's choice ---------------------------------


def test_the_ruled_denominator_is_the_sampler_window() -> None:
    assert RULED_DENOMINATOR is Denominator.SAMPLER_WINDOW


@pytest.mark.parametrize("requested", [None, Denominator.SAMPLER_WINDOW])
def test_the_sampler_window_governs_whether_or_not_it_is_asked_for(
    requested: Denominator | None,
) -> None:
    governing, census, note = resolve_denominator(requested)
    assert governing is RULED_DENOMINATOR
    assert census is False
    assert note


def test_requesting_the_census_window_is_reinterpreted_not_obeyed() -> None:
    """The bar-census window may be SEEN, never SCORED — and the module says so
    rather than quietly substituting the sampler window."""
    governing, census, note = resolve_denominator(Denominator.CENSUS_WINDOW)
    assert governing is RULED_DENOMINATOR
    assert census is True
    assert "forbids it as the sampler denominator" in note


# --- cycle parsing --------------------------------------------------------------


def test_feed_error_cycles_count_to_the_denominator_only(tmp_path: Path) -> None:
    """Registration §8: 'feed_error counts toward the denominator only'."""
    build_partition(tmp_path, "sip", cycles=10, error_slots=frozenset({3, 4}))
    stats = read_cycle_stats(tmp_path / "sip" / SESSION.isoformat() / "quotes" / "samples.jsonl")
    assert stats.total_cycle_slots_seen == 10
    assert stats.observed_cycles == 8
    assert stats.error_cycles == 2
    assert stats.max_consecutive_error_cycles == 2


def test_missing_quote_stream_is_reported_absent_not_empty(tmp_path: Path) -> None:
    stats = read_cycle_stats(tmp_path / "nope" / "samples.jsonl")
    assert stats.present is False
    assert stats.observed_cycles == 0


def test_torn_final_line_is_tolerated_but_earlier_corruption_is_not(tmp_path: Path) -> None:
    """The store's append contract tolerates exactly one torn FINAL line."""
    build_partition(tmp_path, "sip", cycles=3, freeze=False)
    path = tmp_path / "sip" / SESSION.isoformat() / "quotes" / "samples.jsonl"

    torn = path.read_text(encoding="utf-8") + '{"cycle_ts": "2026-08-1'
    path.write_text(torn, encoding="utf-8")
    assert read_cycle_stats(path).torn_tail is True
    assert read_cycle_stats(path).malformed_lines == 0

    path.write_text('{"broken\n' + torn, encoding="utf-8")
    assert read_cycle_stats(path).malformed_lines == 1


# --- counting the numerator against the frozen slot grid ------------------------


def _stats(root: Path, feed: str = "sip") -> Any:
    return read_cycle_stats(root / feed / SESSION.isoformat() / "quotes" / "samples.jsonl")


def test_a_legacy_partition_falls_back_to_cycle_ts_and_says_so(tmp_path: Path) -> None:
    """Partitions written before the fixed-rate collector carry no scheduled
    slot. They stay adjudicable, and the record states the degraded method
    rather than presenting it as the ruled measure."""
    build_partition(tmp_path, "sip", cycles=20)
    count = count_observed_cycles(_stats(tmp_path), WINDOW_START, CLOSE)
    assert count.method is CountMethod.CYCLE_TS_FALLBACK
    assert count.observed_cycles == 20
    assert "FALLBACK" in count.note
    assert "predates the fixed-rate collector" in count.note


def test_a_fixed_rate_partition_is_counted_against_the_frozen_grid(tmp_path: Path) -> None:
    build_partition(tmp_path, "sip", cycles=EXPECTED_CYCLES, slot_fields=True)
    count = count_observed_cycles(_stats(tmp_path), WINDOW_START, CLOSE)
    assert count.method is CountMethod.SLOT_GRID
    assert count.observed_cycles == EXPECTED_CYCLES
    assert count.slots_filled[:3] == (0, 1, 2)
    assert count.off_grid_cycles == 0
    assert "SLOT GRID" in count.note


def test_the_slot_grid_count_ignores_wall_clock_jitter(tmp_path: Path) -> None:
    """The point of the ruling's preference: a cycle whose wall clock wobbled
    still occupies exactly the slot it was scheduled for."""
    build_partition(
        tmp_path, "sip", cycles=EXPECTED_CYCLES, slot_fields=True, cycle_ts_jitter_seconds=0.83
    )
    count = count_observed_cycles(_stats(tmp_path), WINDOW_START, CLOSE)
    assert count.method is CountMethod.SLOT_GRID
    assert count.observed_cycles == EXPECTED_CYCLES
    assert count.marks[0] == WINDOW_START, "marks come from the grid, not the wall clock"


def test_a_mixed_partition_never_mixes_the_two_methods(tmp_path: Path) -> None:
    """A partition straddling the collector change is counted wholly by the
    fallback, and the straddle is reported — it is two instruments in one file."""
    build_partition(tmp_path, "sip", cycles=20, slot_field_slots=frozenset(range(0, 10)))
    count = count_observed_cycles(_stats(tmp_path), WINDOW_START, CLOSE)
    assert count.method is CountMethod.CYCLE_TS_FALLBACK
    assert "MIXED PARTITION" in count.note
    assert "10 of 20" in count.note


def test_an_off_grid_scheduled_slot_is_excluded_and_reported(tmp_path: Path) -> None:
    build_partition(tmp_path, "sip", cycles=10, slot_fields=True, slot_ts_offset_seconds=17.0)
    count = count_observed_cycles(_stats(tmp_path), WINDOW_START, CLOSE)
    assert count.method is CountMethod.SLOT_GRID
    assert count.observed_cycles == 0
    assert count.off_grid_cycles == 10
    assert "not on the ruled grid" in count.note


def test_a_slot_index_disagreeing_with_the_slot_timestamp_is_reported(tmp_path: Path) -> None:
    """The absolute timestamp governs — it maps onto the ruled grid without
    assuming the collector's slot 0 is the ruled slot 0 — and the disagreement
    is surfaced rather than reconciled away."""
    build_partition(tmp_path, "sip", cycles=10, slot_fields=True, slot_index_offset=5)
    count = count_observed_cycles(_stats(tmp_path), WINDOW_START, CLOSE)
    assert count.method is CountMethod.SLOT_GRID
    assert count.observed_cycles == 10
    assert count.slot_index_disagreements == 10
    assert count.slots_filled == tuple(range(10))
    assert "disagreeing" in count.note


def test_two_cycles_claiming_one_slot_are_counted_once(tmp_path: Path) -> None:
    store = CaptureStore(tmp_path)
    ref = PartitionRef(feed="sip", session=SESSION)
    slot_ts = WINDOW_START.isoformat()
    for jitter in (0.0, 0.4):
        ts = (WINDOW_START + timedelta(seconds=jitter)).isoformat()
        store.append_jsonl(
            ref, "quotes", _quote_records(ts, UNIVERSE, slot_ts=slot_ts, slot_index=0)
        )
    count = count_observed_cycles(_stats(tmp_path), WINDOW_START, CLOSE)
    assert count.observed_cycles == 1
    assert count.duplicate_slot_cycles == 1


# --- the happy path -------------------------------------------------------------


def test_complete_corpus_is_admissible_under_the_ruling(tmp_path: Path) -> None:
    build_admissible_corpus(tmp_path)
    report = assess(tmp_path, approved_collector_versions=("mdq-collector/0.1.0",))
    assert report.verdict is Verdict.ADMISSIBLE, report.as_dict()["not_passing"]
    assert report.exit_code == EXIT_ADMISSIBLE
    for feed in ("iex", "sip"):
        fa = report.feeds[feed]
        r = reading(report, feed, RULED_SAMPLER)
        assert r.expected_cycles == EXPECTED_CYCLES
        assert r.completeness == pytest.approx(1.0)
        assert r.max_gap_minutes == pytest.approx(1.0)
        assert all(c.outcome is Outcome.PASS for c in fa.conditions)


def test_naming_the_ruled_denominator_explicitly_changes_nothing(tmp_path: Path) -> None:
    build_admissible_corpus(tmp_path)
    default = assess(tmp_path, approved_collector_versions=("mdq-collector/0.1.0",))
    named = assess_ruled(tmp_path, approved_collector_versions=("mdq-collector/0.1.0",))
    assert default.verdict is Verdict.ADMISSIBLE
    assert named.verdict is Verdict.ADMISSIBLE


def test_a_fixed_rate_corpus_is_admissible_and_counted_on_the_grid(tmp_path: Path) -> None:
    build_admissible_corpus(tmp_path, slot_fields=True, cycle_ts_jitter_seconds=0.6)
    report = assess(tmp_path, approved_collector_versions=("mdq-collector/0.1.0",))
    assert report.verdict is Verdict.ADMISSIBLE, report.as_dict()["not_passing"]
    r = reading(report, "sip", RULED_SAMPLER)
    assert r.count.method is CountMethod.SLOT_GRID
    assert r.observed_cycles == EXPECTED_CYCLES
    assert r.completeness == pytest.approx(1.0)


def test_report_states_the_expected_cycles_derivation(tmp_path: Path) -> None:
    build_admissible_corpus(tmp_path, cycles=5)
    derivation = assess(tmp_path).feeds["sip"].derivation
    assert derivation["formula"].startswith("expected_cycles = #{k >= 0")
    assert "HALF-OPEN" in derivation["grid"]
    assert derivation["cadence_seconds"] == 60
    assert derivation["governing_denominator"] == "sampler_window"
    assert "2026-08-18" in derivation["ruling"]
    sampler = derivation["readings"]["sampler_window"]
    assert sampler["expected_cycles"] == EXPECTED_CYCLES
    assert sampler["window_start_et"].startswith("2026-08-18T09:25")
    assert sampler["window_end_et_exclusive"].startswith("2026-08-18T16:00")


# --- the individual §7.1 conditions ---------------------------------------------


def test_unfrozen_partition_fails_freeze_completed(tmp_path: Path) -> None:
    build_partition(tmp_path, "sip", cycles=5, freeze=False)
    build_partition(tmp_path, "iex", cycles=5)
    report = assess(tmp_path)
    assert outcome_of(report, "freeze_completed", "sip") is Outcome.FAIL
    assert report.verdict is Verdict.NOT_ADMISSIBLE
    assert report.exit_code == EXIT_NOT_ADMISSIBLE


def test_absent_partition_fails_rather_than_being_skipped(tmp_path: Path) -> None:
    build_partition(tmp_path, "sip", cycles=5)
    report = assess(tmp_path)
    assert outcome_of(report, "freeze_completed", "iex") is Outcome.FAIL
    assert outcome_of(report, "both_feeds_present") is Outcome.FAIL


def test_malformed_manifest_fails_closed(tmp_path: Path) -> None:
    build_admissible_corpus(tmp_path, cycles=5)
    mpath = tmp_path / "sip" / SESSION.isoformat() / "manifest.json"
    mpath.write_text("{not json", encoding="utf-8")
    report = assess(tmp_path)
    assert outcome_of(report, "manifest_well_formed", "sip") is Outcome.FAIL
    assert report.verdict is Verdict.NOT_ADMISSIBLE


def test_tampered_bytes_fail_integrity(tmp_path: Path) -> None:
    build_admissible_corpus(tmp_path, cycles=5)
    path = tmp_path / "sip" / SESSION.isoformat() / "quotes" / "samples.jsonl"
    path.write_text("tampered\n", encoding="utf-8")
    report = assess(tmp_path)
    assert outcome_of(report, "integrity_verify", "sip") is Outcome.FAIL


def test_unmanifested_stray_fails_integrity(tmp_path: Path) -> None:
    build_admissible_corpus(tmp_path, cycles=5)
    (tmp_path / "sip" / SESSION.isoformat() / "rogue.txt").write_text("x", encoding="utf-8")
    report = assess(tmp_path)
    assert outcome_of(report, "integrity_verify", "sip") is Outcome.FAIL


def test_pre_registration_smoke_label_is_a_hard_exclusion(tmp_path: Path) -> None:
    """Registration §4 'Pre-registration quarantine'. A labelled partition is
    inadmissible even when everything else about it is perfect."""
    build_partition(tmp_path, "iex")
    build_partition(tmp_path, "sip", label="PRE_REGISTRATION_SMOKE")
    report = assess(tmp_path, approved_collector_versions=("mdq-collector/0.1.0",))
    assert outcome_of(report, "no_provenance_label", "sip") is Outcome.FAIL
    assert outcome_of(report, "no_provenance_label", "iex") is Outcome.PASS
    assert report.verdict is Verdict.NOT_ADMISSIBLE


def test_any_label_at_all_excludes_the_partition(tmp_path: Path) -> None:
    build_admissible_corpus(tmp_path, cycles=5, label="BACKFILL")
    report = assess(tmp_path)
    assert outcome_of(report, "no_provenance_label", "sip") is Outcome.FAIL


def test_capture_before_signoff_fails(tmp_path: Path) -> None:
    early = date(2026, 8, 14)  # the pre-registration smoke session
    close = datetime.combine(early, time(16, 0), tzinfo=ET).astimezone(UTC)
    build_partition(tmp_path, "sip", session=early, cycles=5)
    build_partition(tmp_path, "iex", session=early, cycles=5)
    report = assess_partition(tmp_path, early, session_close_utc=close)
    assert outcome_of(report, "captured_after_signoff", "sip") is Outcome.FAIL


def test_capture_on_the_signoff_date_itself_is_not_evaluable(tmp_path: Path) -> None:
    """§8 freezes a DATE, not a time of day: a same-day session cannot be shown
    to postdate the signature, so the condition fails closed as NOT EVALUABLE
    rather than being waved through. The denominator ruling did not touch this."""
    same_day = REGISTRATION_SIGNOFF_DATE
    close = datetime.combine(same_day, time(16, 0), tzinfo=ET).astimezone(UTC)
    build_partition(tmp_path, "sip", session=same_day, cycles=5)
    build_partition(tmp_path, "iex", session=same_day, cycles=5)
    report = assess_partition(tmp_path, same_day, session_close_utc=close)
    assert outcome_of(report, "captured_after_signoff", "sip") is Outcome.NOT_EVALUABLE
    assert report.verdict is not Verdict.ADMISSIBLE


def test_identity_provenance_must_be_the_pinned_acquisition_identity(tmp_path: Path) -> None:
    build_partition(tmp_path, "iex", cycles=5)
    build_partition(
        tmp_path,
        "sip",
        cycles=5,
        provenance_overrides={"credential_fingerprint": "deadbeefcafe"},
    )
    report = assess(tmp_path)
    assert outcome_of(report, "identity_latch_recorded", "sip") is Outcome.FAIL
    assert outcome_of(report, "identity_latch_recorded", "iex") is Outcome.PASS


def test_identity_expectations_are_the_account7_latch(tmp_path: Path) -> None:
    build_admissible_corpus(tmp_path, cycles=5)
    report = assess(tmp_path)
    assert report.thresholds["expected_credential_fingerprint"] == "b56421a28128"
    assert report.thresholds["expected_account_number"] == "PA3BGKRLH2AP"


def test_wrong_broker_account_fails(tmp_path: Path) -> None:
    build_partition(tmp_path, "iex", cycles=5)
    build_partition(
        tmp_path, "sip", cycles=5, provenance_overrides={"account_number": "PA3344TNRFYD"}
    )
    report = assess(tmp_path)
    assert outcome_of(report, "identity_latch_recorded", "sip") is Outcome.FAIL


def test_universe_mismatch_fails(tmp_path: Path) -> None:
    build_partition(tmp_path, "iex", cycles=5)
    build_partition(tmp_path, "sip", cycles=5, universe=UNIVERSE[:14])
    report = assess(tmp_path)
    assert outcome_of(report, "universe_match", "sip") is Outcome.FAIL
    assert outcome_of(report, "observed_symbols_match", "sip") is Outcome.FAIL


def test_feed_identity_must_match_the_partition_path(tmp_path: Path) -> None:
    build_admissible_corpus(tmp_path, cycles=5)
    mpath = tmp_path / "sip" / SESSION.isoformat() / "manifest.json"
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    manifest["feed"] = "iex"
    mpath.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    report = assess(tmp_path)
    assert outcome_of(report, "feed_identity_explicit", "sip") is Outcome.FAIL


def test_missing_bar_capture_is_scope_mismatch(tmp_path: Path) -> None:
    build_partition(tmp_path, "iex", cycles=5)
    build_partition(
        tmp_path,
        "sip",
        cycles=5,
        with_bars=False,
        provenance_overrides={"capture_modes": [CAPTURE_MODE_SAMPLER]},
    )
    report = assess(tmp_path)
    assert outcome_of(report, "capture_modes_complete", "sip") is Outcome.FAIL
    assert outcome_of(report, "expected_files_present", "sip") is Outcome.FAIL


def test_collector_identity_is_not_evaluable_without_an_approved_version(
    tmp_path: Path,
) -> None:
    """Still NOT_EVALUABLE after the ruling: no approved collector identity is
    frozen in any governing document. The ruling removed the denominator as a
    source of NOT_EVALUABLE and left this one exactly where it was."""
    build_admissible_corpus(tmp_path)
    report = assess(tmp_path)
    assert outcome_of(report, "collector_code_identity", "sip") is Outcome.NOT_EVALUABLE
    assert report.verdict is Verdict.UNDETERMINED
    assert report.exit_code == EXIT_UNDETERMINED


def test_collector_identity_fails_when_the_version_is_not_approved(tmp_path: Path) -> None:
    build_admissible_corpus(tmp_path, cycles=5)
    report = assess(tmp_path, approved_collector_versions=("mdq-collector/9.9.9",))
    assert outcome_of(report, "collector_code_identity", "sip") is Outcome.FAIL


# --- the census window is a diagnostic, never a denominator ---------------------


def test_the_census_reading_is_absent_unless_explicitly_requested(tmp_path: Path) -> None:
    build_admissible_corpus(tmp_path, cycles=5)
    report = assess(tmp_path)
    assert set(report.feeds["sip"].readings) == {"sampler_window"}


def test_the_census_reading_is_reported_on_request_and_labelled(tmp_path: Path) -> None:
    build_admissible_corpus(tmp_path, cycles=5)
    report = assess(tmp_path, include_census_diagnostic=True)
    census = reading(report, "sip", Denominator.CENSUS_WINDOW)
    assert census.expected_cycles == EXPECTED_CYCLES_CENSUS
    assert census.is_governing is False
    assert "DIAGNOSTIC ONLY" in census.role
    assert "NOT the admissibility denominator" in census.role


def test_the_census_diagnostic_never_changes_the_verdict(tmp_path: Path) -> None:
    """A perfect sampler partition scores ~55% against the bar-census window.
    That is precisely the outcome the ruling exists to prevent, so the number is
    shown and the verdict is untouched."""
    build_admissible_corpus(tmp_path)
    report = assess(
        tmp_path,
        include_census_diagnostic=True,
        approved_collector_versions=("mdq-collector/0.1.0",),
    )
    census = reading(report, "sip", Denominator.CENSUS_WINDOW)
    assert census.completeness == pytest.approx(EXPECTED_CYCLES / EXPECTED_CYCLES_CENSUS, abs=1e-4)
    assert census.completeness < 0.56
    assert census.meets_min_completeness is False
    assert outcome_of(report, "completeness_ratio", "sip") is Outcome.PASS
    assert report.verdict is Verdict.ADMISSIBLE


def test_asking_for_the_census_denominator_is_recorded_as_reinterpreted(tmp_path: Path) -> None:
    build_admissible_corpus(tmp_path)
    report = assess(
        tmp_path,
        governing_denominator=Denominator.CENSUS_WINDOW,
        approved_collector_versions=("mdq-collector/0.1.0",),
    )
    doc = json.loads(render_json(report))
    assert doc["inputs"]["governing_denominator"] == "sampler_window"
    assert doc["inputs"]["governing_denominator_requested"] == "census_window"
    assert (
        "forbids it as the sampler denominator"
        in (doc["inputs"]["governing_denominator_ruling_applied"])
    )
    assert doc["verdict"] == "ADMISSIBLE"


# --- scheduling semantics --------------------------------------------------------


def test_the_fixed_rate_loop_is_robust_where_the_fixed_delay_loop_was_marginal(
    tmp_path: Path,
) -> None:
    """Re-derived under the 395-slot grid. The legacy fixed-DELAY loop clears
    98% only up to ~1.4s of per-cycle work; the ruled fixed-RATE loop clears it
    at ANY per-cycle work up to a full cadence period, then collapses in one
    step. The frozen floor is robust under the ruled collector, not marginal."""
    build_admissible_corpus(tmp_path, cycles=5)
    timing = assess(tmp_path).feeds["sip"].derivation["sampler_timing_semantics"]
    assert timing["expected_cycles_half_open_grid"] == EXPECTED_CYCLES
    delay = timing["max_per_cycle_overhead_seconds_meeting_min_completeness_fixed_delay"]
    rate = timing["max_per_cycle_overhead_seconds_meeting_min_completeness_fixed_rate"]
    assert delay == pytest.approx(1.39, abs=0.01)
    assert rate == pytest.approx(float(CADENCE_SECONDS), abs=0.01)
    assert rate > delay * 40


def test_the_partition_reports_which_loop_produced_it(tmp_path: Path) -> None:
    build_admissible_corpus(tmp_path, cycles=5)
    legacy = assess(tmp_path).feeds["sip"].derivation["sampler_timing_semantics"]
    assert "fixed-delay or unknown" in legacy["loop_observed_in_this_partition"]

    other = tmp_path / "fixed_rate"
    build_admissible_corpus(other, cycles=5, slot_fields=True)
    modern = assess(other).feeds["sip"].derivation["sampler_timing_semantics"]
    assert "fixed-rate" in modern["loop_observed_in_this_partition"]


def test_the_achievable_cycles_alternative_is_diagnostic_only(tmp_path: Path) -> None:
    """An 'elapsed-time-derived achievable cycles' denominator has been floated
    as a drift fix. It is absent from the frozen text, excluded by the ruling,
    AND partly self-referential (the denominator comes from the partition's own
    spacing), so it is reported as a number and never scored."""
    build_admissible_corpus(tmp_path, cycles=387, cadence_seconds=61)
    timing = assess(tmp_path).feeds["sip"].derivation["sampler_timing_semantics"]
    assert timing["observed_per_cycle_overhead_seconds"] == pytest.approx(1.0)
    assert timing["achievable_cycles_at_observed_overhead"] == 390
    assert "DIAGNOSTIC ONLY" in timing["achievable_ratio_status"]
    assert "NOT AN ADMISSIBLE DENOMINATOR" in timing["achievable_ratio_status"]
    # ...and the scored condition is unaffected by it.
    report = assess(tmp_path)
    assert outcome_of(report, "completeness_ratio", "sip") is Outcome.FAIL


def test_drift_short_of_the_floor_still_fails(tmp_path: Path) -> None:
    """387 cycles = 97.97% of the 395-slot grid — a FAIL with no outage at all,
    purely from the legacy fixed-delay loop's drift."""
    build_admissible_corpus(tmp_path, cycles=387, cadence_seconds=61)
    report = assess(tmp_path, approved_collector_versions=("mdq-collector/0.1.0",))
    r = reading(report, "sip", RULED_SAMPLER)
    assert r.observed_cycles == 387
    assert r.completeness == pytest.approx(387 / EXPECTED_CYCLES, abs=1e-4)
    assert r.completeness < MIN_COMPLETENESS
    assert outcome_of(report, "completeness_ratio", "sip") is Outcome.FAIL


def test_observed_cycles_are_counted_from_the_data_not_the_wall_clock(tmp_path: Path) -> None:
    """The sampler stamps a shared cycle_ts on every record, so the NUMERATOR is
    read directly from the data. Only the denominator is arithmetic."""
    build_admissible_corpus(tmp_path, cycles=37, cadence_seconds=97)
    report = assess(tmp_path)
    assert report.feeds["sip"].stats.observed_cycles == 37
    assert report.feeds["sip"].stats.median_spacing_seconds == pytest.approx(97.0)
    assert reading(report, "sip", RULED_SAMPLER).observed_cycles == 37


# --- completeness / gap ---------------------------------------------------------


def test_seven_missing_cycles_pass_and_eight_fail(tmp_path: Path) -> None:
    """The floor's exact bite over the ruled grid, asserted from both sides."""
    passing = tmp_path / "seven"
    build_admissible_corpus(
        passing, skip_slots=frozenset(range(10, 10 + 8 * MAX_MISSING_UNDER_FLOOR, 8))
    )
    report = assess(passing, approved_collector_versions=("mdq-collector/0.1.0",))
    assert reading(report, "sip", RULED_SAMPLER).observed_cycles == MIN_OBSERVED_FOR_FLOOR
    assert outcome_of(report, "completeness_ratio", "sip") is Outcome.PASS

    failing = tmp_path / "eight"
    build_admissible_corpus(
        failing, skip_slots=frozenset(range(10, 10 + 8 * (MAX_MISSING_UNDER_FLOOR + 1), 8))
    )
    report = assess(failing, approved_collector_versions=("mdq-collector/0.1.0",))
    assert reading(report, "sip", RULED_SAMPLER).observed_cycles == MIN_OBSERVED_FOR_FLOOR - 1
    assert outcome_of(report, "completeness_ratio", "sip") is Outcome.FAIL


def test_completeness_below_the_frozen_minimum_fails(tmp_path: Path) -> None:
    """A 2%+ shortfall spread thinly enough to leave every gap under 10 minutes:
    the aggregate threshold is what catches it."""
    skip = frozenset(range(10, EXPECTED_CYCLES, 8))  # ~49 slots, never adjacent
    build_admissible_corpus(tmp_path, skip_slots=skip)
    report = assess(tmp_path, approved_collector_versions=("mdq-collector/0.1.0",))
    r = reading(report, "sip", RULED_SAMPLER)
    assert r.completeness < MIN_COMPLETENESS
    assert outcome_of(report, "completeness_ratio", "sip") is Outcome.FAIL
    assert outcome_of(report, "max_contiguous_gap", "sip") is Outcome.PASS
    assert report.verdict is Verdict.NOT_ADMISSIBLE


def test_a_long_hole_fails_both_thresholds(tmp_path: Path) -> None:
    """The GAPPER-v1 failure mode: a 12-minute outage in a partition whose bytes
    verify perfectly."""
    build_admissible_corpus(tmp_path, skip_slots=frozenset(range(100, 112)))
    report = assess(tmp_path, approved_collector_versions=("mdq-collector/0.1.0",))
    r = reading(report, "sip", RULED_SAMPLER)
    assert r.max_gap_minutes > MAX_CONTIGUOUS_GAP_MINUTES
    assert outcome_of(report, "max_contiguous_gap", "sip") is Outcome.FAIL
    assert outcome_of(report, "completeness_ratio", "sip") is Outcome.FAIL
    assert outcome_of(report, "integrity_verify", "sip") is Outcome.PASS


def test_the_completeness_floor_binds_tighter_than_the_gap_rule(tmp_path: Path) -> None:
    """Recorded finding, re-derived under the ruled 395-slot grid: the 98% floor
    admits at most 7 missing cycles while the 10-minute gap rule admits 9
    CONSECUTIVE ones. For a single contiguous outage the aggregate rate
    therefore still trips first — the ordering survived the change from 396 to
    395. The gap rule adds bite for edge outages. Over a longer window (or a
    shorter cadence) the ordering reverses."""
    build_admissible_corpus(tmp_path, skip_slots=frozenset(range(100, 109)))
    report = assess(tmp_path, approved_collector_versions=("mdq-collector/0.1.0",))
    r = reading(report, "sip", RULED_SAMPLER)
    assert r.max_gap_minutes == pytest.approx(10.0)
    assert outcome_of(report, "max_contiguous_gap", "sip") is Outcome.PASS
    assert r.observed_cycles == EXPECTED_CYCLES - 9
    assert outcome_of(report, "completeness_ratio", "sip") is Outcome.FAIL


def test_a_thirty_cycle_error_run_still_verifies_but_is_inadmissible(tmp_path: Path) -> None:
    """The exact hole the frozen abort-after-30 retry policy permits: the bytes
    are the frozen bytes (verify passes) and the partition is still inadmissible."""
    errors = frozenset(range(200, 230))
    build_admissible_corpus(tmp_path, error_slots=errors)
    report = assess(tmp_path, approved_collector_versions=("mdq-collector/0.1.0",))
    assert outcome_of(report, "integrity_verify", "sip") is Outcome.PASS
    assert outcome_of(report, "max_contiguous_gap", "sip") is Outcome.FAIL
    assert report.verdict is Verdict.NOT_ADMISSIBLE


def test_late_start_is_caught_by_the_edge_inclusive_gap(tmp_path: Path) -> None:
    build_admissible_corpus(tmp_path, skip_slots=frozenset(range(0, 20)))
    report = assess(tmp_path)
    assert reading(report, "sip", RULED_SAMPLER).max_gap_minutes == pytest.approx(20.0)
    assert outcome_of(report, "max_contiguous_gap", "sip") is Outcome.FAIL


def test_cadence_deviation_fails_the_cadence_condition(tmp_path: Path) -> None:
    build_admissible_corpus(tmp_path, cycles=50, cadence_seconds=30)
    report = assess(tmp_path)
    assert outcome_of(report, "cadence_match", "sip") is Outcome.FAIL


def test_the_cadence_tolerance_is_still_flagged_as_a_tool_default(tmp_path: Path) -> None:
    """The ruling did not ratify a spacing tolerance, so the condition must keep
    saying whose number it is."""
    build_admissible_corpus(tmp_path, cycles=50)
    condition = condition_of(assess(tmp_path), "cadence_match", "sip")
    assert condition.expected["tolerance_status"] == "TOOL DEFAULT — NOT RATIFIED"


# --- session scope ---------------------------------------------------------------


def _partition_starting_at(root: Path, start_et: time, cycles: int = 5) -> None:
    store = CaptureStore(root)
    for feed in ("iex", "sip"):
        ref = PartitionRef(feed=feed, session=SESSION)
        base = datetime.combine(SESSION, start_et, tzinfo=ET).astimezone(UTC)
        for slot in range(cycles):
            ts = (base + timedelta(seconds=slot * 60)).isoformat()
            store.append_jsonl(ref, "quotes", _quote_records(ts, UNIVERSE))
        store.freeze(ref, provenance={"universe": sorted(UNIVERSE)})


def test_premarket_cycles_are_now_out_of_scope_not_undecidable(tmp_path: Path) -> None:
    """Before the ruling a 04:00 ET cycle was NOT_EVALUABLE — inside the census
    window, outside the sampler window, and the tie unresolved. The ruling makes
    the sampler window the scope, so it is a plain FAIL."""
    _partition_starting_at(tmp_path, time(4, 0))
    report = assess(tmp_path)
    assert outcome_of(report, "session_scope_match", "sip") is Outcome.FAIL
    assert "not the sampler scope" in condition_of(report, "session_scope_match", "sip").detail


def test_cycles_far_outside_the_window_fail_session_scope(tmp_path: Path) -> None:
    _partition_starting_at(tmp_path, time(2, 0))
    report = assess(tmp_path)
    assert outcome_of(report, "session_scope_match", "sip") is Outcome.FAIL


def test_a_legacy_final_cycle_at_the_close_is_still_in_scope(tmp_path: Path) -> None:
    """The legacy fixed-DELAY loop tested `now >= close` AFTER sampling, so its
    last cycle could land up to one cadence past the close. That grace is owed
    to legacy partitions only, and is loop semantics rather than a threshold."""
    store = CaptureStore(tmp_path)
    for feed in ("iex", "sip"):
        ref = PartitionRef(feed=feed, session=SESSION)
        for offset in (0, 395 * 60, 395 * 60 + 45):
            ts = (WINDOW_START + timedelta(seconds=offset)).isoformat()
            store.append_jsonl(ref, "quotes", _quote_records(ts, UNIVERSE))
        store.freeze(ref, provenance={"universe": sorted(UNIVERSE)})
    report = assess(tmp_path)
    assert outcome_of(report, "session_scope_match", "sip") is Outcome.PASS
    observed = condition_of(report, "session_scope_match", "sip").observed
    assert observed["close_grace_seconds"] == 60


def test_a_fixed_rate_partition_is_owed_no_close_grace(tmp_path: Path) -> None:
    """Under the ruled loop the close is checked BEFORE the cycle, so a cycle at
    or past the close cannot be legitimate and no grace is extended."""
    store = CaptureStore(tmp_path)
    for feed in ("iex", "sip"):
        ref = PartitionRef(feed=feed, session=SESSION)
        for slot in (0, 394, 395):
            scheduled = WINDOW_START + timedelta(seconds=slot * 60)
            store.append_jsonl(
                ref,
                "quotes",
                _quote_records(
                    scheduled.isoformat(),
                    UNIVERSE,
                    slot_ts=scheduled.isoformat(),
                    slot_index=slot,
                ),
            )
        store.freeze(ref, provenance={"universe": sorted(UNIVERSE)})
    report = assess(tmp_path)
    observed = condition_of(report, "session_scope_match", "sip").observed
    assert observed["close_grace_seconds"] == 0
    assert outcome_of(report, "session_scope_match", "sip") is Outcome.FAIL


def test_no_session_close_makes_the_cycle_conditions_not_evaluable(tmp_path: Path) -> None:
    """A non-session and an unavailable calendar are indistinguishable from
    inside a partition, so both fail closed rather than scoring against a zero
    denominator."""
    build_admissible_corpus(tmp_path, cycles=5)
    report = assess_partition(tmp_path, SESSION, session_close_utc=None)
    for cond in ("completeness_ratio", "max_contiguous_gap", "cadence_match"):
        assert outcome_of(report, cond, "sip") is Outcome.NOT_EVALUABLE
    assert report.verdict is Verdict.UNDETERMINED


def test_the_module_holds_no_market_calendar_and_says_so() -> None:
    """Deliberate: the capture package may import no foreign app.* module, so
    app/market/session.py is unreachable from here, and a third-party calendar
    would break the stdlib-only posture. The close is an explicit input."""
    source = THRESHOLD_SOURCES["session_close"]
    assert "EXPLICIT REQUIRED INPUT" in source
    assert "holds NO holiday or early-close table" in source
    assert "NOT_EVALUABLE" in source


def test_the_close_provenance_is_echoed_into_the_record(tmp_path: Path) -> None:
    build_admissible_corpus(tmp_path, cycles=5)
    doc = json.loads(render_json(assess(tmp_path)))
    assert "PROVENANCE UNSTATED" in doc["inputs"]["session_close_source"]
    doc = json.loads(
        render_json(assess(tmp_path, session_close_source="NYSE calendar, mcal 5.4.0"))
    )
    assert doc["inputs"]["session_close_source"] == "NYSE calendar, mcal 5.4.0"


# --- joint conditions ------------------------------------------------------------


def test_feeds_are_adjudicated_independently_and_jointly(tmp_path: Path) -> None:
    build_partition(tmp_path, "iex")
    build_partition(tmp_path, "sip", skip_slots=frozenset(range(100, 130)))
    report = assess(tmp_path, approved_collector_versions=("mdq-collector/0.1.0",))
    assert report.feeds["iex"].outcome is Verdict.ADMISSIBLE
    assert report.feeds["sip"].outcome is Verdict.NOT_ADMISSIBLE
    assert outcome_of(report, "paired_cycles") is Outcome.FAIL
    assert report.verdict is Verdict.NOT_ADMISSIBLE


def test_paired_cycles_not_evaluable_with_a_lone_feed(tmp_path: Path) -> None:
    build_partition(tmp_path, "sip", cycles=5)
    report = assess(tmp_path)
    assert outcome_of(report, "paired_cycles") is Outcome.NOT_EVALUABLE


def test_tampered_universe_config_fails_the_joint_condition(tmp_path: Path) -> None:
    fake = tmp_path / "universe.json"
    fake.write_text(json.dumps(["SPY", "QQQ"]), encoding="utf-8")
    build_admissible_corpus(tmp_path / "root", cycles=5)
    report = assess_partition(
        tmp_path / "root",
        SESSION,
        session_close_utc=CLOSE,
        frozen_universe=load_frozen_universe(fake),
    )
    assert outcome_of(report, "universe_config_integrity") is Outcome.FAIL
    assert outcome_of(report, "universe_sha_expectation") is Outcome.FAIL


# --- outcome algebra -------------------------------------------------------------


def _cond(outcome: Outcome) -> ConditionResult:
    return ConditionResult("x", outcome, None, None, "")


def test_not_evaluable_is_never_coerced_to_pass_or_fail() -> None:
    assert roll_up([_cond(Outcome.PASS)]) is Verdict.ADMISSIBLE
    assert roll_up([_cond(Outcome.PASS), _cond(Outcome.NOT_EVALUABLE)]) is Verdict.UNDETERMINED
    assert roll_up([_cond(Outcome.NOT_EVALUABLE), _cond(Outcome.FAIL)]) is Verdict.NOT_ADMISSIBLE
    assert roll_up([]) is Verdict.UNDETERMINED  # no vacuous pass


def test_every_non_admissible_verdict_has_a_non_zero_exit_code(tmp_path: Path) -> None:
    build_admissible_corpus(tmp_path, cycles=5)
    report = assess(tmp_path)
    assert report.verdict is not Verdict.ADMISSIBLE
    assert report.exit_code != 0


# --- the ruled review verdict table ----------------------------------------------


def test_the_four_ruled_rows() -> None:
    assert review_disposition(6, 6).disposition is Disposition.GO
    assert review_disposition(2, 2).disposition is Disposition.GO
    assert review_disposition(2, 0).disposition is Disposition.STOP
    assert review_disposition(1, 1).disposition is Disposition.HOLD
    assert review_disposition(2, 1).disposition is Disposition.HOLD


@pytest.mark.parametrize(
    ("evaluable", "passed"),
    [(e, p) for e in range(7) for p in range(e + 1)],
)
def test_the_verdict_table_is_total_over_every_count_pair(evaluable: int, passed: int) -> None:
    """Exhaustive over all (evaluable, pass) combinations for K1-K6."""
    result = review_disposition(evaluable, passed)
    if evaluable < GO_FLOOR_EVALUABLE:
        expected = Disposition.HOLD
    elif passed >= GO_FLOOR_PASSES:
        expected = Disposition.GO
    elif passed == 0:
        expected = Disposition.STOP
    else:
        expected = Disposition.HOLD
    assert result.disposition is expected
    assert result.evaluable == evaluable
    assert result.passed == passed
    assert result.extension_required is (expected is Disposition.HOLD)
    assert result.rule


def test_a_hold_always_carries_one_stated_extension() -> None:
    for evaluable, passed in ((0, 0), (1, 0), (1, 1), (2, 1), (6, 1)):
        result = review_disposition(evaluable, passed)
        assert result.disposition is Disposition.HOLD
        assert result.extension_required is True
        assert "extension" in result.rule


def test_go_and_stop_never_request_an_extension() -> None:
    assert review_disposition(2, 2).extension_required is False
    assert review_disposition(6, 0).extension_required is False


def test_passing_more_criteria_than_are_evaluable_is_rejected() -> None:
    with pytest.raises(ValueError):
        review_disposition(1, 2)
    with pytest.raises(ValueError):
        review_disposition(-1, 0)


def test_not_evaluable_criteria_never_contribute_to_the_go_floor() -> None:
    """Six criteria all NOT_EVALUABLE is a HOLD; one PASS among five
    NOT_EVALUABLE is still a HOLD; two PASS reaches the floor and is a GO."""
    outcomes = dict.fromkeys(CRITERION_KEYS, Outcome.NOT_EVALUABLE)
    assert review_disposition_from_outcomes(outcomes).disposition is Disposition.HOLD
    outcomes["K1"] = Outcome.PASS
    assert review_disposition_from_outcomes(outcomes).disposition is Disposition.HOLD
    outcomes["K2"] = Outcome.PASS
    result = review_disposition_from_outcomes(outcomes)
    assert result.disposition is Disposition.GO
    assert result.evaluable == 2


def test_the_verdict_table_is_total_over_every_outcome_combination() -> None:
    """All 3^6 assignments of PASS / FAIL / NOT_EVALUABLE to K1-K6."""
    seen: set[Disposition] = set()
    combos = 0
    for combo in itertools.product(
        (Outcome.PASS, Outcome.FAIL, Outcome.NOT_EVALUABLE), repeat=len(CRITERION_KEYS)
    ):
        outcomes = dict(zip(CRITERION_KEYS, combo, strict=True))
        result = review_disposition_from_outcomes(outcomes)
        evaluable = sum(1 for o in combo if o is not Outcome.NOT_EVALUABLE)
        passed = sum(1 for o in combo if o is Outcome.PASS)
        assert result.evaluable == evaluable
        assert result.passed == passed
        assert result.disposition is review_disposition(evaluable, passed).disposition
        seen.add(result.disposition)
        combos += 1
    assert combos == 3 ** len(CRITERION_KEYS)
    assert seen == {Disposition.GO, Disposition.STOP, Disposition.HOLD}


# --- the ruled holdout window ------------------------------------------------------


def test_the_review_window_is_sixty_calendar_dates_half_open() -> None:
    window = holdout_window(SESSION)
    assert window.review_start_date == SESSION
    assert window.review_end_exclusive == SESSION + timedelta(days=REVIEW_WINDOW_DAYS)
    assert len(window.review_dates) == REVIEW_WINDOW_DAYS
    assert window.review_dates[0] == SESSION
    assert window.review_dates[-1] == SESSION + timedelta(days=REVIEW_WINDOW_DAYS - 1)
    assert window.in_review(window.review_dates[-1]) is True
    assert window.in_review(window.review_end_exclusive) is False


def test_the_period_holdout_is_the_final_twelve_calendar_dates() -> None:
    window = holdout_window(SESSION)
    assert window.period_holdout_start == SESSION + timedelta(days=PERIOD_HOLDOUT_OFFSET_DAYS)
    assert len(window.holdout_dates) == PERIOD_HOLDOUT_DAYS
    assert PERIOD_HOLDOUT_DAYS == 12
    offsets = [(d - SESSION).days for d in window.holdout_dates]
    assert offsets == list(range(48, 60))


def test_the_holdout_boundary_is_not_slid_for_weekends() -> None:
    """Sliding would turn 'the final 20% of the window' into 'the final 12
    trading sessions' — a different rule. Weekend dates simply contain no
    trading partition."""
    window = holdout_window(SESSION)
    weekend = [d for d in window.holdout_dates if d.weekday() >= 5]
    assert weekend, "the fixture window must contain weekend dates to be meaningful"
    assert len(window.holdout_dates) == 12
    for start in (date(2026, 8, 15), date(2026, 8, 16), date(2026, 8, 17)):
        assert len(holdout_window(start).holdout_dates) == 12


def test_the_holdout_membership_predicate_is_half_open() -> None:
    window = holdout_window(SESSION)
    assert window.in_period_holdout(window.period_holdout_start - timedelta(days=1)) is False
    assert window.in_period_holdout(window.period_holdout_start) is True
    assert window.in_period_holdout(window.review_end_exclusive - timedelta(days=1)) is True
    assert window.in_period_holdout(window.review_end_exclusive) is False


# --- the ruled exploration embargo --------------------------------------------------


HOLDOUT_SYMBOLS = frozenset({"SPY", "QQQ", "IWM", "XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP"})


def test_holdout_symbols_are_quarantined_for_the_whole_window() -> None:
    window = holdout_window(SESSION)
    for offset in (0, 1, 30, 47, 48, 59):
        assert (
            exploratory_access_allowed(
                "SPY",
                SESSION + timedelta(days=offset),
                holdout_symbols=HOLDOUT_SYMBOLS,
                window=window,
            )
            is False
        )


def test_every_symbol_is_quarantined_in_the_final_twelve_dates() -> None:
    window = holdout_window(SESSION)
    for offset in range(48, 60):
        assert (
            exploratory_access_allowed(
                "XLU",
                SESSION + timedelta(days=offset),
                holdout_symbols=HOLDOUT_SYMBOLS,
                window=window,
            )
            is False
        )


def test_a_non_holdout_symbol_before_the_holdout_is_explorable() -> None:
    window = holdout_window(SESSION)
    for offset in (0, 1, 47):
        assert (
            exploratory_access_allowed(
                "XLU",
                SESSION + timedelta(days=offset),
                holdout_symbols=HOLDOUT_SYMBOLS,
                window=window,
            )
            is True
        )


def test_the_ten_holdout_symbols_are_the_ruled_count() -> None:
    assert HOLDOUT_SYMBOL_COUNT == 10
    assert len(HOLDOUT_SYMBOLS) == HOLDOUT_SYMBOL_COUNT


def test_the_embargo_predicate_touches_no_filesystem(tmp_path: Path) -> None:
    """Pure predicate: nothing is read, nothing is created."""
    window = holdout_window(SESSION)
    before = sorted(tmp_path.rglob("*"))
    exploratory_access_allowed("XLU", SESSION, holdout_symbols=HOLDOUT_SYMBOLS, window=window)
    assert sorted(tmp_path.rglob("*")) == before


# --- output shape ----------------------------------------------------------------


def test_json_record_is_self_describing(tmp_path: Path) -> None:
    build_admissible_corpus(tmp_path)
    report = assess(
        tmp_path,
        approved_collector_versions=("mdq-collector/0.1.0",),
        include_census_diagnostic=True,
    )
    doc = json.loads(render_json(report))
    assert doc["schema"] == "mdq-admissibility-report/1"
    assert doc["verdict"] == "ADMISSIBLE"
    assert doc["exit_code"] == 0
    assert doc["inputs"]["capture_root"] == str(tmp_path.resolve())
    assert doc["inputs"]["session_date"] == SESSION.isoformat()
    assert doc["inputs"]["read_only"] is True
    assert doc["thresholds"]["min_completeness"] == MIN_COMPLETENESS
    assert doc["thresholds"]["max_contiguous_gap_minutes"] == MAX_CONTIGUOUS_GAP_MINUTES
    assert doc["thresholds"]["expected_cycles_for_this_session"] == EXPECTED_CYCLES
    assert "HALF-OPEN" in doc["thresholds"]["expected_cycles_grid"]
    assert set(doc["threshold_sources"]) == set(THRESHOLD_SOURCES)
    assert set(doc["per_feed"]) == {"iex", "sip"}
    by_reading = doc["per_feed"]["sip"]["completeness_by_reading"]
    assert set(by_reading) == {"sampler_window", "census_window"}
    assert by_reading["sampler_window"]["expected_cycles"] == EXPECTED_CYCLES
    assert by_reading["census_window"]["expected_cycles"] == EXPECTED_CYCLES_CENSUS
    assert by_reading["sampler_window"]["scope_note"]
    assert doc["not_passing"] == []
    for cond in doc["per_feed"]["sip"]["conditions"]:
        assert cond["source"], f"{cond['condition']} has no provenance in the record"


def test_the_json_record_carries_the_ruling_and_the_open_questions(tmp_path: Path) -> None:
    build_admissible_corpus(tmp_path, cycles=5)
    doc = json.loads(render_json(assess(tmp_path)))
    assert doc["owner_ruling"] == OWNER_RULING_DENOMINATOR
    assert doc["inputs"]["owner_ruling_date"] == "2026-08-18"
    assert set(doc["unratified_after_ruling"]) == set(UNRATIFIED_AFTER_RULING)
    assert doc["inputs"]["denominator_ruling"] == OWNER_RULING_DENOMINATOR


def test_a_caller_citation_is_recorded_alongside_the_ruling(tmp_path: Path) -> None:
    build_admissible_corpus(tmp_path, cycles=5)
    doc = json.loads(
        render_json(assess_ruled(tmp_path, denominator_ruling="program-start record, item 3"))
    )
    assert doc["inputs"]["denominator_ruling"] == "program-start record, item 3"
    assert doc["owner_ruling"] == OWNER_RULING_DENOMINATOR
    assert doc["thresholds"]["expected_cycles_denominator"] == "sampler_window"


def test_json_record_lists_every_non_passing_condition(tmp_path: Path) -> None:
    build_admissible_corpus(tmp_path, cycles=5, label="PRE_REGISTRATION_SMOKE")
    doc = json.loads(render_json(assess(tmp_path)))
    assert doc["verdict"] == "NOT_ADMISSIBLE"
    entries = doc["not_passing"]
    assert any(i["condition"] == "no_provenance_label" and i["scope"] == "sip" for i in entries)
    assert {i["scope"] for i in entries} <= {"joint", "iex", "sip"}


def test_text_report_prints_thresholds_ruling_and_verdict(tmp_path: Path) -> None:
    build_admissible_corpus(tmp_path, cycles=5)
    text = render_text(assess(tmp_path, include_census_diagnostic=True))
    assert "MDQ-001 PARTITION ADMISSIBILITY" in text
    assert "min_completeness" in text
    assert "session_scope" in text
    assert "sampler_window" in text
    assert "census_window" in text
    assert "diagnostic only" in text
    assert "SCORED" in text
    assert "Owner ruling in force" in text
    assert "Still unratified after this ruling" in text
    assert "fixed-delay" in text
    assert "fixed-rate" in text
    assert "VERDICT:" in text
    assert "NOT-EVALUABLE" in text


# --- read-only discipline ---------------------------------------------------------


def _snapshot(root: Path) -> dict[str, tuple[int, str]]:
    out: dict[str, tuple[int, str]] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            data = path.read_bytes()
            out[str(path.relative_to(root))] = (len(data), hashlib.sha256(data).hexdigest())
    return out


def test_adjudication_does_not_touch_a_single_byte(tmp_path: Path) -> None:
    """Owner rule: a write-capable path is validated read-only or on an isolated
    copy, never with a 'benign' stub. Here the corpus is hashed before and after
    a full adjudication — including the failing branches, which are exactly where
    a repair affordance would be tempting."""
    build_admissible_corpus(tmp_path, skip_slots=frozenset(range(100, 130)))
    before = _snapshot(tmp_path)
    assert before, "fixture built nothing"

    report = assess(
        tmp_path,
        approved_collector_versions=("mdq-collector/0.1.0",),
        include_census_diagnostic=True,
    )
    render_text(report)
    render_json(report)

    after = _snapshot(tmp_path)
    assert after == before
    assert set(after) == set(before), "adjudication created or removed a file"


def test_adjudication_of_a_fixed_rate_corpus_touches_no_bytes_either(tmp_path: Path) -> None:
    """The slot-grid path reads more fields; it must still read only."""
    build_admissible_corpus(tmp_path, slot_fields=True)
    before = _snapshot(tmp_path)
    render_json(assess(tmp_path, approved_collector_versions=("mdq-collector/0.1.0",)))
    assert _snapshot(tmp_path) == before


def test_adjudicating_an_empty_root_creates_nothing(tmp_path: Path) -> None:
    root = tmp_path / "empty_root"
    report = assess(root)
    assert report.verdict is Verdict.NOT_ADMISSIBLE
    assert not root.exists(), "adjudication must not materialise the capture root"


def test_module_holds_no_write_or_network_primitives() -> None:
    """Structural, not reviewed: the adjudicator must stay read-only and offline.

    Complements the package-wide invariant in test_mdq_capture.py, which already
    forbids foreign app imports, mutating HTTP verbs and the trading SDK.

    Router-token containment is deliberately NOT restated here. ADR 0002 leg 2
    (scripts/check_adr0002.sh) already greps every file outside the router and
    adapter seam for the token name, this module included, and it does so more
    thoroughly than a per-module assertion could. Restating it also could not
    work: that check cannot distinguish "leaks the token" from "asserts the
    token is absent", so naming the token here to forbid it made this file the
    violation. An invariant with a dedicated checker belongs to that checker.
    """
    import app.research.capture.admissibility as mod

    source = Path(mod.__file__).read_text(encoding="utf-8")
    forbidden = (
        '"w"',
        '"a"',
        '"wb"',
        '"ab"',
        ".write_text(",
        ".write_bytes(",
        ".mkdir(",
        ".unlink(",
        ".rename(",
        ".replace(tmp",
        "os.replace",
        "os.remove",
        "shutil.",
        "tempfile.",
        "httpx",
        "requests.",
        "urllib",
        "socket",
        "alpaca",
    )
    for token in forbidden:
        assert token not in source, f"admissibility.py must not contain {token!r}"


# --- the adjudicator's grid and the collector's grid must not drift apart ---------


def test_the_adjudicator_grid_equals_the_collectors_grid() -> None:
    """Two independent implementations of the same ruling.

    The collector schedules cycles on its own ``SlotGrid``; the adjudicator
    derives the denominator from the ruling text without consulting it. If those
    ever disagree, completeness is measured against a grid the capture never ran
    on — silently. This is the assertion that makes the drift loud.
    """
    from app.research.capture.collector import SlotGrid

    for close, expected in ((CLOSE, EXPECTED_CYCLES), (EARLY_CLOSE, EXPECTED_CYCLES_EARLY_CLOSE)):
        theirs = SlotGrid.for_session(SESSION, close)
        mine = slot_grid(*sampler_window(SESSION, close))
        assert theirs.expected_cycles == expected
        assert len(mine) == expected
        assert theirs.slot_ts(0) == mine[0]
        assert theirs.slot_ts(expected - 1) == mine[-1]
