"""§8 drift audit — fail-closed provenance manifest tests."""

from __future__ import annotations

import duckdb
import pytest

from app.strategies.drift_audit_provenance import (
    ProvenanceError,
    build_manifest,
    code_provenance,
    db_manifest,
    sha256_file,
    verify_db,
)


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
