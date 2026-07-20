"""MR-002 validation/OOS evaluator — Increment 2 qualification tests (synthetic ONLY).

Frozen cost model + next-open execution + synthetic trade ledger. Expected values are hand-derived by
direct arithmetic (NOT by calling the implementation under test). Reads NO real dataset; no signal
generation, universe reconstruction, sector mapping, portfolio optimization, or exposure constraints.
Run: apps/backend/.venv/Scripts/python.exe -m pytest test_increment2.py -v
"""

from __future__ import annotations


import pytest

import mr002_valoos_costmodel as C
import mr002_valoos_execution as X
import mr002_valoos_report as R
from mr002_valoos_execution import Market, TradeIntent, simulate_position, simulate_sequence

DEP_LOCK_SHA = "0" * 64
CODE_ID = {"module": "increment2-v1.0"}


def _flat_market(sessions=range(0, 9), price=100.0, nav=1e12, adv=1e12, overrides=None):
    opens = {s: price for s in sessions}
    if overrides:
        opens.update(overrides)
    return Market(opens=opens, adv_dollars={s: adv for s in sessions}, nav=nav)


# ── 1. long round trip, exact base costs ────────────────────────────────────────────────────────
def test_01_long_round_trip_exact_base_costs():
    # decision t=0 -> entry open s1 (100); explicit exit decision s5 -> exit open s6 (110)
    mkt = _flat_market(overrides={6: 110.0})
    r = simulate_position(TradeIntent("T1", "AAA", "long", "P1", 0, 100, exit_decision_session=5), mkt, C.BASE)
    p = r["position"]
    gross = (110.0 - 100.0) * 100                      # 1000
    entry_comm = 100.0 * 100 * 10 / 10000              # 10.0
    exit_comm = 110.0 * 100 * 10 / 10000               # 11.0
    assert p["gross_pnl"] == pytest.approx(gross)
    assert p["entry_commission"] == pytest.approx(entry_comm)
    assert p["exit_commission"] == pytest.approx(exit_comm)
    assert p["borrow_cost"] == 0.0
    assert p["net_pnl"] == pytest.approx(gross - entry_comm - exit_comm)   # 979.0


# ── 2. short round trip with daily borrow ─────────────────────────────────────────────────────────
def test_02_short_round_trip_with_borrow():
    mkt = _flat_market(overrides={6: 110.0})
    r = simulate_position(TradeIntent("T2", "BBB", "short", "P2", 0, 100), mkt, C.BASE)  # time-stop s6
    p = r["position"]
    days = 6 - 1                                        # entry s1, exit s6
    gross = (110.0 - 100.0) * 100 * -1.0               # -1000
    borrow = (100.0 * 100) * (50 / 10000) * (days / 360)
    assert p["days_held"] == days
    assert p["gross_pnl"] == pytest.approx(gross)
    assert p["borrow_cost"] == pytest.approx(borrow)
    assert p["net_pnl"] == pytest.approx(gross - 10.0 - 11.0 - borrow)


# ── 3. mandatory cost-stress recomputation ───────────────────────────────────────────────────────
def test_03_cost_stress_recompute():
    mkt = _flat_market(overrides={6: 110.0})
    p = simulate_position(TradeIntent("T3", "AAA", "long", "P3", 0, 100, exit_decision_session=5), mkt)["position"]
    stress = X.recompute_position_under_schedule(p, C.STRESS)
    # 20 bps/side: entry 20.0, exit 22.0; gross unchanged 1000
    assert stress["entry_commission"] == pytest.approx(100.0 * 100 * 20 / 10000)
    assert stress["net_pnl"] == pytest.approx(1000.0 - 20.0 - 22.0)
    assert stress["classification"] == "GATE" and stress["reconciles"] is True


