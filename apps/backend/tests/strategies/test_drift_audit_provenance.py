"""§8 drift audit — fail-closed provenance manifest tests."""

from __future__ import annotations

import duckdb
import pytest

from app.strategies.drift_audit_provenance import (
    ProvenanceError,
    build_manifest,
    code_provenance,
    db_manifest,
    sep_content_digest,
    sha256_file,
    tickers_content_digest,
    verify_content_digests,
    verify_db,
)


def _make_full_db(path) -> None:
    """A db with the audit-consumed sep + tickers columns for content-digest tests."""
    con = duckdb.connect(str(path))
    con.execute("CREATE TABLE sep (ticker VARCHAR, date DATE, open DOUBLE, high DOUBLE, "
                "low DOUBLE, closeadj DOUBLE, closeunadj DOUBLE, volume BIGINT, lastupdated DATE)")
    con.execute("INSERT INTO sep VALUES "
                "('AAA','2005-01-03',9.9,10.1,9.8,10.0,10.0,1000,'2005-01-03'),"
                "('BBB','2005-01-03',19.9,20.1,19.8,20.0,20.0,2000,'2005-01-03'),"
                "('AAA','2026-06-12',14.9,15.1,14.8,15.0,15.0,1500,'2026-06-12')")
    con.execute("CREATE TABLE tickers (ticker VARCHAR, name VARCHAR, exchange VARCHAR, "
                "category VARCHAR, sector VARCHAR, industry VARCHAR, isdelisted BOOLEAN, "
                "firstpricedate DATE, lastpricedate DATE, lastupdated DATE)")
    con.execute("INSERT INTO tickers VALUES "
                "('AAA','A Co','NASDAQ','Common','Tech','Software',false,'2000-01-01','2026-06-12','2026-06-12'),"
                "('BBB','B Co','NYSE','Common','Health','Biotech',false,'2001-01-01','2026-06-12','2026-06-12'),"
                "('ZZZ','Z Co','NYSE','Common','Energy','Oil',true,'1999-01-01','2010-01-01','2010-01-01')")
    con.close()


def _make_db(path) -> None:
    con = duckdb.connect(str(path))
    con.execute("CREATE TABLE sep (date DATE, ticker VARCHAR, closeadj DOUBLE)")
    con.execute("INSERT INTO sep VALUES ('2005-01-03','AAA',10.0), ('2005-01-03','BBB',20.0), "
                "('2026-06-12','AAA',15.0)")
    con.close()


def test_sha256_is_stable_and_content_sensitive(tmp_path):
    a, b = tmp_path / "a.bin", tmp_path / "b.bin"
    a.write_bytes(b"hello")
    b.write_bytes(b"hello")
    assert sha256_file(a) == sha256_file(b)
    b.write_bytes(b"world")
    assert sha256_file(a) != sha256_file(b)


def test_db_manifest_inventories_tables_dates_tickers(tmp_path):
    db = tmp_path / "f.duckdb"
    _make_db(db)
    man = db_manifest(db)
    assert man["abs_path"].endswith("f.duckdb") and len(man["sha256"]) == 64
    assert "sep" in man["tables"]
    sep = man["inventory"]["sep"]
    assert sep["rows"] == 3 and sep["distinct_tickers"] == 2
    assert sep["date_min"] == "2005-01-03" and sep["date_max"] == "2026-06-12"


def test_db_manifest_missing_file_is_provenance_error(tmp_path):
    with pytest.raises(ProvenanceError):
        db_manifest(tmp_path / "nope.duckdb")


def test_verify_db_fails_closed_on_digest_mismatch(tmp_path):
    db = tmp_path / "f.duckdb"
    _make_db(db)
    good = sha256_file(db)
    assert verify_db(db, good)["digest_verified"] is True
    with pytest.raises(ProvenanceError):
        verify_db(db, "0" * 64)


def test_build_manifest_requires_universe_id_and_digest(tmp_path):
    db = tmp_path / "f.duckdb"
    _make_db(db)
    sha = sha256_file(db)
    common = dict(factor_db=db, price_db=db, expected_factor_db_sha256=sha,
                  start_date="2005-01-03", end_date="2026-06-12", strategy_name="momentum-daily",
                  strategy_version="0.2.0", strategy_params={"regime_mode": "graduated"},
                  replica_reference="scripts/backtest_momentum_stage4.py::simulate variant=C")
    with pytest.raises(ProvenanceError):
        build_manifest(expected_universe_id="", **common)          # missing universe id
    with pytest.raises(ProvenanceError):
        build_manifest(expected_universe_id="U1", **{**common, "expected_factor_db_sha256": ""})
    with pytest.raises(ProvenanceError):
        build_manifest(expected_universe_id="U1", **{**common, "expected_factor_db_sha256": "0" * 64})


