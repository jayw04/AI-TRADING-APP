"""K1 — the OR truth table, the exact 10% boundary, and the governed-input boundary.

The most consequential test here is the truth table. `A OR B` over three-valued outcomes is not
"not PASS ⇒ FAIL": a FAIL requires BOTH limbs evaluable and neither passing. FAIL and NOT EVALUABLE
have different consequences under the frozen verdict rules — a NOT-EVALUABLE criterion leaves the
keep/cancel denominator entirely — so a false FAIL can alter HOLD/STOP reachability.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from app.research.mdq_eval.k1_materiality import DIVERGENCE_THRESHOLD, evaluate_k1
from app.research.mdq_eval.results import KOutcome

SESSIONS = [date(2026, 8, 19), date(2026, 8, 20), date(2026, 8, 21),
            date(2026, 8, 25), date(2026, 8, 26)]
TEN = [date(2026, 7, d) for d in range(1, 11)]      # 10 session-days
TWENTY = [date(2026, 7, d) for d in range(1, 21)]   # 20 session-days


def _provider(diverge_on: set[date]):
    def decisions(*, root: Path, feed: str, session: date):
        return ("ELIGIBLE", "AAA") if (session in diverge_on and feed == "sip") else ("ELIGIBLE", "BBB")
    return decisions


# ── the refusal, when nothing governed is available ──────────────────────────────────────────────

def test_without_governed_inputs_k1_is_not_evaluable_and_says_why(tmp_path, adjudication):
    result = evaluate_k1(tmp_path, SESSIONS, tokens=adjudication.tokens(tmp_path, SESSIONS))
    assert result.outcome is KOutcome.NOT_EVALUABLE
    missing = result.measures["missing_inputs"]
    assert any("decision provider" in m for m in missing)
    assert any("PREDECLARED" in m for m in missing)
    assert any("post-hoc" in m for m in missing)


def test_delta_volume_is_a_diagnostic_never_a_trigger(tmp_path, adjudication):
    result = evaluate_k1(tmp_path, SESSIONS, tokens=adjudication.tokens(tmp_path, SESSIONS))
    assert "NOT a keep trigger" in result.measures["delta_volume_note"]


# ── ★ the OR truth table ─────────────────────────────────────────────────────────────────────────

def test_limb_a_fail_with_limb_b_unavailable_is_NOT_EVALUABLE_not_fail(tmp_path, adjudication):
    """★ THE regression. An earlier revision returned FAIL here.

    FAIL asserts "evaluated, and not met". With limb B unavailable that assertion is unsupported, and
    it would wrongly keep K1 inside the evaluable denominator.
    """
    result = evaluate_k1(tmp_path, TWENTY, tokens=adjudication.tokens(tmp_path, TWENTY),
                         decisions=_provider(set()))
    assert result.measures["limb_a"] == "FAIL"
    assert result.measures["limb_b"] == "NOT_EVALUABLE"
    assert result.outcome is KOutcome.NOT_EVALUABLE
    assert "BOTH limbs evaluable" in result.detail


def test_limb_b_fail_with_limb_a_unavailable_is_NOT_EVALUABLE_not_fail(tmp_path, adjudication):
    result = evaluate_k1(tmp_path, SESSIONS, tokens=adjudication.tokens(tmp_path, SESSIONS),
                         predeclared_defects=[{"id": "D1"}], defect_corrected=lambda d: False)
    assert result.measures["limb_a"] == "NOT_EVALUABLE"
    assert result.measures["limb_b"] == "FAIL"
    assert result.outcome is KOutcome.NOT_EVALUABLE


def test_both_limbs_fail_is_the_only_fail(tmp_path, adjudication):
    result = evaluate_k1(tmp_path, TWENTY, tokens=adjudication.tokens(tmp_path, TWENTY),
                         decisions=_provider(set()),
                         predeclared_defects=[{"id": "D1"}], defect_corrected=lambda d: False)
    assert (result.measures["limb_a"], result.measures["limb_b"]) == ("FAIL", "FAIL")
    assert result.outcome is KOutcome.FAIL


def test_either_limb_passing_passes(tmp_path, adjudication):
    a_only = evaluate_k1(tmp_path, TEN, tokens=adjudication.tokens(tmp_path, TEN),
                         decisions=_provider({TEN[0]}))
    assert a_only.outcome is KOutcome.PASS
    b_only = evaluate_k1(tmp_path, SESSIONS, tokens=adjudication.tokens(tmp_path, SESSIONS),
                         predeclared_defects=[{"id": "D1"}], defect_corrected=lambda d: True)
    assert b_only.outcome is KOutcome.PASS


def test_neither_limb_evaluable_is_not_evaluable(tmp_path, adjudication):
    result = evaluate_k1(tmp_path, SESSIONS, tokens=adjudication.tokens(tmp_path, SESSIONS))
    assert result.outcome is KOutcome.NOT_EVALUABLE


# ── ★ the exact 10% boundary ─────────────────────────────────────────────────────────────────────

def test_exactly_ten_percent_passes(tmp_path, adjudication):
    """★ 1/10 = 0.10 exactly. Pins `>=` against `>`; an earlier test used 1/5 = 0.20 and pinned nothing."""
    result = evaluate_k1(tmp_path, TEN, tokens=adjudication.tokens(tmp_path, TEN),
                         decisions=_provider({TEN[0]}))
    assert result.measures["divergence_share"] == pytest.approx(DIVERGENCE_THRESHOLD)
    assert result.outcome is KOutcome.PASS


def test_exactly_ten_percent_at_a_different_denominator_passes(tmp_path, adjudication):
    """2/20 = 0.10 — the same boundary reached another way, guarding against a fluke."""
    result = evaluate_k1(tmp_path, TWENTY, tokens=adjudication.tokens(tmp_path, TWENTY),
                         decisions=_provider({TWENTY[0], TWENTY[1]}))
    assert result.measures["divergence_share"] == pytest.approx(0.10)
    assert result.outcome is KOutcome.PASS


def test_just_below_ten_percent_fails_limb_a(tmp_path, adjudication):
    """1/20 = 0.05 — limb A FAILs; with limb B unavailable K1 is NOT EVALUABLE."""
    result = evaluate_k1(tmp_path, TWENTY, tokens=adjudication.tokens(tmp_path, TWENTY),
                         decisions=_provider({TWENTY[0]}))
    assert result.measures["divergence_share"] == pytest.approx(0.05)
    assert result.measures["limb_a"] == "FAIL"
    assert result.outcome is KOutcome.NOT_EVALUABLE


def test_the_diverged_sessions_are_named(tmp_path, adjudication):
    result = evaluate_k1(tmp_path, SESSIONS, tokens=adjudication.tokens(tmp_path, SESSIONS),
                         decisions=_provider({SESSIONS[1], SESSIONS[3]}))
    assert result.measures["diverged_sessions"] == [SESSIONS[1].isoformat(), SESSIONS[3].isoformat()]


# ── ★ injected inputs carry no governed authority ────────────────────────────────────────────────

def test_an_injected_provider_yields_a_diagnostic_not_evidence(tmp_path, adjudication):
    """★ 'A caller passed a callable' is not 'the owner bound a governed K1 authority'."""
    result = evaluate_k1(tmp_path, TEN, tokens=adjudication.tokens(tmp_path, TEN),
                         decisions=_provider({TEN[0]}))
    assert result.outcome is KOutcome.PASS
    assert result.evidentiary is False           # admissible sessions, but ungoverned input
    assert any("no SCAN-001/GAPPER provider has been bound" in u for u in result.ungoverned_inputs)


def test_an_injected_defect_list_yields_a_diagnostic_not_evidence(tmp_path, adjudication):
    result = evaluate_k1(tmp_path, SESSIONS, tokens=adjudication.tokens(tmp_path, SESSIONS),
                         predeclared_defects=[{"id": "D1"}], defect_corrected=lambda d: True)
    assert result.outcome is KOutcome.PASS
    assert result.evidentiary is False
    assert any("declares no predeclared" in u for u in result.ungoverned_inputs)


def test_the_only_evidentiary_k1_today_is_not_evaluable(tmp_path, adjudication):
    """With no injected inputs the result IS evidentiary — and it is NOT EVALUABLE, which is the
    honest governed state of K1 until a provider or defect declaration is bound."""
    result = evaluate_k1(tmp_path, SESSIONS, tokens=adjudication.tokens(tmp_path, SESSIONS))
    assert result.evidentiary is True
    assert result.outcome is KOutcome.NOT_EVALUABLE
