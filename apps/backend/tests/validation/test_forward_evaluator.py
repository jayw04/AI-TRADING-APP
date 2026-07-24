"""Forward per-session evaluator (R2b) — the fail-closed boundary checks carrying the live production
decision into the shadow ledger. Gate validation (boundary #4) is against the INSTRUMENT's own
decision-state book; shadow-ledger drift is diagnostic only and never invalidates (owner ruling
2026-07-23). One test per boundary check, plus happy paths and the structural non-ordering guard.
"""

from __future__ import annotations

import ast
from datetime import date
from pathlib import Path

import pytest

from app.strategies.drift_audit import SeamRecord
from app.validation import forward_evaluator as fe_mod
from app.validation.forward_evaluator import (
    ForwardDecision,
    ForwardEvaluationError,
    ForwardEvaluator,
    InstrumentDecisionState,
)
from app.validation.forward_window import FROZEN_CONFIG, PRODUCTION_STRATEGY_COMMIT
from app.validation.shadow_ledger import ShadowLedger

DURABLE = "instrument-durable-state-901"
SNAPSHOT = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
LEDGER_ID = "shadow-ledger-accounting-901"
MAX_POSITION_PCT = float(FROZEN_CONFIG["max_position_pct"])
MAX_NAMES = int(FROZEN_CONFIG["max_names"])
OTHER_FULL_SHA = "deadbeef" * 5                     # 40 hex, not the frozen production commit


def _equal_weight(target, gross):
    """The frozen production sizing: equal weight hard-capped at max_position_pct, gross-scaled.
    The cap binds below 5 names (0.20 each), so the book then runs partly in cash."""
    if not target:
        return {}
    return {t: min(1.0 / len(target), MAX_POSITION_PCT) * gross for t in target}


def _rec(*, date_="2026-07-24", target=("AAA", "BBB"), weights=None, gross=1.0, trade=True):
    w = weights if weights is not None else _equal_weight(target, gross)
    return SeamRecord(date=date_, scores={}, eligible=tuple(target), ranking=tuple(target),
                      target_names=tuple(target), weights=dict(w), regime_gross=gross,
                      trade_initiated=trade, trigger="changed" if trade else "reviewed_no_trigger")


def _istate(*, held=("AAA", "BBB"), current=None, target=None, gross=1.0, since=0,
            drift_thr=0.02, backstop=21):
    tw = target if target is not None else {t: 0.5 for t in held}
    cw = current if current is not None else dict(tw)                   # no drift by default
    return InstrumentDecisionState(
        held=tuple(held), current_weights=cw, last_applied_target_weights=tw,
        prior_applied_gross=gross, sessions_since_rebalance=since,
        weight_drift_threshold=drift_thr, backstop_days=backstop)


def _decision(rec, *, identity=PRODUCTION_STRATEGY_COMMIT, durable=DURABLE, istate=None,
              snapshot=SNAPSHOT):
    return ForwardDecision(record=rec, instrument_identity=identity, durable_state_id=durable,
                           instrument_state=istate or _istate(), snapshot_digest=snapshot)


def _ledger():
    return ShadowLedger.start(starting_capital=100_000.0, turnover_cost_bps=10.0,
                              backstop_days=21, weight_drift_pct=0.02)


def _evaluator(ledger, provider):
    return ForwardEvaluator(ledger=ledger, decision_provider=provider,
                            shadow_ledger_identity=LEDGER_ID,
                            expected_snapshot_digest=SNAPSHOT)


def _price(tk, d):
    return {"AAA": 100.0, "BBB": 50.0, "CCC": 200.0}.get(tk, 75.0)


# ---- happy paths ---------------------------------------------------------------------------------

def test_valid_trade_decision_is_booked_and_count_advances():
    led = _ledger()
    ev = _evaluator(led, lambda d: _decision(_rec()))
    out = ev.evaluate_session(date(2026, 7, 24), _price)
    assert out.traded is True
    assert led.state.sessions_processed == 1
    assert set(led.state.held) == {"AAA", "BBB"}


