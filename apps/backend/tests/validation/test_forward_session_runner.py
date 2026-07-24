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
from app.validation.chain_witness import Ed25519AnchorSigner, FileExternalAnchorSink
from app.validation.forward_evaluator import ForwardDecision, InstrumentDecisionState
from app.validation.forward_session_runner import (
    PRE_SESSION_SNAPSHOT,
    STOP_LOG_FILENAME,
    ForwardSessionRunner,
    SessionRunStatus,
)
from app.validation.forward_window import ForwardRunContext, IntegrityStop
from app.validation.observation_store import (
    Account4StateProbe,
    Durability,
    committed_observations,
)
from app.validation.production_bindings import PriceUnavailable
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
SNAPSHOT = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
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
                           durable_state_id=DURABLE_ID, instrument_state=state,
                           snapshot_digest=SNAPSHOT)


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


class _StubFinality:
    """The readiness evidence the runner consumes: a verdict, a detail and open provenance."""

    def __init__(self, ready: bool = True, verdict: str = "READY", detail: str = "stub ready"):
        self.ready = ready
        self.verdict = verdict
        self.detail = detail

    def to_open_provenance(self) -> dict:
        return {"verdict": self.verdict, "detail": self.detail, "session_evidence": "stub"}


class _StubReadiness:
    """Stands in for the R5a/R5b gate. `moved` makes the post-decision store re-check fail."""

    def __init__(self, evidence: _StubFinality | None = None, *, raises: bool = False,
                 moved: bool = False):
        self.evidence = evidence or _StubFinality()
        self.raises = raises
        self.moved = moved

    def assess(self, session_date):
        if self.raises:
            raise IntegrityStop("the factor store could not be interrogated")
        return self.evidence

    def verify_unchanged(self, session_date, evidence):
        if self.moved:
            raise IntegrityStop("the factor store changed during session")


_SIGNER = Ed25519AnchorSigner.generate(witness_identity="runner-test-witness")
_VERIFIER = _SIGNER.verifier()


def _runner(tmp_path, context_builder, *, provider=None, readiness=None) -> ForwardSessionRunner:
    return ForwardSessionRunner(
        store_dir=tmp_path / "store", ledger_path=tmp_path / "store" / "ledger.json",
        decision_provider=provider or (lambda d: _decision(d)), price_fn=_price,
        account4_probe=_probe, context_builder=context_builder,
        ledger_factory=lambda: ShadowLedger.start(starting_capital=100_000.0,
                                                  turnover_cost_bps=10.0, backstop_days=21,
                                                  weight_drift_pct=0.02),
        deployed_tree_identity=TREE, shadow_ledger_identity=LEDGER_ID,
        readiness=readiness if readiness is not None else _StubReadiness(),
        expected_snapshot_digest=SNAPSHOT,
        anchor_signer=_SIGNER, anchor_verifier=_VERIFIER,
        external_anchor_sink=FileExternalAnchorSink(tmp_path / "external_witness", identity="ext"))


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
    _run(r, SESSION_2, ts="2026-07-27T20:10:00Z")
    _run(r, SESSION_3, ts="2026-07-28T20:10:00Z")
    res = _run(r, SESSION_2, ts="2026-07-27T21:10:00Z")               # earlier than the last committed
    assert res.exception_code == "SESSION_OUT_OF_ORDER"
    assert res.session_count == 3


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


def test_same_date_retry_after_a_lost_ledger_save_reports_the_mismatch(tmp_path, context_builder):
    """The exact crash this runner exists to surface: observation committed, ledger save lost, scheduler
    retries the SAME date. A healthy-looking ALREADY_RECORDED would defer discovery to a later session."""
    r = _runner(tmp_path, context_builder)
    _run(r, SESSION_1)
    ledger_after_first = r.ledger_path.read_bytes()
    _run(r, SESSION_2, ts="2026-07-27T20:10:00Z")
    r.ledger_path.write_bytes(ledger_after_first)                     # the session-2 save never landed
    res = _run(r, SESSION_2, ts="2026-07-27T21:10:00Z")               # same-date retry
    assert res.status is SessionRunStatus.INTEGRITY_STOP
    assert res.exception_code == "LEDGER_BEHIND_RECORD"
    assert res.session_count == 2
    assert "LEDGER_BEHIND_RECORD" in [ln["code"] for ln in _stop_lines(r.store_dir)]