def test_build_manifest_full_when_verified(tmp_path):
    db = tmp_path / "f.duckdb"
    _make_db(db)
    sha = sha256_file(db)
    man = build_manifest(
        factor_db=db, price_db=db, expected_factor_db_sha256=sha, expected_price_db_sha256=sha,
        expected_universe_id="momentum_daily_stage2_4_full", start_date="2005-01-03",
        end_date="2026-06-12", strategy_name="momentum-daily", strategy_version="0.2.0",
        strategy_params={"regime_mode": "graduated", "max_names": 5},
        replica_reference="scripts/backtest_momentum_stage4.py::simulate variant=C",
        session_count=3400, exclusions=["market_symbol=SPY (proxy substitution)"])
    assert man["schema"] == "drift_audit_manifest/v1"
    assert man["expected_universe_id"] == "momentum_daily_stage2_4_full"
    assert man["factor_db"]["digest_verified"] and man["price_db"]["digest_verified"]
    assert man["all_digests_verified"] is True
    assert man["window"]["session_count"] == 3400 and man["window"]["exclusions"]
    assert "commit" in man["code"] and "working_tree_clean" in man["code"]
    assert man["strategy"]["params"]["regime_mode"] == "graduated"


def test_code_provenance_reports_commit_and_tree_state():
    cp = code_provenance()
    assert isinstance(cp["commit"], str) and isinstance(cp["working_tree_clean"], bool)


# ---- content-digest binding ----

def test_content_digests_are_deterministic_and_stat_correct(tmp_path):
    db = tmp_path / "f.duckdb"
    _make_full_db(db)
    s1 = sep_content_digest(db, "2005-01-03", "2026-06-12")
    s2 = sep_content_digest(db, "2005-01-03", "2026-06-12")
    assert s1["sha256"] == s2["sha256"] and len(s1["sha256"]) == 64      # deterministic
    assert s1["rows"] == 3 and s1["distinct_sessions"] == 2 and s1["distinct_tickers"] == 2
    assert s1["columns"] == ["ticker", "date", "open", "high", "low", "closeadj", "volume"]
    assert s1["canonicalization"] == "drift_audit_content_digest/v1"
    t = tickers_content_digest(db, "2005-01-03", "2026-06-12")
    assert t["rows"] == 2 and t["distinct_tickers"] == 2                  # only AAA,BBB in-window (not ZZZ)


def test_verify_content_digests_fail_closed_on_mismatch(tmp_path):
    db = tmp_path / "f.duckdb"
    _make_full_db(db)
    sep = sep_content_digest(db, "2005-01-03", "2026-06-12")["sha256"]
    tkr = tickers_content_digest(db, "2005-01-03", "2026-06-12")["sha256"]
    ok = verify_content_digests(db, "2005-01-03", "2026-06-12",
                                expected_sep_sha256=sep, expected_tickers_sha256=tkr)
    assert ok["sep"]["digest_verified"] and ok["tickers"]["digest_verified"]
    with pytest.raises(ProvenanceError):
        verify_content_digests(db, "2005-01-03", "2026-06-12",
                               expected_sep_sha256="0" * 64, expected_tickers_sha256=tkr)
    with pytest.raises(ProvenanceError):
        verify_content_digests(db, "2005-01-03", "2026-06-12",
                               expected_sep_sha256=sep, expected_tickers_sha256="0" * 64)


def test_build_manifest_with_content_pins_emits_binding_and_verifies(tmp_path):
    db = tmp_path / "f.duckdb"
    _make_full_db(db)
    sha = sha256_file(db)
    sep = sep_content_digest(db, "2005-01-03", "2026-06-12")["sha256"]
    tkr = tickers_content_digest(db, "2005-01-03", "2026-06-12")["sha256"]
    man = build_manifest(
        factor_db=db, price_db=db, expected_factor_db_sha256=sha, expected_price_db_sha256=sha,
        expected_universe_id="U1", start_date="2005-01-03", end_date="2026-06-12",
        strategy_name="momentum-daily", strategy_version="0.2.0",
        strategy_params={"regime_mode": "graduated"}, replica_reference="stage4::simulate C",
        expected_sep_content_sha256=sep, expected_tickers_content_sha256=tkr,
        content_digest_artifact_sha256="artifacthash")
    assert man["schema"] == "drift_audit_manifest/v2"
    b = man["provenance_binding"]
    assert b["whole_file_sha256"] == sha and b["sep_content_sha256"] == sep
    assert b["tickers_content_sha256"] == tkr and b["content_digest_artifact_sha256"] == "artifacthash"
    assert b["canonicalization_version"] == "drift_audit_content_digest/v1"
    assert "measurement_code_commit" in b and "working_tree_clean" in b
    assert b["strategy_configuration"]["version"] == "0.2.0"
    # a wrong content pin refuses the whole manifest
    with pytest.raises(ProvenanceError):
        build_manifest(
            factor_db=db, price_db=db, expected_factor_db_sha256=sha, expected_universe_id="U1",
            start_date="2005-01-03", end_date="2026-06-12", strategy_name="m", strategy_version="0",
            strategy_params={}, replica_reference="r",
            expected_sep_content_sha256="0" * 64, expected_tickers_content_sha256=tkr)


def test_build_manifest_requires_both_content_pins_or_neither(tmp_path):
    db = tmp_path / "f.duckdb"
    _make_full_db(db)
    sha = sha256_file(db)
    with pytest.raises(ProvenanceError):
        build_manifest(
            factor_db=db, price_db=db, expected_factor_db_sha256=sha, expected_universe_id="U1",
            start_date="2005-01-03", end_date="2026-06-12", strategy_name="m", strategy_version="0",
            strategy_params={}, replica_reference="r", expected_sep_content_sha256="x" * 64)  # only one
