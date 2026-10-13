"""build_snapshot_manifest.py and build_fetch_universe.py on a SYNTHETIC export directory.

Nothing here is vendor data. The export mimics ``sharadar_window_pull.py`` output
(``tickers/sep/actions.parquet`` plus the pull's ``manifest.json``).
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

import duckdb
import pytest

from app.research.range002.data.manifest import (
    CLASS_SEQUENTIAL_PULLS,
    CLASS_SINGLE_TRANSACTION,
    MANIFEST_SCHEMA,
    MANIFEST_SCHEMA_V2,
    ManifestError,
    parse_snapshot_manifest,
    verify_snapshot_files,
)
from app.research.range002.data.pit_universe import BASIS_SPLIT_ADJUSTED, UniverseParams
from app.research.range002.data.store_adapter import (
    build_month_from_store,
    load_listings,
    open_snapshot,
)
from app.research.range002.screen.session_calendar import expected_sessions
from tests.research.range002.governance.conftest import (
    synthetic_manifest,  # noqa: F401  (autouse manifest seam)
)
from tests.research.range002.screen.conftest import make_capability, synth_payload

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts" / "research" / "range002"))
import build_fetch_universe as bfu  # noqa: E402
import build_snapshot_manifest as bsm  # noqa: E402

COMMON = "Domestic Common Stock"
PRIMARY = "Domestic Common Stock Primary Class"
SECONDARY = "Domestic Common Stock Secondary Class"
START, END = date(2026, 2, 2), date(2026, 2, 27)
DECISION = date(2026, 2, 27)
MONTH = date(2026, 3, 1)
SESSIONS = sorted(expected_sessions(START, END))
PARAMS = UniverseParams(
    n=2, adv_window=5, min_price=10.0, basis=BASIS_SPLIT_ADJUSTED,
    category_map=(COMMON, PRIMARY), intraday_basis="raw",
)  # fmt: skip


def _make_export(
    root: Path,
    *,
    lastupdated: str = "2026-01-10",
    drop_session: date | None = None,
    orphan_sep_ticker: bool = False,
    overlap_conflict: bool = False,
) -> None:
    con = duckdb.connect(":memory:")
    con.execute(
        'CREATE TABLE tickers("table" VARCHAR, permaticker VARCHAR, ticker VARCHAR, category VARCHAR,'
        " isdelisted VARCHAR, firstpricedate DATE, lastpricedate DATE, lastupdated DATE)"
    )
    rows = [
        ("SEP", "P1", "BIG", COMMON, "N", "2010-01-04", "2026-02-27"),
        ("SF1", "P1", "BIG", COMMON, "N", "2012-01-04", "2026-02-27"),
        ("SEP", "P2", "MID", PRIMARY, "N", "2010-01-04", "2026-02-27"),
        ("SEP", "P3", "SMALL", COMMON, "N", "2010-01-04", "2026-02-27"),
        ("SEP", "P4", "ETF1", "ETF", "N", "2010-01-04", "2026-02-27"),
        ("SEP", "P5", "SECC", SECONDARY, "N", "2010-01-04", "2026-02-27"),
    ]
    if overlap_conflict:
        rows += [
            ("SEP", "P1", "BIGOLD", COMMON, "N", "2010-01-04", "2026-02-27"),
        ]
    for tbl, perma, tick, cat, deli, first, last in rows:
        con.execute(
            "INSERT INTO tickers VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [tbl, perma, tick, cat, deli, first, last, lastupdated],
        )
    con.execute(
        "CREATE TABLE sep(ticker VARCHAR, date DATE, close DOUBLE, closeunadj DOUBLE,"
        " volume DOUBLE, lastupdated DATE)"
    )
    spec = [
        ("BIG", 100.0, 1_000_000),
        ("MID", 50.0, 400_000),
        ("SMALL", 20.0, 900_000),
        ("ETF1", 200.0, 5_000_000),
        ("SECC", 30.0, 800_000),
    ]
    if orphan_sep_ticker:
        spec.append(("GHOST", 40.0, 600_000))
    for tick, px, vol in spec:
        for d in SESSIONS:
            if d == drop_session:
                continue
            con.execute(
                "INSERT INTO sep VALUES (?, ?, ?, ?, ?, ?)", [tick, d, px, px, vol, lastupdated]
            )
    con.execute(
        "CREATE TABLE actions(date DATE, action VARCHAR, ticker VARCHAR, contraticker VARCHAR)"
    )
    con.execute("INSERT INTO actions VALUES ('2026-02-10', 'split', 'BIG', NULL)")
    for t in ("tickers", "sep", "actions"):
        con.execute(f"COPY {t} TO '{(root / (t + '.parquet')).as_posix()}' (FORMAT PARQUET)")
    counts = {
        t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]  # type: ignore[index]
        for t in ("tickers", "sep", "actions")
    }
    con.close()
    pull = {
        "schema_version": "range002.sharadar_window_pull_manifest.v1",
        "source": {"system": "synthetic datatables API"},
        "extraction_started_utc": "2026-10-12T14:00:00Z",
        "extraction_finished_utc": "2026-10-12T14:05:00Z",
        "files": [
            {
                "table": t,
                "file": f"{t}.parquet",
                "rows": counts[t],
                "byte_sha256": hashlib.sha256((root / f"{t}.parquet").read_bytes()).hexdigest(),
            }
            for t in ("tickers", "actions", "sep")
        ],
    }
    (root / "manifest.json").write_text(json.dumps(pull), encoding="utf-8")


@pytest.fixture
def export(tmp_path: Path) -> Path:
    root = tmp_path / "export"
    root.mkdir()
    _make_export(root)
    return root


def _build(root: Path, out: Path) -> int:
    return bsm.run(
        root,
        out,
        table_filter="SEP",
        coverage_start=START.isoformat(),
        coverage_end=END.isoformat(),
        decision_days=[DECISION.isoformat()],
    )


# --- snapshot manifest builder ---------------------------------------------------------------


def test_sequential_pulls_manifest_is_never_declared_consistent(
    export: Path, tmp_path: Path
) -> None:
    out = tmp_path / "snapshot_manifest.json"
    assert _build(export, out) == bsm.EXIT_OK
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["schema"] == MANIFEST_SCHEMA_V2
    assert doc["cross_table_consistent"] is False
    assert doc["consistency_class"] == CLASS_SEQUENTIAL_PULLS
    assert doc["integrity"]["all_passed"] is True
    assert (
        "EVIDENCE ONLY" in doc["consistency_basis"]
        and "NOT CROSS-TABLE" in doc["consistency_basis"]
    )
    assert set(doc["integrity"]["byte_sha256"]) == {"tickers", "sep", "actions"}
    for name in ("tickers", "sep", "actions"):
        assert doc["tables"][name]["files"][0]["sha256"] == doc["integrity"]["byte_sha256"][name]
    assert doc["extracted_at_utc"] == "2026-10-12T14:05:00Z"
    assert doc["integrity"]["pull_window_utc"]["per_table_times_recorded"] is False


def test_manifest_is_refused_without_the_opt_in_and_accepted_with_it(
    export: Path, tmp_path: Path
) -> None:
    out = tmp_path / "m.json"
    _build(export, out)
    parsed = parse_snapshot_manifest(out.read_text(encoding="utf-8"))
    refused = verify_snapshot_files(parsed, export)
    assert not refused.ok and "not declared cross-table consistent" in refused.defects[0]
    assert verify_snapshot_files(parsed, export, allow_sequential_pulls=True).ok


def test_lastupdated_evidence_is_recorded_and_never_upgrades_the_flag(
    tmp_path: Path,
) -> None:
    quiet, noisy = tmp_path / "q", tmp_path / "n"
    quiet.mkdir()
    noisy.mkdir()
    _make_export(quiet, lastupdated="2020-01-01")
    _make_export(noisy, lastupdated="2026-10-12")  # revised on the pull day
    for root in (quiet, noisy):
        _build(root, root / "snapshot_manifest.json")
    q = json.loads((quiet / "snapshot_manifest.json").read_text(encoding="utf-8"))
    n = json.loads((noisy / "snapshot_manifest.json").read_text(encoding="utf-8"))
    assert q["cross_table_consistent"] is False and n["cross_table_consistent"] is False
    lu_q = q["integrity"]["lastupdated_evidence"]["sep"]
    lu_n = n["integrity"]["lastupdated_evidence"]["sep"]
    assert lu_q["rows_at_or_after_pull_start"] == 0
    assert lu_n["rows_at_or_after_pull_start"] > 0 and lu_n["max"] == "2026-10-12"
    assert "rows with lastupdated >= 2026-10-12" in n["consistency_basis"]


@pytest.mark.parametrize(
    ("kwargs", "failed"),
    [
        ({"orphan_sep_ticker": True}, "sep_tickers_without_tickers_row"),
        ({"drop_session": SESSIONS[3]}, "expected_sessions_missing_from_sep"),
        ({"drop_session": DECISION}, "decision_days_missing_from_sep"),
    ],
)
def test_integrity_failure_is_recorded_and_refused_even_with_the_opt_in(
    tmp_path: Path, kwargs: dict[str, Any], failed: str
) -> None:
    root = tmp_path / "bad"
    root.mkdir()
    _make_export(root, **kwargs)
    out = root / "snapshot_manifest.json"
    assert _build(root, out) == bsm.EXIT_INTEGRITY_FAILED
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert failed in doc["integrity"]["failed_checks"]
    parsed = parse_snapshot_manifest(out.read_text(encoding="utf-8"))
    res = verify_snapshot_files(parsed, root, allow_sequential_pulls=True)
    assert not res.ok and any("integrity" in d for d in res.defects)


def test_builder_refuses_a_tampered_table_and_never_overwrites(
    export: Path, tmp_path: Path
) -> None:
    out = tmp_path / "m.json"
    _build(export, out)
    with pytest.raises(bsm.ManifestBuildError, match="already exists"):
        _build(export, out)
    (export / "sep.parquet").write_bytes((export / "sep.parquet").read_bytes() + b"x")
    with pytest.raises(bsm.ManifestBuildError, match="sha256"):
        _build(export, tmp_path / "other.json")


# --- manifest schema: v1 unchanged, v2 alongside ---------------------------------------------


def _v2(**over: Any) -> str:
    base: dict[str, Any] = {
        "schema": MANIFEST_SCHEMA_V2,
        "source": "s",
        "extracted_at_utc": "2026-10-12T00:00:00Z",
        "method": "m",
        "cross_table_consistent": False,
        "consistency_class": CLASS_SEQUENTIAL_PULLS,
        "consistency_basis": "b",
        "integrity": {"all_passed": True},
        "tables": {},
    }
    base.update(over)
    return json.dumps(base)


def test_v1_manifests_parse_exactly_as_before() -> None:
    doc = json.dumps(
        {
            "schema": MANIFEST_SCHEMA, "source": "s", "extracted_at_utc": "t", "method": "m",
            "cross_table_consistent": True, "consistency_basis": "b", "tables": {},
        }
    )  # fmt: skip
    m = parse_snapshot_manifest(doc)
    assert m.cross_table_consistent and m.consistency_class == CLASS_SINGLE_TRANSACTION
    # a v1 manifest declared false is refused even with the opt-in (it has no sequential class)
    m1 = parse_snapshot_manifest(doc.replace("true", "false"))
    res = verify_snapshot_files(m1, Path("."), allow_sequential_pulls=True)
    assert any("not declared cross-table consistent" in d for d in res.defects)


def test_v2_class_and_flag_must_agree() -> None:
    with pytest.raises(ManifestError, match="disagree"):
        parse_snapshot_manifest(_v2(cross_table_consistent=True))
    with pytest.raises(ManifestError, match="disagree"):
        parse_snapshot_manifest(
            _v2(consistency_class=CLASS_SINGLE_TRANSACTION, cross_table_consistent=False)
        )
    with pytest.raises(ManifestError, match="consistency_class"):
        parse_snapshot_manifest(_v2(consistency_class="whatever"))
    with pytest.raises(ManifestError, match="all_passed"):
        parse_snapshot_manifest(_v2(integrity={"all_passed": "yes"}))


def test_v2_sequential_without_integrity_is_refused_with_opt_in() -> None:
    doc = json.loads(_v2())
    del doc["integrity"]
    m = parse_snapshot_manifest(json.dumps(doc))
    res = verify_snapshot_files(m, Path("."), allow_sequential_pulls=True)
    assert any("integrity checks are absent" in d for d in res.defects)


# --- fetch universe: no drift from the capability path ---------------------------------------


def test_generator_equals_the_capability_path(export: Path, tmp_path: Path) -> None:
    cap = make_capability(tmp_path, synth_payload())[0]
    con = open_snapshot(export)
    gen = bfu.build_month(con, MONTH, PARAMS, table_filter="SEP", lookback_calendar_days=14)
    real = build_month_from_store(
        cap,
        con,
        MONTH,
        PARAMS,
        table_filter="SEP",
        lookback_calendar_days=14,
        raw_vendor_rows_attested=False,
        exploratory_scope_amendment_id=None,
    )
    assert gen.decision_day == DECISION
    assert gen.observations == real.observations
    assert gen.identity == real.identity
    assert gen.listings == load_listings(
        con, table_filter="SEP", common_stock_categories=frozenset(PARAMS.category_map)
    )
    assert gen.universe == real.universe
    assert [m.vendor_ticker for m in gen.universe.members] == ["BIG", "MID"]  # n=2, by ADV
    con.close()


def _run_gen(
    export: Path, tmp_path: Path, cats: list[str], *, tag: str, inspect: bool = False
) -> tuple[int, dict[str, Any], Path]:
    argv = ["--daily-dir", str(export), "--table-filter", "SEP", "--n", "2",
            "--adv-window-days", "5", "--min-price", "10.0", "--lookback-calendar-days", "14",
            "--month-start", MONTH.isoformat(),
            "--out-report", str(tmp_path / f"{tag}.json"),
            "--out-universe-file", str(tmp_path / f"{tag}.txt")]  # fmt: skip
    for c in cats:
        argv += ["--category-map", c]
    if inspect:
        argv.append("--inspect-identity")
    code = bfu.main(argv)
    rep = json.loads((tmp_path / f"{tag}.json").read_text(encoding="utf-8"))
    return code, rep, tmp_path / f"{tag}.txt"


def test_report_and_universe_file_contents(export: Path, tmp_path: Path) -> None:
    code, rep, symbols = _run_gen(export, tmp_path, [COMMON, PRIMARY], tag="a")
    assert code == bfu.EXIT_OK
    assert symbols.read_text(encoding="utf-8").split() == ["BIG", "MID"]
    m = rep["months"][0]
    assert m["decision_day"] == DECISION.isoformat()
    assert m["members"] == 2 and m["below_cut"] == 1  # SMALL ranks 3rd
    assert m["population"] == m["members"] + m["below_cut"] + m["excluded"]
    assert m["not_common_stock_by_category"] == {"ETF": 1, SECONDARY: 1}
    assert rep["parameters"]["map_includes_secondary_class"] is False
    assert rep["union_size"] == 2 and rep["any_month_short"] is False
    assert "restricted" in rep["category_definition"].lower()
    assert "NOT" in rep["category_definition"]
    # symbols, ranks and counts only: no price or volume value in the document
    text = json.dumps(rep)
    for forbidden in ("closeunadj", "adv", "prior_close", "1000000", "400000"):
        assert forbidden not in text.replace("adv_window_days", "")


def test_secondary_class_only_by_second_explicit_invocation(export: Path, tmp_path: Path) -> None:
    _, base, _ = _run_gen(export, tmp_path, [COMMON, PRIMARY], tag="a")
    _, alt, _ = _run_gen(export, tmp_path, [COMMON, PRIMARY, SECONDARY], tag="b")
    assert base["parameters"]["map_includes_secondary_class"] is False
    assert alt["parameters"]["map_includes_secondary_class"] is True
    assert alt["months"][0]["not_common_stock_by_category"] == {"ETF": 1}


def test_shortfall_is_flagged_and_exit_code_reflects_it(export: Path, tmp_path: Path) -> None:
    argv = ["--daily-dir", str(export), "--table-filter", "SEP", "--n", "10",
            "--adv-window-days", "5", "--min-price", "10.0", "--lookback-calendar-days", "14",
            "--month-start", MONTH.isoformat(), "--category-map", COMMON,
            "--out-report", str(tmp_path / "s.json"), "--out-universe-file", str(tmp_path / "s.txt")]  # fmt: skip
    assert bfu.main(argv) == bfu.EXIT_SHORTFALL
    rep = json.loads((tmp_path / "s.json").read_text(encoding="utf-8"))
    assert rep["months"][0]["fewer_than_n_eligible"] is True
    assert rep["months_with_fewer_than_n_eligible"] == 1


def test_outputs_are_never_overwritten_and_parameters_are_required(
    export: Path, tmp_path: Path
) -> None:
    _run_gen(export, tmp_path, [COMMON], tag="a")
    assert _run_gen_refused(export, tmp_path) == bfu.EXIT_REFUSED
    with pytest.raises(SystemExit):  # no defaults: --n is required
        bfu.main(["--daily-dir", str(export)])


def _run_gen_refused(export: Path, tmp_path: Path) -> int:
    return bfu.main(
        ["--daily-dir", str(export), "--table-filter", "SEP", "--n", "2",
         "--adv-window-days", "5", "--min-price", "10.0", "--lookback-calendar-days", "14",
         "--month-start", MONTH.isoformat(), "--category-map", COMMON,
         "--out-report", str(tmp_path / "a.json"), "--out-universe-file", str(tmp_path / "x.txt")]
    )  # fmt: skip


# --- identity inspection ---------------------------------------------------------------------


def test_identity_inspection_without_conflict(export: Path, tmp_path: Path) -> None:
    _, rep, _ = _run_gen(export, tmp_path, [COMMON, PRIMARY], tag="i", inspect=True)
    ins = rep["identity_inspection"]
    assert ins["overlapping_permaticker_conflicts"] == []
    assert ins["any_conflict_affects_eligible_issuer"] is False


def test_identity_conflict_affecting_an_eligible_issuer_is_explicit(tmp_path: Path) -> None:
    root = tmp_path / "c"
    root.mkdir()
    _make_export(root, overlap_conflict=True)
    _, rep, _ = _run_gen(root, tmp_path, [COMMON, PRIMARY], tag="c", inspect=True)
    ins = rep["identity_inspection"]
    assert len(ins["overlapping_permaticker_conflicts"]) == 1
    conflict = ins["overlapping_permaticker_conflicts"][0]
    assert conflict["key"] == "P1"
    assert sorted(conflict["tickers_or_permatickers"]) == ["BIG", "BIGOLD"]
    assert conflict["affects_eligible_issuer"] is True
    assert "EXPLICIT EXCLUSION" in conflict["resolution_rule"]
    # the builder did not silently resolve it: P1 is excluded with a named reason that month
    statuses = [s for s in conflict["month_status"] if s["permaticker"] == "P1"]
    assert statuses[0]["status"] == "EXCLUDED" and statuses[0]["reason"] == "AMBIGUOUS_IDENTITY"
    assert "BIG" not in (tmp_path / "c.txt").read_text(encoding="utf-8").split()
