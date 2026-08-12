"""End-to-end synthetic qualification of the Phase 3B runner.

Fixture data only. The reader is a `FixtureReader` with no AWS dependency, so this suite physically
cannot reach the sealed store, and the code path it exercises is the governed path with a different
collaborator injected.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat

import pytest

from app.research.mr002.phase3b import admissibility as A
from app.research.mr002.phase3b import census as C
from app.research.mr002.phase3b import enrichment as E
from app.research.mr002.phase3b import publish as P
from app.research.mr002.phase3b import roster as R
from app.research.mr002.phase3b import states as S
from app.research.mr002.phase3b.guard import OOS, VALIDATION, ValidationAccessRefused
from app.research.mr002.phase3b.readers import FixtureReader, PinnedObject, PinnedReadRefused
from app.research.mr002.phase3b.runner import Phase3BRunner, RunOutcome, RunRefused

BUCKET = "workbench-mr002-sealed-219024422756"
VAL_KEYS = ("validation/prices.parquet", "validation/actions.parquet")
CONFIG = {"A": 1.75, "B": 2.00, "C": 2.25}
RUNTIME = {"python": "3.13.14", "numpy": "2.2.6"}
CONTRACT = {
    "ExecutionEnrichmentSchema": "5b2480c1",
    "SignalDecisionRecord_schema": "49c0e550",
    "SignalDecisionRecord_model_module": "efc26d3a",
}
IDENTITIES = {
    "code_identity": "roster",
    "runtime_identity": "p10",
    "governing_identity": "2a1fb775",
}


class Decision:
    def __init__(self, session: int, tag: str, config: str = "B"):
        self.decision_session = session
        self._payload = {"tag": tag, "configuration_id": config}

    def canonical(self):
        return dict(self._payload)

    @property
    def record_identity(self):
        return hashlib.sha256(json.dumps(self.canonical(), sort_keys=True).encode()).hexdigest()


def _facts(**kw):
    base = dict(requested_execution_session=101, official_open=100.0, close_t=100.0)
    base.update(kw)
    return E.ExecutionFacts(**base)


# A fixture population designed so every branch COMPATIBLE WITH PASSING is exercised and each
# config appears. FUTURE_INFORMATION is deliberately absent: it is a preregistered integrity gate
# that must read zero, so a population containing it cannot pass by construction. It is covered by
# its own refusal test below.
POPULATION = [
    ("clean-B", "B", {}),
    ("clean-A", "A", {}),
    ("clean-C", "C", {}),
    ("gap-cancel", "B", dict(official_open=112.0)),
    ("ex-div-admitted", "B", dict(official_open=93.0, cash_distribution=7.0)),
    ("halt", "B", dict(halted=True)),
    ("delist", "B", dict(delisted_at_or_before_t_plus_1=True)),
    ("identity", "B", dict(identity_transition=True)),
    ("no-open", "B", dict(official_open=None)),
    ("basis-conflict", "B", dict(open_basis_conflict=True)),
    ("session-mismatch", "B", dict(actual_source_session=102)),
    ("calendar-mismatch", "B", dict(requested_execution_session=107)),
    ("missing-close", "B", dict(close_t=None)),
    (
        "ca-dividend-unresolved",
        "B",
        dict(corporate_action_kind="dividend", adjusted_open_constructible=False),
    ),
    (
        "ca-split-unresolved",
        "B",
        dict(corporate_action_kind="split", adjusted_open_constructible=False),
    ),
    ("ca-split-resolved", "B", dict(corporate_action_kind="split")),
    ("ca-merger", "B", dict(corporate_action_kind="merger", adjusted_open_constructible=False)),
]


class FixtureCandidateSource:
    """Stands in for the SPQ-1 producer over the validation window."""

    def __init__(self, population=POPULATION, fail_after: int | None = None):
        self.population = population
        self.fail_after = fail_after
        self.payload_keys: list[str] = []

    def candidates(self, payloads):
        self.payload_keys = sorted(payloads)
        out = []
        for i, (tag, cfg, kw) in enumerate(self.population):
            if self.fail_after is not None and i >= self.fail_after:
                raise RuntimeError("injected mid-run failure")
            out.append((Decision(100, tag, cfg), _facts(**kw)))
        return out


def _fixture_root(tmp_path):
    root = tmp_path / "fixtures"
    for key in VAL_KEYS:
        p = root / key
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(f"synthetic:{key}".encode())
    return str(root)


def _read_bytes(path: str) -> bytes:
    with open(path, "rb") as fh:
        return fh.read()


def _read_json(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _inputs(fixture_root):
    objs = []
    for key in VAL_KEYS:
        payload = _read_bytes(os.path.join(fixture_root, *key.split("/")))
        objs.append(PinnedObject(BUCKET, key, f"ver-{key}", hashlib.sha256(payload).hexdigest()))
    return objs


def _runner(tmp_path, *, source=None, out_name="out", reader=None):
    froot = _fixture_root(tmp_path)
    out = tmp_path / out_name
    out.mkdir(parents=True, exist_ok=True)
    return Phase3BRunner(
        reader=reader or FixtureReader(froot),
        candidate_source=source or FixtureCandidateSource(),
        output_root=str(out),
        registered_objects={VALIDATION: set(VAL_KEYS)},
        inputs=_inputs(froot),
        bound_roster=R.current_roster(),
        contract_identities=dict(CONTRACT),
        expected_contract_identities=dict(CONTRACT),
        config_mapping=dict(CONFIG),
        expected_config_mapping=dict(CONFIG),
        runtime_facts=dict(RUNTIME),
        expected_runtime_facts=dict(RUNTIME),
        published_at="2026-08-12T00:00:00Z",
        identities=dict(IDENTITIES),
    )


# --------------------------------------------------------------------- dry launch to the gate
def test_dry_launch_reaches_pre_access_ready_without_consuming_anything(tmp_path):
    runner = _runner(tmp_path)
    outcome = runner.run(stop_at=S.S7_PRE_ACCESS_READY)
    assert outcome.disposition == P.PASS
    assert outcome.state == S.S7_PRE_ACCESS_READY
    assert outcome.opening_consumed is False
    assert runner.guard.counts()["sealed_reads"] == 0
    assert runner.reader.reads == []
    assert os.listdir(runner.output_root) == []


def test_dry_launch_is_repeatable_because_nothing_was_spent(tmp_path):
    for _ in range(3):
        outcome = _runner(tmp_path).run(stop_at=S.S7_PRE_ACCESS_READY)
        assert outcome.disposition == P.PASS and not outcome.opening_consumed


# --------------------------------------------------------------------- full synthetic run
def test_full_synthetic_run_passes_every_gate(tmp_path):
    runner = _runner(tmp_path)
    outcome = runner.run()
    assert outcome.disposition == P.PASS, outcome.error
    assert outcome.exit_code == 0
    assert outcome.state == S.S11_PUBLISHED or outcome.state == S.S10_ENRICHED
    assert outcome.opening_consumed is True

    cen = outcome.enrichment_census
    assert cen["records_examined"] == len(POPULATION) > 0
    assert cen["one_terminal_code_per_record"] is True
    assert cen["reserved_codes"][E.STOP_SOURCE_MISSING] == 0

    integ = outcome.integrity
    assert integ["all_gates_zero"] is True
    assert integ["records_examined"] > 0
    for gate in (
        "decision_record_mutations",
        "missing_decision_enrichment_bindings",
        "duplicate_enrichment_identities",
        "future_information_violations",
        "unregistered_data_source_reads",
        "unreconciled_validation_units",
        "oos_reads",
    ):
        assert integ[gate] == 0, gate


def test_every_pass_compatible_edge_case_and_both_conditional_branches_are_exercised(tmp_path):
    outcome = _runner(tmp_path).run()
    produced = {k for k, v in outcome.enrichment_census["by_code"].items() if v > 0}
    pass_compatible = set(E.REGISTERED_CODES) - set(E.RESERVED_CODES) - {E.FUTURE_INFORMATION}
    assert produced == pass_compatible, f"unexercised: {sorted(pass_compatible - produced)}"
    # both branches of both conditional cases
    assert outcome.enrichment_census["by_code"][E.STOP_CORPORATE_ACTION] >= 3
    assert outcome.enrichment_census["by_code"][E.SUCCESS] >= 3


def test_future_information_refuses_the_whole_run(tmp_path):
    """The one edge case that cannot appear in a passing population: it is a zero-gate."""
    population = [*POPULATION, ("future-info", "B", dict(future_information=True))]
    runner = _runner(tmp_path, source=FixtureCandidateSource(population=population))
    outcome = runner.run()
    assert outcome.disposition == P.REFUSED
    assert outcome.integrity["future_information_violations"] == 1
    assert outcome.integrity["all_gates_zero"] is False
    assert "integrity gates non-zero" in (outcome.error or "")


def test_each_configuration_appears_with_a_non_zero_count(tmp_path):
    source = FixtureCandidateSource()
    runner = _runner(tmp_path, source=source)
    runner.run()
    counts: dict[str, int] = {}
    for _tag, cfg, _kw in POPULATION:
        counts[cfg] = counts.get(cfg, 0) + 1
    for cfg in ("A", "B", "C"):
        assert counts.get(cfg, 0) > 0, cfg


def test_gap_cancellation_is_success_plus_not_admitted_in_the_run(tmp_path):
    runner = _runner(tmp_path)
    outcome = runner.run()
    assert outcome.seam["not_admitted_gap_filter"] >= 1
    assert outcome.enrichment_census["by_code"][E.SUCCESS] >= 1
    # the gap-cancelled candidate did NOT become an enrichment stop
    manifest = _read_json(
        os.path.join(runner.output_root, "ValidationExecutionEnrichmentManifest_v1.0.json")
    )
    codes = [r["ExecutionEnrichmentCode"] for r in manifest["records"]]
    assert codes.count(E.SUCCESS) >= 3


# --------------------------------------------------------------------- the seam
def test_seam_reconciles_with_no_orphans_and_no_duplicate_joins(tmp_path):
    outcome = _runner(tmp_path).run()
    seam = outcome.seam
    assert seam["records_examined"] == seam["adjudications_examined"] == len(POPULATION)
    for k in (
        "orphan_enriched_records",
        "orphan_adjudications",
        "duplicate_enrichment_identities",
        "duplicate_adjudications",
        "state_violations",
        "missing_decision_enrichment_bindings",
    ):
        assert seam[k] == 0, k
    assert seam["economically_adjudicated"] + seam["not_adjudicated"] == len(POPULATION)


def test_seam_refuses_an_orphan_adjudication():
    d, f = Decision(100, "x"), _facts()
    rec = E.enrich(d, f)
    extra = A.adjudicate_entry(E.enrich(Decision(100, "y"), f), f)
    with pytest.raises(C.CensusRefused, match="no enriched record"):
        C.seam_reconciliation([rec], [A.adjudicate_entry(rec, f), extra])


def test_seam_refuses_a_missing_adjudication():
    d, f = Decision(100, "x"), _facts()
    rec = E.enrich(d, f)
    with pytest.raises(C.CensusRefused, match="no adjudication"):
        C.seam_reconciliation([rec], [])


def test_seam_refuses_a_duplicate_join():
    d, f = Decision(100, "x"), _facts()
    rec = E.enrich(d, f)
    adj = A.adjudicate_entry(rec, f)
    with pytest.raises(C.CensusRefused, match="duplicate"):
        C.seam_reconciliation([rec, rec], [adj, adj])


def test_seam_refuses_a_stop_carrying_an_economic_decision():
    f_stop = _facts(halted=True)
    rec = E.enrich(Decision(100, "x"), f_stop)
    bad = A.EntryAdjudication(
        rec.decision_record_sha256, 101, True, A.ADMITTED, 0.0, 0.06, "forged"
    )
    with pytest.raises(C.CensusRefused, match="stop carrying a decision"):
        C.seam_reconciliation([rec], [bad])


def test_census_refuses_an_empty_population():
    with pytest.raises(C.CensusRefused, match="not a pass"):
        C.enrichment_census([])


# --------------------------------------------------------------------- outputs
def test_all_nine_artifacts_are_expected_and_six_deliverables_are_written(tmp_path):
    runner = _runner(tmp_path)
    outcome = runner.run()
    written = sorted(os.listdir(runner.output_root))
    for name in P.DELIVERABLES:
        assert name in written, name
    assert P.REPORT in written and P.PUBLICATION in written
    assert len(P.EXPECTED_ARTIFACTS) == 9
    assert set(outcome.deliverable_hashes) == set(P.DELIVERABLES)


def test_every_output_is_locked_read_only_and_hash_recorded(tmp_path):
    runner = _runner(tmp_path)
    outcome = runner.run()
    for name, sha in outcome.deliverable_hashes.items():
        path = os.path.join(runner.output_root, name)
        mode = os.stat(path).st_mode
        assert not mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH), name
        with open(path, "rb") as fh:
            assert hashlib.sha256(fh.read()).hexdigest() == sha


def test_publication_refuses_an_occupied_output_root(tmp_path):
    runner = _runner(tmp_path)
    assert runner.run().disposition == P.PASS
    second = _runner(tmp_path, out_name="out")  # same root, already populated
    outcome = second.run()
    assert outcome.disposition == P.REFUSED
    assert "output_root_occupied" in (outcome.error or "")
    assert outcome.opening_consumed is False, "a refused rerun must not spend the opening"


def test_partial_output_is_preserved_on_an_injected_mid_run_failure(tmp_path):
    runner = _runner(tmp_path, source=FixtureCandidateSource(fail_after=5))
    outcome = runner.run()
    assert outcome.disposition == P.REFUSED
    assert outcome.opening_consumed is True
    written = sorted(os.listdir(runner.output_root))
    assert P.REPORT in written and P.PUBLICATION in written
    report = _read_json(os.path.join(runner.output_root, P.REPORT))
    assert report["partial_run"] is True
    assert report["deliverables_not_produced"], "a partial run must name what it did not produce"


def test_exit_code_must_agree_with_the_disposition():
    with pytest.raises(P.PublicationRefused, match="exit_disposition_disagreement"):
        P.verify_exit_agreement(P.PASS, 3)


# --------------------------------------------------------------------- refusals before the gate
def test_roster_drift_refuses_before_anything_is_spent(tmp_path):
    runner = _runner(tmp_path)
    runner.bound_roster["producer"]["producer.py"] = "0" * 64
    outcome = runner.run()
    assert outcome.disposition == P.REFUSED
    assert outcome.opening_consumed is False
    assert runner.guard.counts()["sealed_reads"] == 0


def test_configuration_mismatch_refuses_before_the_gate(tmp_path):
    runner = _runner(tmp_path)
    runner.config_mapping = {"A": 1.75, "B": 2.10, "C": 2.25}
    outcome = runner.run()
    assert outcome.disposition == P.REFUSED and not outcome.opening_consumed
    assert "configuration mismatch" in outcome.error


def test_contract_identity_drift_refuses_before_the_gate(tmp_path):
    runner = _runner(tmp_path)
    runner.contract_identities["ExecutionEnrichmentSchema"] = "deadbeef"
    outcome = runner.run()
    assert outcome.disposition == P.REFUSED and not outcome.opening_consumed


def test_runtime_mismatch_refuses_before_the_gate(tmp_path):
    runner = _runner(tmp_path)
    runner.runtime_facts["numpy"] = "1.26.0"
    outcome = runner.run()
    assert outcome.disposition == P.REFUSED and not outcome.opening_consumed


def test_input_outside_the_registered_set_refuses(tmp_path):
    runner = _runner(tmp_path)
    runner.inputs[0] = PinnedObject(BUCKET, "validation/rogue.parquet", "v", "0" * 64)
    outcome = runner.run()
    assert outcome.disposition == P.REFUSED and not outcome.opening_consumed


# --------------------------------------------------------------------- reader + OOS
def test_oos_is_rejected_even_under_the_synthetic_reader(tmp_path):
    runner = _runner(tmp_path)
    runner.run(stop_at=S.S7_PRE_ACCESS_READY)
    runner.guard.pre_access_ready = True
    with pytest.raises(ValidationAccessRefused):
        runner.guard.open_object(OOS, "oos/prices.parquet", version_id="v")
    assert runner.guard.counts()["oos_reads"] == 0


def test_fixture_reader_refuses_an_unpinned_or_mismatched_object(tmp_path):
    froot = _fixture_root(tmp_path)
    reader = FixtureReader(froot)
    obj = PinnedObject(BUCKET, VAL_KEYS[0], "", "0" * 64)
    with pytest.raises(PinnedReadRefused, match="unpinned"):
        reader.read(obj)
    with pytest.raises(PinnedReadRefused, match="checksum mismatch"):
        reader.read(PinnedObject(BUCKET, VAL_KEYS[0], "v", "0" * 64))


def test_fixture_reader_has_no_aws_dependency():
    import app.research.mr002.phase3b.readers as mod

    with open(mod.__file__, encoding="utf-8") as fh:
        src = fh.read()
    assert "import boto3" not in src and "botocore" not in src


def test_retry_is_refused_after_simulated_consumption(tmp_path):
    runner = _runner(tmp_path)
    runner.run()
    assert runner.sequence.opening_consumed
    with pytest.raises(S.SequenceViolation, match="PROHIBITED"):
        runner.sequence.assert_may_restart()


def test_run_outcome_defaults_to_refused_not_pass():
    """A result object that defaults to PASS would make a crashed run look successful."""
    assert RunOutcome().disposition == P.REFUSED
    assert RunOutcome().exit_code == P.EXIT_BY_DISPOSITION[P.REFUSED]


def test_runner_refuses_a_zero_candidate_run(tmp_path):
    runner = _runner(tmp_path, source=FixtureCandidateSource(population=[]))
    outcome = runner.run()
    assert outcome.disposition == P.REFUSED
    assert "zero candidates" in (outcome.error or "")
    assert isinstance(RunRefused("x"), Exception)