def test_valid_no_trade_decision_passes_when_instrument_conceals_nothing():
    led = _ledger()
    ev = _evaluator(led, lambda d: _decision(
        _rec(date_=d.isoformat(), trade=False),
        istate=_istate(held=("AAA", "BBB"), gross=1.0, since=3)))       # consistent: no gate fired
    out = ev.evaluate_session(date(2026, 7, 24), _price)
    assert out.traded is False and led.state.sessions_processed == 1


# ---- (1) date must match the session --------------------------------------------------------------

def test_date_mismatch_fails_closed():
    ev = _evaluator(_ledger(), lambda d: _decision(_rec(date_="2026-07-25")))
    with pytest.raises(ForwardEvaluationError, match="!= session"):
        ev.evaluate_session(date(2026, 7, 24), _price)


# ---- (2) provenance must be the frozen production instrument --------------------------------------

def test_wrong_instrument_identity_fails_closed():
    ev = _evaluator(_ledger(), lambda d: _decision(_rec(), identity=OTHER_FULL_SHA))
    with pytest.raises(ForwardEvaluationError, match="instrument identity"):
        ev.evaluate_session(date(2026, 7, 24), _price)


@pytest.mark.parametrize("identity", [
    PRODUCTION_STRATEGY_COMMIT[:1],                                 # one-character prefix
    PRODUCTION_STRATEGY_COMMIT[:7],                                 # abbreviated SHA — not governed
    PRODUCTION_STRATEGY_COMMIT[:12],                                # governed length, but not a full SHA
    PRODUCTION_STRATEGY_COMMIT[:39],                                # one character short
    PRODUCTION_STRATEGY_COMMIT + "0",                               # one character long
    OTHER_FULL_SHA,                                                 # a different full SHA
    "z" * 40,                                                       # non-hex
    PRODUCTION_STRATEGY_COMMIT[:20] + "g" + PRODUCTION_STRATEGY_COMMIT[21:],   # non-hex character
    "", "   ", "\t\n",                                              # empty / whitespace
])
def test_partial_or_malformed_runtime_identity_fails_closed(identity):
    """A prefix is not an identity: the RUNTIME identity must be the full 40-hex commit."""
    ev = _evaluator(_ledger(), lambda d: _decision(_rec(), identity=identity))
    with pytest.raises(ForwardEvaluationError, match="instrument identity"):
        ev.evaluate_session(date(2026, 7, 24), _price)


def test_exact_full_sha_matches_case_insensitively():
    led = _ledger()
    ev = _evaluator(led, lambda d: _decision(_rec(), identity=PRODUCTION_STRATEGY_COMMIT.upper()))
    assert ev.evaluate_session(date(2026, 7, 24), _price).traded is True


@pytest.mark.parametrize("short_len", [12, 20, 39])
def test_governed_short_frozen_binding_accepts_only_the_full_runtime_sha(short_len):
    """A frozen binding stored short (legacy config) is honoured at the governed minimum length — but
    only against a FULL runtime SHA."""
    frozen_short = PRODUCTION_STRATEGY_COMMIT[:short_len]
    led = _ledger()
    ev = ForwardEvaluator(ledger=led, decision_provider=lambda d: _decision(_rec()),
                          shadow_ledger_identity=LEDGER_ID, expected_snapshot_digest=SNAPSHOT,
                          expected_instrument_identity=frozen_short)
    assert ev.evaluate_session(date(2026, 7, 24), _price).traded is True


@pytest.mark.parametrize("short_len", [1, 7, 11])
def test_frozen_binding_shorter_than_the_governed_minimum_fails_closed(short_len):
    ev = ForwardEvaluator(ledger=_ledger(), decision_provider=lambda d: _decision(_rec()),
                          shadow_ledger_identity=LEDGER_ID, expected_snapshot_digest=SNAPSHOT,
                          expected_instrument_identity=PRODUCTION_STRATEGY_COMMIT[:short_len])
    with pytest.raises(ForwardEvaluationError, match="instrument identity"):
        ev.evaluate_session(date(2026, 7, 24), _price)