def test_same_date_retry_with_a_ledger_ahead_reports_the_mismatch(tmp_path, context_builder):
    r = _runner(tmp_path, context_builder)
    _run(r, SESSION_1)
    led = ShadowLedger.load(r.ledger_path)
    led.state.sessions_processed = 2
    led.save(r.ledger_path)
    res = _run(r, SESSION_1)                                          # same date, ledger ahead
    assert res.exception_code == "LEDGER_AHEAD_OF_RECORD"


def test_first_session_crash_before_the_ledger_save_is_reported_on_retry(tmp_path, context_builder):
    """Sequence 1 committed but the ledger was never written: the retry must diagnose it, not open a
    fresh ledger over an existing record."""
    r = _runner(tmp_path, context_builder)
    _run(r, SESSION_1)
    r.ledger_path.unlink()
    res = _run(r, SESSION_1)
    assert res.exception_code == "LEDGER_UNAVAILABLE"
    assert res.session_count == 1


def test_same_date_retry_with_a_consistent_ledger_is_still_a_no_op(tmp_path, context_builder):
    r = _runner(tmp_path, context_builder)
    _run(r, SESSION_1)
    res = _run(r, SESSION_1)
    assert res.status is SessionRunStatus.ALREADY_RECORDED and res.session_count == 1


# ---- one observation per ELIGIBLE session ---------------------------------------------------------

def test_skipping_an_eligible_session_is_refused(tmp_path, context_builder):
    """Monday committed, Tuesday eligible but never run, Wednesday requested → refused, not recorded."""
    r = _runner(tmp_path, context_builder)
    _run(r, SESSION_1)
    _run(r, SESSION_2, ts="2026-07-27T20:10:00Z")                     # Monday 07-27
    res = _run(r, date(2026, 7, 29), ts="2026-07-29T20:10:00Z")       # Wednesday; Tuesday skipped
    assert res.status is SessionRunStatus.INTEGRITY_STOP
    assert res.exception_code == "MISSED_ELIGIBLE_SESSION"
    assert "2026-07-28" in res.detail                                  # names the missed session
    assert res.session_count == 2
    assert not (r.store_dir / "observations" / "000003").exists()
    assert ShadowLedger.load(r.ledger_path).state.sessions_processed == 2


def test_a_weekend_is_not_a_missed_session(tmp_path, context_builder):
    r = _runner(tmp_path, context_builder)
    _run(r, SESSION_1)                                                 # Friday 07-24
    res = _run(r, SESSION_2, ts="2026-07-27T20:10:00Z")               # Monday 07-27
    assert res.status is SessionRunStatus.RECORDED and res.sequence == 2


def test_a_holiday_is_not_a_missed_session(tmp_path, context_builder):
    """Friday 2026-09-04 → Tuesday 2026-09-08 across Labor Day: no false gap."""
    r = _runner(tmp_path, context_builder)
    _run(r, date(2026, 9, 4), ts="2026-09-04T20:10:00Z")
    res = _run(r, date(2026, 9, 8), ts="2026-09-08T20:10:00Z")
    assert res.status is SessionRunStatus.RECORDED and res.sequence == 2


def test_the_first_observation_may_begin_on_any_eligible_session(tmp_path, context_builder):
    """§0 path A: the record starts at the first eligible session after deployment readiness — the
    next-eligible rule governs continuation, not inception."""
    r = _runner(tmp_path, context_builder)
    res = _run(r, date(2026, 8, 14), ts="2026-08-14T20:10:00Z")
    assert res.status is SessionRunStatus.RECORDED and res.sequence == 1 and res.session_count == 1


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


# ---- the stop log uses the injected durability policy ---------------------------------------------

