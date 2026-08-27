"""The gate: a K-value computed over an inadmissible partition is a number, never evidence.

These tests probe the *structure* — can evidentiary status be asserted, can a token be forged, can one
be reused across scopes — rather than checking that a happy path sets a flag. Tokens are obtained by
driving `require_admissible` against a controlled adjudication, so the gate's own verdict handling is
on the tested path.
"""

from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from app.research.capture.admissibility import Verdict
from app.research.mdq_eval.gate import NotAdmissible, validate_tokens
from app.research.mdq_eval.k1_materiality import evaluate_k1
from app.research.mdq_eval.k3_completeness import evaluate_k3
from app.research.mdq_eval.results import AdmissibilityToken, KOutcome, KResult

ET = ZoneInfo("America/New_York")
SESSION = date(2026, 8, 26)
OTHER = date(2026, 8, 25)


def _write_bars(root, feed: str, session: date, n: int) -> None:
    import pandas as pd

    d = root / feed / session.isoformat() / "bars"
    d.mkdir(parents=True, exist_ok=True)
    rows = [{"symbol": "AAA",
             "ts": datetime.combine(session, time(9, 30 + i), tzinfo=ET).isoformat()}
            for i in range(n)]
    pd.DataFrame(rows).to_parquet(d / "bars_1min.parquet")


# ── evidentiary status cannot be asserted ────────────────────────────────────────────────────────

def test_a_result_cannot_claim_to_be_evidentiary(tmp_path):
    """★ THE regression. `KResult(..., evidentiary=True)` must not be constructible at all.

    An earlier revision took `evidentiary: bool`, so the "structural" gate was documentary: any caller
    could stamp a number as evidence.
    """
    with pytest.raises(TypeError):
        KResult(criterion="K3", outcome=KOutcome.PASS, threshold="t", detail="d",
                evidentiary=True)  # type: ignore[call-arg]


def test_evidentiary_is_derived_from_real_tokens(tmp_path, adjudication):
    result = KResult(criterion="K3", outcome=KOutcome.PASS, threshold="t", detail="d")
    assert result.evidentiary is False
    with_token = KResult(criterion="K3", outcome=KOutcome.PASS, threshold="t", detail="d",
                         tokens=(adjudication.token(tmp_path, SESSION),))
    assert with_token.evidentiary is True


def test_token_dictionaries_are_refused(tmp_path, adjudication):
    """Dicts would reintroduce the assertion path; only real token objects count."""
    fake = adjudication.token(tmp_path, SESSION).as_dict()
    with pytest.raises(TypeError, match="must contain AdmissibilityToken"):
        KResult(criterion="K3", outcome=KOutcome.PASS, threshold="t", detail="d",
                tokens=(fake,))  # type: ignore[arg-type]


def test_a_token_cannot_be_constructed_directly():
    with pytest.raises(TypeError, match="cannot be constructed directly"):
        AdmissibilityToken(root="/x", session=SESSION, verdict="ADMISSIBLE",
                           assessed_at="2026-08-27T00:00:00Z", admissibility_digest="d" * 64)


# ── the gate's own verdict handling ──────────────────────────────────────────────────────────────

def test_only_admissible_mints_a_token(tmp_path, adjudication):
    adjudication.set_verdict(Verdict.NOT_ADMISSIBLE)
    with pytest.raises(NotAdmissible, match="no evidentiary K-value"):
        adjudication.token(tmp_path, SESSION)


def test_undetermined_is_not_a_pass(tmp_path, adjudication):
    """★ 'We could not tell' must not become evidence — it reads as a pass in every summary."""
    adjudication.set_verdict(Verdict.UNDETERMINED)
    with pytest.raises(NotAdmissible):
        adjudication.token(tmp_path, SESSION)


def test_the_token_names_the_adjudication_it_came_from(tmp_path, adjudication):
    token = adjudication.token(tmp_path, SESSION)
    assert token.verdict == str(Verdict.ADMISSIBLE)
    assert len(token.admissibility_digest) == 64


# ── evidence requires a token for exactly this scope ─────────────────────────────────────────────

def test_evaluating_without_tokens_refuses(tmp_path):
    _write_bars(tmp_path, "iex", SESSION, 2)
    _write_bars(tmp_path, "sip", SESSION, 4)
    with pytest.raises(Exception, match="requires admissibility tokens"):
        evaluate_k3(tmp_path, [SESSION])


def test_a_missing_session_token_refuses(tmp_path, adjudication):
    """★ The laundering path: one admissible day's token must not cover a second, unassessed day."""
    for s in (SESSION, OTHER):
        _write_bars(tmp_path, "iex", s, 2)
        _write_bars(tmp_path, "sip", s, 4)
    with pytest.raises(NotAdmissible, match="no admissibility token"):
        evaluate_k3(tmp_path, [SESSION, OTHER], tokens=[adjudication.token(tmp_path, SESSION)])


def test_a_token_for_an_unevaluated_session_refuses(tmp_path, adjudication):
    _write_bars(tmp_path, "iex", SESSION, 2)
    _write_bars(tmp_path, "sip", SESSION, 4)
    with pytest.raises(NotAdmissible, match="not being evaluated"):
        evaluate_k3(tmp_path, [SESSION], tokens=adjudication.tokens(tmp_path, [SESSION, OTHER]))


def test_a_token_does_not_travel_between_corpora(tmp_path, adjudication):
    other_root = tmp_path / "elsewhere"
    other_root.mkdir()
    _write_bars(tmp_path, "iex", SESSION, 2)
    _write_bars(tmp_path, "sip", SESSION, 4)
    with pytest.raises(NotAdmissible, match="does not travel between corpora"):
        evaluate_k3(tmp_path, [SESSION], tokens=[adjudication.token(other_root, SESSION)])


def test_a_non_token_object_is_refused(tmp_path):
    class Impostor:
        root = str(tmp_path.resolve())
        session = SESSION

    with pytest.raises(TypeError, match="not an AdmissibilityToken"):
        validate_tokens(tmp_path, [SESSION], [Impostor()])  # type: ignore[list-item]


# ── evidentiary vs diagnostic is visible in the record ───────────────────────────────────────────

def test_a_diagnostic_result_is_labelled_non_evidentiary(tmp_path):
    _write_bars(tmp_path, "iex", SESSION, 2)
    _write_bars(tmp_path, "sip", SESSION, 4)
    result = evaluate_k3(tmp_path, [SESSION], diagnostic=True)
    assert result.evidentiary is False
    assert "NOT a governed K-value" in result.as_dict()["evidentiary_note"]


def test_a_tokened_k3_result_is_evidentiary(tmp_path, adjudication):
    _write_bars(tmp_path, "iex", SESSION, 2)
    _write_bars(tmp_path, "sip", SESSION, 4)
    result = evaluate_k3(tmp_path, [SESSION], tokens=[adjudication.token(tmp_path, SESSION)])
    assert result.evidentiary is True
    assert result.as_dict()["admissibility_tokens"][0]["verdict"] == str(Verdict.ADMISSIBLE)


def test_the_same_gate_governs_k1(tmp_path, adjudication):
    with pytest.raises(ValueError, match="requires admissibility tokens"):
        evaluate_k1(tmp_path, [SESSION])
    result = evaluate_k1(tmp_path, [SESSION], tokens=[adjudication.token(tmp_path, SESSION)])
    assert result.evidentiary is True
    assert result.outcome is KOutcome.NOT_EVALUABLE
