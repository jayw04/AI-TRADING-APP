"""COMPONENT end-to-end: the real ProducerCandidateSource with injected units/identity.

⚠ This is component qualification, NOT execution qualification. It injects units, CIK map and
lineage. The production-entry qualification that injects nothing but the reader lives in
test_phase3b_entrypoint_qualification.py.

Same synthetic world as the qualified equivalence suite, the same code path the governed run will
take, and a `FixtureReader` with no AWS dependency in place of the S3 reader. Nothing else differs,
which is the whole point of injecting the reader rather than importing it.

Each test names one of the owner's acceptance conditions for this run.
"""

from __future__ import annotations

import io
import json
import os
import stat
from datetime import UTC, date, datetime

import pytest

pa = pytest.importorskip("pyarrow")
import pyarrow.parquet as pq  # noqa: E402


def _d(values):
    """A real Arrow DATE column, matching the sealed partition's declared logical type."""
    return pa.array([date.fromisoformat(str(v)[:10]) for v in values], type=pa.date32())


def _ts(values):
    """A real Arrow TIMESTAMP('us', tz='UTC') column, as sic_observations.accepted_utc is declared."""
    out = []
    for v in values:
        dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        out.append(dt if dt.tzinfo else dt.replace(tzinfo=UTC))
    return pa.array(out, type=pa.timestamp("us", tz="UTC"))



from app.research.mr002.phase3b import candidates as CS  # noqa: E402
from app.research.mr002.phase3b import enrichment as E  # noqa: E402
from app.research.mr002.phase3b import publish as P  # noqa: E402
from app.research.mr002.phase3b import roster as R  # noqa: E402
from app.research.mr002.phase3b import states as S  # noqa: E402
from app.research.mr002.phase3b.guard import OOS, VALIDATION, ValidationAccessRefused  # noqa: E402
from app.research.mr002.phase3b.readers import FixtureReader, PinnedObject  # noqa: E402
from app.research.mr002.phase3b.runner import Phase3BRunner  # noqa: E402
from app.research.mr002.spq1.calendar import RegisteredCalendar  # noqa: E402
from app.research.mr002.spq1.identities import InputIdentityRegistry  # noqa: E402
from tests.research.phase3b import fixtures_producer as F  # noqa: E402
from tests.research.phase3b.test_phase3b_candidate_equivalence import (  # noqa: E402
    SIC_OBS_ROWS,
)

BUCKET = "workbench-mr002-sealed-219024422756"
CAL = RegisteredCalendar(tuple(F.SESSIONS))

VALIDATION_TABLES = ("prices", "etf_prices", "actions", "sic_observations")
REFERENCE_TABLES = ("sic_mapping",)


def _arrow_tables() -> dict[str, object]:
    prices, etfs = F.price_rows(), F.etf_rows()
    return {
        "prices": pa.table(
            {
                "ticker": [r[0] for r in prices],
                "date": _d([r[1] for r in prices]),
                "open": [r[4] - 0.25 for r in prices],
                "high": [r[2] + 1.0 for r in prices],
                "low": [r[2] - 1.0 for r in prices],
                "close": [r[4] for r in prices],
                "closeadj": [r[2] for r in prices],
                "closeunadj": [r[3] for r in prices],
                "volume": [r[5] for r in prices],
            }
        ),
        "etf_prices": pa.table(
            {
                "ticker": [r[0] for r in etfs],
                "date": _d([r[1] for r in etfs]),
                "adjclose": [r[2] for r in etfs],
            }
        ),
        "actions": pa.table(
            {
                "date": _d([F.SESSIONS[F.SCORE_T + 1]]),
                "ticker": ["HEALTHY"],
                "action": ["dividend"],
                "value": [0.40],
            }
        ),
        "sic_observations": pa.table(
            {
                "cik": [r[0] for r in SIC_OBS_ROWS],
                "accepted_utc": _ts([r[1] for r in SIC_OBS_ROWS]),
                "sic": [r[2] for r in SIC_OBS_ROWS],
                "accession": [r[3] for r in SIC_OBS_ROWS],
            }
        ),
        "sic_mapping": pa.table(
            {
                "sic_start": [r[0] for r in F.SIC_MAP_ROWS],
                "sic_end": [r[1] for r in F.SIC_MAP_ROWS],
                "effective_from": [r[2] for r in F.SIC_MAP_ROWS],
                "research_sector": [r[3] for r in F.SIC_MAP_ROWS],
                "sector_etf": [r[4] for r in F.SIC_MAP_ROWS],
            }
        ),
    }


