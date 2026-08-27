"""The gate: a K-value computed over an inadmissible partition is a number, never evidence.

This is the property the whole package exists to hold. It is enforced structurally rather than by
convention, so these tests probe the structure — can a token be forged, can one be reused across
scopes, can a diagnostic be mistaken for evidence — rather than merely checking that the happy path
sets a flag.
"""

from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from app.research.mdq_eval.gate import NotAdmissible, validate_tokens
from app.research.mdq_eval.k1_materiality import evaluate_k1
from app.research.mdq_eval.k3_completeness import evaluate_k3
from app.research.mdq_eval.results import AdmissibilityToken, KOutcome, _mint_token

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


def _token(root, session: date = SESSION) -> AdmissibilityToken:
    """Mint through the internal construction site — the same one the gate uses on a PASS."""
    return _mint_token(root=str(root.resolve()), session=session, verdict="ADMISSIBLE",
                       assessed_at="2026-08-27T00:00:00Z", admissibility_digest="d" * 64)


# ── the token cannot be forged ───────────────────────────────────────────────────────────────────

def test_a_token_cannot_be_constructed_directly():
    """★ A token anyone could build makes the gate advisory, which is the failure mode being closed."""
    with pytest.raises(TypeError, match="cannot be constructed directly"):
        AdmissibilityToken(root="/x", session=SESSION, verdict="ADMISSIBLE",
                           assessed_at="2026-08-27T00:00:00Z", admissibility_digest="d" * 64)


def test_a_non_token_object_is_refused(tmp_path):
    class Impostor:
        root = str(tmp_path.resolve())
        session = SESSION

    with pytest.raises(TypeError, match="not an AdmissibilityToken"):
        validate_tokens(tmp_path, [SESSION], [Impostor()])  # type: ignore[list-item]


# ── evidence requires a token for exactly this scope ─────────────────────────────────────────────

def test_evaluating_without_tokens_refuses_rather_than_returning_a_number(tmp_path):
    _write_bars(tmp_path, "iex", SESSION, 2)
    _write_bars(tmp_path, "sip", SESSION, 4)
    with pytest.raises(Exception, match="requires admissibility tokens"):
        evaluate_k3(tmp_path, [SESSION])


def test_a_missing_session_token_refuses(tmp_path):
    """★ The laundering path: one admissible day's token must not cover a second, unassessed day."""
    for s in (SESSION, OTHER):
        _write_bars(tmp_path, "iex", s, 2)
        _write_bars(tmp_path, "sip", s, 4)
    with pytest.raises(NotAdmissible, match="no admissibility token"):
        evaluate_k3(tmp_path, [SESSION, OTHER], tokens=[_token(tmp_path, SESSION)])


def test_a_token_for_an_unevaluated_session_refuses(tmp_path):
    """Refusing an EXTRA token is deliberate: a scope mismatch is evidence of a mistake somewhere."""
    _write_bars(tmp_path, "iex", SESSION, 2)
    _write_bars(tmp_path, "sip", SESSION, 4)
    with pytest.raises(NotAdmissible, match="not being evaluated"):
        evaluate_k3(tmp_path, [SESSION],
                    tokens=[_token(tmp_path, SESSION), _token(tmp_path, OTHER)])


def test_a_token_does_not_travel_between_corpora(tmp_path):
    """A token minted under one root must not validate a different root's data."""
    other_root = tmp_path / "elsewhere"
    other_root.mkdir()
    _write_bars(tmp_path, "iex", SESSION, 2)
    _write_bars(tmp_path, "sip", SESSION, 4)
    with pytest.raises(NotAdmissible, match="does not travel between corpora"):
        evaluate_k3(tmp_path, [SESSION], tokens=[_token(other_root, SESSION)])


# ── evidentiary vs diagnostic is visible in the record ───────────────────────────────────────────

def test_a_diagnostic_result_is_labelled_non_evidentiary(tmp_path):
    _write_bars(tmp_path, "iex", SESSION, 2)
    _write_bars(tmp_path, "sip", SESSION, 4)
    result = evaluate_k3(tmp_path, [SESSION], diagnostic=True)
    assert result.evidentiary is False
    assert result.tokens == ()
    assert "NOT a governed K-value" in result.as_dict()["evidentiary_note"]


def test_a_tokened_result_is_evidentiary_and_names_its_tokens(tmp_path):
    _write_bars(tmp_path, "iex", SESSION, 2)
    _write_bars(tmp_path, "sip", SESSION, 4)
    result = evaluate_k3(tmp_path, [SESSION], tokens=[_token(tmp_path)])
    assert result.evidentiary is True
    assert result.tokens and result.tokens[0]["session"] == SESSION.isoformat()
    assert result.tokens[0]["verdict"] == "ADMISSIBLE"


def test_the_same_gate_governs_k1(tmp_path):
    """K1 is behind the identical gate — the rule is per-package, not per-criterion."""
    with pytest.raises(ValueError, match="requires admissibility tokens"):
        evaluate_k1(tmp_path, [SESSION])
    result = evaluate_k1(tmp_path, [SESSION], tokens=[_token(tmp_path)])
    assert result.evidentiary is True
    assert result.outcome is KOutcome.NOT_EVALUABLE  # no governed inputs; see the K1 tests
