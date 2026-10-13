"""PU-1: the six evidence report scripts are INTERNAL reports routed through the shared writers.

They declare their sources from their real reads, write a footer + scope sidecar, state that a
label/sidecar is not a permission to share, and no longer call themselves customer-facing.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import re
import sqlite3
import sys
from pathlib import Path

import pytest

import app.licensing as lic
from app.licensing.scopes import LicenseScope

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parents[1]
SCRIPTS = BACKEND / "scripts"
OWNER = "owner_generated_records"
MARKET = "alpaca_market_data"
REPORTS = (
    "monthly_evidence",
    "live_evidence",
    "confidence_score",
    "ops_kpis",
    "edge_evidence",
    "range_evidence",
)


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _assert_internal_outputs(directory: Path, stem: str, sources_expected: set[str]) -> None:
    md, js = directory / f"{stem}.md", directory / f"{stem}.json"
    assert md.is_file() and js.is_file()
    text = md.read_text(encoding="utf-8")
    assert lic.PERSONAL_FOOTER in text
    assert lic.PERMISSION_NOTE in text
    payload = json.loads(js.read_text(encoding="utf-8"))
    assert payload["license_note"] == lic.PERMISSION_NOTE
    for artifact in (md, js):
        side = json.loads(Path(str(artifact) + ".license.json").read_text(encoding="utf-8"))
        assert side["artifact_sha256"] == hashlib.sha256(artifact.read_bytes()).hexdigest()
        assert set(side["license_sources"]) == sources_expected
        assert side["license_scope"] == "PERSONAL"
        assert lic.scope_of_file(artifact) is LicenseScope.PERSONAL
    # the sidecar makes the file un-exportable through the seam
    with pytest.raises(lic.PersonalScopeBlocked):
        lic.export_file_for_external_use(md, directory / "outbound" / md.name)


def _book_db(path: Path) -> str:
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE audit_log (ts TEXT, user_id INT, action TEXT, actor_type TEXT,
                                target_type TEXT, target_id TEXT);
        CREATE TABLE equity_snapshots (ts TEXT, account_id INT, equity REAL);
        CREATE TABLE reconciliation_runs (ran_at TEXT, account_id INT, result TEXT,
                                          n_checked INT, n_discrepancies INT);
        CREATE TABLE replay_runs (ran_at TEXT, n_checked INT, n_matched INT, n_mismatched INT);
        CREATE TABLE strategies (id INT, user_id INT, name TEXT, version TEXT,
                                 status TEXT, params_json TEXT);
        CREATE TABLE accounts (id INT, user_id INT, broker TEXT, mode TEXT);
        CREATE TABLE accounts_state (account_id INT, cash REAL, equity REAL, portfolio_value REAL,
                                     buying_power REAL, day_change_pct REAL, status TEXT,
                                     updated_at TEXT);
        CREATE TABLE symbols (id INT, ticker TEXT);
        CREATE TABLE orders (id INT, symbol_id INT, side TEXT, qty REAL, status TEXT,
                             created_at TEXT, source_type TEXT, account_id INT);
        CREATE TABLE fills (order_id INT, qty REAL, price REAL, commission REAL);
        CREATE TABLE positions (symbol_id INT, qty REAL, market_value REAL, unrealized_pl REAL,
                                unrealized_plpc REAL, account_id INT);
        """
    )
    con.execute("INSERT INTO accounts VALUES (1, 1, 'alpaca', 'paper')")
    con.execute(
        "INSERT INTO strategies VALUES (2, 1, 'mom', '1.0', 'PAPER', '{\"use_daily_overlay\": true, \"vol_target_annual\": 0.15}')"
    )
    con.executemany(
        "INSERT INTO equity_snapshots VALUES (?,?,?)",
        [("2026-06-02 16:10:00.0", 1, 100000.0), ("2026-06-03 16:10:00.0", 1, 100500.0)],
    )
    con.execute("INSERT INTO replay_runs VALUES ('2026-06-03 03:30:00.0', 5, 5, 0)")
    con.execute("INSERT INTO reconciliation_runs VALUES ('2026-06-03 03:30:00.0', 1, 'pass', 4, 0)")
    con.execute(
        "INSERT INTO audit_log VALUES ('2026-06-03 10:00:00.0', 1, 'ORDER_RISK_PASSED', 'USER', "
        "'order', '1')"
    )
    con.commit()
    con.close()
    return str(path)


def test_declared_sources_come_from_the_real_reads() -> None:
    live = _load("live_evidence")
    monthly = _load("monthly_evidence")
    edge = _load("edge_evidence")
    rng = _load("range_evidence")
    assert set(live.LICENSE_SOURCES) == {OWNER, MARKET}
    assert set(monthly.LICENSE_SOURCES) == {OWNER, MARKET}
    assert set(edge.LICENSE_SOURCES) == {"sharadar", MARKET}
    assert set(rng.LICENSE_SOURCES) == {MARKET}
    # every declared id is a registered source (an unregistered id would be UNKNOWN by accident)
    reg = lic.load_registry()
    for mod in (live, monthly, edge, rng):
        for sid in mod.LICENSE_SOURCES:
            assert sid in reg.entries, (mod.__name__, sid)


