"""Forward per-session evaluator (R2b) — the fail-closed boundary checks carrying the live production
decision into the shadow ledger. One test per owner boundary check (2026-07-23), plus happy paths and
the structural non-ordering guard.
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
)
from app.validation.forward_window import PRODUCTION_STRATEGY_COMMIT
from app.validation.shadow_ledger import ShadowLedger

DURABLE = "instrument-durable-state-901"
LEDGER_ID = "shadow-ledger-accounting-901"


def _rec(*, date_="2026-07-24", target=("AAA", "BBB"), weights=None, gross=1.0, trade=True):
    w = weights if weights is not None else {t: 1.0 / len(target) for t in target}
    return SeamRecord(date=date_, scores={}, eligible=tuple(target), ranking=tuple(target),
                      target_names=tuple(target), weights=dict(w), regime_gross=gross,
                      trade_initiated=trade, trigger="changed" if trade else "reviewed_no_trigger")


def _decision(rec, *, identity=PRODUCTION_STRATEGY_COMMIT, durable=DURABLE):
    return ForwardDecision(record=rec, instrument_identity=identity, durable_state_id=durable)


def _ledger():
    return ShadowLedger.start(starting_capital=100_000.0, turnover_cost_bps=10.0,
                              backstop_days=21, weight_drift_pct=0.02)


def _evaluator(ledger, provider):
    return ForwardEvaluator(ledger=ledger, decision_provider=provider,
                            shadow_ledger_identity=LEDGER_ID)


def _price(tk, d):
    return {"AAA": 100.0, "BBB": 50.0, "CCC": 200.0}[tk]


# ---- happy path: a valid decision books and advances the count -----------------------------------

def test_valid_decision_is_booked_and_count_advances():
    led = _ledger()
    ev = _evaluator(led, lambda d: _decision(_rec()))
    out = ev.evaluate_session(date(2026, 7, 24), _price)
    assert out.traded is True
    assert led.state.sessions_processed == 1
    assert set(led.state.held) == {"AAA", "BBB"}


def test_valid_no_trade_decision_passes_when_nothing_is_concealed():
    led = _ledger()
    provider = {"d": lambda d: _decision(_rec(date_=d.isoformat()))}
    ev = _evaluator(led, lambda d: provider["d"](d))
    ev.evaluate_session(date(2026, 7, 24), _price)                      # establish held {AAA,BBB}, gross 1.0
    # a genuine no-trade: same members, same gross, no drift, since<backstop
    provider["d"] = lambda d: _decision(_rec(date_=d.isoformat(), trade=False))
    out = ev.evaluate_session(date(2026, 7, 27), _price)
    assert out.traded is False and led.state.sessions_processed == 2


# ---- (1) date must match the session --------------------------------------------------------------

def test_date_mismatch_fails_closed():
    ev = _evaluator(_ledger(), lambda d: _decision(_rec(date_="2026-07-25")))
    with pytest.raises(ForwardEvaluationError, match="!= session"):
        ev.evaluate_session(date(2026, 7, 24), _price)


# ---- (2) provenance must be the frozen production instrument --------------------------------------

def test_wrong_instrument_identity_fails_closed():
    ev = _evaluator(_ledger(), lambda d: _decision(_rec(), identity="deadbeef" * 5))
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


@pytest.mark.parametrize("gross", [float("nan"), float("inf"), -0.5])
def test_invalid_regime_gross_fails_closed(gross):
    ev = _evaluator(_ledger(), lambda d: _decision(_rec(gross=gross)))
    with pytest.raises(ForwardEvaluationError, match="regime_gross"):
        ev.evaluate_session(date(2026, 7, 24), _price)


# ---- (4) trade_initiated=False must conceal no transition ----------------------------------------

def _seed(ev):
    ev.evaluate_session(date(2026, 7, 24), _price)                      # held {AAA,BBB}, gross 1.0, since 0


def test_no_trade_concealing_membership_change_fails_closed():
    led = _ledger()
    provider = {"d": lambda d: _decision(_rec())}
    ev = _evaluator(led, lambda d: provider["d"](d))
    _seed(ev)
    provider["d"] = lambda d: _decision(_rec(date_=d.isoformat(), target=("AAA", "CCC"), trade=False))
    with pytest.raises(ForwardEvaluationError, match="MEMBERSHIP"):
        ev.evaluate_session(date(2026, 7, 27), _price)


def test_no_trade_concealing_regime_transition_fails_closed():
    led = _ledger()
    provider = {"d": lambda d: _decision(_rec())}
    ev = _evaluator(led, lambda d: provider["d"](d))
    _seed(ev)
    provider["d"] = lambda d: _decision(_rec(date_=d.isoformat(), gross=0.6, trade=False))
    with pytest.raises(ForwardEvaluationError, match="REGIME"):
        ev.evaluate_session(date(2026, 7, 27), _price)


def test_no_trade_concealing_backstop_fails_closed():
    led = _ledger()
    provider = {"d": lambda d: _decision(_rec())}
    ev = _evaluator(led, lambda d: provider["d"](d))
    _seed(ev)
    led.state.since = led.backstop_days                                # a backstop is now due
    provider["d"] = lambda d: _decision(_rec(date_=d.isoformat(), trade=False))
    with pytest.raises(ForwardEvaluationError, match="BACKSTOP"):
        ev.evaluate_session(date(2026, 7, 27), _price)


def test_no_trade_concealing_drift_fails_closed():
    led = _ledger()
    provider = {"d": lambda d: _decision(_rec())}
    ev = _evaluator(led, lambda d: provider["d"](d))
    _seed(ev)
    # force a large book drift vs the last target so the no-trade claim is inconsistent
    led.state.sleeves = {"AAA": 90_000.0, "BBB": 10_000.0}
    led.state.equity = 100_000.0
    led.state.target_w = {"AAA": 0.5, "BBB": 0.5}
    provider["d"] = lambda d: _decision(_rec(date_=d.isoformat(), trade=False))
    with pytest.raises(ForwardEvaluationError, match="DRIFT"):
        ev.evaluate_session(date(2026, 7, 27), _price)


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
