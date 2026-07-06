"""P12.5 monthly evidence report — month-window aggregation + incident classification (offline)."""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "monthly_evidence.py"
_spec = importlib.util.spec_from_file_location("monthly_evidence", _SCRIPT)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)
build = _mod.build
month_bounds = _mod._month_bounds


def _make_db(path: Path, *, equity_days: int = 3) -> str:
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
        """
    )
    # Book under test = strategy 2 / user 1 / paper account 1. Noise rows belong to
    # another book (user 99 / account 2) and MUST be excluded by the per-profile scoping.
    con.executemany("INSERT INTO accounts VALUES (?,?,?,?)",
                    [(1, 1, "alpaca", "paper"), (2, 99, "alpaca", "paper")])
    audit = [
        # June, user 1 (in-window, our book)
        ("2026-06-05 10:00:00.0", 1, "ORDER_RISK_PASSED", "USER", "order", "1"),
        ("2026-06-05 10:00:01.0", 1, "ORDER_RISK_PASSED", "USER", "order", "2"),
        ("2026-06-06 11:00:00.0", 1, "ORDER_REJECTED_BY_RISK", "STRATEGY", "order", "3"),
        ("2026-06-11 21:59:29.0", 1, "ORDER_REJECTED_BY_BROKER", "STRATEGY", "order", "4"),
        ("2026-06-15 14:50:16.0", 1, "CIRCUIT_BREAKER_TRIPPED", "SYSTEM", "account", "1"),
        ("2026-06-15 15:10:00.0", 1, "CIRCUIT_BREAKER_RESET", "USER", "account", "1"),
        ("2026-06-15 14:47:59.0", 1, "STRATEGY_UPDATED", "USER", "strategy", "2"),
        ("2026-06-15 02:02:02.0", 1, "STRATEGY_REGISTERED", "SYSTEM", "strategy", "2"),
        ("2026-06-16 02:02:02.0", 1, "STRATEGY_REGISTERED", "SYSTEM", "strategy", "2"),
        ("2026-06-17 02:02:02.0", 1, "STRATEGY_REGISTERED", "SYSTEM", "strategy", "2"),
        # May, user 1 (out of the June window — must be excluded)
        ("2026-05-21 20:58:56.0", 1, "ORDER_REJECTED_BY_RISK", "STRATEGY", "order", "9"),
        ("2026-05-21 20:58:57.0", 1, "ORDER_RISK_PASSED", "USER", "order", "8"),
        # June, user 99 — ANOTHER book; must be excluded by user scoping (else passed=3).
        ("2026-06-07 10:00:00.0", 99, "ORDER_RISK_PASSED", "USER", "order", "77"),
        ("2026-06-07 10:00:01.0", 99, "CIRCUIT_BREAKER_TRIPPED", "SYSTEM", "account", "2"),
    ]
    con.executemany("INSERT INTO audit_log VALUES (?,?,?,?,?,?)", audit)
    eq = [(f"2026-06-{2 + i:02d} 16:10:00.0", 1, 100000.0 + i * 500) for i in range(equity_days)]
    eq.append(("2026-06-04 16:10:00.0", 2, 555555.0))  # account 2 noise — must be excluded
    con.executemany("INSERT INTO equity_snapshots VALUES (?,?,?)", eq)
    con.executemany(
        "INSERT INTO reconciliation_runs VALUES (?,?,?,?,?)",
        [("2026-06-10 03:30:00.0", 1, "pass", 4, 0), ("2026-06-20 03:30:00.0", 1, "pass", 4, 0),
         ("2026-06-12 03:30:00.0", 2, "fail", 4, 9)],  # account 2 noise — must be excluded
    )
    con.executemany("INSERT INTO replay_runs VALUES (?,?,?,?)",
                    [("2026-06-12 03:30:00.0", 5, 5, 0)])
    con.execute("INSERT INTO strategies VALUES (?,?,?,?,?,?)",
                (2, 1, "momentum-portfolio", "0.3.0", "PAPER", '{"use_daily_overlay": true,'
                 ' "vol_target_annual": 0.15}'))
    con.commit()
    con.close()
    return str(path)


def test_month_bounds():
    assert month_bounds("2026-06") == ("2026-06-01", "2026-06-30")
    assert month_bounds("2026-02") == ("2026-02-01", "2026-02-28")  # non-leap


def test_month_window_excludes_other_months(tmp_path):
    r = build(_make_db(tmp_path / "w.sqlite"), 2, "2026-06")
    # exclusion proven both ways: May's pass (would make passed=3) and May's reject (would make
    # rejected=2) are both dropped; only the June rows count.
    assert r["risk"]["orders_risk_passed"] == 2
    assert r["risk"]["orders_rejected_by_risk"] == 1
    assert r["risk"]["breaker_trips"] == 1
    assert r["risk"]["breaker_resets"] == 1


def test_incident_classification(tmp_path):
    r = build(_make_db(tmp_path / "i.sqlite"), 2, "2026-06")
    kinds = {i["kind"] for i in r["incidents"]}
    # breaker trip + broker reject ARE incidents; a risk rejection is NOT (it's the gate working)
    assert kinds == {"breaker", "broker_reject"}
    assert all(i["kind"] != "risk" for i in r["incidents"])
    assert r["recovery"]["recovered"] is True


def test_changes_exclude_boot_registrations(tmp_path):
    r = build(_make_db(tmp_path / "c.sqlite"), 2, "2026-06")
    actions = {c["action"] for c in r["changes"]}
    assert "STRATEGY_REGISTERED" not in actions
    assert "STRATEGY_UPDATED" in actions
    assert r["operations"]["strategy_reregistrations"] == 3  # summarized, not listed


def test_performance_computed_vs_accruing(tmp_path):
    full = build(_make_db(tmp_path / "p.sqlite", equity_days=3), 2, "2026-06")
    assert full["performance"]["status"] == "live curve"
    assert full["performance"]["n_days"] == 3
    assert "max_drawdown" in full["performance"] and "sharpe" in full["performance"]

    accruing = build(_make_db(tmp_path / "a.sqlite", equity_days=1), 2, "2026-06")
    assert accruing["performance"]["status"].startswith("accruing")


def test_verifiability_clean(tmp_path):
    r = build(_make_db(tmp_path / "v.sqlite"), 2, "2026-06")
    assert r["verifiability"]["clean"] is True
    assert r["verifiability"]["replay_consistency"] == 1.0
    # the rendered report contains every numbered section
    md = _mod._render(r)
    for n in range(1, 10):
        assert f"## {n}." in md


def test_scoping_excludes_other_books(tmp_path):
    """Per-profile scoping: the strategy-2 (user 1 / account 1) report MUST exclude the
    noise rows belonging to user 99 / account 2 — the bug this fix addresses (every book
    previously got the same global aggregate)."""
    r = build(_make_db(tmp_path / "scope.sqlite"), 2, "2026-06")
    assert r["strategy"]["user_id"] == 1 and r["strategy"]["account_id"] == 1
    # user-99's ORDER_RISK_PASSED + breaker trip are excluded -> still 2 passed / 1 trip.
    assert r["risk"]["orders_risk_passed"] == 2
    assert r["risk"]["breaker_trips"] == 1
    # account-2's $555,555 snapshot is excluded -> our curve starts at 100,000.
    assert r["performance"]["start_equity"] == 100000.0
    # account-2's FAILED reconciliation is excluded -> our book is clean.
    assert r["verifiability"]["clean"] is True
    assert r["verifiability"]["reconciliation_runs"] == 2


def test_unknown_strategy_yields_empty_scope(tmp_path):
    """A strategy with no resolvable account/user returns an empty (accruing / zero) report
    rather than leaking another book's data."""
    r = build(_make_db(tmp_path / "unk.sqlite"), 999, "2026-06")
    assert r["strategy"]["account_id"] is None and r["strategy"]["user_id"] is None
    assert r["performance"]["status"].startswith("accruing")
    assert r["risk"]["orders_risk_passed"] == 0
    assert r["verifiability"]["reconciliation_runs"] == 0