def test_ops_kpis_and_confidence_report_write_footer_note_and_sidecar(tmp_path) -> None:
    db = _book_db(tmp_path / "w.sqlite")
    ops, conf = _load("ops_kpis"), _load("confidence_score")
    out = tmp_path / "out"
    out.mkdir()
    ops._run_one(db, out)
    conf._run_one(db, out)
    _assert_internal_outputs(out, "ops_kpis", {OWNER, MARKET})
    _assert_internal_outputs(out, "confidence_score", {OWNER, MARKET})


def test_live_evidence_report_writes_footer_note_and_sidecar(tmp_path, monkeypatch) -> None:
    db = _book_db(tmp_path / "w.sqlite")
    live = _load("live_evidence")
    out = tmp_path / "live"
    monkeypatch.setattr(
        sys,
        "argv",
        ["live_evidence.py", "--db", db, "--strategy-id", "2", "--report-dir", str(out)],
    )
    assert live.main() == 0
    _assert_internal_outputs(out, "live_evidence", {OWNER, MARKET})
    _assert_internal_outputs(out, "live_evidence_2", {OWNER, MARKET})


def test_monthly_evidence_report_writes_footer_note_and_sidecar(tmp_path, monkeypatch) -> None:
    db = _book_db(tmp_path / "w.sqlite")
    monthly = _load("monthly_evidence")
    out = tmp_path / "monthly"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "monthly_evidence.py",
            "--db",
            db,
            "--strategy-id",
            "2",
            "--month",
            "2026-06",
            "--report-dir",
            str(out),
        ],
    )
    assert monthly.main() == 0
    _assert_internal_outputs(out, "monthly_evidence", {OWNER, MARKET})


def test_range_evidence_report_writes_footer_note_and_sidecar(tmp_path, monkeypatch) -> None:
    rng = _load("range_evidence")
    monkeypatch.setattr(rng, "_run", lambda *a, **k: [5.0, -2.0, 3.0, -1.0])
    out = tmp_path / "range"
    monkeypatch.setattr(
        sys, "argv", ["range_evidence.py", "--bootstrap", "50", "--report-dir", str(out)]
    )
    assert rng.main() == 0
    _assert_internal_outputs(out, "range_evidence", {MARKET})


def test_edge_evidence_writes_only_through_the_shared_writers() -> None:
    """The harness needs the Sharadar store to run, so this asserts structure: the report is
    written through write_internal_report/write_internal_json with the declared sources and the
    script has no direct text write left."""
    src = (SCRIPTS / "edge_evidence.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    calls = {
        n.func.id
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }
    assert {"write_internal_report", "write_internal_json"} <= calls
    assert not any(
        isinstance(n, ast.Attribute) and n.attr in ("write_text", "write_bytes")
        for n in ast.walk(tree)
    )
    assert "sources=LICENSE_SOURCES" in src
    assert "PERMISSION_NOTE" in src


@pytest.mark.parametrize("name", REPORTS)
def test_reports_are_internal_and_no_longer_labelled_customer_facing(name) -> None:
    src = (SCRIPTS / f"{name}.py").read_text(encoding="utf-8")
    assert not re.search(r"customer[- ]facing|allocator[- ]readable|allocator/buyer", src, re.I), (
        name
    )
    assert "INTERNAL report (PU-1)" in src
    assert "does not establish permission to share" in src
    # the writers are the shared seam, with sources always passed explicitly
    assert "write_internal_report" in src and "write_internal_json" in src


def test_kpi_module_docstring_no_longer_claims_customer_facing() -> None:
    src = (BACKEND / "app" / "ops" / "kpis.py").read_text(encoding="utf-8")
    assert not re.search(r"customer[- ]facing|\*\*customer\*\*|allocator/buyer", src, re.I)


def test_report_scripts_are_internal_only_in_the_export_registry() -> None:
    reg = json.loads((BACKEND / "ci" / "pu1_export_paths.json").read_text(encoding="utf-8"))
    by_file = {e["file"]: e for e in reg["entries"]}
    for name in REPORTS:
        e = by_file[f"apps/backend/scripts/{name}.py"]
        assert e["classification"] == "INTERNAL_ONLY", name
        assert "does not establish permission to share" in e["reason"], name
        assert "write_internal_report" in e["reason"], name


def test_daily_report_is_stamped_with_a_declared_lineage() -> None:
    src = (REPO / "scripts" / "reports" / "daily_report.py").read_text(encoding="utf-8")
    assert "stamp(" in src and "REPORT_SOURCES" in src and "taint_from_fields" in src
