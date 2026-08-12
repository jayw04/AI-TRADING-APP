"""WP7 AMD-17 / D1 — O4 decision-time vs forensic replay (hermetic; no broker)."""

from __future__ import annotations

from decimal import Decimal as D

from app.risk.loss_control.phase0_contracts import (
    REASON_INSUFFICIENT_EXECUTION_COST,
    REASON_MODEL_UNAVAILABLE,
    VERDICT_INDETERMINATE,
    VERDICT_UNREACHABLE_WITHIN_CAPS,
)
from app.risk.loss_control.phase0_o4_replay import (
    DecisionTimeEvidence,
    ForensicEvidence,
    InstrumentTermination,
    O4GateVerdict,
    O4RefuseReason,
    assert_no_order_path_imports,
    run_o4_gate,
    run_o4a,
    run_o4b,
)
from app.risk.loss_control.phase0_reachability import Caps

CAPS = Caps(
    loss_target=D("3000"),
    max_round_trips=12,
    max_setup_notional=D("25000"),
    max_position_qty=D("1000"),
)


def _quote(bid="128.09", ask="131.03", age="2"):
    """Wide displayed spread — Tier C would project REACHABLE; Tier D → INDETERMINATE."""
    return {"bid": bid, "ask": ask, "age_s": age}


def _term() -> InstrumentTermination:
    return InstrumentTermination(symbol="KOKU", reason="session_end", at="2026-07-24T20:00:00Z")


def test_o4a_tier_d_displayed_spread_is_indeterminate() -> None:
    ev = DecisionTimeEvidence(
        quotes={"KOKU": _quote()},
        symbols=("KOKU",),
        day_change=D("0"),
    )
    r = run_o4a(ev, CAPS, original_termination=_term())
    assert r.gate_verdict == O4GateVerdict.PASS
    assert r.expected_verdict == VERDICT_INDETERMINATE
    assert r.expected_reason == REASON_INSUFFICIENT_EXECUTION_COST
    assert r.adjudicated is not None
    assert r.adjudicated.verdict == VERDICT_INDETERMINATE
    assert r.original_termination is not None
    assert r.original_termination.symbol == "KOKU"


def test_o4a_model_unavailable() -> None:
    ev = DecisionTimeEvidence(
        quotes={},
        symbols=("KOKU",),
        day_change=None,
        model_available=False,
    )
    r = run_o4a(ev, CAPS)
    assert r.gate_verdict == O4GateVerdict.PASS
    assert r.expected_reason == REASON_MODEL_UNAVAILABLE


def test_o4a_lookahead_fills_refused() -> None:
    ev = DecisionTimeEvidence(
        quotes={"KOKU": _quote()},
        symbols=("KOKU",),
        day_change=D("0"),
        fills=({"client_order_id": "x", "qty": "10"},),
    )
    r = run_o4a(ev, CAPS)
    assert r.gate_verdict == O4GateVerdict.REFUSED
    assert r.refuse_reason is O4RefuseReason.LOOKAHEAD_FILLS_IN_DECISION_TIME


def test_o4b_fill_evidence_unreachable_within_caps() -> None:
    # Tiny fill-derived loss/RT → cannot hit 3000 in 12 trips.
    ev = ForensicEvidence(
        quotes={},
        symbols=("KOKU",),
        day_change=D("0"),
        fills=({"client_order_id": "a"}, {"client_order_id": "b"}),
        fill_loss_per_round_trip=D("50.00"),
    )
    r = run_o4b(ev, CAPS, original_termination=_term())
    assert r.gate_verdict == O4GateVerdict.PASS
    assert r.expected_verdict == VERDICT_UNREACHABLE_WITHIN_CAPS
    assert r.adjudicated is not None
    assert r.adjudicated.verdict == VERDICT_UNREACHABLE_WITHIN_CAPS
    assert r.original_termination is not None


def test_o4b_missing_fills_refused() -> None:
    ev = ForensicEvidence(
        quotes={},
        symbols=("KOKU",),
        day_change=D("0"),
        fills=(),
        fill_loss_per_round_trip=D("50.00"),
    )
    r = run_o4b(ev, CAPS)
    assert r.gate_verdict == O4GateVerdict.REFUSED
    assert r.refuse_reason is O4RefuseReason.FORENSIC_MISSING_FILLS


def test_o4_gate_requires_both() -> None:
    decision = DecisionTimeEvidence(
        quotes={"KOKU": _quote()},
        symbols=("KOKU",),
        day_change=D("0"),
    )
    forensic = ForensicEvidence(
        quotes={},
        symbols=("KOKU",),
        day_change=D("0"),
        fills=({"id": "1"},),
        fill_loss_per_round_trip=D("40.00"),
    )
    g = run_o4_gate(
        decision=decision, forensic=forensic, caps=CAPS, original_termination=_term()
    )
    assert g.verdict == O4GateVerdict.PASS
    assert g.o4a.gate_verdict == O4GateVerdict.PASS
    assert g.o4b.gate_verdict == O4GateVerdict.PASS


def test_o4_gate_refuses_mixed_evidence() -> None:
    decision = DecisionTimeEvidence(
        quotes={"KOKU": _quote()},
        symbols=("KOKU",),
        day_change=D("0"),
        fills=({"id": "leak"},),
    )
    forensic = ForensicEvidence(
        quotes={},
        symbols=("KOKU",),
        day_change=D("0"),
        fills=({"id": "1"},),
        fill_loss_per_round_trip=D("40.00"),
    )
    g = run_o4_gate(decision=decision, forensic=forensic, caps=CAPS)
    assert g.verdict == O4GateVerdict.REFUSED


def test_no_order_path_imports() -> None:
    assert_no_order_path_imports()
