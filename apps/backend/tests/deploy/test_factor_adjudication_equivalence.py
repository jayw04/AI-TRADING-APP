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
from datetime import UTC, date, datetime, timedelta
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
    # WBS: the name that halted the refresh on 08-25/26/27/28. These are its OBSERVED
    # production values, read from the live store and a live alternate-source probe on
    # 2026-08-28: Sharadar and Alpaca BOTH end at 2026-08-19, and the store's own `actions`
    # table carries `delisted` + `acquisitionby` -> `SAN` on that date. Webster Financial was
    # acquired by Banco Santander and ceased trading. Same signature as EA.
    #
    # ⚠ CORRECTED 2026-08-28. This row previously modelled WBS as provider_last 2026-08-10 /
    # alt_last 2026-08-26 -> FAILED_OR_UNEXPLAINED, on the premise that WBS was a coverage
    # regression that regeneration could not clear. Production evidence refutes that premise:
    # WBS was never a coverage regression, and its live failure was EVIDENCE_ABSENT (no record
    # in the 2026-08-11 artifact at all), which regeneration DOES clear. The coverage-regression
    # shape is real and still exercised — by SYNTH.D below, under a name that asserts nothing
    # about a real ticker.
    "WBS": {
        "provider_last": date(2026, 8, 19),
        "alt_last": date(2026, 8, 19),
        "rows_after": 0,
        "expect": fa.PROVIDER_EXHAUSTED,
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
    # THE COVERAGE-REGRESSION SHAPE, under a synthetic name. Provider history exists and then
    # stops while the alternate source stays current: the rule refuses it as "coverage
    # regression, not exhaustion", and regenerating evidence does NOT make it attributable,
    # because the observations were never the problem. Held here deliberately — the branch is
    # real and must stay covered — but under a name that makes no claim about a live ticker.
    # WBS was believed to be this shape until 2026-08-28; it is not (see the WBS row).
    "SYNTH.D": {
        "provider_last": date(2026, 8, 10),
        "alt_last": date(2026, 8, 26),
        "rows_after": 0,
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
    # A name the artifact has never heard of: regenerate. This is the real WBS-on-2026-08-25
    # state, confirmed against production on 2026-08-28 — WBS had no record in the 2026-08-11
    # artifact at all, so it diagnosed EVIDENCE_ABSENT, not EVIDENCE_PRESENT_REFUSED.
    assert diagnosis["NEVER.SEEN"] == fa.EVIDENCE_ABSENT
    # A name with a current record the rule refused: investigate. Regeneration will not help,
    # and the prose says exactly that. SYNTH.D is the coverage-regression shape.
    assert diagnosis["SYNTH.D"] == fa.EVIDENCE_PRESENT_REFUSED
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


# ------------------------------------------------- the generate() seam (regression, 2026-08-28)
#
# ⚠ EVERY test above calls ``build_evidence_document`` DIRECTLY, and pins ``AS_OF = FRONTIER``
# with ``OBSERVED_AT`` on that same day. That is precisely the arrangement under which the
# defect found in review on 2026-08-28 is invisible: ``generate()`` derived its own run date
# from ``max(stage_effective)`` — the store frontier — while stamping ``adjudicated_at_utc``
# with the current instant. The refresh runs 06:00 ET, so the frontier is always the PRIOR
# trading day, every record claimed to be observed after its own run date, and
# ``classify_stale_symbol`` refused all of them. The generator refused everything it wrote and
# regeneration could never clear a name.
#
# The seam that carried the defect is the one no test crossed. These tests cross it: they call
# ``generate()`` end to end against real stores, with the production clock shape.


def _seam_stores(tmp_path: Path) -> tuple[Path, Path]:
    """Two DuckDB stores shaped like production on 2026-08-28.

    Staging reaches 2026-08-27. ``WBS`` stops at 2026-08-19 in BOTH stores and in
    ``tickers.lastpricedate`` — the observed production shape of a name that ceased trading.
    """
    import duckdb

    live, stage = tmp_path / "live.duckdb", tmp_path / "stage.duckdb"
    for path, frontier in ((live, date(2026, 8, 21)), (stage, date(2026, 8, 27))):
        con = duckdb.connect(str(path))
        try:
            con.execute("CREATE TABLE sep (ticker VARCHAR, date DATE, close DOUBLE, volume BIGINT)")
            con.execute("CREATE TABLE tickers (ticker VARCHAR, lastpricedate DATE)")
            # A fresh name carrying the store's frontier, so the frontier is not WBS's own date.
            for d in (frontier - timedelta(days=1), frontier):
                con.execute("INSERT INTO sep VALUES ('AAPL', ?, 100.0, 1000)", [d])
            con.execute("INSERT INTO tickers VALUES ('AAPL', ?)", [frontier])
            # WBS: ceased trading 2026-08-19, in both stores.
            for d in (date(2026, 8, 18), date(2026, 8, 19)):
                con.execute("INSERT INTO sep VALUES ('WBS', ?, 77.57, 91317000)", [d])
            con.execute("INSERT INTO tickers VALUES ('WBS', ?)", [date(2026, 8, 19)])
        finally:
            con.close()
    return live, stage


#: The run date these seam tests model — the morning AFTER the staging frontier, which is the
#: production shape at 06:00 ET and the condition the defect needed.
SEAM_RUN_DATE = date(2026, 8, 28)


def _seam_generate(tmp_path: Path, monkeypatch, **overrides):
    """``generate()`` end to end, with the production clock: frontier 08-27, run 08-28.

    ⚠ ``as_of`` is deliberately NOT passed. The defect lived in the DEFAULT derivation
    (``as_of = as_of or ...``), so a test that supplies ``as_of`` explicitly walks straight
    past it — which is how the original suite missed this. The schedule clock is stubbed
    instead, so the default path runs and stays deterministic.
    """
    live, stage = _seam_stores(tmp_path)
    monkeypatch.setattr(fe, "schedule_today", lambda *a, **k: SEAM_RUN_DATE)
    kwargs = {
        "live_path": live,
        "stage_path": stage,
        "universe": ["AAPL", "WBS"],
        "app_db": None,
        "probe": fe.StaticProbe(
            {"WBS": date(2026, 8, 19), "AAPL": date(2026, 8, 27)}, source="alpaca"
        ),
        "control_symbol": "AAPL",
        "now": datetime(2026, 8, 28, 10, 30, 27, tzinfo=UTC),
        "max_lag_days": TOLERANCE_DAYS,
    }
    kwargs.update(overrides)
    return fe.generate(**kwargs)


def test_generate_dates_the_run_by_the_schedule_not_the_store_frontier(tmp_path, monkeypatch):
    """THE REGRESSION. ``as_of`` is the run date; the frontier is data, not a clock.

    The negative assertion is the point: 2026-08-27 is the staging frontier, and it is exactly
    what the defective implementation wrote here.
    """
    doc = _seam_generate(tmp_path, monkeypatch)
    assert doc["as_of"] == "2026-08-28", (
        "as_of must be the scheduled RUN date. '2026-08-27' is the staging frontier - the "
        "defect this test exists to catch."
    )
    assert doc["as_of"] != "2026-08-27"
    # The metadata clock and the enforcement clock now agree (finding 9 resolves with this).
    assert doc["expires_on"] == "2026-09-27"


def test_generated_wbs_record_survives_the_loader_and_re_derives_exhausted(tmp_path, monkeypatch):
    """Generator -> artifact -> loader -> adjudicator, on the real WBS shape.

    Every earlier test stops at the document. This one carries it through the two steps that
    actually decided the production outcome: ``load_evidence_records`` (which DROPS a record
    claiming anything outside ``CLAIMABLE``) and the verifier's own re-derivation.
    """
    doc = _seam_generate(tmp_path, monkeypatch)
    record = next(r for r in doc["symbols"] if r["symbol"] == "WBS")
    assert record["expected_classification"] == fa.PROVIDER_EXHAUSTED
    assert "ceased trading" in record["generator_derived_reason"]

    path = tmp_path / "_factor_exhaustion_evidence.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    all_records, claimable, _note, status = fa.load_evidence_records(path)
    assert status == "ok"
    assert "WBS" in all_records
    assert "WBS" in claimable, (
        "the generated record was dropped by the loader - it claimed a classification outside "
        "CLAIMABLE, so adjudication would see no evidence and abort the swap"
    )

    # The verifier re-derives independently, from live facts, with ITS OWN as_of.
    verdict, reason = fa.classify_stale_symbol(
        "WBS",
        live_last=date(2026, 8, 19),
        stage_last=date(2026, 8, 19),
        cutoff=date(2026, 8, 23),
        tolerance_days=TOLERANCE_DAYS,
        as_of=date(2026, 8, 28),
        evidence=claimable["WBS"],
        held_qty=0.0,
        open_orders=0,
        registered_in=[],
    )
    assert verdict == fa.PROVIDER_EXHAUSTED, reason


def test_generate_refuses_to_write_an_artifact_that_postdates_its_own_run(tmp_path, monkeypatch):
    """The invariant, enforced: observation date <= run date. Loud, not silent.

    Passing the frontier as ``as_of`` is exactly what the defective default did. It must now
    raise rather than emit a document that refutes itself record by record.
    """
    with pytest.raises(fe.EvidenceError, match="AFTER the run date"):
        _seam_generate(tmp_path, monkeypatch, as_of=date(2026, 8, 27))


def test_the_defective_default_would_have_failed_this_suite(tmp_path):
    """Falsification: reproduce the OLD behaviour explicitly and prove it is refused.

    A regression test that only exercises the fixed path cannot show the defect was real. This
    one asserts the precise verdict and message the shipped generator produced in production.
    """
    doc = fe.build_evidence_document(
        non_fresh=["WBS"],
        live_effective={"WBS": date(2026, 8, 19)},
        stage_effective={"WBS": date(2026, 8, 19)},
        rows_after_frontier={"WBS": 0},
        corroborated={"WBS": date(2026, 8, 19)},
        control_symbol="AAPL",
        control_last_date=date(2026, 8, 27),
        corroboration_source="alpaca",
        requested={"WBS": True},
        request_status={"WBS": "ok"},
        operational={},
        universe_size=510,
        cutoff=date(2026, 8, 23),
        tolerance_days=TOLERANCE_DAYS,
        as_of=date(2026, 8, 27),  # the staging frontier - the defect
        observed_at=datetime(2026, 8, 28, 10, 30, 27, tzinfo=UTC),
    )
    record = doc["symbols"][0]
    assert record["expected_classification"] == fa.FAILED_OR_UNEXPLAINED
    assert "after the run date" in record["generator_derived_reason"]

    path = tmp_path / "_defective.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    _all, claimable, _note, _status = fa.load_evidence_records(path)
    assert claimable == {}, "the defective artifact must attribute nothing - that was the bug"


# ------------------------------ an empty universe must FAIL verification (finding 8, 2026-08-28)
#
# The verifier is documented as THE gate: the evidence writer is deliberately non-fatal
# ("a non-zero exit must NOT abort the refresh on its own — the verifier is the gate"). Until
# 2026-08-28 the entire per-name block — staleness, adjudication, the coverage gate AND the
# evidence-health check — sat behind `if s_sep is not None and universe:` with no `else`, so an
# empty universe produced ZERO failures and a passing verify, and the swap proceeded on a
# vacuously-green gate. `derive_refresh_universe` refuses to WRITE an empty universe, which
# lowers reachability but does not make the gate correct.


def _verify_stores(tmp_path: Path, name: str = "v") -> tuple[Path, Path]:
    """A healthy live/staging pair: same frontier, one fresh liquid name."""
    import duckdb

    live, stage = tmp_path / f"{name}_live.duckdb", tmp_path / f"{name}_stage.duckdb"
    for path in (live, stage):
        con = duckdb.connect(str(path))
        try:
            con.execute("CREATE TABLE sep (ticker VARCHAR, date DATE, close DOUBLE, volume BIGINT)")
            con.execute("CREATE TABLE tickers (ticker VARCHAR, lastpricedate DATE)")
            for d in (date(2026, 8, 26), date(2026, 8, 27)):
                con.execute("INSERT INTO sep VALUES ('AAPL', ?, 100.0, 1000)", [d])
            con.execute("INSERT INTO tickers VALUES ('AAPL', ?)", [date(2026, 8, 27)])
        finally:
            con.close()
    return live, stage


def test_an_empty_universe_fails_verification(tmp_path):
    """NEGATIVE CONTROL. A healthy staging store plus an empty universe must NOT pass.

    "Nothing to verify" is not "nothing failed". The universe defines the population being
    verified; with none, no per-name freshness, adjudication, coverage or evidence check is
    performed, and an unperformed check is not a passed one.
    """
    fr = _load("factor_refresh")
    live, stage = _verify_stores(tmp_path, "empty")
    failures, _report = fr.verify_staging(
        live_path=live, stage_path=stage, universe=[], evidence={}, as_of=date(2026, 8, 27)
    )
    assert any("universe is EMPTY" in f for f in failures), (
        f"an empty universe passed verification; failures were {failures}. A gate that passes "
        "when its input is absent is not a gate."
    )


def test_a_healthy_non_empty_universe_still_passes(tmp_path):
    """POSITIVE CONTROL. The new refusal must not fail an ordinary healthy run.

    Without this, the negative control above is satisfiable by failing everything.
    """
    fr = _load("factor_refresh")
    live, stage = _verify_stores(tmp_path, "healthy")
    failures, _report = fr.verify_staging(
        live_path=live, stage_path=stage, universe=["AAPL"], evidence={}, as_of=date(2026, 8, 27)
    )
    assert not any("universe is EMPTY" in f for f in failures), (
        f"a healthy non-empty universe was refused as empty: {failures}"
    )


# ---------- the counter's frontier is the SEP frontier (production gate-1 failure, 2026-08-28)
#
# Observed in production: `EA` adjudicated FAILED_OR_UNEXPLAINED with "provider returned 1 newer
# row(s); ingestion missed them" and `rows_after_live_frontier: 1`. EA is a delisted name whose
# live store holds `sep_max 2026-08-05` and `tickers.lastpricedate 2026-08-04`. The generator
# anchored the row COUNT to the EFFECTIVE frontier — min(sep_max, lastpricedate) = 08-04 — while
# counting SEP rows, so the already-ingested 08-05 row sat "after" the frontier permanently.
#
# Nothing was missed. The counter was measuring "SEP is ahead of lagging ticker metadata", which
# is not what `provider_rows_after_live_frontier` means, and the classifier correctly refused a
# name the evidence had mis-described. Generic defect, generic repair: no ticker is named in the
# code, and this shape is exercised under a synthetic name too.


def _delisted_shape_stores(tmp_path: Path, name: str) -> tuple[Path, Path]:
    """A store pair in the production `EA` shape, under a caller-chosen ticker.

    sep_max 2026-08-05, tickers.lastpricedate 2026-08-04, delisted — and the 08-05 SEP row is
    ALREADY PRESENT in both stores, which is the whole point: it is ingested, not missing.
    """
    import duckdb

    live, stage = tmp_path / "l.duckdb", tmp_path / "s.duckdb"
    for path, frontier in ((live, date(2026, 8, 21)), (stage, date(2026, 8, 27))):
        con = duckdb.connect(str(path))
        try:
            con.execute("CREATE TABLE sep (ticker VARCHAR, date DATE, close DOUBLE, volume BIGINT)")
            con.execute("CREATE TABLE tickers (ticker VARCHAR, lastpricedate DATE)")
            for d in (frontier - timedelta(days=1), frontier):
                con.execute("INSERT INTO sep VALUES ('AAPL', ?, 100.0, 1000)", [d])
            con.execute("INSERT INTO tickers VALUES ('AAPL', ?)", [frontier])
            for d in (date(2026, 8, 4), date(2026, 8, 5)):  # 08-05 present in BOTH stores
                con.execute(f"INSERT INTO sep VALUES ('{name}', ?, 120.0, 5000)", [d])
            con.execute(f"INSERT INTO tickers VALUES ('{name}', ?)", [date(2026, 8, 4)])
        finally:
            con.close()
    return live, stage


@pytest.mark.parametrize("ticker", ["EA", "SYNTH.E"])
def test_a_lagging_lastpricedate_is_not_reported_as_a_missed_ingestion(
    tmp_path, monkeypatch, ticker
):
    """THE REGRESSION. An already-ingested row must never read as one ingestion missed.

    Parametrised over the historical name and a synthetic one, so the repair cannot be satisfied
    by anything specific to `EA`.
    """
    live, stage = _delisted_shape_stores(tmp_path, ticker)
    monkeypatch.setattr(fe, "schedule_today", lambda *a, **k: date(2026, 8, 28))
    doc = fe.generate(
        live_path=live,
        stage_path=stage,
        universe=["AAPL", ticker],
        app_db=None,
        probe=fe.StaticProbe({ticker: None, "AAPL": date(2026, 8, 27)}, source="alpaca"),
        control_symbol="AAPL",
        now=datetime(2026, 8, 28, 21, 6, 18, tzinfo=UTC),
        max_lag_days=TOLERANCE_DAYS,
    )
    record = next(r for r in doc["symbols"] if r["symbol"] == ticker)

    assert record["provider_rows_after_live_frontier"] == 0, (
        "the already-ingested 2026-08-05 SEP row was counted as 'after the frontier' because "
        "the counter was anchored to min(sep_max, lastpricedate) instead of the SEP frontier"
    )
    assert "ingestion missed" not in (record["generator_derived_reason"] or "")
    assert record["expected_classification"] == fa.PROVIDER_EXHAUSTED, record[
        "generator_derived_reason"
    ]

    # ...and it must survive the loader, which is what the production run could not do.
    path = tmp_path / "_ev.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    _all, claimable, _note, status = fa.load_evidence_records(path)
    assert status == "ok" and ticker in claimable


def test_a_genuinely_missed_ingestion_is_still_refused(tmp_path, monkeypatch):
    """POSITIVE CONTROL for the guard the repair must NOT weaken.

    When the staging store really does hold price rows past the live SEP frontier, that IS an
    ingestion miss and must still be refused. Without this, the regression above is satisfiable
    by never counting anything.
    """
    import duckdb

    live, stage = _delisted_shape_stores(tmp_path, "SYNTH.F")
    con = duckdb.connect(str(stage))
    try:  # a real newer row, past the SEP frontier, present only in staging
        con.execute("INSERT INTO sep VALUES ('SYNTH.F', DATE '2026-08-26', 121.0, 5000)")
    finally:
        con.close()

    monkeypatch.setattr(fe, "schedule_today", lambda *a, **k: date(2026, 8, 28))
    doc = fe.generate(
        live_path=live,
        stage_path=stage,
        universe=["AAPL", "SYNTH.F"],
        app_db=None,
        probe=fe.StaticProbe({"SYNTH.F": None, "AAPL": date(2026, 8, 27)}, source="alpaca"),
        control_symbol="AAPL",
        now=datetime(2026, 8, 28, 21, 6, 18, tzinfo=UTC),
        max_lag_days=TOLERANCE_DAYS,
    )
    record = next(r for r in doc["symbols"] if r["symbol"] == "SYNTH.F")
    assert record["provider_rows_after_live_frontier"] == 1
    assert record["expected_classification"] == fa.FAILED_OR_UNEXPLAINED
    assert "ingestion missed" in record["generator_derived_reason"]