def _manifest(tables: dict, names: tuple[str, ...]) -> dict:
    """A P9-shaped commitment built from the fixture, so the decode control is genuinely applied."""
    schema, structure = {}, {}
    for name in names:
        table = tables[name]
        schema[name] = [{"name": c, "type": "ANY"} for c in table.column_names]
        entry: dict = {"row_count": table.num_rows}
        if "date" in table.column_names:
            values = [str(v)[:10] for v in table.column("date").to_pylist() if v is not None]
            entry["date_bounds"] = {
                "availability_column": "date",
                "first": min(values),
                "last": max(values),
            }
        structure[name] = entry
    return {"schema_identity": {"tables": schema}, "structure": structure}


def _payload(table) -> bytes:
    buf = io.BytesIO()
    pq.write_table(table, buf)
    return buf.getvalue()


def _world(tmp_path):
    tables = _arrow_tables()
    root = tmp_path / "fixtures"
    objects: list[PinnedObject] = []
    import hashlib

    for prefix, names in (("validation", VALIDATION_TABLES), ("reference", REFERENCE_TABLES)):
        for name in names:
            payload = _payload(tables[name])
            path = root / prefix / f"{name}.parquet"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
            objects.append(
                PinnedObject(
                    BUCKET,
                    f"{prefix}/{name}.parquet",
                    f"ver-{prefix}-{name}",
                    hashlib.sha256(payload).hexdigest(),
                )
            )
    return tables, str(root), objects


def _registry() -> InputIdentityRegistry:
    ids = dict(F.OBSERVED_IDENTITIES)
    ids["registered_exchange_calendar"] = CAL.identity
    ids.update(F.GOVERNING)
    return InputIdentityRegistry(ids)


def _units(config="B"):
    return [CS.Unit(s, F.SCORE_T, "LONG", config) for s in F.SECURITIES]


def _runner(tmp_path, *, units=None, out_name="out", source=None):
    tables, froot, objects = _world(tmp_path)
    out = tmp_path / out_name
    out.mkdir(parents=True, exist_ok=True)
    real_source = source or CS.ProducerCandidateSource(
        calendar=CAL,
        units=units or _units(),
        lineage=F.lineage_registry(),
        cik_by_symbol=F.CIK_BY_SYMBOL,
        registry=_registry(),
        observed_identities=dict(F.OBSERVED_IDENTITIES),
        spy_ticker=F.SPY,
        structural_manifest=_manifest(tables, VALIDATION_TABLES),
        reference_manifest=_manifest(tables, REFERENCE_TABLES),
        # COMPONENT qualification: this suite predates the production construction path and
        # carries no anchors/universe/crosswalk tables. Declaring empty checks opts out of the
        # earnings controls explicitly rather than letting a missing table disable them silently.
        # PRODUCTION qualification is test_phase3b_entrypoint_qualification.py, which builds
        # everything from the six committed tables.
        eligibility_checks_by_symbol={},
    )
    return Phase3BRunner(
        reader=FixtureReader(froot),
        candidate_source=real_source,
        output_root=str(out),
        registered_objects={VALIDATION: {o.key for o in objects}},
        inputs=objects,
        bound_roster=R.current_roster(),
        contract_identities={"ExecutionEnrichmentSchema": "5b2480c1"},
        expected_contract_identities={"ExecutionEnrichmentSchema": "5b2480c1"},
        config_mapping={"A": 1.75, "B": 2.00, "C": 2.25},
        expected_config_mapping={"A": 1.75, "B": 2.00, "C": 2.25},
        runtime_facts={"python": "3.13.14"},
        expected_runtime_facts={"python": "3.13.14"},
        clock=lambda: "2026-08-12T00:00:00Z",
        identities={
            # The live closure identity, as a real execution configuration declares it.
            "code_identity": R.closure_identity(),
            "runtime_identity": "p10",
            "governing_identity": "2a1fb775",
        },
        observed_identities={"execution_closure_sha256": R.closure_identity()},
    )


def _read_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# --------------------------------------------------------------- 1-3 reader, gate, no AWS
def test_runner_uses_the_real_producer_candidate_source(tmp_path):
    runner = _runner(tmp_path)
    assert isinstance(runner.candidate_source, CS.ProducerCandidateSource)
    assert runner.reader.reader_kind == "FIXTURE"


