"""Forward session runner (R4) — one governed observation per eligible session, or an explicit stop.

Pins the four outcomes and the rules that make a daily scheduler safe: eligibility comes from the
authoritative XNYS calendar; re-running a recorded session is a no-op; an eligible session whose
instrument produced no real decision is an INTEGRITY STOP (never a synthesized flat observation, owner
ruling 2026-07-24) while a genuine zero-gross decision records normally; a ledger that disagrees with
committed storage stops the run rather than being repaired; and every stop is recorded outside the
sealed performance and outside `observations/`.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from app.strategies.drift_audit import SeamRecord
from app.validation import forward_window as fw
from app.validation.forward_evaluator import ForwardDecision, InstrumentDecisionState
from app.validation.forward_session_runner import (
    PRE_SESSION_SNAPSHOT,
    STOP_LOG_FILENAME,
    ForwardSessionRunner,
    SessionRunStatus,
)
from app.validation.forward_window import ForwardRunContext
from app.validation.observation_store import Account4StateProbe, committed_observations
from app.validation.shadow_ledger import ShadowLedger

REPO = Path(__file__).resolve().parents[4]
DATA = REPO / "docs/review/momentum_daily/equal_weight_validation"

SESSION_1 = date(2026, 7, 24)                      # Friday — the frozen forward start
SESSION_2 = date(2026, 7, 27)                      # Monday
SESSION_3 = date(2026, 7, 28)
WEEKEND = date(2026, 7, 25)
PRE_START = date(2026, 7, 23)
HOLIDAY = date(2026, 9, 7)                         # Labor Day

DURABLE_ID = "instrument-durable-state-901"
LEDGER_ID = "shadow-ledger-accounting-901"
TREE = "c1efd8e"
MAX_POSITION_PCT = float(fw.FROZEN_CONFIG["max_position_pct"])


def _probe():
    return Account4StateProbe(hold_status="ACTIVE",
                              hold_reason_code="AWAITING_PRODUCTION_SIZING_VALIDATION",
                              hold_rev=2, strategy_status="idle", positions_sha256="0" * 64)


def _price(tk, d):
    return {"AAA": 100.0, "BBB": 50.0, "CCC": 200.0}.get(tk, 75.0)


def _weights(target, gross):
    return {t: min(1.0 / len(target), MAX_POSITION_PCT) * gross for t in target} if target else {}


def _decision(d: date, *, target=("AAA", "BBB"), gross=0.98, trade=True, weights=None, is_seed=False):
    rec = SeamRecord(date=d.isoformat(), scores={}, eligible=tuple(target), ranking=tuple(target),
                     target_names=tuple(target),
                     weights=_weights(target, gross) if weights is None else dict(weights),
                     regime_gross=gross, trade_initiated=trade,
                     trigger="changed" if trade else "reviewed_no_trigger", is_seed=is_seed)
    state = InstrumentDecisionState(
        held=tuple(target), current_weights=_weights(target, gross),
        last_applied_target_weights=_weights(target, gross), prior_applied_gross=gross,
        sessions_since_rebalance=0, weight_drift_threshold=0.02, backstop_days=21)
    return ForwardDecision(record=rec, instrument_identity=fw.PRODUCTION_STRATEGY_COMMIT,
                           durable_state_id=DURABLE_ID, instrument_state=state)


@pytest.fixture
def artifacts():
    dgs3mo = DATA / "data/DGS3MO.csv"
    ledger = DATA / "TrialLedger_v1.0.json"
    if not (dgs3mo.exists() and ledger.exists()):
        pytest.skip("committed artifacts required")
    return dgs3mo, ledger


@pytest.fixture
def context_builder(artifacts):
    dgs3mo, trial_ledger = artifacts

    def build(session: date) -> ForwardRunContext:
        return ForwardRunContext(
            session_date=session, is_nyse_trading_session=True,
            code_commit=fw.VALIDATION_MEASUREMENT_COMMIT,
            benchmark_commits=dict(fw.BENCHMARK_COMMITS), dgs3mo_path=dgs3mo,
            dgs3mo_cutoff=fw.DGS3MO_OBSERVATION_CUTOFF, trial_ledger_path=trial_ledger,
            effective_dsr_trial_count=45, config=dict(fw.FROZEN_CONFIG), ledger_account_id=901,
            ledger_is_shadow_or_separate_paper=True, references_account4_capital=False,
            references_retired_baseline=False)

    return build


def _runner(tmp_path, context_builder, *, provider=None) -> ForwardSessionRunner:
    return ForwardSessionRunner(
        store_dir=tmp_path / "store", ledger_path=tmp_path / "store" / "ledger.json",
        decision_provider=provider or (lambda d: _decision(d)), price_fn=_price,
        account4_probe=_probe, context_builder=context_builder,
        ledger_factory=lambda: ShadowLedger.start(starting_capital=100_000.0,
                                                  turnover_cost_bps=10.0, backstop_days=21,
                                                  weight_drift_pct=0.02),
        deployed_tree_identity=TREE, shadow_ledger_identity=LEDGER_ID)


def _stop_lines(store: Path) -> list[dict]:
    p = store / STOP_LOG_FILENAME
    if not p.exists():
        return []
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _run(runner, session, ts="2026-07-24T20:10:00Z"):
    return runner.run_session(session, run_timestamp=ts)


# ---- eligibility ---------------------------------------------------------------------------------

@pytest.mark.parametrize("session", [WEEKEND, PRE_START, HOLIDAY])
def test_ineligible_dates_are_a_no_op(session, tmp_path, context_builder):
    r = _runner(tmp_path, context_builder)
    res = _run(r, session)
    assert res.status is SessionRunStatus.NOT_ELIGIBLE
    assert res.session_count == 0
    assert not (r.store_dir / "observations").exists()
    assert not r.ledger_path.exists()


# ---- the recording path --------------------------------------------------------------------------

def test_first_eligible_session_opens_the_window_and_books_the_ledger(tmp_path, context_builder):
    r = _runner(tmp_path, context_builder)
    res = _run(r, SESSION_1)
    assert res.status is SessionRunStatus.RECORDED
    assert res.session_count == 1 and res.sequence == 1
    assert r.ledger_path.exists()
    led = ShadowLedger.load(r.ledger_path)
    assert led.state.sessions_processed == 1 and set(led.state.held) == {"AAA", "BBB"}
    assert not (r.store_dir / PRE_SESSION_SNAPSHOT).exists()          # dropped after success
    open_txt = (r.store_dir / "observations" / "000001" / "open.json").read_text(encoding="utf-8")
    assert "strategy_return" not in open_txt and "equity_after" not in open_txt


def test_subsequent_sessions_extend_the_chain(tmp_path, context_builder):
    r = _runner(tmp_path, context_builder)
    _run(r, SESSION_1)
    res = _run(r, SESSION_2, ts="2026-07-27T20:10:00Z")
    assert res.status is SessionRunStatus.RECORDED and res.sequence == 2 and res.session_count == 2
    recs = committed_observations(r.store_dir)
    assert [x.session_date for x in recs] == [SESSION_1.isoformat(), SESSION_2.isoformat()]
    assert recs[1].previous_commit_sha256 == recs[0].commit_sha256
    assert ShadowLedger.load(r.ledger_path).state.sessions_processed == 2


def test_rerunning_a_recorded_session_is_a_no_op(tmp_path, context_builder):
    r = _runner(tmp_path, context_builder)
    _run(r, SESSION_1)
    equity_after_first = ShadowLedger.load(r.ledger_path).state.equity
    res = _run(r, SESSION_1)                                          # scheduler fires twice
    assert res.status is SessionRunStatus.ALREADY_RECORDED
    assert res.session_count == 1
    assert not (r.store_dir / "observations" / "000002").exists()
    assert ShadowLedger.load(r.ledger_path).state.equity == equity_after_first   # not double-booked


def test_seed_session_is_counted(tmp_path, context_builder):
    r = _runner(tmp_path, context_builder, provider=lambda d: _decision(d, is_seed=True))
    _run(r, SESSION_1)
    rec = json.loads((r.store_dir / "observations" / "000001" / "open.json").read_bytes())
    assert rec["seeds"] == 1 and rec["rebalances"] == 1 and rec["orders_submitted"] == 0


def test_no_trade_session_records_zero_rebalances(tmp_path, context_builder):
    r = _runner(tmp_path, context_builder)
    _run(r, SESSION_1)
    r.decision_provider = lambda d: _decision(d, trade=False)
    res = _run(r, SESSION_2, ts="2026-07-27T20:10:00Z")
    assert res.status is SessionRunStatus.RECORDED
    rec = json.loads((r.store_dir / "observations" / "000002" / "open.json").read_bytes())
    assert rec["rebalances"] == 0


# ---- the absent-evaluation ruling -----------------------------------------------------------------

def test_absent_evaluation_is_an_integrity_stop_not_a_flat_observation(tmp_path, context_builder):
    """`capture_seam` yields targets with NO weights when the class returned before `_evaluate`. That
    session was never evaluated, so it must not be recorded as a no-trade day."""
    r = _runner(tmp_path, context_builder)
    _run(r, SESSION_1)
    ledger_before = r.ledger_path.read_bytes()
    r.decision_provider = lambda d: _decision(d, gross=0.0, trade=False, weights={})
    res = _run(r, SESSION_2, ts="2026-07-27T20:10:00Z")
    assert res.status is SessionRunStatus.INTEGRITY_STOP
    assert res.exception_code == "NO_VALID_INSTRUMENT_DECISION"
    assert res.session_count == 1                                     # unchanged
    assert not (r.store_dir / "observations" / "000002").exists()     # nothing committed
    assert r.ledger_path.read_bytes() == ledger_before                # nothing booked durably
    codes = [ln["code"] for ln in _stop_lines(r.store_dir)]
    assert "NO_VALID_INSTRUMENT_DECISION" in codes                    # recorded, outside the record


def test_genuine_zero_gross_decision_records_normally(tmp_path, context_builder):
    """The instrument DID evaluate and chose zero exposure — a real decision, recorded as a session."""
    r = _runner(tmp_path, context_builder,
                provider=lambda d: _decision(d, gross=0.0, trade=True))
    res = _run(r, SESSION_1)
    assert res.status is SessionRunStatus.RECORDED and res.session_count == 1


def test_the_stop_log_lives_outside_observations_and_does_not_disturb_the_chain(
        tmp_path, context_builder):
    r = _runner(tmp_path, context_builder)
    _run(r, SESSION_1)
    r.decision_provider = lambda d: _decision(d, weights={"AAA": 0.9, "BBB": 0.9})   # non-conformant
    _run(r, SESSION_2, ts="2026-07-27T20:10:00Z")
    assert (r.store_dir / STOP_LOG_FILENAME).is_file()
    assert not (r.store_dir / "observations" / STOP_LOG_FILENAME).exists()
    assert len(committed_observations(r.store_dir)) == 1               # chain + count untouched


# ---- durable-state reconciliation: stop, never repair ---------------------------------------------

def test_ledger_ahead_of_the_record_stops_the_run(tmp_path, context_builder):
    r = _runner(tmp_path, context_builder)
    _run(r, SESSION_1)
    led = ShadowLedger.load(r.ledger_path)
    led.state.sessions_processed = 2                                   # booked, commit never landed
    led.save(r.ledger_path)
    res = _run(r, SESSION_2, ts="2026-07-27T20:10:00Z")
    assert res.status is SessionRunStatus.INTEGRITY_STOP
    assert res.exception_code == "LEDGER_AHEAD_OF_RECORD"
    assert not (r.store_dir / "observations" / "000002").exists()


def test_ledger_behind_the_record_stops_the_run(tmp_path, context_builder):
    r = _runner(tmp_path, context_builder)
    _run(r, SESSION_1)
    led = ShadowLedger.load(r.ledger_path)
    led.state.sessions_processed = 0                                   # ledger save never landed
    led.save(r.ledger_path)
    res = _run(r, SESSION_2, ts="2026-07-27T20:10:00Z")
    assert res.exception_code == "LEDGER_BEHIND_RECORD"


def test_missing_ledger_with_an_open_record_stops_the_run(tmp_path, context_builder):
    r = _runner(tmp_path, context_builder)
    _run(r, SESSION_1)
    r.ledger_path.unlink()
    res = _run(r, SESSION_2, ts="2026-07-27T20:10:00Z")
    assert res.exception_code == "LEDGER_UNAVAILABLE"
    assert res.session_count == 1


def test_unreadable_ledger_stops_the_run(tmp_path, context_builder):
    r = _runner(tmp_path, context_builder)
    _run(r, SESSION_1)
    r.ledger_path.write_text("{not json", encoding="utf-8")
    res = _run(r, SESSION_2, ts="2026-07-27T20:10:00Z")
    assert res.exception_code == "LEDGER_UNAVAILABLE"


def test_corrupt_committed_storage_stops_the_run(tmp_path, context_builder):
    r = _runner(tmp_path, context_builder)
    _run(r, SESSION_1)
    (r.store_dir / "observations" / "000001" / "manifest.json").write_bytes(b"{}\n")
    res = _run(r, SESSION_2, ts="2026-07-27T20:10:00Z")
    assert res.exception_code == "COMMITTED_RECORD_INVALID"


def test_out_of_order_session_stops_the_run(tmp_path, context_builder):
    r = _runner(tmp_path, context_builder)
    _run(r, SESSION_1)
    _run(r, SESSION_3, ts="2026-07-28T20:10:00Z")
    res = _run(r, SESSION_2, ts="2026-07-27T20:10:00Z")               # earlier than the last committed
    assert res.exception_code == "SESSION_OUT_OF_ORDER"
    assert res.session_count == 2


def test_stale_pre_session_snapshot_is_recorded_and_the_session_still_runs(tmp_path, context_builder):
    r = _runner(tmp_path, context_builder)
    _run(r, SESSION_1)
    ShadowLedger.load(r.ledger_path).save(r.store_dir / PRE_SESSION_SNAPSHOT)    # crashed attempt
    res = _run(r, SESSION_2, ts="2026-07-27T20:10:00Z")
    assert res.status is SessionRunStatus.RECORDED
    assert "STALE_PRE_SESSION_SNAPSHOT" in res.operational_exceptions
    rec = json.loads((r.store_dir / "observations" / "000002" / "open.json").read_bytes())
    assert rec["operational_exceptions"] == ["STALE_PRE_SESSION_SNAPSHOT"]
    assert "STALE_PRE_SESSION_SNAPSHOT" in [ln["code"] for ln in _stop_lines(r.store_dir)]


# ---- the frozen-binding gate still governs every session ------------------------------------------

def test_config_drift_stops_the_run_without_writing(tmp_path, context_builder):
    def drifted(session: date) -> ForwardRunContext:
        return replace(context_builder(session), config=dict(fw.FROZEN_CONFIG, max_names=7))

    r = _runner(tmp_path, context_builder)
    _run(r, SESSION_1)
    r.context_builder = drifted
    res = _run(r, SESSION_2, ts="2026-07-27T20:10:00Z")
    assert res.exception_code == "OBSERVATION_NOT_COMMITTED"
    assert res.session_count == 1
    assert ShadowLedger.load(r.ledger_path).state.sessions_processed == 1        # not advanced


def test_context_built_for_the_wrong_session_stops_the_run(tmp_path, context_builder):
    r = _runner(tmp_path, context_builder)
    r.context_builder = lambda session: context_builder(SESSION_3)
    res = _run(r, SESSION_1)
    assert res.exception_code == "CONTEXT_SESSION_MISMATCH"
    assert res.session_count == 0