# ── 4. severe-cost diagnostic isolated from verdict ──────────────────────────────────────────────
def test_04_severe_cost_is_diagnostic():
    mkt = _flat_market(overrides={6: 110.0})
    p = simulate_position(TradeIntent("T4", "AAA", "long", "P4", 0, 100, exit_decision_session=5), mkt)["position"]
    severe = X.recompute_position_under_schedule(p, C.SEVERE)
    assert severe["classification"] == "DIAGNOSTIC"       # reported, never gated
    assert C.SEVERE.commission_slippage_bps_per_side == 30.0 and C.SEVERE.borrow_bps_per_year == 1000.0


# ── 5. entry at t+1 ───────────────────────────────────────────────────────────────────────────────
def test_05_entry_at_t_plus_1():
    mkt = _flat_market(overrides={6: 110.0})
    r = simulate_position(TradeIntent("T5", "AAA", "long", "P5", 0, 100, exit_decision_session=5), mkt)
    entry = r["events"][0]
    assert entry["event_type"] == "ENTRY_FILL"
    assert entry["decision_session"] == 0 and entry["actual_execution_session"] == 1


# ── 6. time exit at open of session 6 ─────────────────────────────────────────────────────────────
def test_06_time_stop_at_session_6():
    mkt = _flat_market(overrides={6: 110.0})
    r = simulate_position(TradeIntent("T6", "AAA", "long", "P6", 0, 100), mkt)  # no explicit exit
    exit_ev = r["events"][-1]
    assert exit_ev["event_type"] == "EXIT_FILL" and exit_ev["actual_execution_session"] == 6
    assert exit_ev["reason"] == "TIME_STOP"


# ── 7. missing entry open cancellation ────────────────────────────────────────────────────────────
def test_07_missing_entry_open_cancels():
    mkt = Market(opens={0: 100.0, 2: 100.0, 3: 100.0}, adv_dollars={s: 1e12 for s in range(0, 4)}, nav=1e12)
    r = simulate_position(TradeIntent("T7", "AAA", "long", "P7", 0, 100), mkt)  # entry s1 missing
    assert r["disposition"] == "CANCELLED" and r["position"] is None
    assert r["events"][0]["event_type"] == "ENTRY_CANCELLED"
    assert r["events"][0]["reason"] == "MISSING_ENTRY_OPEN"


# ── 8. missing exit open deferral ─────────────────────────────────────────────────────────────────
def test_08_missing_exit_open_defers():
    mkt = _flat_market(sessions=range(0, 9), overrides={6: None, 7: 120.0})  # time-stop s6 absent -> s7
    mkt.opens.pop(6)
    r = simulate_position(TradeIntent("T8", "AAA", "long", "P8", 0, 100), mkt)
    exit_ev = r["events"][-1]
    assert exit_ev["event_type"] == "EXIT_FILL" and exit_ev["actual_execution_session"] == 7
    assert "DEFERRED_FROM_6" in exit_ev["reason"]
    assert r["position"]["days_held"] == 7 - 1


def test_08b_missing_exit_open_no_future_open_pends():
    mkt = Market(opens={0: 100.0, 1: 100.0}, adv_dollars={s: 1e12 for s in range(0, 2)}, nav=1e12)
    r = simulate_position(TradeIntent("T8b", "AAA", "long", "P8b", 0, 100), mkt)
    assert r["disposition"] == "PENDING" and r["events"][-1]["event_type"] == "EXIT_PENDING"
    assert "PENDING_NO_OPEN" in r["events"][-1]["reason"]


# ── 9. 2% ADV clipping ────────────────────────────────────────────────────────────────────────────
def test_09_adv_participation_clip():
    # 2% of 500,000 = 10,000 dollars / 100 = 100 shares max, desired 250
    mkt = Market(opens={s: 100.0 for s in range(0, 9)}, adv_dollars={1: 500000.0}, nav=1e12)
    mkt.opens[6] = 110.0
    r = simulate_position(TradeIntent("T9", "AAA", "long", "P9", 0, 250, exit_decision_session=5), mkt)
    assert r["position"]["shares"] == 100
    assert "CLIPPED_150_SHARES_TO_CASH" in r["events"][0]["reason"]