def test_reaches_pre_access_ready_without_consuming_anything(tmp_path):
    runner = _runner(tmp_path)
    outcome = runner.run(stop_at=S.S7_PRE_ACCESS_READY)
    assert outcome.disposition == P.PASS
    assert outcome.state == S.S7_PRE_ACCESS_READY
    assert not outcome.opening_consumed
    assert runner.reader.reads == [] and os.listdir(runner.output_root) == []


def test_full_post_gate_path_runs_without_aws(tmp_path):
    runner = _runner(tmp_path)
    outcome = runner.run()
    assert outcome.disposition == P.PASS, outcome.error
    assert outcome.opening_consumed
    assert runner.reader.reader_kind == "FIXTURE"
    assert len(runner.reader.reads) == len(runner.inputs)


# --------------------------------------------------------------- 4-5 artifacts, configs
def test_a_passing_run_reaches_the_terminal_published_state(tmp_path):
    """S11 must actually be entered; a terminal state nothing reaches is not a state machine."""
    runner = _runner(tmp_path)
    outcome = runner.run()
    assert outcome.disposition == P.PASS, outcome.error
    assert outcome.state == S.S11_PUBLISHED
    assert outcome.history[-1] == S.S11_PUBLISHED


def test_real_adapter_population_is_homogeneous_by_construction(tmp_path):
    """Producer refusals drop out BEFORE enrichment, so this run exercises only SUCCESS.

    That is correct behaviour, not coverage: the enrichment edge cases are exercised by the
    fixture-source end-to-end suite, which can present arbitrary execution facts. Recorded here so
    a green real-adapter run is not mistaken for enrichment coverage it does not provide.
    """
    runner = _runner(tmp_path)
    outcome = runner.run()
    exercised = {k for k, v in outcome.enrichment_census["by_code"].items() if v}
    assert exercised == {E.SUCCESS}
    assert runner.candidate_source.refusals, "producer refusals must still be exercised upstream"
    assert len({c for _s, _t, c in runner.candidate_source.refusals}) >= 3


def test_produces_all_nine_expected_artifacts(tmp_path):
    runner = _runner(tmp_path)
    outcome = runner.run()
    assert outcome.disposition == P.PASS, outcome.error
    written = set(os.listdir(runner.output_root))
    for name in P.DELIVERABLES:
        assert name in written, name
    assert P.REPORT in written and P.PUBLICATION in written
    assert len(P.EXPECTED_ARTIFACTS) == 9


@pytest.mark.parametrize("config", ["A", "B", "C"])
def test_exact_config_coverage(tmp_path, config):
    runner = _runner(tmp_path, units=_units(config), out_name=f"out-{config}")
    outcome = runner.run()
    assert outcome.disposition == P.PASS, outcome.error
    manifest = _read_json(
        os.path.join(runner.output_root, "ValidationExecutionEnrichmentManifest_v1.0.json")
    )
    assert manifest["count"] > 0, f"config {config} produced no enriched record"


# --------------------------------------------------------------- 6-9 censuses and the seam
def test_enrichment_and_adjudication_counts_reconcile(tmp_path):
    runner = _runner(tmp_path)
    outcome = runner.run()
    cen, seam = outcome.enrichment_census, outcome.seam
    assert cen["records_examined"] == seam["records_examined"] > 0
    assert seam["records_examined"] == seam["adjudications_examined"]
    assert seam["economically_adjudicated"] + seam["not_adjudicated"] == seam["records_examined"]
    assert cen["one_terminal_code_per_record"] is True


def test_source_missing_is_zero_and_price_conflict_counted_separately(tmp_path):
    runner = _runner(tmp_path)
    outcome = runner.run()
    by_code = outcome.enrichment_census["by_code"]
    by_cat = outcome.enrichment_census["by_census_category"]
    assert by_code[E.STOP_SOURCE_MISSING] == 0
    assert outcome.enrichment_census["reserved_codes"][E.STOP_SOURCE_MISSING] == 0
    assert "price conflict" in by_cat
    assert by_cat["price conflict"] == by_code[E.STOP_PRICE_CONFLICT]


def test_no_orphan_joins_no_future_information_no_mutation(tmp_path):
    runner = _runner(tmp_path)
    outcome = runner.run()
    seam, integ = outcome.seam, outcome.integrity
    for key in (
        "orphan_enriched_records",
        "orphan_adjudications",
        "duplicate_enrichment_identities",
        "duplicate_adjudications",
        "state_violations",
        "missing_decision_enrichment_bindings",
    ):
        assert seam[key] == 0, key
    assert integ["future_information_violations"] == 0
    assert integ["decision_record_mutations"] == 0
    assert integ["all_gates_zero"] is True
    assert integ["records_examined"] > 0


