"""Qualification from the TRUE production entry point.

No downstream fixture injection. The only injected dependency below the entry point is the reader,
and it is the hermetic `FixtureReader`; units, CIK map, lineage, earnings controls, sector data,
prices and actions are all built by the production code from the six committed tables.

Each test names one of the owner's non-vacuity conditions for this qualification.
"""

from __future__ import annotations

import hashlib
import io
import json
import os

import pytest

pa = pytest.importorskip("pyarrow")
import pyarrow.parquet as pq  # noqa: E402

from app.research.mr002.phase3b import entrypoint as EP  # noqa: E402
from app.research.mr002.phase3b import publish as P  # noqa: E402
from app.research.mr002.phase3b import roster as R  # noqa: E402
from app.research.mr002.phase3b import states as S  # noqa: E402
from app.research.mr002.phase3b.readers import FixtureReader  # noqa: E402
from app.research.mr002.spq1 import (  # noqa: E402
    PHASE0_CENSUS_SHA256,
    PHASE0_OWNER_RULINGS_SHA256,
    PHASE0_SCHEMA_SHA256,
    PRODUCER_CODE_VERSION,
)
from tests.research.phase3b import fixtures_producer as F  # noqa: E402

BUCKET = "workbench-mr002-sealed-219024422756"
WINDOW_TABLES = ("prices", "etf_prices", "actions", "sic_observations", "universe", "anchors")
REFERENCE_TABLES = ("sic_mapping", "crosswalk")

ANCHOR_SESSION = F.SESSIONS[40]  # early enough that its 70-day blackout lands in-window
MIDWINDOW_LINEAGE_START = F.SESSIONS[5]  # a crosswalk interval opening INSIDE the window