def test_short_frozen_binding_that_is_not_a_prefix_fails_closed():
    ev = ForwardEvaluator(ledger=_ledger(), decision_provider=lambda d: _decision(_rec()),
                          shadow_ledger_identity=LEDGER_ID, expected_snapshot_digest=SNAPSHOT,
                          expected_instrument_identity=OTHER_FULL_SHA[:16])
    with pytest.raises(ForwardEvaluationError, match="instrument identity"):
        ev.evaluate_session(date(2026, 7, 24), _price)


# ---- (3) weights + regime_gross must be finite and valid -----------------------------------------

@pytest.mark.parametrize("weights", [
    {"AAA": float("nan"), "BBB": 0.5},
    {"AAA": -0.1, "BBB": 0.5},
    {"AAA": 0.7, "BBB": 0.7},                                           # sum > 1
])
def test_invalid_weights_fail_closed(weights):
    ev = _evaluator(_ledger(), lambda d: _decision(_rec(weights=weights)))
    with pytest.raises(ForwardEvaluationError, match="weight"):
        ev.evaluate_session(date(2026, 7, 24), _price)


@pytest.mark.parametrize("gross", [float("nan"), float("inf"), -0.5, 1.5])
def test_invalid_regime_gross_fails_closed(gross):
    ev = _evaluator(_ledger(), lambda d: _decision(_rec(gross=gross)))
    with pytest.raises(ForwardEvaluationError, match="regime_gross"):
        ev.evaluate_session(date(2026, 7, 24), _price)


# ---- (3) the weights must DESCRIBE the stated decision --------------------------------------------

def test_duplicate_target_names_fail_closed():
    ev = _evaluator(_ledger(), lambda d: _decision(
        _rec(target=("AAA", "AAA"), weights={"AAA": 0.2})))
    with pytest.raises(ForwardEvaluationError, match="duplicates"):
        ev.evaluate_session(date(2026, 7, 24), _price)


def test_more_targets_than_frozen_max_names_fail_closed():
    target = tuple(f"T{i}" for i in range(MAX_NAMES + 1))
    ev = _evaluator(_ledger(), lambda d: _decision(_rec(target=target)))
    with pytest.raises(ForwardEvaluationError, match="max_names"):
        ev.evaluate_session(date(2026, 7, 24), _price)


@pytest.mark.parametrize("weights", [
    {"CCC": 0.2, "DDD": 0.2},                       # weights for entirely unrelated names
    {"AAA": 0.2},                                    # a target carries no weight
    {"AAA": 0.2, "BBB": 0.2, "CCC": 0.2},           # a weight has no target
])
def test_weights_that_do_not_describe_the_targets_fail_closed(weights):
    ev = _evaluator(_ledger(), lambda d: _decision(
        _rec(target=("AAA", "BBB"), weights=weights)))
    with pytest.raises(ForwardEvaluationError, match="do not describe the stated decision"):
        ev.evaluate_session(date(2026, 7, 24), _price)


def test_weights_exceeding_the_regime_gross_fail_closed():
    # regime allows 0.60 gross; the record books 0.70
    ev = _evaluator(_ledger(), lambda d: _decision(
        _rec(gross=0.6, weights={"AAA": 0.35, "BBB": 0.35})))
    with pytest.raises(ForwardEvaluationError, match="exceeds the regime-allowed gross"):
        ev.evaluate_session(date(2026, 7, 24), _price)


# ---- (3) registered equal-weight / cap conformance -------------------------------------------------

@pytest.mark.parametrize("weights", [
    {"AAA": 0.25, "BBB": 0.15},                     # unequal (sums to the same 0.40)
    {"AAA": 0.19, "BBB": 0.19},                     # equal but not the capped equal-weight result
    {"AAA": 0.10, "BBB": 0.10},                     # equal, under-invested vs the registered rule
])
def test_non_conformant_sizing_fails_closed(weights):
    ev = _evaluator(_ledger(), lambda d: _decision(
        _rec(target=("AAA", "BBB"), weights=weights)))
    with pytest.raises(ForwardEvaluationError, match="frozen equal-weight result"):
        ev.evaluate_session(date(2026, 7, 24), _price)


