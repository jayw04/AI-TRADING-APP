"""The verifier and the watchdog, run against ONE input, must agree.

This is the test the 2026-08-11 incident asks for. On that day the refresh verifier
aborted the swap at coverage 0.9784 while the watchdog published PASS at 1.0000 — same
store, same universe, same evidence artifact, opposite verdicts. Property tests that each
component "uses the shared module" would not have caught that; only running both and
comparing does.

Both halves are exercised for real: ``verify_staging`` is called directly, and the
watchdog's in-container block is composed with the helper exactly as the shell composes
them and executed. Nothing here is a fixture standing in for the other side.
"""

from __future__ import annotations

import datetime
import importlib.util
import json
import re
import sqlite3
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
WATCHDOG = REPO_ROOT / "deploy" / "aws" / "factor-freshness.sh"
HELPER = REPO_ROOT / "apps" / "backend" / "scripts" / "factor_adjudication.py"
VERIFIER = REPO_ROOT / "apps" / "backend" / "scripts" / "factor_refresh.py"

TODAY = datetime.date(2026, 8, 11)
FRONTIER = datetime.date(2026, 8, 10)
DEAD = datetime.date(2026, 6, 12)


def _module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _driver_source() -> str:
    blocks = re.findall(r"<<'PY'[^\n]*\n(.*?)\nPY\n", WATCHDOG.read_text(encoding="utf-8"), re.S)
    matching = [b for b in blocks if "DATA_UNADJUDICATED_STALE" in b]
    assert len(matching) == 1
    return HELPER.read_text(encoding="utf-8") + "\n" + matching[0]


def _store(tmp: Path, names: dict[str, tuple[datetime.date, datetime.date] | None]) -> Path:
    duckdb = pytest.importorskip("duckdb")
    p = tmp / "factor_data.duckdb"
    con = duckdb.connect(str(p))
    con.execute("CREATE TABLE sep (ticker VARCHAR, date DATE, close DOUBLE, volume DOUBLE)")
    con.execute("CREATE TABLE tickers (ticker VARCHAR, lastpricedate DATE)")
    for ticker, dates in names.items():
        if dates is None:  # absent from the provider entirely
            continue
        sep_max, lpd = dates
        con.execute("INSERT INTO sep VALUES (?, ?, 1.0, 1.0)", [ticker, sep_max])
        con.execute("INSERT INTO tickers VALUES (?, ?)", [ticker, lpd])
    con.close()
    return p


def _app_db(tmp: Path) -> Path:
    p = tmp / "workbench.sqlite"
    con = sqlite3.connect(p)
    con.executescript(
        """
        CREATE TABLE symbols (id INTEGER PRIMARY KEY, ticker TEXT);
        CREATE TABLE positions (id INTEGER PRIMARY KEY, symbol_id INTEGER, qty REAL);
        CREATE TABLE orders (id INTEGER PRIMARY KEY, symbol_id INTEGER, status TEXT);
        CREATE TABLE strategies (id INTEGER PRIMARY KEY, status TEXT, symbols_json TEXT);
        """
    )
    con.commit()
    con.close()
    return p


def _evidence_doc(tmp: Path, records) -> Path:
    p = tmp / "_factor_exhaustion_evidence.json"
    p.write_text(
        json.dumps({"generated_at_utc": "2026-08-11T10:00:00Z", "symbols": records}),
        encoding="utf-8",
    )
    return p


def _record(symbol, *, claim, alive):
    return {
        "symbol": symbol,
        "expected_classification": claim,
        "requested": True,
        "request_status": "ok",
        "provider_rows_after_live_frontier": 0,
        "corroboration": {
            "source": "alpaca",
            "control_symbol": "AAPL",
            "control_last_date": FRONTIER.isoformat(),
            "last_date": FRONTIER.isoformat() if alive else None,
        },
    }


# The 2026-08-11 production shape, in miniature: ETFs the provider never carried, one dead
# name, one genuinely stale name with no evidence at all.
UNIVERSE = ["AAPL", "MSFT", "UUP", "KMLM", "SATS", "ZZZZ"]
NAMES = {
    "AAPL": (FRONTIER, FRONTIER),
    "MSFT": (FRONTIER, FRONTIER),
    "UUP": None,
    "KMLM": None,
    "SATS": (DEAD, DEAD),
    "ZZZZ": (DEAD, DEAD),
}
RECORDS = [
    _record("UUP", claim="PROVIDER_NOT_COVERED", alive=True),
    _record("KMLM", claim="PROVIDER_NOT_COVERED", alive=True),
    _record("SATS", claim="PROVIDER_EXHAUSTED", alive=False),
]


