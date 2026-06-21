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
        CREATE TABLE audit_log (ts TEXT, action TEXT, actor_type TEXT,
                                target_type TEXT, target_id TEXT);
        CREATE TABLE equity_snapshots (ts TEXT, account_id INT, equity REAL);
        CREATE TABLE reconciliation_runs (ran_at TEXT, result TEXT, n_checked INT,
                                          n_discrepancies INT);
        CREATE TABLE replay_runs (ran_at TEXT, n_checked INT, n_matched INT, n_mismatched INT);
        CREATE TABLE strategies (id INT, name TEXT, version TEXT, status TEXT, params_json TEXT);
        """
    )
    audit = [
        # June (in-window)
        ("2026-06-05 10:00:00.0", "ORDER_RISK_PASSED", "USER", "order", "1"),
        ("2026-06-05 10:00:01.0", "ORDER_RISK_PASSED", "USER", "order", "2"),
        ("2026-06-06 11:00:00.0", "ORDER_REJECTED_BY_RISK", "STRATEGY", "order", "3"),
        ("2026-06-11 21:59:29.0", "ORDER_REJECTED_BY_BROKER", "STRATEGY", "order", "4"),
        ("2026-06-15 14:50:16.0", "CIRCUIT_BREAKER_TRIPPED", "SYSTEM", "account", "1"),
        ("2026-06-15 15:10:00.0", "CIRCUIT_BREAKER_RESET", "USER", "account", "1"),
        ("2026-06-15 14:47:59.0", "STRATEGY_UPDATED", "USER", "strategy", "2"),
        ("2026-06-15 02:02:02.0", "STRATEGY_REGISTERED", "SYSTEM", "strategy", "2"),
        ("2026-06-16 02:02:02.0", "STRATEGY_REGISTERED", "SYSTEM", "strategy", "2"),
        ("2026-06-17 02:02:02.0", "STRATEGY_REGISTERED", "SYSTEM", "strategy", "2"),
        # May (out of the June window — must be excluded)
        ("2026-05-21 20:58:56.0", "ORDER_REJECTED_BY_RISK", "STRATEGY", "order", "9"),
        ("2026-05-21 20:58:57.0", "ORDER_RISK_PASSED", "USER", "order", "8"),
    ]
    con.executemany("INSERT INTO audit_log VALUES (?,?,?,?,?)", audit)
    eq = [(f"2026-06-{2 + i:02d} 16:10:00.0", 1, 100000.0 + i * 500) for i in range(equity_days)]
    con.executemany("INSERT INTO equity_snapshots VALUES (?,?,?)", eq)
    con.executemany(
        "INSERT INTO reconciliation_runs VALUES (?,?,?,?)",
        [("2026-06-10 03:30:00.0", "pass", 4, 0), ("2026-06-20 03:30:00.0", "pass", 4, 0)],
    )
    con.executemany("INSERT INTO replay_runs VALUES (?,?,?,?)",
                    [("2026-06-12 03:30:00.0", 5, 5, 0)])
    con.execute("INSERT INTO strategies VALUES (?,?,?,?,?)",
                (2, "momentum-portfolio", "0.3.0", "PAPER", '{"use_daily_overlay": true,'
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