def test_only_produced_records_are_enriched_refusals_are_dropped(tmp_path):
    """The producer refuses several fixture securities; those must never become candidates."""
    runner = _runner(tmp_path)
    outcome = runner.run()
    source = runner.candidate_source
    assert source.refusals, "the fixture world must exercise producer refusals"
    assert outcome.enrichment_census["records_examined"] + len(source.refusals) == len(source.units)


# --------------------------------------------------------------- 10-13 failure behaviour
def test_occupied_output_root_refuses_without_consuming(tmp_path):
    first = _runner(tmp_path)
    assert first.run().disposition == P.PASS
    second = _runner(tmp_path, out_name="out")
    outcome = second.run()
    assert outcome.disposition == P.REFUSED
    assert "output_root_occupied" in (outcome.error or "")
    assert not outcome.opening_consumed


def test_injected_mid_run_failure_preserves_partial_output(tmp_path):
    class Failing(CS.ProducerCandidateSource):
        def candidates(self, payloads):  # noqa: ANN001
            super().candidates(payloads)
            raise RuntimeError("injected mid-run failure")

    tables, froot, objects = _world(tmp_path)
    failing = Failing(
        calendar=CAL,
        units=_units(),
        lineage=F.lineage_registry(),
        cik_by_symbol=F.CIK_BY_SYMBOL,
        registry=_registry(),
        observed_identities=dict(F.OBSERVED_IDENTITIES),
        spy_ticker=F.SPY,
        structural_manifest=_manifest(tables, VALIDATION_TABLES),
        reference_manifest=_manifest(tables, REFERENCE_TABLES),
    )
    runner = _runner(tmp_path, source=failing, out_name="out-fail")
    outcome = runner.run()
    assert outcome.disposition == P.REFUSED
    assert outcome.opening_consumed, "the failure occurred after the opening was consumed"
    written = set(os.listdir(runner.output_root))
    assert P.REPORT in written and P.PUBLICATION in written
    report = _read_json(os.path.join(runner.output_root, P.REPORT))
    assert report["partial_run"] is True
    assert report["deliverables_not_produced"]


def test_retry_prohibited_after_simulated_consumption(tmp_path):
    runner = _runner(tmp_path)
    runner.run()
    assert runner.sequence.opening_consumed
    with pytest.raises(S.SequenceViolation, match="PROHIBITED"):
        runner.sequence.assert_may_restart()


def test_oos_remains_refused(tmp_path):
    runner = _runner(tmp_path)
    runner.run()
    with pytest.raises(ValidationAccessRefused):
        runner.guard.open_object(OOS, "oos/prices.parquet", version_id="v")
    assert runner.guard.counts()["oos_reads"] == 0


# --------------------------------------------------------------- 14-16 identity + outputs
def test_execution_roster_checks_remain_green_and_refuse_drift(tmp_path):
    runner = _runner(tmp_path)
    assert runner.run().disposition == P.PASS
    drifted = _runner(tmp_path, out_name="out-drift")
    drifted.bound_roster["producer"]["producer.py"] = "0" * 64
    outcome = drifted.run()
    assert outcome.disposition == P.REFUSED
    assert not outcome.opening_consumed


def test_every_output_is_read_only_with_a_recorded_hash(tmp_path):
    runner = _runner(tmp_path)
    outcome = runner.run()
    import hashlib

    for name, sha in outcome.deliverable_hashes.items():
        path = os.path.join(runner.output_root, name)
        assert not os.stat(path).st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH), name
        with open(path, "rb") as fh:
            assert hashlib.sha256(fh.read()).hexdigest() == sha


def test_opened_object_ledger_chains_and_records_pinned_reads(tmp_path):
    runner = _runner(tmp_path)
    runner.run()
    ledger = _read_json(os.path.join(runner.output_root, "ValidationOpenedObjectLedger_v1.0.json"))
    assert ledger["chain_verifies"] is True
    assert ledger["counts"]["oos_reads"] == 0
    assert ledger["counts"]["validation_reads"] == len(runner.inputs)
    assert all(e["version_id"] for e in ledger["ledger"] if e["permitted"])