@pytest.mark.parametrize("n_names", list(range(1, 6)))
def test_capped_equal_weight_at_every_book_size_is_accepted(n_names):
    """1..5 names: below 5 the 20% cap binds and the book runs partly in cash; at 5 it is fully
    invested to the regime gross."""
    target = tuple(f"T{i}" for i in range(n_names))
    gross = 0.98
    led = _ledger()
    ev = _evaluator(led, lambda d: _decision(_rec(target=target, gross=gross)))
    out = ev.evaluate_session(date(2026, 7, 24), _price)
    assert out.traded is True
    expected = min(1.0 / n_names, MAX_POSITION_PCT) * gross
    assert all(w == pytest.approx(expected) for w in out.record.weights.values())
    assert sum(out.record.weights.values()) <= gross + 1e-9


def test_zero_gross_all_cash_decision_is_accepted():
    ev = _evaluator(_ledger(), lambda d: _decision(_rec(target=("AAA", "BBB"), gross=0.0)))
    out = ev.evaluate_session(date(2026, 7, 24), _price)
    assert out.traded is True and sum(out.record.weights.values()) == 0.0


def test_no_targets_with_no_weights_is_accepted():
    ev = _evaluator(_ledger(), lambda d: _decision(
        _rec(target=(), weights={}, gross=0.15)))
    out = ev.evaluate_session(date(2026, 7, 24), _price)
    assert out.record.weights == {}


# ---- (4) trade_initiated=False conceals nothing — vs the INSTRUMENT book --------------------------

def test_no_trade_concealing_membership_change_fails_closed():
    # instrument holds {AAA,BBB} but this session selected {AAA,CCC} with no trade
    ev = _evaluator(_ledger(), lambda d: _decision(
        _rec(target=("AAA", "CCC"), trade=False), istate=_istate(held=("AAA", "BBB"))))
    with pytest.raises(ForwardEvaluationError, match="MEMBERSHIP"):
        ev.evaluate_session(date(2026, 7, 24), _price)


def test_no_trade_concealing_regime_transition_fails_closed():
    ev = _evaluator(_ledger(), lambda d: _decision(
        _rec(gross=0.6, trade=False), istate=_istate(gross=1.0)))       # gross moved 1.0 -> 0.6
    with pytest.raises(ForwardEvaluationError, match="REGIME"):
        ev.evaluate_session(date(2026, 7, 24), _price)


def test_no_trade_concealing_backstop_fails_closed():
    ev = _evaluator(_ledger(), lambda d: _decision(
        _rec(trade=False), istate=_istate(since=21, backstop=21)))      # backstop due
    with pytest.raises(ForwardEvaluationError, match="BACKSTOP"):
        ev.evaluate_session(date(2026, 7, 24), _price)


def test_no_trade_concealing_instrument_drift_fails_closed():
    # instrument's OWN current vs last-target drift exceeds the threshold, but it declared no trade
    ev = _evaluator(_ledger(), lambda d: _decision(
        _rec(trade=False),
        istate=_istate(current={"AAA": 0.9, "BBB": 0.1}, target={"AAA": 0.5, "BBB": 0.5},
                       drift_thr=0.02)))
    with pytest.raises(ForwardEvaluationError, match="DRIFT"):
        ev.evaluate_session(date(2026, 7, 24), _price)


# ---- shadow-ledger drift is DIAGNOSTIC ONLY — it never invalidates a correct instrument decision --