def test_stop_log_creation_fsyncs_the_file_and_its_parent_directory(tmp_path, context_builder):
    class _RecordingDurability(Durability):
        def __init__(self):
            self.files: list[Path] = []
            self.dirs: list[Path] = []

        def fsync_file(self, path: Path) -> None:
            self.files.append(path)

        def fsync_dir(self, path: Path) -> None:
            self.dirs.append(path)

    dur = _RecordingDurability()
    r = _runner(tmp_path, context_builder)
    r.durability = dur
    _run(r, SESSION_1)                                         # a clean session writes no stop log
    log = r.store_dir / STOP_LOG_FILENAME
    assert not log.exists()

    # A stop raised BEFORE the pre-session snapshot isolates the stop log's own durability calls.
    (r.store_dir / "observations" / "000001" / "manifest.json").write_bytes(b"{}\n")
    dur.files.clear()
    dur.dirs.clear()
    res = _run(r, SESSION_2, ts="2026-07-27T20:10:00Z")
    assert res.exception_code == "COMMITTED_RECORD_INVALID"
    assert log in dur.files                                    # the appended bytes are fsynced
    assert r.store_dir in dur.dirs                             # the new directory entry is fsynced

    dur.files.clear()
    dur.dirs.clear()
    _run(r, SESSION_2, ts="2026-07-27T21:10:00Z")              # appends to an existing log
    assert log in dur.files
    assert r.store_dir not in dur.dirs                         # only on creation, not on every append


# ---- the session's data must be proven final before the decision is taken (R5c) ----------------------

def test_no_readiness_gate_configured_refuses(tmp_path, context_builder):
    r = _runner(tmp_path, context_builder)
    r.readiness = None
    res = _run(r, SESSION_1)
    assert res.exception_code == "DATA_READINESS_UNAVAILABLE"
    assert res.session_count == 0
    assert not (r.store_dir / "observations").exists()


@pytest.mark.parametrize("verdict", [
    "NOT_READY_DATA_STALE", "NOT_READY_ADJUSTMENT_UNVERIFIED", "NOT_READY_LOOKBACK_INCOMPLETE",
    "INTEGRITY_STOP_DATA_CONFLICT",
])
def test_an_unready_verdict_becomes_the_stop_code_verbatim(verdict, tmp_path, context_builder):
    """The taxonomy survives into the record: an operator reads why the session did not run, not a
    generic failure."""
    r = _runner(tmp_path, context_builder,
                readiness=_StubReadiness(_StubFinality(ready=False, verdict=verdict,
                                                       detail=f"{verdict} detail")))
    res = _run(r, SESSION_1)
    assert res.status is SessionRunStatus.INTEGRITY_STOP
    assert res.exception_code == verdict
    assert res.session_count == 0
    assert verdict in [ln["code"] for ln in _stop_lines(r.store_dir)]


def test_a_readiness_assessment_that_fails_closed_refuses(tmp_path, context_builder):
    r = _runner(tmp_path, context_builder, readiness=_StubReadiness(raises=True))
    res = _run(r, SESSION_1)
    assert res.exception_code == "DATA_READINESS_UNAVAILABLE"


def test_a_store_that_moves_during_the_session_commits_nothing(tmp_path, context_builder):
    """The decision was taken against data that then changed: nothing is committed and the durable
    ledger still holds the pre-session state."""
    r = _runner(tmp_path, context_builder, readiness=_StubReadiness(moved=True))
    res = _run(r, SESSION_1)
    assert res.exception_code == "DATA_STORE_CHANGED_DURING_SESSION"
    assert res.session_count == 0
    assert not (r.store_dir / "observations" / "000001").exists()
    assert not r.ledger_path.exists()


def test_a_committed_observation_carries_the_readiness_evidence(tmp_path, context_builder):
    r = _runner(tmp_path, context_builder)
    _run(r, SESSION_1)
    rec = json.loads((r.store_dir / "observations" / "000001" / "open.json").read_bytes())
    assert rec["data_finality"]["verdict"] == "READY"
    assert "strategy_return" not in json.dumps(rec["data_finality"])       # still no performance


# ---- every security the ledger accounts for must be markable this session (R5c) ---------------------

def _strict_price(prices: dict):
    """A production-shaped price function: raises for anything it cannot mark."""
    def price(tk, d):
        value = prices.get(tk)
        if value is None:
            raise PriceUnavailable(f"{tk} has no usable closeadj on {d.isoformat()}")
        return value
    return price


