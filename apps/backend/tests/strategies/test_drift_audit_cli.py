"""§8 drift-audit CLI — fail-closed provenance gate + --provenance-only mode."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import duckdb

_CLI = Path(__file__).resolve().parents[2] / "scripts" / "drift_audit_momentum_daily.py"
_spec = importlib.util.spec_from_file_location("drift_audit_cli", _CLI)
_cli = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _cli
_spec.loader.exec_module(_cli)


def _make_db(path) -> None:
    con = duckdb.connect(str(path))
    con.execute("CREATE TABLE sep (date DATE, ticker VARCHAR, closeadj DOUBLE)")
    con.execute("INSERT INTO sep VALUES ('2005-01-03','AAA',10.0), ('2026-06-12','AAA',15.0)")
    con.close()


def _argv(db, out, *, sha, universe="U1", extra=()):
    return ["prog", "--factor-db", str(db), "--price-db", str(db),
            "--expected-factor-db-sha256", sha, "--expected-universe-id", universe,
            "--start-date", "2005-01-03", "--end-date", "2026-06-12",
            "--output", str(out), *extra]


def test_cli_refuses_on_digest_mismatch(tmp_path, monkeypatch):
    db = tmp_path / "f.duckdb"
    _make_db(db)
    out = tmp_path / "m.json"
    monkeypatch.setattr(sys, "argv", _argv(db, out, sha="0" * 64, extra=("--provenance-only",)))
    assert _cli.main() == 5          # fail-closed
    assert not out.exists()          # nothing written on refusal


def test_cli_provenance_only_writes_verified_manifest(tmp_path, monkeypatch):
    from app.strategies.drift_audit_provenance import sha256_file
    db = tmp_path / "f.duckdb"
    _make_db(db)
    out = tmp_path / "m.json"
    monkeypatch.setattr(sys, "argv",
                        _argv(db, out, sha=sha256_file(db), extra=("--provenance-only",)))
    assert _cli.main() == 0
    doc = json.loads(out.read_text())
    assert doc["mode"] == "provenance-only"
    man = doc["manifest"]
    assert man["factor_db"]["digest_verified"] is True
    assert man["expected_universe_id"] == "U1"
    assert man["replica_reference"].startswith("scripts/backtest_momentum_stage4.py")
    assert man["strategy"]["params"]["regime_mode"] == "graduated"
    assert "commit" in man["code"]


def test_cli_requires_universe_id(tmp_path, monkeypatch):
    from app.strategies.drift_audit_provenance import sha256_file
    db = tmp_path / "f.duckdb"
    _make_db(db)
    out = tmp_path / "m.json"
    monkeypatch.setattr(sys, "argv",
                        _argv(db, out, sha=sha256_file(db), universe="", extra=("--provenance-only",)))
    assert _cli.main() == 5          # empty universe id is fail-closed
