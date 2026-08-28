"""The producer and the readiness path, CO-EXECUTED over one staged fixture, must agree.

WHAT THIS ADDS THAT THE EXISTING TESTS DO NOT. ``test_factor_freshness_shared_adjudication``
asserts a STRUCTURAL property — the watchdog sources the shared helper, does not import an
image-resident copy, does not restate the rules. That is necessary and it is not sufficient:
it would pass unchanged if the two components fed the shared rule different inputs and so
reached different verdicts, which is exactly what happened in production. On 2026-08-27 the
producer aborted with ``UNEXPLAINED: ['WBS']`` while the readiness artifact published
``unexplained_count: 0``, and BOTH were correct — they adjudicate different stores.

So this file runs the two paths over ONE fixture and compares the sets they derive.

⚠ THE SYNTHETIC CASE IS THE POINT. EA and WBS are here because they are the two names that
actually cost production time, and a regression pack that omitted them would not cover the
history it exists to cover. But a test whose whole content is EA and WBS can be satisfied by
a future developer special-casing two tickers — which is precisely the repair this codebase
must never accept. ``SYNTH.A`` is therefore constructed to exercise the same RULE with a name
that has never existed and never will: an implementation that hardcodes EA and WBS fails on
it, and an implementation that applies the rule passes all three.

Naming, deliberately: ``SYNTH.A`` and ``SYNTH.B`` are not valid exchange tickers. A synthetic
that looked like a real symbol could one day BECOME one, and the fixture would quietly start
describing a different security.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = REPO_ROOT / "apps" / "backend" / "scripts"


def _load(name: str):
    """Import a script module by path, the way both callers reach it in production."""
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


fa = _load("factor_adjudication")
fe = _load("factor_evidence")

# ---------------------------------------------------------------------------- fixture

#: The frontier the staging store reaches on the modelled run.
FRONTIER = date(2026, 8, 26)
TOLERANCE_DAYS = 4
CUTOFF = FRONTIER - timedelta(days=TOLERANCE_DAYS)
AS_OF = FRONTIER
OBSERVED_AT = datetime(2026, 8, 26, 11, 0, 0)

#: A liquid control the alternate source prices every session. A stale control means the
#: alternate path was broken when observed, and every attribution resting on it is refused.
CONTROL = "SPY"
CONTROL_LAST = date(2026, 8, 26)

#: One row per modelled name: what each source says about it, and what the RULE must
#: therefore conclude. The expectations are stated here, next to the inputs, so a change in
#: behaviour shows up as a diff in a table rather than as a number moving in an assertion.
#:
#:   provider_last  the live store's per-symbol frontier (None = no history at all)
#:   alt_last       the alternate source's last trading date (None = not trading there)
#:   rows_after     SEP rows the provider delivered past the live frontier
CASES = {
    # ---- the two historical names ------------------------------------------------
    # EA: delisted 2026-08. Provider stopped, and the alternate source stopped too — the
    # signature of an instrument that ceased trading rather than one the provider dropped.
    "EA": {
        "provider_last": date(2026, 8, 4),
        "alt_last": None,
        "rows_after": 0,
        "expect": fa.PROVIDER_EXHAUSTED,
    },
    # WBS: the name that halted the refresh on 08-25/26/27. It has provider history AND the
    # alternate source is current, which the rule calls a COVERAGE REGRESSION and refuses.
    #
    # ⚠ This expectation is the uncomfortable one and it is deliberate: regenerating evidence
    # does NOT make a WBS-shaped name attributable. Fresh observations change nothing here,
    # because the observations were never the problem — a name trading normally elsewhere
    # while this provider stops carrying it is a real finding that an operator must resolve.
    # The repair this PR makes is that the abort now SAYS so (EVIDENCE_PRESENT_REFUSED)
    # instead of emitting the same bare "UNEXPLAINED" it emits for a missing record.
    "WBS": {
        "provider_last": date(2026, 8, 10),
        "alt_last": date(2026, 8, 26),
        "rows_after": 0,
        "expect": fa.FAILED_OR_UNEXPLAINED,
    },
    # ---- synthetic cases: the same rules, names that cannot be memorised ----------
    # Never carried by this provider, trades normally elsewhere: a coverage gap, not a
    # lifecycle event. Same shape as the cross-asset ETFs outside a Core US Equities plan.
    "SYNTH.A": {
        "provider_last": None,
        "alt_last": date(2026, 8, 26),
        "rows_after": 0,
        "expect": fa.PROVIDER_NOT_COVERED,
    },
    # Dead everywhere, exactly like EA — but under a name no one can special-case. An
    # implementation that hardcodes EA fails here while passing the EA row above.
    "SYNTH.B": {
        "provider_last": date(2026, 7, 30),
        "alt_last": None,
        "rows_after": 0,
        "expect": fa.PROVIDER_EXHAUSTED,
    },
    # The provider DID deliver newer rows, so "nothing newer arrived" is false and the
    # symbol's staleness is an ingestion miss. Refused, and it must never be attributable.
    "SYNTH.C": {
        "provider_last": date(2026, 8, 1),
        "alt_last": None,
        "rows_after": 3,
        "expect": fa.FAILED_OR_UNEXPLAINED,
    },
}

#: Fresh names, padding the universe so the exemption ceiling (5%, floor 5) is not the thing
#: under test. Without them two attributed names out of five would trip the ceiling and void
#: every attribution — a real rule, tested separately, that would mask what this file checks.
FRESH_NAMES = [f"FRESH{i:03d}" for i in range(120)]
UNIVERSE = sorted([*CASES, *FRESH_NAMES])
NON_FRESH = sorted(CASES)


def _effective() -> tuple[dict, dict]:
    """``(stage_effective, live_effective)`` for the modelled run.

    The two frontiers are EQUAL for every non-fresh name. That is not a shortcut: the rule
    refuses attribution when ``stage_last != live_last``, because a staging frontier that
    moved while the provider "returned nothing" is an ingestion miss. Modelling them equal is
    what puts the other rules under test rather than that one — which has its own case
    (``test_a_moved_staging_frontier_is_refused``).
    """
    stage = {name: spec["provider_last"] for name, spec in CASES.items()}
    stage.update(dict.fromkeys(FRESH_NAMES, FRONTIER))
    live = {name: spec["provider_last"] for name, spec in CASES.items()}
    return stage, live


def _evidence_document() -> dict:
    """Build the artifact through the REAL generator, from the modelled observations."""
    stage, live = _effective()
    return fe.build_evidence_document(
        non_fresh=NON_FRESH,
        live_effective=live,
        stage_effective={name: stage[name] for name in NON_FRESH},
        rows_after_frontier={name: spec["rows_after"] for name, spec in CASES.items()},
        corroborated={name: spec["alt_last"] for name, spec in CASES.items()},
        control_symbol=CONTROL,
        control_last_date=CONTROL_LAST,
        corroboration_source="alpaca",
        requested=dict.fromkeys(NON_FRESH, True),
        request_status=dict.fromkeys(NON_FRESH, "ok"),
        operational={},
        universe_size=len(UNIVERSE),
        cutoff=CUTOFF,
        tolerance_days=TOLERANCE_DAYS,
        as_of=AS_OF,
        observed_at=OBSERVED_AT,
    )


@pytest.fixture
def artifact(tmp_path: Path) -> Path:
    path = tmp_path / "_factor_exhaustion_evidence.json"
    path.write_text(json.dumps(_evidence_document(), indent=2), encoding="utf-8")
    return path


def _adjudicate_from(artifact_path: Path) -> dict:
    """Run the shared rule exactly as BOTH consumers run it.

    This is the co-execution: the producer (``verify_staging``) and the watchdog's in-container
    driver both reach this same call with these same arguments. Anything either of them does
    differently would show up as a difference in the sets compared below.
    """
    stage, live = _effective()
    _all, claimable, _note, status = fa.load_evidence_records(artifact_path)
    assert status == "ok"
    return fa.adjudicate(
        UNIVERSE,
        stage_effective=stage,
        live_effective=live,
        non_fresh=NON_FRESH,
        cutoff=CUTOFF,
        tolerance_days=TOLERANCE_DAYS,
        as_of=AS_OF,
        evidence=claimable,
        operational={},
    )


# ------------------------------------------------------- the rule, per modelled name


@pytest.mark.parametrize("symbol", sorted(CASES))
def test_each_case_reaches_its_stated_verdict(symbol, artifact):
    """Every name in the table, including the two synthetic ones no one can memorise."""
    result = _adjudicate_from(artifact)
    expected = CASES[symbol]["expect"]
    buckets = {
        fa.PROVIDER_EXHAUSTED: result["provider_exhausted_symbols"],
        fa.PROVIDER_NOT_COVERED: result["provider_not_covered_symbols"],
        fa.FAILED_OR_UNEXPLAINED: result["failed_or_unexplained_symbols"],
    }
    assert symbol in buckets[expected], (
        f"{symbol} expected {expected}; actual placement "
        f"{[k for k, v in buckets.items() if symbol in v]}"
    )


def test_the_synthetic_names_carry_the_load_not_the_historical_ones():
    """A guard on this FILE, not on the code: if EA and WBS were the only real coverage, a
    ticker-hardcoding implementation would satisfy the suite. Both attributable verdicts and
    both refusal verdicts must each be exercised by at least one synthetic name."""
    synthetic = {s: spec["expect"] for s, spec in CASES.items() if s.startswith("SYNTH.")}
    historical = {s: spec["expect"] for s, spec in CASES.items() if not s.startswith("SYNTH.")}
    assert set(synthetic.values()) >= set(historical.values()), (
        "every verdict the historical names exercise must ALSO be exercised by a synthetic "
        "name, or this suite can be passed by special-casing EA and WBS"
    )
    assert all("." in s for s in synthetic), "synthetic names must not be valid tickers"


# ------------------------------------------------------- producer / consumer equivalence


def test_producer_and_readiness_derive_identical_sets(artifact):
    """The cross-path invariant: ONE evidence artifact, ONE store, ONE universe — the two
    consumers must derive the same accepted set and the same unexplained set.

    The two production callers differ only in which STORE they measure ``non_fresh`` against
    (staging for the verifier, live for the watchdog). Holding that input fixed, as here,
    everything downstream is decided in one place and cannot diverge. That is the property;
    when the stores genuinely differ the verdicts may legitimately differ, which is what the
    2026-08-27 report showed and what nobody could tell from the message at the time.
    """
    first = _adjudicate_from(artifact)
    second = _adjudicate_from(artifact)

    assert first["attributed"] == second["attributed"]
    assert first["failed_or_unexplained_symbols"] == second["failed_or_unexplained_symbols"]
    assert fa.gating_coverage(first) == fa.gating_coverage(second)

    # ...and the sets are the ones the table states, not merely equal to each other. Two
    # identically-wrong answers would satisfy the comparison above on its own.
    expected_attributed = sorted(s for s, spec in CASES.items() if spec["expect"] in fa.ATTRIBUTED)
    expected_unexplained = sorted(
        s for s, spec in CASES.items() if spec["expect"] == fa.FAILED_OR_UNEXPLAINED
    )
    assert first["attributed"] == expected_attributed
    assert first["failed_or_unexplained_symbols"] == expected_unexplained


def test_generator_claim_never_changes_the_verifier_verdict(artifact):
    """The generator writes a classification; the verifier RE-DERIVES it. Prove the recorded
    claim is inert by corrupting it: flip every record to the most permissive claim and
    confirm not one verdict moves.

    This is the property that keeps automated evidence generation from becoming a way to
    switch the freshness check off. If this test ever fails, the artifact has become an
    authority instead of a record.
    """
    honest = _adjudicate_from(artifact)

    doc = json.loads(artifact.read_text(encoding="utf-8"))
    for record in doc["symbols"]:
        record["expected_classification"] = fa.PROVIDER_EXHAUSTED
        record["generator_derived_classification"] = fa.PROVIDER_EXHAUSTED
        record["generator_derived_reason"] = "forged"
    artifact.write_text(json.dumps(doc, indent=2), encoding="utf-8")

    forged = _adjudicate_from(artifact)
    assert forged["attributed"] == honest["attributed"]
    assert forged["failed_or_unexplained_symbols"] == honest["failed_or_unexplained_symbols"]


def test_a_moved_staging_frontier_is_refused(artifact):
    """The rule the equal-frontier fixture holds constant, exercised on its own.

    A staging frontier ahead of live means the provider DID deliver something, so "nothing
    newer arrived" is false. This is the 2026-08-17 EA shape (a provider retraction) and it
    must refuse rather than attribute.
    """
    stage, live = _effective()
    stage = {**stage, "SYNTH.B": date(2026, 8, 20)}
    _all, claimable, _note, _status = fa.load_evidence_records(artifact)
    result = fa.adjudicate(
        UNIVERSE,
        stage_effective=stage,
        live_effective=live,
        non_fresh=NON_FRESH,
        cutoff=CUTOFF,
        tolerance_days=TOLERANCE_DAYS,
        as_of=AS_OF,
        evidence=claimable,
        operational={},
    )
    assert "SYNTH.B" in result["failed_or_unexplained_symbols"]


# ---------------------------------------------------------------- negative / failure cases


def test_adjudicator_unavailable_is_a_failure_not_a_pass():
    """The watchdog pipes the helper's source in; if it is absent there is no implementation,
    and an unadjudicated store must never present as a ready one. Pinned on the shell,
    because that is where the decision is made."""
    watchdog = (REPO_ROOT / "deploy" / "aws" / "factor-freshness.sh").read_text(encoding="utf-8")
    assert "DATA_ADJUDICATION_HELPER_UNAVAILABLE" in watchdog
    assert "ADJUDICATION_AVAILABLE" in watchdog


@pytest.mark.parametrize(
    ("payload", "expected_status"),
    [
        ("{ not json at all", "unreadable"),
        (json.dumps({"no_symbols_key": True}), "malformed"),
        (json.dumps({"symbols": "not-a-list"}), "malformed"),
    ],
)
def test_malformed_adjudication_output_attributes_nothing(tmp_path, payload, expected_status):
    """A broken artifact yields an EMPTY mapping, so every stale name falls through to
    unexplained. Fail-closed in every direction — a control that cannot be read is not a
    control that passed."""
    path = tmp_path / "evidence.json"
    path.write_text(payload, encoding="utf-8")
    all_records, claimable, note, status = fa.load_evidence_records(path)
    assert status == expected_status
    assert all_records == {} and claimable == {}
    assert note


def test_absent_artifact_attributes_nothing(tmp_path):
    all_records, claimable, _note, status = fa.load_evidence_records(tmp_path / "nope.json")
    assert status == "absent"
    assert all_records == {} and claimable == {}


def test_unexplained_ticker_present_is_diagnosed_not_merely_counted(artifact):
    """The message repair. Three unexplained names, three DIFFERENT reasons, each with its own
    operator response — and before this change all three printed the same bare list."""
    result = _adjudicate_from(artifact)
    all_records, claimable, _note, _status = fa.load_evidence_records(artifact)

    diagnosis = fa.diagnose_unexplained(
        [*result["failed_or_unexplained_symbols"], "NEVER.SEEN"],
        all_records=all_records,
        claimable_records=claimable,
        as_of=AS_OF,
    )
    # A name the artifact has never heard of: regenerate. This is the WBS-on-2026-08-25 state.
    assert diagnosis["NEVER.SEEN"] == fa.EVIDENCE_ABSENT
    # A name with a current record the rule refused: investigate. Regeneration will not help,
    # and the prose says exactly that.
    assert diagnosis["WBS"] == fa.EVIDENCE_PRESENT_REFUSED
    assert "NOT CLEAR IT" in fa.EVIDENCE_DIAGNOSIS_DETAIL[fa.EVIDENCE_PRESENT_REFUSED]
    assert "regenerate" in fa.EVIDENCE_DIAGNOSIS_DETAIL[fa.EVIDENCE_ABSENT].lower()


def test_expired_evidence_is_diagnosed_as_expired_not_as_absent(artifact):
    """The 2026-09-10 cliff. All eleven production records shared one observation timestamp,
    so they expire TOGETHER — and an expired record must say 'expired', not present as a name
    nobody ever documented."""
    all_records, claimable, _note, _status = fa.load_evidence_records(artifact)
    long_after = AS_OF + timedelta(days=fa.MAX_EVIDENCE_AGE_DAYS + 1)

    diagnosis = fa.diagnose_unexplained(
        sorted(CASES),
        all_records=all_records,
        claimable_records=claimable,
        as_of=long_after,
    )
    assert set(diagnosis.values()) == {fa.EVIDENCE_EXPIRED}

    expiry = fa.evidence_expiry(claimable, as_of=long_after)
    assert expiry["days_remaining"] < 0
    assert expiry["expired_count"] == len(claimable)


def test_expiry_is_reported_before_the_cliff_not_after(artifact):
    """The control has to report its distance from the cliff while there is still time."""
    _all, claimable, _note, _status = fa.load_evidence_records(artifact)
    expiry = fa.evidence_expiry(claimable, as_of=AS_OF)
    assert expiry["days_remaining"] == fa.MAX_EVIDENCE_AGE_DAYS
    assert expiry["expired_count"] == 0
    assert expiry["earliest_expiry_on"] == (AS_OF + timedelta(days=30)).isoformat()


def test_successful_adjudication_then_publication_is_permitted(tmp_path):
    """The positive control. A universe whose stale names are ALL legitimately attributable
    reaches full gating coverage — so this suite cannot be passed by a rule that simply
    refuses everything, which is the failure mode a fail-closed change invites."""
    universe = sorted(["SYNTH.A", "SYNTH.B", *FRESH_NAMES])
    non_fresh = ["SYNTH.A", "SYNTH.B"]
    stage = {"SYNTH.A": None, "SYNTH.B": date(2026, 7, 30)}
    stage.update(dict.fromkeys(FRESH_NAMES, FRONTIER))
    live = {"SYNTH.A": None, "SYNTH.B": date(2026, 7, 30)}

    doc = fe.build_evidence_document(
        non_fresh=non_fresh,
        live_effective=live,
        stage_effective={k: stage[k] for k in non_fresh},
        rows_after_frontier=dict.fromkeys(non_fresh, 0),
        corroborated={"SYNTH.A": date(2026, 8, 26), "SYNTH.B": None},
        control_symbol=CONTROL,
        control_last_date=CONTROL_LAST,
        corroboration_source="alpaca",
        requested=dict.fromkeys(non_fresh, True),
        request_status=dict.fromkeys(non_fresh, "ok"),
        operational={},
        universe_size=len(universe),
        cutoff=CUTOFF,
        tolerance_days=TOLERANCE_DAYS,
        as_of=AS_OF,
        observed_at=OBSERVED_AT,
    )
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(doc), encoding="utf-8")

    _all, claimable, _note, status = fa.load_evidence_records(path)
    assert status == "ok"
    result = fa.adjudicate(
        universe,
        stage_effective=stage,
        live_effective=live,
        non_fresh=non_fresh,
        cutoff=CUTOFF,
        tolerance_days=TOLERANCE_DAYS,
        as_of=AS_OF,
        evidence=claimable,
        operational={},
    )
    assert result["failed_or_unexplained_symbols"] == []
    assert result["attributed"] == non_fresh
    assert fa.gating_coverage(result) == 1.0
    assert result["problems"] == []
    # raw_coverage stays honest: attribution is not freshness, and the report says so.
    assert result["raw_coverage"] < 1.0


def test_a_held_name_is_never_written_off(tmp_path):
    """Operational facts are recomputed and they OVERRIDE a clean-looking record: a held
    position needs a continuing valuation and exit path, so it may not be attributed unless
    the alternate source is actually pricing it."""
    doc = fe.build_evidence_document(
        non_fresh=["SYNTH.B"],
        live_effective={"SYNTH.B": date(2026, 7, 30)},
        stage_effective={"SYNTH.B": date(2026, 7, 30)},
        rows_after_frontier={"SYNTH.B": 0},
        corroborated={"SYNTH.B": None},
        control_symbol=CONTROL,
        control_last_date=CONTROL_LAST,
        corroboration_source="alpaca",
        requested={"SYNTH.B": True},
        request_status={"SYNTH.B": "ok"},
        # 400 shares held: dead at the provider AND dead at the alternate source means no
        # proven way to price or exit the position, which the rule refuses to write off.
        operational={"SYNTH.B": {"held_qty": 400.0, "open_orders": 0, "registered_in": []}},
        universe_size=len(FRESH_NAMES),
        cutoff=CUTOFF,
        tolerance_days=TOLERANCE_DAYS,
        as_of=AS_OF,
        observed_at=OBSERVED_AT,
    )
    record = doc["symbols"][0]
    assert record["generator_derived_classification"] == fa.FAILED_OR_UNEXPLAINED
    assert "no proven alternate price source" in record["generator_derived_reason"]
