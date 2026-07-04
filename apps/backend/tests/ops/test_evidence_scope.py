"""Per-account evidence scoping — the resolver + the scoped confidence/KPI builds.

Seeds a minimal read-model DB with two live books (a mature clean acct 1 + a brand-new acct 7) and an
IDLE strategy, then checks: (a) the resolver maps strategy → (user, account), (b) `paper_strategy_ids`
excludes IDLE, (c) the confidence/KPI `build()`s scope by account/user (and keep replay global).
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

from app.ops.evidence_scope import paper_strategy_ids, resolve_paper_account
from scripts.confidence_score import build as confidence_build
from scripts.ops_kpis import build as kpis_build


def _seed(path: str) -> None:
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE strategies (id INTEGER, user_id INTEGER, status TEXT);
        CREATE TABLE accounts (id INTEGER, user_id INTEGER, broker TEXT, mode TEXT);
        CREATE TABLE equity_snapshots (account_id INTEGER, ts TEXT, equity REAL);
        CREATE TABLE audit_log (user_id INTEGER, action TEXT, ts TEXT);
        CREATE TABLE reconciliation_runs (account_id INTEGER, result TEXT, n_discrepancies INTEGER);
        CREATE TABLE replay_runs (n_mismatched INTEGER, n_checked INTEGER, n_matched INTEGER);
        CREATE TABLE orders (account_id INTEGER, source_type TEXT, created_at TEXT);
        """
    )
    # two PAPER books (2→user1→acct1, 9→user7→acct7) + one IDLE (3→user2, no account).
    con.executemany("INSERT INTO strategies VALUES (?,?,?)",
                    [(2, 1, "PAPER"), (9, 7, "PAPER"), (3, 2, "IDLE")])
    con.executemany("INSERT INTO accounts VALUES (?,?,?,?)",
                    [(1, 1, "alpaca", "paper"), (7, 7, "alpaca", "paper")])

    now = datetime.now(UTC)
    # acct 1: 30 daily snapshots (mature); acct 7: 2 (brand new).
    for i in range(30):
        con.execute("INSERT INTO equity_snapshots VALUES (?,?,?)",
                    (1, (now - timedelta(days=29 - i)).isoformat(), 100_000 + i))
    for i in range(2):
        con.execute("INSERT INTO equity_snapshots VALUES (?,?,?)",
                    (7, (now - timedelta(days=1 - i)).isoformat(), 100_000 + i))

    # user 1: lots of clean risk-passed orders; user 7: just a couple.
    con.executemany("INSERT INTO audit_log VALUES (?,?,?)",
                    [(1, "ORDER_RISK_PASSED", now.isoformat()) for _ in range(20)]
                    + [(7, "ORDER_RISK_PASSED", now.isoformat()) for _ in range(2)])
    # reconciliation: acct 1 has clean passes; acct 7 none.
    con.executemany("INSERT INTO reconciliation_runs VALUES (?,?,?)",
                    [(1, "pass", 0) for _ in range(10)])
    con.execute("INSERT INTO replay_runs VALUES (0, 100, 100)")  # global, clean
    con.execute("INSERT INTO orders VALUES (?,?,?)",
                (1, "STRATEGY", (now - timedelta(days=29)).isoformat()))
    con.commit()
    con.close()


def test_resolver_and_paper_ids(tmp_path):
    db = str(tmp_path / "wb.sqlite")
    _seed(db)
    con = sqlite3.connect(db)
    try:
        assert paper_strategy_ids(con) == [2, 9]              # IDLE strategy 3 excluded
        assert resolve_paper_account(con, 2) == (1, 1)
        assert resolve_paper_account(con, 9) == (7, 7)
        assert resolve_paper_account(con, 3) == (2, None)     # user has no paper account
        assert resolve_paper_account(con, 999) == (None, None)  # unknown strategy
    finally:
        con.close()


def test_confidence_scopes_by_account_and_user(tmp_path):
    db = str(tmp_path / "wb.sqlite")
    _seed(db)
    acct1 = confidence_build(db, account_id=1, user_id=1)
    acct7 = confidence_build(db, account_id=7, user_id=7)
    platform = confidence_build(db)

    # maturity: acct 1 (30 snapshots) has a longer track record than acct 7 (2).
    assert acct1["signals"]["track_record_days"] > acct7["signals"]["track_record_days"]
    # safety scopes by user: acct 1's user passed 20 orders, acct 7's user 2.
    assert acct1["signals"]["orders_risk_passed"] == 20
    assert acct7["signals"]["orders_risk_passed"] == 2
    assert platform["signals"]["orders_risk_passed"] == 22        # global sees both
    # reconciliation scopes by account: acct 1 has 10 runs, acct 7 none.
    assert acct1["signals"]["reconciliation_runs"] == 10
    assert acct7["signals"]["reconciliation_runs"] == 0
    # scope tag is set for per-account, absent-kind for platform.
    assert acct1["scope"]["kind"] == "account" and acct1["scope"]["account_id"] == 1
    assert platform["scope"]["kind"] == "platform"


def test_kpis_scope_by_account_replay_stays_global(tmp_path):
    db = str(tmp_path / "wb.sqlite")
    _seed(db)
    acct1 = kpis_build(db, account_id=1, user_id=1)
    acct7 = kpis_build(db, account_id=7, user_id=7)

    def _kpi(rows, key):
        return next(r for r in rows if r["key"] == key)

    # reconciliation success: acct 1 has runs → a real value; acct 7 has none → n/a.
    assert _kpi(acct1["kpis"], "reconciliation_success")["value"] is not None
    assert _kpi(acct7["kpis"], "reconciliation_success")["status"] == "n_a"
    # replay is a platform property — both scoped builds see the same (clean) replay result.
    r1 = _kpi(acct1["kpis"], "replay_consistency")["value"]
    r7 = _kpi(acct7["kpis"], "replay_consistency")["value"]
    assert r1 == r7