def _tables() -> dict:
    prices, etfs = F.price_rows(), F.etf_rows()
    months = sorted({s[:7] for s in F.SESSIONS})
    universe_rows = [
        (f"{m}-01", sym, 1000 + i, True, True) for m in months for i, sym in enumerate(F.SECURITIES)
    ]
    crosswalk_rows = [
        (1000 + i, sym, F.CIK_BY_SYMBOL[sym], MIDWINDOW_LINEAGE_START)
        for i, sym in enumerate(F.SECURITIES)
    ]
    crosswalk_rows.append((9999, "AMBIG", 777, MIDWINDOW_LINEAGE_START))
    crosswalk_rows.append((9998, "AMBIG", 778, MIDWINDOW_LINEAGE_START))
    anchor_rows = [
        (
            sym,
            F.CIK_BY_SYMBOL[sym],
            f"acc-{sym}",
            ANCHOR_SESSION,
            "PRE_OPEN",
            f"{ANCHOR_SESSION}T12:00:00Z",
        )
        for sym in F.SECURITIES
    ]
    return {
        "prices": pa.table(
            {
                "ticker": [r[0] for r in prices],
                "date": [r[1] for r in prices],
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
                "date": [r[1] for r in etfs],
                "adjclose": [r[2] for r in etfs],
            }
        ),
        "actions": pa.table(
            {
                "date": [F.SESSIONS[F.SCORE_T + 1]],
                "ticker": ["HEALTHY"],
                "action": ["dividend"],
                "value": [0.40],
            }
        ),
        "sic_observations": pa.table(
            {
                "cik": [c for c, *_ in [(v, 0) for v in F.CIK_BY_SYMBOL.values()]],
                "accepted_utc": ["2019-10-04T12:00:00Z"] * len(F.CIK_BY_SYMBOL),
                "sic": ["2500"] * len(F.CIK_BY_SYMBOL),
                "accession": [f"sic-{v}" for v in F.CIK_BY_SYMBOL.values()],
            }
        ),
        "universe": pa.table(
            {
                "universe_month": [r[0] for r in universe_rows],
                "ticker": [r[1] for r in universe_rows],
                "permaticker": [r[2] for r in universe_rows],
                "siccode": [2500] * len(universe_rows),
                "liquidity_rank": [1] * len(universe_rows),
                "med_dv_60": [1e9] * len(universe_rows),
                "in_long_universe": [r[3] for r in universe_rows],
                "in_short_universe": [r[4] for r in universe_rows],
            }
        ),
        "anchors": pa.table(
            {
                "ticker": [r[0] for r in anchor_rows],
                "cik": [r[1] for r in anchor_rows],
                "accession": [r[2] for r in anchor_rows],
                "session_date": [r[3] for r in anchor_rows],
                "availability_class": [r[4] for r in anchor_rows],
                "is_amendment_origin": [False] * len(anchor_rows),
                "acceptance_utc": [r[5] for r in anchor_rows],
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
        "crosswalk": pa.table(
            {
                "permaticker": [r[0] for r in crosswalk_rows],
                "ticker": [r[1] for r in crosswalk_rows],
                "cik": [r[2] for r in crosswalk_rows],
                "effective_from": [r[3] for r in crosswalk_rows],
                "effective_to": [None] * len(crosswalk_rows),
                "relationship_type": ["ticker_rename"] * len(crosswalk_rows),
                "source": ["fixture"] * len(crosswalk_rows),
                "source_record_id": ["x"] * len(crosswalk_rows),
                "confidence": ["high"] * len(crosswalk_rows),
                "mapping_rationale": ["fixture"] * len(crosswalk_rows),
                "review_status": ["auto"] * len(crosswalk_rows),
            }
        ),
    }


def _payload(table) -> bytes:
    buf = io.BytesIO()
    pq.write_table(table, buf)
    return buf.getvalue()


def _manifest(tables: dict, names: tuple[str, ...]) -> dict:
    schema, structure = {}, {}
    for name in names:
        t = tables[name]
        schema[name] = [{"name": c, "type": "ANY"} for c in t.column_names]
        entry: dict = {"row_count": t.num_rows}
        if "date" in t.column_names:
            vals = [str(v) for v in t.column("date").to_pylist() if v is not None]
            entry["date_bounds"] = {
                "availability_column": "date",
                "first": min(vals),
                "last": max(vals),
            }
        structure[name] = entry
    return {"schema_identity": {"tables": schema}, "structure": structure}


def _reference_manifest(tables: dict, names: tuple[str, ...]) -> dict:
    """A reference manifest now DECLARES its objects; the entry point fetches exactly those."""
    m = _manifest(tables, names)
    m["objects"] = {f"reference/{n}.parquet": {"declared_by": "reference manifest"} for n in names}
    return m


def _world(tmp_path, omit: str | None = None):
    tables = _tables()
    root = tmp_path / "fixtures"
    objects = {}
    for prefix, names in (("validation", WINDOW_TABLES), ("reference", REFERENCE_TABLES)):
        for name in names:
            if name == omit:
                continue
            payload = _payload(tables[name])
            path = root / prefix / f"{name}.parquet"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
            objects[f"{prefix}/{name}.parquet"] = {
                "version_id": f"ver-{name}",
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
    return tables, str(root), {"bucket": BUCKET, "objects": objects}


CONFIG = {
    "observed_identities": dict(F.OBSERVED_IDENTITIES),
    "runtime_facts": {"python": "3.13.14"},
    "expected_runtime_facts": {"python": "3.13.14"},
    "contract_identities": {"ExecutionEnrichmentSchema": "5b2480c1"},
    "identities": {
        "code_identity": "roster",
        "runtime_identity": "p10",
        "governing_identity": "2a1fb775",
    },
    "config_mapping": {"A": 1.75, "B": 2.00, "C": 2.25},
}


def _config_declaring_the_live_closure() -> dict:
    """CONFIG with the closure identity a real execution configuration would carry.

    Resolved per call, not at import: sibling suites transiently add and remove modules inside the
    package while exercising the closure machinery, so an identity captured at module scope goes
    stale depending on test order.
    """
    live = R.closure_identity()
    cfg = {k: (dict(v) if isinstance(v, dict) else v) for k, v in CONFIG.items()}
    cfg["identities"]["code_identity"] = live
    cfg["observed_identities"]["execution_closure_sha256"] = live
    return cfg
assert PRODUCER_CODE_VERSION and PHASE0_CENSUS_SHA256 and PHASE0_OWNER_RULINGS_SHA256
assert PHASE0_SCHEMA_SHA256


def _runner(tmp_path, *, omit: str | None = None, out="out"):
    tables, froot, upload = _world(tmp_path, omit=omit)
    out_dir = tmp_path / out
    out_dir.mkdir(parents=True, exist_ok=True)
    return EP.build_runner(
        reader=FixtureReader(froot),
        output_root=str(out_dir),
        sessions=list(F.SESSIONS),
        upload_manifest=upload,
        structural_manifest=_manifest(tables, tuple(n for n in WINDOW_TABLES if n != omit)),
        reference_manifest=_reference_manifest(
            tables, tuple(n for n in REFERENCE_TABLES if n != omit)
        ),
        **_config_declaring_the_live_closure(),
    )


# --------------------------------------------------------------- 1: all six tables opened
def test_all_six_committed_window_tables_are_opened_by_production_construction(tmp_path):
    runner = _runner(tmp_path)
    runner.run()
    opened = set(runner.candidate_source.tables_opened)
    for name in WINDOW_TABLES:
        assert name in opened, f"{name} was never opened by the production path"
    for name in REFERENCE_TABLES:
        assert name in opened, name


# --------------------------------------------------------------- 2-5: each input contributes
def test_universe_contributes_units(tmp_path):
    runner = _runner(tmp_path)
    runner.run()
    assert runner.candidate_source.units, "universe contributed no units"
    assert len(runner.candidate_source.units) > len(F.SECURITIES)


def test_crosswalk_contributes_a_midwindow_lineage_interval(tmp_path):
    runner = _runner(tmp_path)
    runner.run()
    lineage = runner.candidate_source.lineage
    ordinals = {r.effective_session_ordinal for recs in lineage.lineage.values() for r in recs}
    assert any(o > 0 for o in ordinals), "no lineage interval opened inside the window"


def test_anchors_produce_both_a_cooling_and_a_stale_anchor_exclusion(tmp_path):
    from app.research.mr002.phase3b.earnings_blackout import (
        BLACKOUT_RULE_ID,
        COOLING_RULE_ID,
    )

    runner = _runner(tmp_path)
    runner.run()
    source = runner.candidate_source
    anchor_ordinal = F.SESSIONS.index(ANCHOR_SESSION)
    cooling = source._eligibility_checks(
        type(source.units[0])("HEALTHY", anchor_ordinal - 1, "LONG", "B")
    )
    late = source._eligibility_checks(
        type(source.units[0])("HEALTHY", len(F.SESSIONS) - 2, "LONG", "B")
    )
    assert any(c.rule_id == COOLING_RULE_ID and c.excludes for c in cooling), "cooling never fired"
    assert any(c.rule_id == BLACKOUT_RULE_ID and c.excludes for c in late), "blackout never fired"


def test_an_ambiguous_symbol_stays_unresolved_and_is_reported(tmp_path):
    runner = _runner(tmp_path)
    runner.run()
    source = runner.candidate_source
    assert "AMBIG" in source.ambiguous_symbols
    assert "AMBIG" not in source.cik_by_symbol, "an ambiguous symbol must never be arbitrated"


# --------------------------------------------------------------- 6: each input is required
@pytest.mark.parametrize("table", [*WINDOW_TABLES, *REFERENCE_TABLES])
def test_removing_any_required_input_makes_the_run_refuse(tmp_path, table):
    runner = _runner(tmp_path, omit=table, out=f"out-{table}")
    outcome = runner.run()
    assert outcome.disposition != P.PASS, f"the run passed without {table}"


# --------------------------------------------------------------- 7-8: gate and injection surface
def test_reaches_pre_access_ready_without_aws_using_the_fixture_reader(tmp_path):
    runner = _runner(tmp_path)
    outcome = runner.run(stop_at=S.S7_PRE_ACCESS_READY)
    assert outcome.disposition == P.PASS, outcome.error
    assert outcome.state == S.S7_PRE_ACCESS_READY
    assert not outcome.opening_consumed
    assert runner.reader.reads == []


def test_the_reader_is_the_only_injected_dependency_below_the_entry_point(tmp_path):
    runner = _runner(tmp_path)
    source = runner.candidate_source
    assert source.units is None and source.lineage is None and source.cik_by_symbol is None, (
        "the entry point must not pre-supply any constructed input"
    )
    assert source.eligibility_checks_by_symbol is None
    assert isinstance(runner.reader, FixtureReader)


def test_the_real_reader_builds_no_client_until_a_read(tmp_path):
    reader = EP.s3_reader()
    assert reader.reader_kind == "S3"
    assert reader._client is None, "an eager client invites a probe before PRE_ACCESS_READY"


def test_execute_mode_refuses_a_fixture_root(tmp_path):
    with pytest.raises(EP.EntrypointRefused, match="refusing to call a fixture run an execution"):
        EP.main(
            [
                "--mode",
                "execute",
                "--output-root",
                str(tmp_path),
                "--sessions",
                "s.json",
                "--upload-manifest",
                "u.json",
                "--structural-manifest",
                "st.json",
                "--reference-manifest",
                "r.json",
                "--config",
                "c.json",
                "--fixture-root",
                str(tmp_path),
            ]
        )


def test_a_missing_required_file_refuses_before_anything_opens(tmp_path):
    with pytest.raises(EP.EntrypointRefused, match="required input absent"):
        EP.main(
            [
                "--output-root",
                str(tmp_path),
                "--sessions",
                str(tmp_path / "nope.json"),
                "--upload-manifest",
                "u.json",
                "--structural-manifest",
                "st.json",
                "--reference-manifest",
                "r.json",
                "--config",
                str(tmp_path / "nope.json"),
            ]
        )


def test_the_full_run_from_the_entry_point_passes(tmp_path):
    runner = _runner(tmp_path)
    outcome = runner.run()
    assert outcome.disposition == P.PASS, outcome.error
    assert outcome.opening_consumed
    assert outcome.state == S.S11_PUBLISHED
    assert outcome.integrity["all_gates_zero"] is True
    assert outcome.integrity["records_examined"] > 0
    written = set(os.listdir(runner.output_root))
    for name in P.DELIVERABLES:
        assert name in written, name


def test_the_run_is_not_vacuous_and_the_controls_actually_removed_units(tmp_path):
    """The whole point of the correction: eligibility must now exclude, not pass everything."""
    runner = _runner(tmp_path)
    outcome = runner.run()
    source = runner.candidate_source
    assert outcome.enrichment_census["records_examined"] > 0
    assert source.refusals, "no unit was refused; the controls cannot be firing"
    codes = {c for _s, _t, c in source.refusals}
    assert any("INELIGIBLE" in c for c in codes), f"no eligibility refusal among {codes}"


# --- reference scope: fetched == decoded == consumed == manifest set -------------------------

OVERRIDES = ("predecessor_overrides", "security_sector_overrides")


def test_registered_override_objects_are_not_fetched_merely_for_sharing_the_prefix(tmp_path):
    """The reference layer registers four objects; Phase 3B consumes two.

    Fetching the overrides would ADD an execution dependency the development window never had:
    Phase 2B reads sic_mapping and crosswalk RAW. Sharing a prefix is not a reason to fetch.
    """
    tables, _, upload = _world(tmp_path)
    for name in OVERRIDES:  # registered in the upload manifest, absent from the reference manifest
        upload["objects"][f"reference/{name}.parquet"] = {"version_id": "v", "sha256": "0" * 64}

    ref = _reference_manifest(tables, REFERENCE_TABLES)
    keys = {o.key for o in EP.pinned_inputs(upload, window="validation", reference_manifest=ref)}

    fetched_reference = {k for k in keys if k.startswith("reference/")}
    assert fetched_reference == set(ref["objects"]), fetched_reference
    for name in OVERRIDES:
        assert f"reference/{name}.parquet" not in keys, f"{name} was fetched by prefix"


def test_fetched_reference_set_equals_the_committed_structure():
    """fetched == decoded: decode_all consumes exactly `structure`, so the sets must agree."""
    tables = _tables()
    ref = _reference_manifest(tables, REFERENCE_TABLES)
    named = {k.split("/", 1)[-1].removesuffix(".parquet") for k in ref["objects"]}
    assert named == set(ref["structure"]) == set(REFERENCE_TABLES)


def test_a_reference_manifest_naming_a_validation_object_is_refused(tmp_path):
    tables, _, upload = _world(tmp_path)
    ref = _reference_manifest(tables, REFERENCE_TABLES)
    ref["objects"]["validation/prices.parquet"] = {}
    with pytest.raises(EP.EntrypointRefused, match="non-reference objects"):
        EP.pinned_inputs(upload, window="validation", reference_manifest=ref)


def test_an_internally_inconsistent_reference_manifest_is_refused(tmp_path):
    """Objects and committed structure must agree, or fetched != decoded."""
    tables, _, upload = _world(tmp_path)
    ref = _reference_manifest(tables, REFERENCE_TABLES)
    ref["objects"]["reference/predecessor_overrides.parquet"] = {}
    with pytest.raises(EP.EntrypointRefused, match="internally inconsistent"):
        EP.pinned_inputs(upload, window="validation", reference_manifest=ref)


def test_a_declared_object_absent_from_the_upload_manifest_is_refused(tmp_path):
    tables, _, upload = _world(tmp_path)
    ref = _reference_manifest(tables, REFERENCE_TABLES)
    upload["objects"].pop("reference/crosswalk.parquet")
    with pytest.raises(EP.EntrypointRefused, match="absent from the upload manifest"):
        EP.pinned_inputs(upload, window="validation", reference_manifest=ref)


def test_the_reference_manifest_is_hash_bound_so_an_edit_cannot_be_substituted(tmp_path):
    """Without this, 'fetch whatever the manifest declares' would obey an edited manifest."""
    p = tmp_path / "ref.json"
    p.write_text(json.dumps({"objects": {"reference/sic_mapping.parquet": {}}}))
    with pytest.raises(EP.EntrypointRefused, match="is not the bound artifact"):
        EP._load_bound(str(p), "f" * 64)


def test_the_bound_reference_manifest_identity_matches_the_generated_artifact():
    """The constant in the entry point must be the identity of the real generated manifest."""
    here = os.path.abspath(__file__)
    repo = here
    for _ in range(6):  # phase3b -> research -> tests -> backend -> apps -> repo root
        repo = os.path.dirname(repo)
    artifact = os.path.join(
        repo, "docs", "review", "mr002", "phase3bc", "MR002_Phase3B_ReferenceManifest_v1.0.json"
    )
    # NOT skipped when absent: a guard that silently skips is a vacuous pass, and this one exists
    # to prove the pinned constant is the identity of the REAL generated manifest.
    assert os.path.exists(artifact), f"reference manifest artifact not found at {artifact}"
    with open(artifact, "rb") as fh:
        assert hashlib.sha256(fh.read()).hexdigest() == EP.REFERENCE_MANIFEST_SHA256