def test_shadow_ledger_drift_is_diagnostic_only():
    led = _ledger()
    # seed a real trade so the shadow book has positions + a last target
    ev = _evaluator(led, lambda d: _decision(_rec(date_=d.isoformat())))
    ev.evaluate_session(date(2026, 7, 24), _price)
    # force the SHADOW book to be heavily drifted (cost-adjusted overlay), while the INSTRUMENT book is
    # perfectly on-target and declares no trade — this must PASS and merely record the shadow drift.
    led.state.sleeves = {"AAA": 90_000.0, "BBB": 10_000.0}
    led.state.equity = 100_000.0
    led.state.target_w = {"AAA": 0.5, "BBB": 0.5}
    ev.decision_provider = lambda d: _decision(
        _rec(date_=d.isoformat(), trade=False),
        istate=_istate(held=("AAA", "BBB"), current={"AAA": 0.5, "BBB": 0.5},
                       target={"AAA": 0.5, "BBB": 0.5}))                # instrument: NO drift
    out = ev.evaluate_session(date(2026, 7, 27), _price)                # must NOT raise
    assert out.traded is False
    assert ev.shadow_ledger_drift_diagnostics["2026-07-27"] == pytest.approx(0.4)   # recorded, not gating


# ---- (5) exactly one decision per session --------------------------------------------------------

def test_duplicate_session_fails_closed():
    led = _ledger()
    ev = _evaluator(led, lambda d: _decision(_rec(date_=d.isoformat())))
    ev.evaluate_session(date(2026, 7, 24), _price)
    with pytest.raises(ForwardEvaluationError, match="already evaluated"):
        ev.evaluate_session(date(2026, 7, 24), _price)


# ---- (7) durable-state identity must be distinct from the ledger accounting identity --------------

def test_durable_state_id_equal_to_ledger_id_fails_closed():
    ev = _evaluator(_ledger(), lambda d: _decision(_rec(), durable=LEDGER_ID))
    with pytest.raises(ForwardEvaluationError, match="DISTINCT"):
        ev.evaluate_session(date(2026, 7, 24), _price)


# ---- (6) structural: the evaluator imports no order path -----------------------------------------

def test_forward_evaluator_imports_no_order_path():
    tree = ast.parse(Path(fe_mod.__file__).read_text(encoding="utf-8"))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules += [n.name for n in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    forbidden = ("order_router", "broker", "alpaca", "services.order")
    hits = [m for m in modules if any(f in m for f in forbidden)]
    assert not hits, f"forward evaluator must be non-ordering; forbidden imports: {hits}"


# ---- (9) the decision must belong to THIS run's instrument snapshot (R5c-2a review) -----------------

def test_an_evaluator_without_an_expected_snapshot_digest_refuses():
    """Carrying a digest is not checking one: with no expected digest configured, a decision cannot be
    tied to the state it was taken under, so nothing may be booked."""
    ev = ForwardEvaluator(ledger=_ledger(), decision_provider=lambda d: _decision(_rec()),
                          shadow_ledger_identity=LEDGER_ID)
    with pytest.raises(ForwardEvaluationError, match="no expected instrument-snapshot digest"):
        ev.evaluate_session(date(2026, 7, 24), _price)


def test_a_decision_without_a_snapshot_digest_is_refused():
    ev = _evaluator(_ledger(), lambda d: _decision(_rec(), snapshot=""))
    with pytest.raises(ForwardEvaluationError, match="carries no instrument-snapshot digest"):
        ev.evaluate_session(date(2026, 7, 24), _price)


@pytest.mark.parametrize("digest", [
    "a" * 64,                                    # another run's snapshot
    SNAPSHOT[:-1] + "0",                         # one character off
    "   ",                                       # whitespace
])
def test_a_decision_from_another_snapshot_is_refused(digest):
    ev = _evaluator(_ledger(), lambda d: _decision(_rec(), snapshot=digest))
    with pytest.raises(ForwardEvaluationError, match="snapshot"):
        ev.evaluate_session(date(2026, 7, 24), _price)


def test_the_exact_run_snapshot_digest_is_accepted():
    led = _ledger()
    out = _evaluator(led, lambda d: _decision(_rec())).evaluate_session(date(2026, 7, 24), _price)
    assert out.traded is True and led.state.sessions_processed == 1


def test_a_genuine_zero_gross_decision_with_the_correct_digest_books():
    led = _ledger()
    ev = _evaluator(led, lambda d: _decision(_rec(target=("AAA", "BBB"), gross=0.0)))
    out = ev.evaluate_session(date(2026, 7, 24), _price)
    assert out.traded is True and sum(out.record.weights.values()) == 0.0
