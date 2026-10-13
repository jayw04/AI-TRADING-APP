"""S1 identity export on SYNTHETIC DuckDB fixtures built in tmp_path. Nothing here touches a real
store; asserted numbers describe the fixture only."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import duckdb
import pytest

SCRIPTS = Path(__file__).resolve().parents[4] / "scripts" / "research" / "range002"
sys.path.insert(0, str(SCRIPTS))
import export_identity_snapshot as ex  # noqa: E402
import pit_coverage_ro  # noqa: E402

from app.licensing.envelope import write_sidecar  # noqa: E402
from app.licensing.gate import PersonalScopeBlocked  # noqa: E402
from app.licensing.output import export_file_for_external_use  # noqa: E402

PERM_REF = "synthetic-test-ref (not a real record)"
PERM_SCOPE = "tickers, actions, ingest_runs, dataset_coverage, sep_coverage (synthetic)"


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def build_store(path: Path) -> Path:
    con = duckdb.connect(str(path))
    cols = (
        "permaticker VARCHAR, ticker VARCHAR, name VARCHAR, exchange VARCHAR, category VARCHAR, "
        "sector VARCHAR, industry VARCHAR, isdelisted BOOLEAN, firstpricedate DATE, "
        "lastpricedate DATE, lastupdated DATE"
    )
    con.execute(f"CREATE TABLE tickers ({cols})")
    con.execute(
        """INSERT INTO tickers (permaticker, ticker, name, exchange, category, sector, industry,
        isdelisted, firstpricedate, lastpricedate, lastupdated) VALUES
        ('1','AAA','Alpha Inc','NYSE','Domestic Common Stock','S','I',false,'2010-01-04','2026-06-12','2026-06-12'),
        ('2','REUS','Old Reus Corp','NYSE','Domestic Common Stock','S','I',true,'2010-01-04','2012-01-03','2012-01-03'),
        ('3','REUS','New Reus Ltd','NASDAQ','Domestic Common Stock','S','I',false,'2018-01-02','2026-06-12','2026-06-12'),
        ('5','OLDN','Rename Co','NYSE','Domestic Common Stock','S','I',true,'2010-01-04','2017-06-30','2017-06-30'),
        ('5','NEWN','Rename Co','NYSE','Domestic Common Stock','S','I',false,'2017-07-01','2026-06-12','2026-06-12')"""
    )
    con.execute(
        "CREATE TABLE actions (date DATE, action VARCHAR, ticker VARCHAR, name VARCHAR, "
        "value DOUBLE, contraticker VARCHAR)"
    )
    con.execute(
        """INSERT INTO actions VALUES
        ('2017-07-01','tickerchangefrom','NEWN','Rename Co',NULL,'OLDN'),
        ('2017-07-01','tickerchangeto','OLDN','Rename Co',NULL,'NEWN'),
        ('2020-01-02','split','AAA','Alpha Inc',2.0,NULL)"""
    )
    con.execute(
        "CREATE TABLE ingest_runs (dataset VARCHAR, started_at TIMESTAMP, finished_at TIMESTAMP, "
        "rows BIGINT, status VARCHAR, run_id VARCHAR)"
    )
    con.execute(
        "INSERT INTO ingest_runs VALUES ('sep','2026-06-01 10:00:00','2026-06-01 10:05:00',"
        "100,'ok','run-1'), ('actions','2026-06-01 10:06:00','2026-06-01 10:07:00',3,'ok','run-2')"
    )
    con.execute(
        "CREATE TABLE dataset_coverage (dataset VARCHAR, ingest_run_id VARCHAR, coverage_start DATE,"
        " coverage_end DATE, artifact_sha256 VARCHAR, artifact_path VARCHAR, source_identity VARCHAR,"
        " rows_loaded BIGINT, recorded_at TIMESTAMP, status VARCHAR)"
    )
    con.execute(
        "INSERT INTO dataset_coverage VALUES ('sep','run-1','2010-01-01','2026-06-12','ab'||repeat('0',62),"
        "'synthetic/sep.parquet','SHARADAR/SEP synthetic',100,'2026-06-01 10:05:01','ok')"
    )
    con.execute(
        "CREATE TABLE sep (ticker VARCHAR, date DATE, open DOUBLE, high DOUBLE, low DOUBLE, "
        "close DOUBLE, volume BIGINT, closeadj DOUBLE, closeunadj DOUBLE, lastupdated DATE)"
    )
    con.execute(
        "INSERT INTO sep SELECT 'AAA', d, 1.5, 2.5, 0.5, 1.75, 123456, 1.7, 1.8, DATE '2026-06-12' "
        "FROM range(DATE '2024-01-01', DATE '2024-01-11', INTERVAL 1 DAY) t(d)"
    )
    con.execute(
        "INSERT INTO sep SELECT 'OLDN', d, 9.5, 9.6, 9.4, 9.55, 777, 9.5, 9.5, DATE '2017-06-30' "
        "FROM range(DATE '2017-06-20', DATE '2017-06-23', INTERVAL 1 DAY) t(d)"
    )
    con.close()
    return path


@pytest.fixture
def store(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    return build_store(tmp_path / "src" / "synthetic.duckdb")


@pytest.fixture
def dest(tmp_path: Path) -> Path:
    d = tmp_path / "dest"
    d.mkdir()
    return d


def do_export(store: Path, dest: Path, export_id: str = "exp-1", **kw: Any) -> Path:
    args: dict[str, Any] = {
        "source": store,
        "dest_root": dest,
        "export_id": export_id,
        "purpose": "synthetic test",
        "executing_identity": "test runner",
        "permission_ref": PERM_REF,
        "permission_scope": PERM_SCOPE,
    }
    args.update(kw)
    return ex.run_export(**args)


def manifest_of(root: Path) -> dict[str, Any]:
    return json.loads((root / "manifest.json").read_text(encoding="utf-8"))


# ------------------------------------------------------------------ content / columns
def test_default_mode_selected_columns_no_price_or_volume(store: Path, dest: Path) -> None:
    out = do_export(store, dest)
    assert (out / "EXPORT_COMPLETE.json").is_file()
    tables = {p.stem for p in out.glob("*.parquet")}
    assert tables == {"tickers", "actions", "ingest_runs", "dataset_coverage", "sep_coverage"}
    con = duckdb.connect(":memory:")
    all_cols: set[str] = set()
    for p in out.glob("*.parquet"):
        cols = [
            r[0]
            for r in con.execute(
                f"DESCRIBE SELECT * FROM read_parquet('{p.as_posix()}')"
            ).fetchall()
        ]
        all_cols |= {c.lower() for c in cols}
        if p.stem == "sep_coverage":
            assert cols == ["ticker", "min_date", "max_date", "n_rows"]
    assert not (all_cols & ex.PRICE_VOLUME_COLUMNS)
    assert "sector" not in all_cols and "industry" not in all_cols
    cov = con.execute(
        f"SELECT ticker, n_rows FROM read_parquet('{(out / 'sep_coverage.parquet').as_posix()}') ORDER BY 1"
    ).fetchall()
    assert cov == [("AAA", 10), ("OLDN", 3)]


def test_sep_coverage_default_on_and_flag_off(store: Path, dest: Path) -> None:
    out = do_export(store, dest, "exp-off", include_sep_coverage=False)
    assert not (out / "sep_coverage.parquet").exists()
    m = manifest_of(out)
    assert "sep_coverage" in m["tables_not_exported"]
    assert ex.build_parser().parse_args(["--no-sep-coverage"]).no_sep_coverage is True


def test_reused_ticker_and_rename_present_in_export(store: Path, dest: Path) -> None:
    out = do_export(store, dest)
    rows = (
        duckdb.connect(":memory:")
        .execute(
            f"SELECT ticker, permaticker FROM read_parquet('{(out / 'tickers.parquet').as_posix()}') ORDER BY 1, 2"
        )
        .fetchall()
    )
    assert rows.count(("REUS", "2")) == 1 and rows.count(("REUS", "3")) == 1
    assert ("OLDN", "5") in rows and ("NEWN", "5") in rows


def test_optional_table_column_absent_is_recorded_not_guessed(store: Path, dest: Path) -> None:
    m = manifest_of(do_export(store, dest))
    t = next(f for f in m["files"] if f["table"] == "tickers")
    assert t["optional_columns_absent"] == ["table"]
    assert "table" not in t["columns"]


def test_unverified_columns_listed_when_present(tmp_path: Path, dest: Path) -> None:
    src = build_store(tmp_path / "s.duckdb")
    con = duckdb.connect(str(src))
    con.execute('ALTER TABLE tickers ADD COLUMN "table" VARCHAR')
    con.close()
    m = manifest_of(do_export(src, dest))
    assert m["columns_unverified_in_schema"] == ["tickers.table"]


def test_missing_requested_column_fails_closed(tmp_path: Path, dest: Path) -> None:
    src = tmp_path / "s.duckdb"
    con = duckdb.connect(str(src))
    con.execute("CREATE TABLE tickers (ticker VARCHAR, name VARCHAR)")
    con.execute(
        "CREATE TABLE actions (date DATE, action VARCHAR, ticker VARCHAR, name VARCHAR, value DOUBLE, contraticker VARCHAR)"
    )
    con.close()
    with pytest.raises(ex.ExportRefused, match="lacks requested column"):
        do_export(src, dest)
    assert not (dest / "exp-1").exists()


# ------------------------------------------------------------------ manifest
def test_manifest_fields_and_hashes(store: Path, dest: Path) -> None:
    out = do_export(store, dest)
    m = manifest_of(out)
    assert ex.validate_manifest(m) == []
    assert m["schema_version"] == "range002.identity_export_manifest.v1"
    assert m["permission_verified"] is False
    assert m["permission_basis_claimed"]["ref"] == PERM_REF
    assert m["permission_basis_claimed"]["scope"] == PERM_SCOPE
    assert m["permission_basis_claimed"]["tables_not_named_in_scope"] == []
    assert m["license_status"] == "UNKNOWN"
    assert m["script_sha256"] == _sha(SCRIPTS / "export_identity_snapshot.py")
    joined = "\n".join(m["queries"][t] for t in ex.ALL_TABLE_NAMES if t in m["queries"])
    assert m["query_text_sha256"] == hashlib.sha256(joined.encode()).hexdigest()
    assert all("NULLS FIRST" in q for q in m["queries"].values())
    assert not any("SELECT *" in q for q in m["queries"].values())
    for f in m["files"]:
        assert f["byte_sha256"] == _sha(out / f["file"])
    assert (
        m["ingest_identifiers"]["ingest_runs"][0]["run_id"] == "run-2"
    )  # ORDER BY dataset: actions first
    assert str(store) in m["source"]["path_as_given"]
    assert "sha256" not in json.dumps(m["source"]).lower()
    assert ex.validate_export_dir(out, m) == []


def test_ingest_identifiers_unavailable_with_reason(tmp_path: Path, dest: Path) -> None:
    src = build_store(tmp_path / "s.duckdb")
    con = duckdb.connect(str(src))
    con.execute("DROP TABLE dataset_coverage")
    con.execute("DROP TABLE ingest_runs")
    con.close()
    m = manifest_of(do_export(src, dest))
    for k in ("ingest_runs", "dataset_coverage"):
        assert m["ingest_identifiers"][k]["value"] == "unavailable"
        assert m["ingest_identifiers"][k]["reason"]
    assert ex.validate_manifest(m) == []


@pytest.mark.parametrize(
    "field",
    [
        "export_id",
        "purpose",
        "executing_identity",
        "query_text_sha256",
        "files",
        "permission_verified",
        "permission_basis_claimed",
        "ingest_identifiers",
        "license_status",
    ],
)
def test_manifest_validation_fails_on_missing_or_empty(store: Path, dest: Path, field: str) -> None:
    m = manifest_of(do_export(store, dest))
    broken = dict(m)
    del broken[field]
    assert ex.validate_manifest(broken)
    if field != "permission_verified":
        broken = dict(m)
        broken[field] = "" if isinstance(m[field], str) else None
        assert ex.validate_manifest(broken)
    broken = dict(m)
    broken["permission_verified"] = True
    assert any("permission_verified" in d for d in ex.validate_manifest(broken))


def test_validation_rejects_forbidden_column_and_bad_sep_coverage(store: Path, dest: Path) -> None:
    m = manifest_of(do_export(store, dest))
    bad = json.loads(json.dumps(m))
    bad["files"][0]["columns"].append("close")
    assert any("allowed only in sep_daily" in d for d in ex.validate_manifest(bad))


# ------------------------------------------------------------------ atomicity / overwrite / args
def test_failure_midway_is_not_published(
    store: Path, dest: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = ex.copy_query_to_parquet
    calls = {"n": 0}

    def boom(con: Any, sql: str, target: Path) -> None:
        calls["n"] += 1
        if calls["n"] == 2:
            raise duckdb.IOException("injected failure")
        real(con, sql, target)

    monkeypatch.setattr(ex, "copy_query_to_parquet", boom)
    with pytest.raises(duckdb.IOException):
        do_export(store, dest)
    assert not (dest / "exp-1").exists()
    staging = dest / ".staging-exp-1"
    assert staging.is_dir()
    assert not (staging / "EXPORT_COMPLETE.json").exists()
    assert (staging / "EXPORT_FAILED.json").is_file()
    with pytest.raises(ex.ExportRefused, match="staging"):
        do_export(store, dest)


def test_refuses_overwrite_of_existing_export(store: Path, dest: Path) -> None:
    out = do_export(store, dest)
    before = _sha(out / "manifest.json")
    with pytest.raises(ex.ExportRefused, match="already exists"):
        do_export(store, dest)
    assert _sha(out / "manifest.json") == before


def test_refuses_missing_permission_fields(store: Path, dest: Path) -> None:
    with pytest.raises(ex.ExportRefused, match="permission-ref"):
        do_export(store, dest, permission_ref="  ")
    with pytest.raises(ex.ExportRefused, match="permission-scope"):
        do_export(store, dest, permission_scope="")
    assert list(dest.iterdir()) == []
    base = [
        sys.executable,
        "-I",
        str(SCRIPTS / "export_identity_snapshot.py"),
        "--source",
        str(store),
        "--dest-root",
        str(dest),
        "--export-id",
        "x",
        "--purpose",
        "p",
        "--executing-identity",
        "me",
    ]
    r = subprocess.run(base, capture_output=True, text=True)
    assert r.returncode == 2 and "permission-ref" in r.stderr
    assert list(dest.iterdir()) == []


def test_cli_standalone_isolated_mode_end_to_end(store: Path, dest: Path) -> None:
    cmd = [
        sys.executable,
        "-I",
        str(SCRIPTS / "export_identity_snapshot.py"),
        "--source",
        str(store),
        "--dest-root",
        str(dest),
        "--export-id",
        "cli-1",
        "--purpose",
        "p",
        "--executing-identity",
        "me",
        "--permission-ref",
        PERM_REF,
        "--permission-scope",
        PERM_SCOPE,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    v = subprocess.run(
        [
            sys.executable,
            "-I",
            str(SCRIPTS / "export_identity_snapshot.py"),
            "--verify",
            str(dest / "cli-1"),
        ],
        capture_output=True,
        text=True,
    )
    assert v.returncode == 0 and "OK" in v.stdout


@pytest.mark.parametrize("bad", ["../escape", "a/b", "", ".hidden", "x y"])
def test_bad_export_ids_refused(store: Path, dest: Path, bad: str) -> None:
    with pytest.raises(ex.ExportRefused):
        do_export(store, dest, bad)


def test_source_bytes_unchanged_and_no_db_copy(store: Path, dest: Path) -> None:
    before = _sha(store)
    out = do_export(store, dest)
    assert _sha(store) == before
    assert not list(out.glob("*.duckdb")) and not list(dest.rglob("*.duckdb"))
    assert not list(store.parent.glob("*.wal"))


# ------------------------------------------------------------------ logical hash
def _logical(m: dict[str, Any], table: str) -> str:
    return next(f["logical_sha256"] for f in m["files"] if f["table"] == table)


def test_logical_hash_reproducible_and_sensitive(tmp_path: Path, dest: Path) -> None:
    src = build_store(tmp_path / "s.duckdb")
    m1 = manifest_of(do_export(src, dest, "a"))
    m2 = manifest_of(do_export(src, dest, "b"))
    assert [f["logical_sha256"] for f in m1["files"]] == [f["logical_sha256"] for f in m2["files"]]
    con = duckdb.connect(str(src))
    con.execute("UPDATE actions SET value = 3.0 WHERE action = 'split'")
    con.close()
    m3 = manifest_of(do_export(src, dest, "c"))
    assert _logical(m3, "actions") != _logical(m1, "actions")
    assert _logical(m3, "tickers") == _logical(m1, "tickers")


def test_logical_hash_independent_of_source_row_order(tmp_path: Path, dest: Path) -> None:
    a = build_store(tmp_path / "a.duckdb")
    b = build_store(tmp_path / "b.duckdb")
    con = duckdb.connect(str(b))
    con.execute("CREATE TABLE t2 AS SELECT * FROM tickers ORDER BY ticker DESC, permaticker DESC")
    con.execute("DROP TABLE tickers")
    con.execute("ALTER TABLE t2 RENAME TO tickers")
    con.close()
    ma = manifest_of(do_export(a, dest, "a"))
    mb = manifest_of(do_export(b, dest, "b"))
    assert _logical(ma, "tickers") == _logical(mb, "tickers")


def test_canonical_form_null_vs_empty_and_int_vs_float() -> None:
    cols, types = ["a"], ["VARCHAR"]
    assert ex.canonical_rows_digest(cols, types, [(None,)]) != ex.canonical_rows_digest(
        cols, types, [("",)]
    )
    assert ex.canonical_rows_digest(["a"], ["BIGINT"], [(1,)]) != ex.canonical_rows_digest(
        ["a"], ["DOUBLE"], [(1.0,)]
    )
    assert ex.canonical_rows_digest(["a"], ["DOUBLE"], [(1,)]) != ex.canonical_rows_digest(
        ["a"], ["DOUBLE"], [(1.0,)]
    )  # documented rule: int and float values are NOT canonicalised together
    assert ex.canonical_rows_digest(cols, types, [("x",)]) != ex.canonical_rows_digest(
        cols, types, [("y",)]
    )
    # strings are byte-exact: no NFC folding (documented)
    assert ex.canonical_rows_digest(cols, types, [("é",)]) != ex.canonical_rows_digest(
        cols, types, [("é",)]
    )
    # column order is part of the form
    assert ex.canonical_rows_digest(
        ["a", "b"], ["INTEGER"] * 2, [(1, 2)]
    ) != ex.canonical_rows_digest(["b", "a"], ["INTEGER"] * 2, [(1, 2)])


def test_null_vs_empty_string_differ_through_export(tmp_path: Path, dest: Path) -> None:
    a = build_store(tmp_path / "a.duckdb")
    b = build_store(tmp_path / "b.duckdb")
    con = duckdb.connect(str(a))
    con.execute("UPDATE actions SET contraticker = '' WHERE action = 'split'")
    con.close()
    ma = manifest_of(do_export(a, dest, "a"))
    mb = manifest_of(do_export(b, dest, "b"))
    assert _logical(ma, "actions") != _logical(mb, "actions")


# ------------------------------------------------------------------ licensing seam
def test_sidecars_agree_with_licensing_module_and_seam_refuses(
    store: Path, dest: Path, tmp_path: Path
) -> None:
    out = do_export(store, dest, license_status="COMMERCIAL_OK")  # recorded only; grants nothing
    assert manifest_of(out)["license_status"] == "COMMERCIAL_OK"
    assert (out / "README_PU1.txt").is_file()
    targets = sorted(out.glob("*.parquet")) + [out / "manifest.json"]
    assert len(targets) == 6
    for f in targets:
        mine = (out / (f.name + ".license.json")).read_bytes()
        ref = tmp_path / f"ref-{f.name}"
        ref.write_bytes(f.read_bytes())
        write_sidecar(ref, ["sharadar"])
        assert (tmp_path / f"ref-{f.name}.license.json").read_bytes() == mine
        with pytest.raises(PersonalScopeBlocked):
            export_file_for_external_use(f, tmp_path / "ext" / f.name)
        assert not (tmp_path / "ext" / f.name).exists()


def test_internal_diagnostic_reads_remain_possible(store: Path, dest: Path) -> None:
    out = do_export(store, dest)
    con = duckdb.connect(":memory:")
    n = con.execute(
        f"SELECT COUNT(*) FROM read_parquet('{(out / 'tickers.parquet').as_posix()}')"
    ).fetchone()
    assert n == (5,)
    text = pit_coverage_ro.report(str(out))
    assert "tickers.parquet" in text and "sep_coverage.parquet" in text
    assert _sha(out / "tickers.parquet") in text
    # The export deliberately holds no sep prices, so the PIT report states that it is blocked.
    assert "BLOCKED: tickers/sep table missing" in text
    with pytest.raises(PersonalScopeBlocked):
        export_file_for_external_use(out / "tickers.parquet", store.parent / "ext" / "t.parquet")


def test_script_agrees_with_store_projection_lists() -> None:
    from app.factor_data import store as fstore

    assert set(fstore._TICKERS_COLS) == ex.VERIFIED_IN_SCHEMA["tickers"]
    assert set(fstore._ACTIONS_COLS) == ex.VERIFIED_IN_SCHEMA["actions"]
    assert set(fstore._SEP_COLS) == ex.VERIFIED_IN_SCHEMA["sep"]
    for _t, req, opt, _r in ex.TABLE_SPECS:
        assert set(req) | set(opt)  # non-empty


# ------------------------------------------------------------------ cleanup
def _two_exports(store: Path, dest: Path) -> tuple[Path, Path]:
    a = do_export(store, dest, "exp-a")
    b = do_export(store, dest, "exp-b")
    return a, b


def test_cleanup_dry_run_lists_only_that_export_and_removes_nothing(
    store: Path, dest: Path
) -> None:
    a, b = _two_exports(store, dest)
    other = dest / "unrelated.txt"
    other.write_text("keep")
    before = sorted(p.name for p in a.iterdir())
    victims = ex.cleanup_export(dest, "exp-a", apply=False)
    assert {v.parent for v in victims} == {a}
    assert sorted(v.name for v in victims) == before
    assert sorted(p.name for p in a.iterdir()) == before


def test_cleanup_apply_removes_only_that_export(store: Path, dest: Path) -> None:
    a, b = _two_exports(store, dest)
    other = dest / "unrelated.txt"
    other.write_text("keep")
    src_sha = _sha(store)
    staging = dest / ".staging-exp-a"
    staging.mkdir()
    (staging / "tickers.parquet").write_bytes(b"partial")
    ex.cleanup_export(dest, "exp-a", apply=True)
    assert not a.exists() and not staging.exists()
    assert b.is_dir() and (b / "EXPORT_COMPLETE.json").is_file()
    assert other.read_text() == "keep"
    assert _sha(store) == src_sha


def test_cleanup_refuses_unknown_file_and_wrong_manifest_id(store: Path, dest: Path) -> None:
    a, b = _two_exports(store, dest)
    (a / "notes.txt").write_text("not in manifest")
    with pytest.raises(ex.ExportRefused, match="unknown content"):
        ex.cleanup_export(dest, "exp-a", apply=True)
    assert (a / "manifest.json").exists()
    m = manifest_of(b)
    m["export_id"] = "someone-else"
    (b / "manifest.json").write_text(json.dumps(m))
    with pytest.raises(ex.ExportRefused, match="does not match"):
        ex.cleanup_export(dest, "exp-b", apply=True)


def test_cleanup_refuses_path_escape_and_subdir(store: Path, dest: Path) -> None:
    a, _ = _two_exports(store, dest)
    with pytest.raises(ex.ExportRefused):
        ex.cleanup_export(dest, "../dest", apply=True)
    (a / "sub").mkdir()
    with pytest.raises(ex.ExportRefused):
        ex.cleanup_export(dest, "exp-a", apply=True)


def test_cleanup_refuses_symlink(store: Path, dest: Path, tmp_path: Path) -> None:
    a = do_export(store, dest, "exp-a")
    target = tmp_path / "elsewhere"
    target.mkdir()
    (target / "keep.txt").write_text("x")
    link = dest / "exp-link"
    try:
        os.symlink(target, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted")
    with pytest.raises(ex.ExportRefused, match="symlink"):
        ex.cleanup_export(dest, "exp-link", apply=True)
    assert (target / "keep.txt").exists()
    # a symlinked file inside an export is refused too
    try:
        os.symlink(target / "keep.txt", a / "README_PU1.txt.link")
    except (OSError, NotImplementedError):
        return
    with pytest.raises(ex.ExportRefused):
        ex.cleanup_export(dest, "exp-a", apply=True)
    assert (target / "keep.txt").exists()


def test_cleanup_cli_dry_run_default(store: Path, dest: Path) -> None:
    a = do_export(store, dest, "exp-a")
    r = subprocess.run(
        [
            sys.executable,
            "-I",
            str(SCRIPTS / "export_identity_snapshot.py"),
            "--cleanup",
            "exp-a",
            "--dest-root",
            str(dest),
        ],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0 and "DRY-RUN" in r.stdout
    assert a.is_dir()


@pytest.mark.skipif(sys.platform != "win32", reason="NTFS junction")
def test_cleanup_refuses_junction(store: Path, dest: Path, tmp_path: Path) -> None:
    target = tmp_path / "elsewhere2"
    target.mkdir()
    (target / "keep.txt").write_text("x")
    link = dest / "exp-junc"
    r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True)
    if r.returncode != 0:
        pytest.skip("junction creation not permitted")
    with pytest.raises(ex.ExportRefused, match="symlink/junction"):
        ex.cleanup_export(dest, "exp-junc", apply=True)
    assert (target / "keep.txt").exists()


# =============================================================== screening handoff (sep_daily)
WINDOW = {
    "include_sep_daily": True,
    "sep_date_from": "2015-11-02",
    "sep_date_to": "2016-03-31",
    "screen_start": "2016-01-01",
    "required_lookback_trading_days": 20,
    "lookback_calendar_days": 45,
}


def add_history(path: Path) -> Path:
    """Weekday SEP rows 2015-10-01..2016-04-08 for AAA and BBB (synthetic price/volume)."""
    con = duckdb.connect(str(path))
    con.execute(
        "INSERT INTO sep SELECT t, d, 10.0, 11.0, 9.0, 10.5, 1000, 10.4, 10.6, DATE '2016-04-09' "
        "FROM range(DATE '2015-10-01', DATE '2016-04-09', INTERVAL 1 DAY) r(d), "
        "(VALUES ('AAA'), ('BBB')) v(t) WHERE dayofweek(d) BETWEEN 1 AND 5"
    )
    con.close()
    return path


@pytest.fixture
def hist(store: Path) -> Path:
    return add_history(store)


def _daily_cols(out: Path) -> list[str]:
    con = duckdb.connect(":memory:")
    p = (out / "sep_daily.parquet").as_posix()
    return [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{p}')").fetchall()]


def test_default_mode_has_no_sep_daily_and_no_price_volume(hist: Path, dest: Path) -> None:
    out = do_export(hist, dest)
    m = manifest_of(out)
    assert not (out / "sep_daily.parquet").exists()
    assert "sep_daily" not in m and "sep_daily" in m["tables_not_exported"]
    con = duckdb.connect(":memory:")
    for p in out.glob("*.parquet"):
        q = f"DESCRIBE SELECT * FROM read_parquet('{p.as_posix()}')"
        cols = [r[0].lower() for r in con.execute(q).fetchall()]
        assert not [c for c in cols if c in ex.PRICE_VOLUME_COLUMNS]


def test_sep_daily_explicit_columns_window_and_full_history_coverage(
    hist: Path, dest: Path
) -> None:
    out = do_export(hist, dest, **WINDOW)
    assert _daily_cols(out) == list(ex.SEP_DAILY_COLUMNS)
    con = duckdb.connect(":memory:")
    p = (out / "sep_daily.parquet").as_posix()
    got = con.execute(f"SELECT MIN(date), MAX(date), COUNT(*) FROM read_parquet('{p}')").fetchone()
    assert got is not None
    lo, hi, n = got
    assert str(lo) == "2015-11-02" and str(hi) == "2016-03-31"  # inclusive; 04-01 excluded
    src = duckdb.connect(str(hist), read_only=True)
    expect = src.execute(
        "SELECT COUNT(*) FROM sep WHERE date BETWEEN DATE '2015-11-02' AND DATE '2016-03-31'"
    ).fetchone()
    src.close()
    assert expect is not None and n == expect[0]
    m = manifest_of(out)
    assert ex.validate_manifest(m) == [] and ex.validate_export_dir(out, m) == []
    sd = m["sep_daily"]
    assert sd["requested_window"] == {"from": "2015-11-02", "to": "2016-03-31", "inclusive": True}
    assert sd["rows"] == n and sd["distinct_tickers"] == 2
    assert set(sd["rows_per_year"]) == {"2015", "2016"}
    assert sd["columns_requested"] == list(ex.SEP_DAILY_COLUMNS)
    assert sd["columns_present"] == list(ex.SEP_DAILY_COLUMNS) and sd["columns_missing"] == []
    assert sd["price_basis_declared"] == ex.PRICE_BASIS_DECLARED
    assert sd["lookback"]["result"] == "PASS" and sd["lookback"]["found_trading_days_min"] >= 20
    assert any("SIP" in x for x in sd["limitations"])
    assert any("overwritten" in x for x in sd["limitations"])
    assert "lastupdated" in sd["provenance_fields_present"]
    cp = (out / "sep_coverage.parquet").as_posix()
    cov = con.execute(
        f"SELECT ticker, min_date, max_date FROM read_parquet('{cp}') ORDER BY 1"
    ).fetchall()
    d = {r[0]: (str(r[1]), str(r[2])) for r in cov}
    assert d["AAA"] == ("2015-10-01", "2024-01-10")  # FULL sep table, beyond the window
    assert d["OLDN"] == ("2017-06-20", "2017-06-22")
    for tbl in ("tickers", "actions", "ingest_runs", "dataset_coverage", "sep_coverage"):
        cols = next(f for f in m["files"] if f["table"] == tbl)["columns"]
        assert ex.column_guard_defects(tbl, cols) == []


def _bare_sep_store(path: Path, cols: str) -> Path:
    con = duckdb.connect(str(path))
    con.execute(
        "CREATE TABLE tickers (permaticker VARCHAR, ticker VARCHAR, name VARCHAR, exchange VARCHAR,"
        " category VARCHAR, isdelisted BOOLEAN, firstpricedate DATE, lastpricedate DATE,"
        " lastupdated DATE)"
    )
    con.execute(
        "CREATE TABLE actions (date DATE, action VARCHAR, ticker VARCHAR, name VARCHAR,"
        " value DOUBLE, contraticker VARCHAR)"
    )
    con.execute(f"CREATE TABLE sep ({cols})")
    names = [c.split()[0] for c in cols.split(", ")]
    sel = ", ".join(
        {"ticker": "'AAA'", "date": "d"}.get(n, "1.0" if n != "volume" else "5") for n in names
    )
    con.execute(
        f"INSERT INTO sep SELECT {sel} "
        "FROM range(DATE '2015-11-02', DATE '2016-02-01', INTERVAL 1 DAY) r(d)"
    )
    con.close()
    return path


def test_missing_optional_column_recorded_not_guessed(tmp_path: Path, dest: Path) -> None:
    src = _bare_sep_store(
        tmp_path / "s.duckdb",
        "ticker VARCHAR, date DATE, close DOUBLE, closeunadj DOUBLE, volume BIGINT",
    )
    out = do_export(src, dest, **WINDOW)
    sd = manifest_of(out)["sep_daily"]
    assert sd["columns_missing"] == ["open", "high", "low", "closeadj", "lastupdated"]
    assert _daily_cols(out) == ["ticker", "date", "close", "closeunadj", "volume"]
    assert sd["provenance_fields_present"] == []


def test_missing_required_sep_column_fails_closed(tmp_path: Path, dest: Path) -> None:
    src = _bare_sep_store(
        tmp_path / "s.duckdb", "ticker VARCHAR, date DATE, close DOUBLE, volume BIGINT"
    )
    with pytest.raises(ex.ExportRefused, match="closeunadj"):
        do_export(src, dest, **WINDOW)
    assert not (dest / "exp-1").exists()


def test_lookback_insufficient_refuses_and_publishes_nothing(hist: Path, dest: Path) -> None:
    kw = dict(WINDOW, required_lookback_trading_days=500)
    with pytest.raises(ex.ExportRefused, match="lookback inadequate"):
        do_export(hist, dest, **kw)
    assert not (dest / "exp-1").exists()
    staging = dest / ".staging-exp-1"
    assert not list(staging.glob("*.parquet")) and not (staging / "EXPORT_COMPLETE.json").exists()


def test_lookback_boundary_is_exact_slice_count(hist: Path, dest: Path) -> None:
    first = manifest_of(do_export(hist, dest, "first", **WINDOW))
    found = first["sep_daily"]["lookback"]["found_trading_days_min"]
    assert found >= 20
    out = do_export(hist, dest, "ok", **dict(WINDOW, required_lookback_trading_days=found))
    assert manifest_of(out)["sep_daily"]["lookback"]["required_trading_days"] == found
    with pytest.raises(ex.ExportRefused, match="lookback inadequate"):
        do_export(hist, dest, "no", **dict(WINDOW, required_lookback_trading_days=found + 1))


@pytest.mark.parametrize(
    "kw,match",
    [
        ({"include_sep_daily": True}, "requires --sep-date-from"),
        ({"sep_date_from": "2015-11-02"}, "only valid with --include-sep-daily"),
        (dict(WINDOW, sep_date_from="2015/11/02"), "YYYY-MM-DD"),
        (dict(WINDOW, sep_date_from="2016-04-01"), "must be <="),
        (dict(WINDOW, screen_start="2015-11-02"), "screen-start"),
        (dict(WINDOW, required_lookback_trading_days=0), ">= 1"),
        (dict(WINDOW, lookback_calendar_days=0), "lookback-calendar-days"),
        ({k: v for k, v in WINDOW.items() if k != "lookback_calendar_days"}, "requires"),
    ],
)
def test_sep_daily_argument_validation(
    hist: Path, dest: Path, kw: dict[str, Any], match: str
) -> None:
    with pytest.raises(ex.ExportRefused, match=match):
        do_export(hist, dest, **kw)
    assert not (dest / "exp-1").exists() and not (dest / ".staging-exp-1").exists()


@pytest.mark.parametrize("name", ["sep_minute", "intraday_bars", "bars_1min", "sip_quotes"])
def test_intraday_tables_refused_by_name(hist: Path, dest: Path, name: str) -> None:
    with pytest.raises(ex.ExportRefused, match="out of scope"):
        do_export(hist, dest, **dict(WINDOW, requested_tables=[name]))
    with pytest.raises(ex.ExportRefused, match="not one of"):
        do_export(hist, dest, "e2", requested_tables=["fundamentals"])
    with pytest.raises(ex.ExportRefused, match="requires --include-sep-daily"):
        do_export(hist, dest, "e3", requested_tables=["sep_daily"])
    assert list(dest.iterdir()) == []


def test_allowlist_guard_semantics() -> None:
    assert ex.column_guard_defects("sep_daily", list(ex.SEP_DAILY_COLUMNS)) == []
    assert ex.column_guard_defects("sep_daily", [*ex.SEP_DAILY_COLUMNS, "adj_close"])
    assert ex.column_guard_defects("sep_daily", ["ticker", "vwap"])  # not in the explicit list
    assert ex.column_guard_defects("tickers", ["ticker", "close"])
    assert ex.column_guard_defects("actions", ["ticker", "closeadj_x"])  # substring rule
    assert ex.column_guard_defects("tickers", ["firstpricedate", "lastpricedate"]) == []


def test_manifest_validation_sep_daily(hist: Path, dest: Path) -> None:
    m = manifest_of(do_export(hist, dest, **WINDOW))
    assert ex.validate_manifest(m) == []

    def _file(x: dict[str, Any], t: str) -> dict[str, Any]:
        return next(f for f in x["files"] if f["table"] == t)

    mutations = (
        lambda x: x.pop("sep_daily"),
        lambda x: x["sep_daily"].pop("limitations"),
        lambda x: x["sep_daily"].__setitem__("price_basis_declared", {"close": "verified"}),
        lambda x: x["sep_daily"]["lookback"].__setitem__("result", "FAIL"),
        lambda x: _file(x, "sep_daily")["columns"].append("vwap"),
        lambda x: _file(x, "tickers")["columns"].append("close"),
    )
    for mutate in mutations:
        bad = json.loads(json.dumps(m))
        mutate(bad)
        assert ex.validate_manifest(bad)


def test_sep_daily_logical_hash_reproducible_and_price_sensitive(
    tmp_path: Path, dest: Path
) -> None:
    src = add_history(build_store(tmp_path / "s.duckdb"))
    a = manifest_of(do_export(src, dest, "a", **WINDOW))
    b = manifest_of(do_export(src, dest, "b", **WINDOW))
    assert _logical(a, "sep_daily") == _logical(b, "sep_daily")
    con = duckdb.connect(str(src))
    con.execute("UPDATE sep SET close = 10.51 WHERE ticker = 'AAA' AND date = DATE '2016-02-01'")
    con.close()
    c = manifest_of(do_export(src, dest, "c", **WINDOW))
    assert _logical(c, "sep_daily") != _logical(a, "sep_daily")
    assert _logical(c, "tickers") == _logical(a, "tickers")


def test_sep_daily_internal_read_works_and_seam_refuses(
    hist: Path, dest: Path, tmp_path: Path
) -> None:
    out = do_export(hist, dest, **WINDOW)
    con = duckdb.connect(":memory:")
    # the consumer-side one-line mapping documented in the spec
    con.execute(
        f"CREATE VIEW sep AS SELECT * FROM read_parquet('{(out / 'sep_daily.parquet').as_posix()}')"
    )
    row = con.execute("SELECT COUNT(DISTINCT ticker), MIN(date), MAX(date) FROM sep").fetchone()
    assert row is not None and row[0] == 2 and str(row[1]) == "2015-11-02"
    for f in (out / "sep_daily.parquet", out / "manifest.json"):
        with pytest.raises(PersonalScopeBlocked):
            export_file_for_external_use(f, tmp_path / "ext" / f.name)
    assert not (tmp_path / "ext").exists()


def test_cleanup_with_sep_daily_touches_only_that_export(hist: Path, dest: Path) -> None:
    a = do_export(hist, dest, "exp-a", **WINDOW)
    b = do_export(hist, dest, "exp-b", **WINDOW)
    victims = ex.cleanup_export(dest, "exp-a", apply=True)
    assert any(v.name == "sep_daily.parquet" for v in victims)
    assert not a.exists() and b.is_dir() and (b / "sep_daily.parquet").is_file()
    assert not any(v.parent == b for v in victims)


def test_cli_sep_daily_end_to_end(hist: Path, dest: Path) -> None:
    script = str(SCRIPTS / "export_identity_snapshot.py")
    cmd = [
        sys.executable, "-I", script, "--source", str(hist), "--dest-root", str(dest),
        "--export-id", "cli-d", "--purpose", "p", "--executing-identity", "me",
        "--permission-ref", PERM_REF, "--permission-scope", PERM_SCOPE,
        "--include-sep-daily", "--sep-date-from", "2015-11-02", "--sep-date-to", "2016-03-31",
        "--screen-start", "2016-01-01", "--required-lookback-trading-days", "20",
        "--lookback-calendar-days", "45",
    ]  # fmt: skip
    r = subprocess.run(cmd, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    v = subprocess.run(
        [sys.executable, "-I", script, "--verify", str(dest / "cli-d")],
        capture_output=True,
        text=True,
    )
    assert v.returncode == 0
    bad = subprocess.run(
        [*cmd[:8], "cli-e", *cmd[9:], "--table", "bars_1min"], capture_output=True, text=True
    )
    assert bad.returncode == 2


# =============================================================== decision-day slice checks
def _add_issuers(path: Path) -> Path:
    """CCC: only 9 rows ending on the first decision day. DDD: zero volume through December.
    EEE: NULL close through December. FFF: complete and clean."""
    con = duckdb.connect(str(path))
    wk = "dayofweek(d) BETWEEN 1 AND 5"
    mk = (
        "INSERT INTO sep SELECT '{t}', d, 10.0, 11.0, 9.0, 10.5, 1000, 10.4, 10.6, "
        "DATE '2016-04-09' FROM range(DATE '{a}', DATE '{b}', INTERVAL 1 DAY) r(d) WHERE " + wk
    )
    con.execute(mk.format(t="CCC", a="2015-12-21", b="2016-01-01"))
    con.execute(mk.format(t="DDD", a="2015-10-01", b="2016-04-09"))
    con.execute(mk.format(t="EEE", a="2015-10-01", b="2016-04-09"))
    con.execute(mk.format(t="FFF", a="2015-10-01", b="2016-04-09"))
    con.execute(
        "UPDATE sep SET volume = 0 WHERE ticker = 'DDD' "
        "AND date BETWEEN DATE '2015-12-01' AND DATE '2015-12-31'"
    )
    con.execute(
        "UPDATE sep SET close = NULL WHERE ticker = 'EEE' "
        "AND date BETWEEN DATE '2015-12-01' AND DATE '2015-12-31'"
    )
    con.close()
    return path


def test_decision_days_derived_from_data_and_recorded(hist: Path, dest: Path) -> None:
    m = manifest_of(do_export(hist, dest, **WINDOW))
    days = m["sep_daily"]["lookback"]["decision_days"]
    assert [d["decision_day"] for d in days] == ["2015-12-31", "2016-01-29", "2016-02-29"]
    assert [d["month_start"] for d in days] == ["2016-01-01", "2016-02-01", "2016-03-01"]
    for d in days:
        assert d["d_precedes_month_start"] is True
        assert d["slice_end"] == d["decision_day"]
        assert d["max_date_in_slice"] == d["decision_day"]
        assert d["rows_in_slice_with_date_after_decision_day"] == 0
        assert d["distinct_trading_dates_in_slice"] >= 20
        lu = d["lastupdated_vs_decision_day"]
        # synthetic lastupdated (2016-04-09) is later than every decision day: report-only
        assert lu["rows_in_slice_with_lastupdated_after_decision_day"] == d["rows_in_slice"] > 0
    assert days[0]["slice_start"] == "2015-11-16"  # 2015-12-31 minus 45 calendar days
    pi = m["planning_inputs"]
    assert pi["universe.adv_window_days"] == 20 and pi["adv_window_matches_schema_pin"] is True
    assert pi["universe.min_price"] == 10.0 and pi["lookback_calendar_days"] == 45
    assert pi["export_window"] == {"from": "2015-11-02", "to": "2016-03-31"}
    assert any("schema.py:293" in e for e in pi["evidence"])


def test_short_slice_refuses_even_with_extra_history_before_it(hist: Path, dest: Path) -> None:
    # 10 calendar days gives ~9 sessions; months of earlier history exist but must not count
    with pytest.raises(ex.ExportRefused, match=r"decision day 2015-12-31.*slice"):
        do_export(hist, dest, **dict(WINDOW, lookback_calendar_days=10))
    assert not (dest / "exp-1").exists()
    assert not list((dest / ".staging-exp-1").glob("*.parquet"))


def test_decision_day_absent_refuses(hist: Path, dest: Path) -> None:
    con = duckdb.connect(str(hist))
    con.execute("DELETE FROM sep WHERE date < DATE '2016-01-04'")
    con.close()
    with pytest.raises(ex.ExportRefused, match="no session before month start 2016-01-01"):
        do_export(hist, dest, **WINDOW)
    assert not (dest / "exp-1").exists()


def test_per_issuer_report_reasons_do_not_fail_or_change_rows(tmp_path: Path, dest: Path) -> None:
    src = _add_issuers(add_history(build_store(tmp_path / "s.duckdb")))
    out = do_export(src, dest, **WINDOW)
    m = manifest_of(out)
    assert ex.validate_manifest(m) == [] and ex.validate_export_dir(out, m) == []
    rep = json.loads((out / "lookback_affected_issuers.json").read_text(encoding="utf-8"))
    d1 = {a["ticker"]: a["reasons"] for a in rep["decision_days"]["2015-12-31"]}
    assert d1 == {
        "CCC": ["ROWS_IN_SLICE_LT_20"],
        "DDD": ["ZERO_VOLUME"],
        "EEE": ["NULL_FIELD"],
    }
    # EEE's NULL close persists to D1 only; CCC has no row on later decision days (not listed)
    for later in ("2016-01-29", "2016-02-29"):
        got = {a["ticker"] for a in rep["decision_days"][later]}
        assert "CCC" not in got and "FFF" not in got and "AAA" not in got
    summ = m["sep_daily"]["lookback"]["decision_days"][0]
    assert summ["affected_issuers_count"] == 3
    assert summ["affected_by_reason"] == {
        "NULL_FIELD": 1,
        "ROWS_IN_SLICE_LT_20": 1,
        "ZERO_VOLUME": 1,
    }
    assert summ["affected_sample"] == ["CCC", "DDD", "EEE"]
    # nothing removed or changed: affected issuers' rows are all delivered
    con = duckdb.connect(":memory:")
    p = (out / "sep_daily.parquet").as_posix()
    got_t = {
        r[0] for r in con.execute(f"SELECT DISTINCT ticker FROM read_parquet('{p}')").fetchall()
    }
    assert {"AAA", "BBB", "CCC", "DDD", "EEE", "FFF"} <= got_t
    assert not [f.name for f in out.iterdir() if "universe" in f.name.lower()]
    # the report file is registered, hashed, licensed and removable by cleanup
    assert m["report_files"][0]["file"] == "lookback_affected_issuers.json"
    assert (out / "lookback_affected_issuers.json.license.json").is_file()
    with pytest.raises(PersonalScopeBlocked):
        export_file_for_external_use(
            out / "lookback_affected_issuers.json", tmp_path / "ext" / "r.json"
        )
    victims = ex.cleanup_export(dest, "exp-1", apply=True)
    assert any(v.name == "lookback_affected_issuers.json" for v in victims)
    assert not out.exists()
