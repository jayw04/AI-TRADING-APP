"""Range calibration report — banding / funnel / P&L math (offline, synthetic sqlite).

Builds a minimal DB with the columns the report's SQL reads (audit_log, orders, fills, signals,
symbols), seeds a 2-day scenario (a win, a loss, a selected-but-not-triggered name, and a filled-
but-unexited hold), and asserts the per-band aggregation, the conversion funnel, and Selection
Precision. No app deps — the report is stdlib + raw SQL.
"""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "range_calibration_report.py"
_spec = importlib.util.spec_from_file_location("range_calibration_report", _SCRIPT)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)


def _seed(path: Path) -> None:
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE audit_log (id INTEGER PRIMARY KEY, action TEXT, target_id TEXT,
                                ts TEXT, payload_json TEXT);
        CREATE TABLE symbols (id INTEGER PRIMARY KEY, ticker TEXT);
        CREATE TABLE orders (id INTEGER PRIMARY KEY, side TEXT, source_type TEXT,
                             source_id TEXT, symbol_id INTEGER);
        CREATE TABLE fills (id INTEGER PRIMARY KEY, order_id INTEGER, qty REAL, price REAL,
                            commission REAL, filled_at TEXT);
        CREATE TABLE signals (id INTEGER PRIMARY KEY, strategy_id INTEGER, type TEXT,
                              symbol_id INTEGER, received_at TEXT);
        """
    )
    con.executemany("INSERT INTO symbols VALUES (?,?)",
                    [(10, "NVDA"), (11, "MU"), (12, "INTC")])

    def sel(day, items, qualified):
        selected = [{"symbol": s, "score": sc, "rank": i + 1, "win_rate": None,
                     "backtested": False} for i, (s, sc) in enumerate(items)]
        payload = {"source": "daily_preopen_auto_select",
                   "changed": {"symbols": [s for s, _ in items]},
                   "selection": {"universe_size": 18, "qualified_size": qualified,
                                 "n_requested": 5, "min_score": 0.0, "selected": selected}}
        import json
        return (None, "STRATEGY_UPDATED", "1", f"{day} 13:00:00.000000", json.dumps(payload))

    con.executemany(
        "INSERT INTO audit_log (id, action, target_id, ts, payload_json) VALUES (?,?,?,?,?)",
        [
            sel("2026-06-29", [("NVDA", 0.033), ("MU", 0.078), ("INTC", 0.072)], 6),
            sel("2026-06-30", [("NVDA", 0.040), ("MU", 0.080)], 5),
        ],
    )

    # orders + fills: NVDA d1 win (round-trip +48), MU d1 loss (-10), NVDA d2 filled-not-exited
    con.executemany("INSERT INTO orders VALUES (?,?,?,?,?)", [
        (1, "BUY", "STRATEGY", "1", 10), (2, "SELL", "STRATEGY", "1", 10),   # NVDA d1
        (3, "BUY", "STRATEGY", "1", 11), (4, "SELL", "STRATEGY", "1", 11),   # MU d1
        (5, "BUY", "STRATEGY", "1", 10),                                      # NVDA d2 (no exit)
    ])
    con.executemany("INSERT INTO fills VALUES (?,?,?,?,?,?)", [
        (1, 1, 10, 100.0, 1.0, "2026-06-29 14:00:00"),   # NVDA buy
        (2, 2, 10, 105.0, 1.0, "2026-06-29 15:30:00"),   # NVDA sell -> +48 net of $2 comm
        (3, 3, 5, 50.0, 0.0, "2026-06-29 14:10:00"),     # MU buy
        (4, 4, 5, 48.0, 0.0, "2026-06-29 15:40:00"),     # MU sell -> -10
        (5, 5, 10, 100.0, 0.0, "2026-06-30 14:00:00"),   # NVDA d2 buy only (net_qty=10)
    ])
    # ENTRY signals: NVDA d1, MU d1, NVDA d2 triggered; INTC d1 + MU d2 NOT triggered
    con.executemany("INSERT INTO signals VALUES (?,?,?,?,?)", [
        (1, 1, "ENTRY", 10, "2026-06-29 13:35:00"),
        (2, 1, "ENTRY", 11, "2026-06-29 13:40:00"),
        (3, 1, "ENTRY", 10, "2026-06-30 13:35:00"),
    ])
    con.commit()
    con.close()


def test_calibration_aggregation(tmp_path):
    db = tmp_path / "cal.sqlite"
    _seed(db)
    con = sqlite3.connect(db)
    data = _mod.gather(con, 1)
    con.close()
    agg = _mod.aggregate(data, _mod.DEFAULT_BANDS)

    assert agg["n_selections"] == 5 and agg["n_days"] == 2
    # funnel: qualified 6+5=11; 5 selected; 3 triggered; 3 filled; 2 exited (NVDA d2 still held)
    assert agg["funnel"] == {"qualified": 11, "selected": 5, "triggered": 3, "filled": 3, "exited": 2}
    assert abs(agg["selection_precision"] - 0.6) < 1e-9   # 3/5

    by = {b["band"]: b for b in agg["bands"]}
    # NVDA d1 score 0.033 -> [0.02,0.04): win, +48
    b1 = by["0.02-0.04"]
    assert b1["n_selected"] == 1 and b1["n_exited"] == 1
    assert b1["win_rate"] == 1.0 and abs(b1["avg_pnl"] - 48.0) < 1e-9
    # MU d1 (0.078) + INTC d1 (0.072) -> [0.06,0.08): 2 selected, 1 triggered, 1 exit, loss
    b3 = by["0.06-0.08"]
    assert b3["n_selected"] == 2 and abs(b3["trigger_rate"] - 0.5) < 1e-9
    assert b3["n_exited"] == 1 and b3["win_rate"] == 0.0 and abs(b3["avg_pnl"] + 10.0) < 1e-9
    # NVDA d2 (0.04) -> [0.04,0.06): filled but not exited -> no win_rate/avg_pnl
    b2 = by["0.04-0.06"]
    assert b2["n_filled"] == 1 and b2["n_exited"] == 0
    assert b2["win_rate"] is None and b2["avg_pnl"] is None

    # render must not crash and reflects the funnel
    md = _mod.render(agg, 1, str(db), _mod.DEFAULT_BANDS)
    assert "Opportunity Conversion funnel" in md and "Selection Precision" in md


def test_empty_db_is_graceful(tmp_path):
    db = tmp_path / "empty.sqlite"
    _seed(db)
    con = sqlite3.connect(db)
    # wipe selections -> no auto-select rows
    con.execute("DELETE FROM audit_log")
    con.commit()
    data = _mod.gather(con, 1)
    con.close()
    agg = _mod.aggregate(data, _mod.DEFAULT_BANDS)
    assert agg["n_selections"] == 0 and agg["selection_precision"] is None
    md = _mod.render(agg, 1, str(db), _mod.DEFAULT_BANDS)
    assert "No selections have accrued yet" in md