def test_a_held_name_without_todays_mark_stops_the_session(tmp_path, context_builder):
    """The name may have left the scoring universe entirely — it is still on the book, so the book
    cannot be valued without carrying a stale price."""
    r = _runner(tmp_path, context_builder)
    _run(r, SESSION_1)                                            # book AAA + BBB
    r.price_fn = _strict_price({"AAA": 100.0})                    # BBB can no longer be marked
    res = _run(r, SESSION_2, ts="2026-07-27T20:10:00Z")
    assert res.exception_code == "NOT_READY_CURRENT_SESSION_MISSING"
    assert "BBB" in res.detail
    assert res.session_count == 1
    assert not (r.store_dir / "observations" / "000002").exists()
    assert ShadowLedger.load(r.ledger_path).state.sessions_processed == 1


def test_a_decision_target_without_todays_mark_stops_the_session(tmp_path, context_builder):
    """Nothing is held yet, so the refusal can only come from the target being sleeved."""
    r = _runner(tmp_path, context_builder,
                provider=lambda d: _decision(d, target=("AAA", "CCC")))
    r.price_fn = _strict_price({"AAA": 100.0})                    # CCC has no mark
    res = _run(r, SESSION_1)
    assert res.exception_code == "NOT_READY_CURRENT_SESSION_MISSING"
    assert res.session_count == 0
    assert not (r.store_dir / "observations").exists()
    assert not r.ledger_path.exists()


@pytest.mark.parametrize("bad", [None, 0.0, -1.0])
def test_a_null_or_nonpositive_held_mark_stops_the_session(bad, tmp_path, context_builder):
    r = _runner(tmp_path, context_builder)
    _run(r, SESSION_1)
    r.price_fn = lambda tk, d: (100.0 if tk == "AAA" else bad)
    res = _run(r, SESSION_2, ts="2026-07-27T20:10:00Z")
    assert res.exception_code == "NOT_READY_CURRENT_SESSION_MISSING"
    assert res.session_count == 1


def test_a_session_with_every_mark_present_records(tmp_path, context_builder):
    r = _runner(tmp_path, context_builder)
    _run(r, SESSION_1)
    r.price_fn = _strict_price({"AAA": 101.0, "BBB": 51.0})
    res = _run(r, SESSION_2, ts="2026-07-27T20:10:00Z")
    assert res.status is SessionRunStatus.RECORDED and res.session_count == 2


def test_a_run_without_an_instrument_snapshot_digest_refuses(tmp_path, context_builder):
    """The runner must know which snapshot this session's decision belongs to before it books it."""
    r = _runner(tmp_path, context_builder)
    r.expected_snapshot_digest = ""
    res = _run(r, SESSION_1)
    assert res.exception_code == "INSTRUMENT_SNAPSHOT_UNAVAILABLE"
    assert res.session_count == 0
    assert not (r.store_dir / "observations").exists()


def test_a_decision_from_another_snapshot_stops_the_session(tmp_path, context_builder):
    r = _runner(tmp_path, context_builder,
                provider=lambda d: replace(_decision(d), snapshot_digest="a" * 64))
    res = _run(r, SESSION_1)
    assert res.exception_code == "NO_VALID_INSTRUMENT_DECISION"
    assert "snapshot" in res.detail
    assert res.session_count == 0


# ---- the durable-book write comes after the observation commits (R5c-2b2) ---------------------------

def test_on_committed_fires_after_a_recorded_session(tmp_path, context_builder):
    fired: list = []
    r = _runner(tmp_path, context_builder)
    r.on_committed = lambda sequence, iso: fired.append((sequence, iso))
    res = _run(r, SESSION_1)
    assert res.status is SessionRunStatus.RECORDED
    assert fired == [(1, SESSION_1.isoformat())]                  # exactly once, with the sequence


def test_on_committed_does_not_fire_when_the_session_stops(tmp_path, context_builder):
    fired: list = []
    r = _runner(tmp_path, context_builder,
                provider=lambda d: _decision(d, weights={"AAA": 0.9, "BBB": 0.9}))  # non-conformant
    r.on_committed = lambda sequence, iso: fired.append((sequence, iso))
    res = _run(r, SESSION_1)
    assert res.status is SessionRunStatus.INTEGRITY_STOP
    assert fired == []                                            # the book is never written on a stop