# ── 10. 1.5% NAV clipping ─────────────────────────────────────────────────────────────────────────
def test_10_nav_new_entry_clip():
    # 1.5% of 1,000,000 = 15,000 / 100 = 150 shares max, desired 250, ADV unbounded
    mkt = _flat_market(nav=1_000_000.0, overrides={6: 110.0})
    r = simulate_position(TradeIntent("T10", "AAA", "long", "P10", 0, 250, exit_decision_session=5), mkt)
    assert r["position"]["shares"] == 150
    assert "CLIPPED_100_SHARES_TO_CASH" in r["events"][0]["reason"]


# ── 11. clip never delays: no residual order for the clipped quantity ─────────────────────────────
def test_11_clip_never_delay_no_residual():
    mkt = _flat_market(nav=1_000_000.0, overrides={6: 110.0})
    r = simulate_position(TradeIntent("T11", "AAA", "long", "P11", 0, 250, exit_decision_session=5), mkt)
    entry_fills = [e for e in r["events"] if e["event_type"] == "ENTRY_FILL"]
    assert len(entry_fills) == 1                          # the clipped 100 is dropped to cash, not re-tried
    assert all(e["event_type"] != "ENTRY_RESIDUAL" for e in r["events"])


# ── 12. no same-open re-entry ─────────────────────────────────────────────────────────────────────
def test_12_no_same_open_reentry():
    mkt = _flat_market(sessions=range(0, 12), overrides={6: 110.0})
    a = TradeIntent("A", "AAA", "long", "PA", 0, 100)                    # entry s1, time-stop exit s6
    b = TradeIntent("B", "AAA", "long", "PB", 5, 100)                    # entry would fill s6 == A exit
    seq = simulate_sequence([a, b], mkt)
    refused = [e for e in seq["events"] if e["event_type"] == "ENTRY_REFUSED_SAME_OPEN"]
    assert len(refused) == 1 and refused[0]["reason"] == "NO_SAME_OPEN_REENTRY"
    assert len(seq["positions"]) == 1                     # only A established


# ── 13. deterministic ledger and report hashes ───────────────────────────────────────────────────
def _sample_ledger():
    mkt = _flat_market(overrides={6: 110.0})
    seq = simulate_sequence([TradeIntent("T", "AAA", "long", "P", 0, 100, exit_decision_session=5)], mkt)
    p = seq["positions"][0]
    stress = X.recompute_position_under_schedule(p, C.STRESS)
    severe = X.recompute_position_under_schedule(p, C.SEVERE)
    return X.ledger_report(events=seq["events"], positions=seq["positions"], base_schedule="BASE",
                           stress=stress, severe=severe, code_identity=CODE_ID,
                           dependency_lock_sha256=DEP_LOCK_SHA)


def test_13_deterministic_ledger_report_hash():
    r1, r2 = _sample_ledger(), _sample_ledger()
    assert r1["output_hash"] == r2["output_hash"]
    assert X.ledger_report_hash(r1) == r1["output_hash"]
    assert r1["validation_data_read"] is False and r1["synthetic_fixture_only"] is True


# ── 14. signed-zero preserved and non-finite refusal ─────────────────────────────────────────────
def test_14_signed_zero_gross_preserved():
    # short with exit == entry -> gross = (0.0)*shares*(-1.0) = -0.0
    mkt = _flat_market(overrides={6: 100.0})
    r = simulate_position(TradeIntent("T14", "AAA", "short", "P14", 0, 100), mkt)
    gross = r["position"]["gross_pnl"]
    assert R.encode_float(gross)["exact_hex"] == "-0x0.0p+0"
    # the exact-hex survives canonical serialization in the ledger report
    rep = X.ledger_report(events=r["events"], positions=[r["position"]], base_schedule="BASE",
                          stress=None, severe=None, code_identity=CODE_ID, dependency_lock_sha256=DEP_LOCK_SHA)
    assert rep["positions"][0]["gross_pnl"]["exact_hex"] == "-0x0.0p+0"


