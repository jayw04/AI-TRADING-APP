"""MR-002 validation/OOS evaluator — Increment 2 qualification tests (synthetic ONLY; hardened v1.1).

Frozen cost model + next-open execution + synthetic trade ledger. Expected values are hand-derived by
direct arithmetic (NOT by calling the implementation under test). Reads NO real dataset; no signal
generation, universe reconstruction, sector mapping, portfolio optimization, or exposure constraints.
Run: apps/backend/.venv/Scripts/python.exe -m pytest test_increment2.py -v
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

import mr002_valoos_costmodel as C
import mr002_valoos_execution as X
import mr002_valoos_report as R
from mr002_valoos_execution import Market, TradeIntent, simulate_position, simulate_sequence

DEP_LOCK_SHA = "0" * 64
CODE_ID = {"module": "increment2-v1.1"}


def _flat_market(sessions=range(0, 9), price=100.0, nav=1e12, adv=1e12, overrides=None,
                 adv_overrides=None, date_base="2024-01-01"):
    opens = {s: price for s in sessions}
    if overrides:
        opens.update(overrides)
    adv_d = {s: adv for s in sessions}
    if adv_overrides:
        adv_d.update(adv_overrides)
    base = date.fromisoformat(date_base)
    dates = {s: (base + timedelta(days=s)).isoformat() for s in sessions}
    return Market(opens=opens, adv_dollars=adv_d, session_dates=dates, nav=nav)


# ── 1. long round trip, exact base costs ────────────────────────────────────────────────────────
def test_01_long_round_trip_exact_base_costs():
    mkt = _flat_market(overrides={6: 110.0})
    r = simulate_position(TradeIntent("T1", "AAA", "long", "P1", 0, 100, exit_decision_session=5), mkt, C.BASE)
    p = r["position"]
    gross, entry_comm, exit_comm = 1000.0, 10.0, 11.0
    assert p["gross_pnl"] == pytest.approx(gross)
    assert p["entry_commission"] == pytest.approx(entry_comm)
    assert p["exit_commission"] == pytest.approx(exit_comm)
    assert p["borrow_cost"] == 0.0
    assert p["net_pnl"] == pytest.approx(gross - entry_comm - exit_comm)   # 979.0


# ── 2. short round trip with daily borrow (calendar days) ────────────────────────────────────────
def test_02_short_round_trip_with_borrow():
    mkt = _flat_market(overrides={6: 110.0})            # 1 calendar day per session -> s1..s6 = 5 days
    r = simulate_position(TradeIntent("T2", "BBB", "short", "P2", 0, 100), mkt, C.BASE)  # time-stop s6
    p = r["position"]
    days = 5
    borrow = (100.0 * 100) * (50 / 10000) * (days / 360)
    assert p["borrow_calendar_days"] == days
    assert p["gross_pnl"] == pytest.approx(-1000.0)
    assert p["borrow_cost"] == pytest.approx(borrow)
    assert p["net_pnl"] == pytest.approx(-1000.0 - 10.0 - 11.0 - borrow)


# ── 3. mandatory cost-stress recomputation ───────────────────────────────────────────────────────
def test_03_cost_stress_recompute():
    mkt = _flat_market(overrides={6: 110.0})
    p = simulate_position(TradeIntent("T3", "AAA", "long", "P3", 0, 100, exit_decision_session=5), mkt)["position"]
    stress = X.recompute_position_under_schedule(p, C.STRESS)
    assert stress["entry_commission"] == pytest.approx(20.0)
    assert stress["net_pnl"] == pytest.approx(1000.0 - 20.0 - 22.0)
    assert stress["classification"] == "GATE" and stress["reconciles"] is True


# ── 4. severe-cost diagnostic isolated from verdict ──────────────────────────────────────────────
def test_04_severe_cost_is_diagnostic():
    mkt = _flat_market(overrides={6: 110.0})
    p = simulate_position(TradeIntent("T4", "AAA", "long", "P4", 0, 100, exit_decision_session=5), mkt)["position"]
    severe = X.recompute_position_under_schedule(p, C.SEVERE)
    assert severe["classification"] == "DIAGNOSTIC"
    assert C.SEVERE.commission_slippage_bps_per_side == 30.0 and C.SEVERE.borrow_bps_per_year == 1000.0


# ── 5. entry at t+1 ───────────────────────────────────────────────────────────────────────────────
def test_05_entry_at_t_plus_1():
    mkt = _flat_market(overrides={6: 110.0})
    entry = simulate_position(TradeIntent("T5", "AAA", "long", "P5", 0, 100, exit_decision_session=5), mkt)["events"][0]
    assert entry["event_type"] == "ENTRY_FILL"
    assert entry["decision_session"] == 0 and entry["decision_type"] == "ENTRY_SIGNAL"
    assert entry["actual_execution_session"] == 1


# ── 6. time exit at open of session 6 ─────────────────────────────────────────────────────────────
def test_06_time_stop_at_session_6():
    mkt = _flat_market(overrides={6: 110.0})
    exit_ev = simulate_position(TradeIntent("T6", "AAA", "long", "P6", 0, 100), mkt)["events"][-1]
    assert exit_ev["event_type"] == "EXIT_FILL" and exit_ev["actual_execution_session"] == 6
    assert exit_ev["reason"] == "TIME_STOP"


# ── 6b. explicit exit event records the EXIT decision session (defect 1) ──────────────────────────
def test_06b_explicit_exit_records_exit_decision_session():
    mkt = _flat_market(overrides={6: 110.0})
    exit_ev = simulate_position(TradeIntent("T6b", "AAA", "long", "P6b", 0, 100, exit_decision_session=5), mkt)["events"][-1]
    assert exit_ev["event_type"] == "EXIT_FILL"
    assert exit_ev["decision_session"] == 5              # NOT the entry decision session 0
    assert exit_ev["decision_type"] == "EXIT_DECISION"


# ── 6c. time-stop event records the frozen causal decision (defect 1) ─────────────────────────────
def test_06c_time_stop_records_frozen_causal_decision():
    mkt = _flat_market(overrides={6: 110.0})
    exit_ev = simulate_position(TradeIntent("T6c", "AAA", "long", "P6c", 0, 100), mkt)["events"][-1]
    assert exit_ev["decision_session"] == 5             # t + HORIZON - 1
    assert exit_ev["decision_type"] == "TIME_STOP_SCHEDULED_AT_ENTRY"
    assert exit_ev["decision_session"] != 0             # never the entry decision session


# ── 7. missing entry open cancellation ────────────────────────────────────────────────────────────
def test_07_missing_entry_open_cancels():
    mkt = _flat_market(sessions=range(0, 4), overrides={1: None})
    r = simulate_position(TradeIntent("T7", "AAA", "long", "P7", 0, 100), mkt)
    assert r["disposition"] == "CANCELLED" and r["position"] is None
    assert r["events"][0]["event_type"] == "ENTRY_CANCELLED" and r["events"][0]["reason"] == "MISSING_ENTRY_OPEN"


# ── 8. missing exit open deferral ─────────────────────────────────────────────────────────────────
def test_08_missing_exit_open_defers():
    mkt = _flat_market(sessions=range(0, 9), overrides={6: None, 7: 120.0})   # time-stop s6 absent -> s7
    exit_ev = simulate_position(TradeIntent("T8", "AAA", "long", "P8", 0, 100), mkt)["events"][-1]
    assert exit_ev["event_type"] == "EXIT_FILL" and exit_ev["actual_execution_session"] == 7
    assert "DEFERRED_FROM_6" in exit_ev["reason"]


def test_08b_missing_exit_open_no_future_open_pends_deterministic():
    def build():
        m = Market(opens={0: 100.0, 1: 100.0}, adv_dollars={0: 1e12, 1: 1e12},
                   session_dates={0: "2024-01-01", 1: "2024-01-02"}, nav=1e12)
        return simulate_position(TradeIntent("T8b", "AAA", "long", "P8b", 0, 100), m)
    r1, r2 = build(), build()
    assert r1["disposition"] == "PENDING" and r1["events"][-1]["event_type"] == "EXIT_PENDING"
    assert "PENDING_NO_OPEN" in r1["events"][-1]["reason"]
    assert r1["events"] == r2["events"]                 # deterministic


# ── 9. 2% ADV clipping ────────────────────────────────────────────────────────────────────────────
def test_09_adv_participation_clip():
    mkt = _flat_market(overrides={6: 110.0}, adv_overrides={1: 500000.0})    # 2%*500k/100 = 100 sh
    r = simulate_position(TradeIntent("T9", "AAA", "long", "P9", 0, 250, exit_decision_session=5), mkt)
    assert r["position"]["shares"] == 100
    assert "CLIPPED_150_SHARES_TO_CASH" in r["events"][0]["reason"]


# ── 10. 1.5% NAV clipping ─────────────────────────────────────────────────────────────────────────
def test_10_nav_new_entry_clip():
    mkt = _flat_market(nav=1_000_000.0, overrides={6: 110.0})               # 1.5%*1M/100 = 150 sh
    r = simulate_position(TradeIntent("T10", "AAA", "long", "P10", 0, 250, exit_decision_session=5), mkt)
    assert r["position"]["shares"] == 150
    assert "CLIPPED_100_SHARES_TO_CASH" in r["events"][0]["reason"]


# ── 11. clip never delays: no residual order for the clipped quantity ─────────────────────────────
def test_11_clip_never_delay_no_residual():
    mkt = _flat_market(nav=1_000_000.0, overrides={6: 110.0})
    r = simulate_position(TradeIntent("T11", "AAA", "long", "P11", 0, 250, exit_decision_session=5), mkt)
    assert len([e for e in r["events"] if e["event_type"] == "ENTRY_FILL"]) == 1
    assert all(e["event_type"] != "ENTRY_RESIDUAL" for e in r["events"])


# ── 12. no same-open re-entry ─────────────────────────────────────────────────────────────────────
def test_12_no_same_open_reentry():
    mkt = _flat_market(sessions=range(0, 12), overrides={6: 110.0})
    a = TradeIntent("A", "AAA", "long", "PA", 0, 100)                       # entry s1, time-stop exit s6
    b = TradeIntent("B", "AAA", "long", "PB", 5, 100)                       # entry would fill s6 == A exit
    seq = simulate_sequence([a, b], mkt)
    refused = [e for e in seq["events"] if e["event_type"] == "ENTRY_REFUSED_SAME_OPEN"]
    assert len(refused) == 1 and refused[0]["reason"] == "NO_SAME_OPEN_REENTRY"
    assert len(seq["positions"]) == 1


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


# ── 13b. canonical report never stamps the entry decision on an exit event ────────────────────────
def test_13b_report_has_no_exit_with_entry_decision_session():
    rep = _sample_ledger()
    for e in rep["events"]:
        if e["event_type"] in ("EXIT_FILL", "EXIT_PENDING"):
            assert e["decision_type"] in ("EXIT_DECISION", "TIME_STOP_SCHEDULED_AT_ENTRY")
            assert not (e["decision_type"] == "ENTRY_SIGNAL")
    exit_ev = [e for e in rep["events"] if e["event_type"] == "EXIT_FILL"][0]
    assert exit_ev["decision_session"] == 5 and exit_ev["decision_type"] == "EXIT_DECISION"


# ── 14. signed-zero preserved and non-finite refusal ─────────────────────────────────────────────
def test_14_signed_zero_gross_preserved():
    mkt = _flat_market(overrides={6: 100.0})            # short, exit == entry -> gross = -0.0
    r = simulate_position(TradeIntent("T14", "AAA", "short", "P14", 0, 100), mkt)
    assert R.encode_float(r["position"]["gross_pnl"])["exact_hex"] == "-0x0.0p+0"
    rep = X.ledger_report(events=r["events"], positions=[r["position"]], base_schedule="BASE",
                          stress=None, severe=None, code_identity=CODE_ID, dependency_lock_sha256=DEP_LOCK_SHA)
    assert rep["positions"][0]["gross_pnl"]["exact_hex"] == "-0x0.0p+0"


def test_14b_nonfinite_price_refuses():
    with pytest.raises(X.ExecIntegrityStop, match="EXEC_PRICE_NONFINITE"):
        simulate_position(TradeIntent("T14b", "AAA", "long", "P14b", 0, 100), _flat_market(overrides={6: float("inf")}))
    with pytest.raises(X.ExecIntegrityStop, match="EXEC_PRICE_NONPOSITIVE"):
        simulate_position(TradeIntent("T14c", "AAA", "long", "P14c", 0, 100), _flat_market(overrides={1: -5.0}))


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


# ── defect 2: calendar-day borrow accrual ─────────────────────────────────────────────────────────
def test_16_friday_to_monday_borrow_is_three_calendar_days():
    # entry Fri 2024-01-05 (s1), explicit exit -> Mon 2024-01-08 (s2): 3 calendar days, not 1 session
    mkt = Market(opens={0: 100.0, 1: 100.0, 2: 100.0}, adv_dollars={0: 1e12, 1: 1e12, 2: 1e12},
                 session_dates={0: "2024-01-04", 1: "2024-01-05", 2: "2024-01-08"}, nav=1e12)
    p = simulate_position(TradeIntent("F", "AAA", "short", "PF", 0, 100, exit_decision_session=1), mkt)["position"]
    assert p["borrow_calendar_days"] == 3
    assert p["borrow_cost"] == pytest.approx((100.0 * 100) * (50 / 10000) * (3 / 360))


def test_17_holiday_gap_borrow_accrual():
    # entry Wed 2024-11-27 (s1), exit Fri 2024-11-29 (s2); Thu 11-28 (Thanksgiving) has no session
    mkt = Market(opens={0: 100.0, 1: 100.0, 2: 100.0}, adv_dollars={0: 1e12, 1: 1e12, 2: 1e12},
                 session_dates={0: "2024-11-26", 1: "2024-11-27", 2: "2024-11-29"}, nav=1e12)
    p = simulate_position(TradeIntent("H", "AAA", "short", "PH", 0, 100, exit_decision_session=1), mkt)["position"]
    assert p["borrow_calendar_days"] == 2               # 2 calendar days across the holiday, 1 session gap


# ── defect 3: horizon identity ────────────────────────────────────────────────────────────────────
def test_18_caller_horizon_must_be_six():
    mkt = _flat_market(overrides={6: 110.0})
    for bad in (5, 7):
        with pytest.raises(X.ExecRefused, match="EXECUTION_HORIZON"):
            simulate_position(TradeIntent("HZ", "AAA", "long", "PHZ", 0, 100, horizon=bad), mkt)


# ── defect 4: ADV/NAV integrity ───────────────────────────────────────────────────────────────────
def test_19_missing_adv_stops():
    mkt = Market(opens={0: 100.0, 1: 100.0, 6: 110.0}, adv_dollars={0: 1e12},   # entry session 1 absent
                 session_dates={s: "2024-01-0%d" % (s + 1) for s in (0, 1)} | {6: "2024-01-07"}, nav=1e12)
    with pytest.raises(X.ExecIntegrityStop, match="EXEC_ADV_MISSING"):
        simulate_position(TradeIntent("AV", "AAA", "long", "PAV", 0, 100), mkt)


def test_20_negative_adv_stops():
    mkt = _flat_market(overrides={6: 110.0}, adv_overrides={1: -1.0})
    with pytest.raises(X.ExecIntegrityStop, match="EXEC_ADV_NEGATIVE"):
        simulate_position(TradeIntent("AVN", "AAA", "long", "PAVN", 0, 100), mkt)


def test_21_nonpositive_and_missing_nav_stop():
    mkt0 = _flat_market(nav=0.0, overrides={6: 110.0})
    with pytest.raises(X.ExecIntegrityStop, match="EXEC_NAV_NONPOSITIVE"):
        simulate_position(TradeIntent("NV", "AAA", "long", "PNV", 0, 100), mkt0)
    mktN = _flat_market(nav=None, overrides={6: 110.0})
    with pytest.raises(X.ExecIntegrityStop, match="EXEC_NAV_MISSING"):
        simulate_position(TradeIntent("NVM", "AAA", "long", "PNVM", 0, 100), mktN)


# ── defect 5: cost-schedule identity ──────────────────────────────────────────────────────────────
def test_22_tampered_base_schedule_refuses():
    tampered = C.CostSchedule("BASE", 5.0, 50.0, 360, "GATE")     # wrong bps under the BASE name
    with pytest.raises(C.CostRefused, match="COST_SCHEDULE:BPS_PER_SIDE"):
        simulate_position(TradeIntent("CS", "AAA", "long", "PCS", 0, 100, exit_decision_session=5),
                          _flat_market(overrides={6: 110.0}), tampered)


def test_23_day_count_365_refuses():
    bad = C.CostSchedule("BASE", 10.0, 50.0, 365, "GATE")
    with pytest.raises(C.CostRefused, match="COST_SCHEDULE:DAY_COUNT"):
        C.validate_schedule(bad)
    with pytest.raises(C.CostRefused, match="COST_SCHEDULE:UNKNOWN_NAME"):
        C.validate_schedule(C.CostSchedule("BOGUS", 10.0, 50.0, 360, "GATE"))


# ── defect 6: strict typing + duplicate ids + exit-before-entry ──────────────────────────────────
def test_24_float_and_bool_holding_days_refuse():
    with pytest.raises(C.CostIntegrityStop, match="BORROW_DAYS_NOT_INT"):
        C.borrow_cost(1000.0, 5.9, C.BASE, is_short=True)
    with pytest.raises(C.CostIntegrityStop, match="BORROW_DAYS_NOT_INT"):
        C.borrow_cost(1000.0, True, C.BASE, is_short=True)


def test_25_duplicate_trade_and_position_id_refuse():
    mkt = _flat_market(overrides={6: 110.0})
    a = TradeIntent("DUP", "AAA", "long", "PA", 0, 100)
    b = TradeIntent("DUP", "BBB", "long", "PB", 0, 100)          # same trade_id
    with pytest.raises(X.ExecRefused, match="DUPLICATE_TRADE_ID"):
        simulate_sequence([a, b], mkt)
    c = TradeIntent("C1", "AAA", "long", "PP", 0, 100)
    d = TradeIntent("C2", "BBB", "long", "PP", 0, 100)          # same position_id
    with pytest.raises(X.ExecRefused, match="DUPLICATE_POSITION_ID"):
        simulate_sequence([c, d], mkt)


def test_26_exit_before_entry_and_bad_sessions_refuse():
    mkt = _flat_market(overrides={6: 110.0})
    with pytest.raises(X.ExecIntegrityStop, match="EXEC_EXIT_BEFORE_ENTRY"):
        simulate_position(TradeIntent("XB", "AAA", "long", "PXB", 3, 100, exit_decision_session=2), mkt)
    with pytest.raises(X.ExecIntegrityStop, match="EXEC_INVALID_SESSION"):
        simulate_position(TradeIntent("XN", "AAA", "long", "PXN", -1, 100), mkt)


# ── costs from executed (not intended) notional + event shape ─────────────────────────────────────
def test_27_costs_from_executed_not_intended_notional():
    mkt = _flat_market(nav=1_000_000.0, overrides={6: 110.0})
    p = simulate_position(TradeIntent("EX", "AAA", "long", "PEX", 0, 250, exit_decision_session=5), mkt)["position"]
    assert p["entry_commission"] == pytest.approx(150 * 100.0 * 10 / 10000)   # executed 150, not 250
    assert p["entry_notional"] == pytest.approx(150 * 100.0)


def test_28_invalid_side_and_shares_refuse():
    mkt = _flat_market(overrides={6: 110.0})
    with pytest.raises(X.ExecIntegrityStop, match="EXEC_INVALID_SIDE"):
        simulate_position(TradeIntent("SD", "AAA", "flat", "PSD", 0, 100), mkt)
    with pytest.raises(X.ExecIntegrityStop, match="EXEC_INVALID_SHARES"):
        simulate_position(TradeIntent("SH", "AAA", "long", "PSH", 0, 0), mkt)


def test_29_event_has_17_frozen_fields():
    mkt = _flat_market(overrides={6: 110.0})
    r = simulate_position(TradeIntent("EV", "AAA", "long", "PEV", 0, 100, exit_decision_session=5), mkt)
    for e in r["events"]:
        assert tuple(e.keys()) == X.EVENT_FIELDS
    assert len(X.EVENT_FIELDS) == 17 and "decision_type" in X.EVENT_FIELDS
