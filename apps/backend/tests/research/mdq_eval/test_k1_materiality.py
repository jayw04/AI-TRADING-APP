"""K1 — the frame, and the refusal to invent the parts the registration does not specify.

The most important test here is that K1 returns NOT EVALUABLE with a *stated reason* rather than a
number. K1 has two limbs and neither is executable from the frozen partitions alone; a calculator that
quietly picked a decision function, or assembled a defect list after seeing the corpus, would emit
something that looks exactly like K1 and is not.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from app.research.mdq_eval.k1_materiality import DIVERGENCE_THRESHOLD, evaluate_k1
from app.research.mdq_eval.results import KOutcome, _mint_token

SESSIONS = [date(2026, 8, 19), date(2026, 8, 20), date(2026, 8, 21),
            date(2026, 8, 25), date(2026, 8, 26)]


def _tokens(root):
    return [_mint_token(root=str(Path(root).resolve()), session=s, verdict="ADMISSIBLE",
                        assessed_at="2026-08-27T00:00:00Z", admissibility_digest="d" * 64)
            for s in SESSIONS]


# ── the refusal ──────────────────────────────────────────────────────────────────────────────────

def test_without_governed_inputs_k1_is_not_evaluable_and_says_why(tmp_path):
    """★ NOT EVALUABLE, not FAIL, not a fabricated number — and the reason names both limbs."""
    result = evaluate_k1(tmp_path, SESSIONS, tokens=_tokens(tmp_path))
    assert result.outcome is KOutcome.NOT_EVALUABLE
    missing = result.measures["missing_inputs"]
    assert any("decision provider" in m for m in missing)
    assert any("PREDECLARED" in m for m in missing)


def test_the_defect_list_gap_is_stated_as_post_hoc_risk(tmp_path):
    """Assembling a defect list now, after the corpus exists, is barred selection — say so."""
    result = evaluate_k1(tmp_path, SESSIONS, tokens=_tokens(tmp_path))
    assert any("post-hoc" in m for m in result.measures["missing_inputs"])


def test_delta_volume_is_recorded_as_a_diagnostic_never_a_trigger(tmp_path):
    result = evaluate_k1(tmp_path, SESSIONS, tokens=_tokens(tmp_path))
    assert "NOT a keep trigger" in result.measures["delta_volume_note"]


# ── limb A: decision divergence ──────────────────────────────────────────────────────────────────

def _provider(diverge_on: set[date]):
    def decisions(*, root: Path, feed: str, session: date):
        if session in diverge_on and feed == "sip":
            return ("ELIGIBLE", "AAA")
        return ("ELIGIBLE", "BBB")
    return decisions


def test_divergence_at_the_threshold_passes(tmp_path):
    """1 of 5 session-days = 0.20 >= 0.10."""
    result = evaluate_k1(tmp_path, SESSIONS, tokens=_tokens(tmp_path),
                         decisions=_provider({SESSIONS[0]}))
    assert result.measures["divergence_share"] == pytest.approx(0.2)
    assert result.outcome is KOutcome.PASS


def test_no_divergence_fails(tmp_path):
    result = evaluate_k1(tmp_path, SESSIONS, tokens=_tokens(tmp_path), decisions=_provider(set()))
    assert result.measures["diverged_session_days"] == 0
    assert result.outcome is KOutcome.FAIL


def test_divergence_below_the_threshold_fails(tmp_path):
    many = [date(2026, 7, d) for d in range(1, 21)]  # 20 session-days
    tokens = [_mint_token(root=str(Path(tmp_path).resolve()), session=s, verdict="ADMISSIBLE",
                          assessed_at="2026-08-27T00:00:00Z", admissibility_digest="d" * 64)
              for s in many]
    result = evaluate_k1(tmp_path, many, tokens=tokens, decisions=_provider({many[0]}))
    assert result.measures["divergence_share"] == pytest.approx(0.05)
    assert result.measures["divergence_share"] < DIVERGENCE_THRESHOLD
    assert result.outcome is KOutcome.FAIL


def test_the_diverged_sessions_are_named(tmp_path):
    """A bare share is not reviewable; the record must say which days diverged."""
    result = evaluate_k1(tmp_path, SESSIONS, tokens=_tokens(tmp_path),
                         decisions=_provider({SESSIONS[1], SESSIONS[3]}))
    assert result.measures["diverged_sessions"] == [SESSIONS[1].isoformat(), SESSIONS[3].isoformat()]


# ── limb B: predeclared defect correction ────────────────────────────────────────────────────────

def test_one_corrected_predeclared_defect_passes(tmp_path):
    result = evaluate_k1(
        tmp_path, SESSIONS, tokens=_tokens(tmp_path),
        predeclared_defects=[{"id": "D1"}, {"id": "D2"}],
        defect_corrected=lambda d: d["id"] == "D1",
    )
    assert result.outcome is KOutcome.PASS
    assert result.measures["defects_corrected_by_sip"] == 1


def test_a_predeclared_list_with_no_corrections_falls_through_to_limb_a(tmp_path):
    """Limb B not met is not K1 failed — limb A still decides, or NOT EVALUABLE if it cannot."""
    result = evaluate_k1(
        tmp_path, SESSIONS, tokens=_tokens(tmp_path),
        predeclared_defects=[{"id": "D1"}], defect_corrected=lambda d: False,
    )
    assert result.outcome is KOutcome.NOT_EVALUABLE
    assert result.measures["defects_corrected_by_sip"] == 0