def test_14b_nonfinite_price_refuses():
    mkt = _flat_market(overrides={6: float("inf")})
    with pytest.raises(X.ExecIntegrityStop, match="EXEC_PRICE_NONFINITE"):
        simulate_position(TradeIntent("T14b", "AAA", "long", "P14b", 0, 100), mkt)
    mkt2 = _flat_market(overrides={1: -5.0})
    with pytest.raises(X.ExecIntegrityStop, match="EXEC_PRICE_NONPOSITIVE"):
        simulate_position(TradeIntent("T14c", "AAA", "long", "P14c", 0, 100), mkt2)


def test_14c_nonfinite_in_report_refuses():
    with pytest.raises(R.CanonicalizationError, match="NONFINITE_FLOAT"):
        X.ledger_report(events=[{"x": float("nan")}], positions=[], base_schedule="BASE",
                        stress=None, severe=None, code_identity=CODE_ID, dependency_lock_sha256=DEP_LOCK_SHA)


# ── 15. reconciliation gross - costs = net ────────────────────────────────────────────────────────
def test_15_reconciliation_long_and_short():
    mkt = _flat_market(overrides={6: 110.0})
    for side in ("long", "short"):
        p = simulate_position(TradeIntent(f"R{side}", "AAA", side, f"PR{side}", 0, 100), mkt)["position"]
        assert p["reconciles"] is True
        assert p["net_pnl"] == pytest.approx(p["gross_pnl"] - p["total_costs"])
        for sched in (C.STRESS, C.SEVERE):
            rc = X.recompute_position_under_schedule(p, sched)
            assert rc["net_pnl"] == pytest.approx(rc["gross_pnl"] - rc["total_costs"])


# ── cost-model primitive edges ───────────────────────────────────────────────────────────────────
def test_16_cost_primitive_edges():
    assert C.commission_slippage_cost(0.0, C.BASE) == 0.0
    with pytest.raises(C.CostIntegrityStop, match="COST_NEGATIVE_NOTIONAL"):
        C.commission_slippage_cost(-1.0, C.BASE)
    with pytest.raises(C.CostIntegrityStop, match="BORROW_NEGATIVE_DAYS"):
        C.borrow_cost(1000.0, -1, C.BASE, is_short=True)
    with pytest.raises(C.CostIntegrityStop, match="BORROW_LONG_SIDE"):
        C.borrow_cost(1000.0, 5, C.BASE, is_short=False)
    assert C.borrow_cost(0.0, 0, C.BASE, is_short=False) == 0.0


def test_17_costs_from_executed_not_intended_notional():
    # desired 250 clipped to 150 -> commission keyed to EXECUTED 150*price, not intended 250*price
    mkt = _flat_market(nav=1_000_000.0, overrides={6: 110.0})
    p = simulate_position(TradeIntent("T17", "AAA", "long", "P17", 0, 250, exit_decision_session=5), mkt)["position"]
    assert p["entry_commission"] == pytest.approx(150 * 100.0 * 10 / 10000)   # executed 150, not 250
    assert p["entry_notional"] == pytest.approx(150 * 100.0)


def test_18_invalid_side_and_shares_refuse():
    mkt = _flat_market()
    with pytest.raises(X.ExecIntegrityStop, match="EXEC_INVALID_SIDE"):
        simulate_position(TradeIntent("T18", "AAA", "flat", "P18", 0, 100), mkt)
    with pytest.raises(X.ExecIntegrityStop, match="EXEC_INVALID_SHARES"):
        simulate_position(TradeIntent("T18b", "AAA", "long", "P18b", 0, 0), mkt)


def test_19_event_has_16_frozen_fields():
    mkt = _flat_market(overrides={6: 110.0})
    r = simulate_position(TradeIntent("T19", "AAA", "long", "P19", 0, 100, exit_decision_session=5), mkt)
    for e in r["events"]:
        assert tuple(e.keys()) == X.EVENT_FIELDS
    assert len(X.EVENT_FIELDS) == 16