def _watchdog_output(tmp: Path, monkeypatch, capsys) -> str:
    sealed = tmp / "_factor_refresh_universe_sealed.json"
    sealed.write_text(json.dumps({"universe": UNIVERSE}), encoding="utf-8")
    for key, value in {
        "TOLERANCE": "4",
        "MAX_LAG_DAYS": "4",
        "MIN_COVERAGE": "0.98",
        "STALE_SAMPLE": "12",
        "SEALED_PATH": str(sealed),
        "EXHAUSTION_PATH": str(_evidence_doc(tmp, RECORDS)),
        "STORE_PATH": str(_store(tmp, NAMES)),
        "APP_DB": str(_app_db(tmp)),
        "ET_TODAY": TODAY.isoformat(),
        "REFRESH_TZ": "America/New_York",
    }.items():
        monkeypatch.setenv(key, value)
    exec(  # noqa: S102
        compile(_driver_source(), "factor-freshness.sh:<composed>", "exec"),
        {"__name__": "__main__"},
    )
    return capsys.readouterr().out


def _verifier_classification(tmp: Path):
    verifier = _module(VERIFIER, "factor_refresh")
    helper = _module(HELPER, "factor_adjudication")
    store = _store(tmp / "v", NAMES)
    evidence, _, _ = helper.load_evidence(_evidence_doc(tmp / "v", RECORDS))
    operational = helper.operational_facts(_app_db(tmp / "v"), UNIVERSE)
    # Same store for live and stage: no pending swap to disprove, which is exactly the
    # watchdog's situation. Anything else would compare two different questions.
    failures, report = verifier.verify_staging(
        store, store, UNIVERSE, evidence=evidence, operational=operational
    )
    return failures, report["per_name"]["classification"]


def test_both_components_reach_the_same_verdict_on_one_input(tmp_path, monkeypatch, capsys):
    (tmp_path / "v").mkdir()
    (tmp_path / "w").mkdir()

    _, classification = _verifier_classification(tmp_path)
    out = _watchdog_output(tmp_path / "w", monkeypatch, capsys)

    metric = re.search(
        r"METRIC universe=(\d+) assessable=(\d+) attributed=(\d+) covered=(\d+) "
        r"coverage=([\d.]+) raw_coverage=([\d.]+) unexplained=(\d+)",
        out,
    )
    assert metric, out

    # Same populations.
    assert int(metric.group(3)) == classification["attributed_count"], out
    assert int(metric.group(7)) == classification["failed_or_unexplained_count"], out
    assert int(metric.group(2)) == classification["assessable_count"], out
    # Same gating figure, to the precision the watchdog prints.
    assert float(metric.group(5)) == pytest.approx(classification["gating_coverage"], abs=5e-5)
    # ...and the same honest figure alongside it.
    assert float(metric.group(6)) == pytest.approx(
        classification["raw_freshness_coverage"], abs=5e-5
    )


def test_both_components_agree_on_WHICH_symbols_were_attributed(tmp_path, monkeypatch, capsys):
    (tmp_path / "v").mkdir()
    (tmp_path / "w").mkdir()

    _, classification = _verifier_classification(tmp_path)
    out = _watchdog_output(tmp_path / "w", monkeypatch, capsys)

    # Counts can coincide while the sets differ; the sets are the real claim.
    assert set(classification["provider_not_covered_symbols"]) == {"UUP", "KMLM"}
    assert set(classification["provider_exhausted_symbols"]) == {"SATS"}
    assert set(classification["failed_or_unexplained_symbols"]) == {"ZZZZ"}
    # The watchdog names the unadjudicated one in its problem line.
    assert "ZZZZ" in out
    assert "DATA_UNADJUDICATED_STALE" in out
    for attributed in ("UUP", "KMLM", "SATS"):
        assert f"e.g. {attributed}" not in out, f"{attributed} was adjudicated, not reported stale"


def test_both_components_fail_together_when_the_evidence_is_withdrawn(
    tmp_path, monkeypatch, capsys
):
    """The conformance that matters most: they must agree on FAILURE too, not just on the
    happy path. With no evidence, every non-fresh name is unexplained on both sides."""
    (tmp_path / "v").mkdir()
    (tmp_path / "w").mkdir()

    global RECORDS
    saved = RECORDS
    try:
        RECORDS = []
        failures, classification = _verifier_classification(tmp_path)
        out = _watchdog_output(tmp_path / "w", monkeypatch, capsys)
    finally:
        RECORDS = saved

    assert classification["attributed_count"] == 0
    assert classification["failed_or_unexplained_count"] == 4  # UUP KMLM SATS ZZZZ
    assert any("per-name coverage" in f for f in failures)
    assert "PROBLEM DATA_PER_NAME_COVERAGE" in out
    metric = re.search(r"attributed=(\d+) covered=\d+ coverage=([\d.]+)", out)
    assert int(metric.group(1)) == 0
    assert float(metric.group(2)) == pytest.approx(classification["gating_coverage"], abs=5e-5)
