"""Runnable forward session — end to end (R5c-2b2).

Drives the REAL frozen MomentumDaily through the full orchestration against a synthetic store: one
snapshot captured, its digest wired to provider/evaluator/runner, provider evidence bound into the
committed observation, the instrument book persisted after the commit and restored on the next run, and
the single-snapshot and post-commit-durability invariants enforced.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from app.strategies.deployment_state import initial_blob as _initial_blob
from app.validation.account4_probe import Account4Probe
from app.validation.data_finality import DataReadiness
from app.validation.forward_session_runner import SessionRunStatus
from app.validation.forward_window import ForwardRunContext
from app.validation.observation_store import committed_observations
from app.validation.session_assembly import AssemblyError, SnapshotOnce
from app.validation.session_orchestration import (
    SessionRuntime,
    run_production_session,
)

REPO = Path(__file__).resolve().parents[4]
DATA = REPO / "docs/review/momentum_daily/equal_weight_validation"

SESSION_1 = date(2026, 7, 24)                      # the frozen forward start (a Friday)
SESSION_2 = date(2026, 7, 27)                      # Monday
MARKET = "SPY"
NAMES = [f"N{i:03d}" for i in range(40)]     # >= the frozen 30-name minimum cross-section
STRATEGY_ID = 11
STORE_IDENTITY = "store-identity-under-test"
DEPLOYMENT = _initial_blob().to_dict()       # the real NEVER_DEPLOYED lifecycle blob


def _sessions(end: date, n: int) -> tuple[date, ...]:
    out: list[date] = []
    d = end
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return tuple(sorted(out))


SESSIONS = _sessions(SESSION_2, 320)


def _scores(day: date) -> pd.DataFrame:
    z = [3.0 - i * 0.05 for i in range(len(NAMES))]
    frame = pd.DataFrame({"momentum": [0.4 - i * 0.005 for i in range(len(NAMES))],
                          "winsorized": z, "zscore": z, "rank": list(range(1, len(NAMES) + 1)),
                          "score": z}, index=pd.Index(NAMES, name="ticker"))
    return frame


class _Accessor:
    def momentum_scores(self, as_of=None, *, n=500, lookback_days=105, skip_days=21):
        return _scores(as_of)


def _price(symbol: str, session: date) -> float:
    return 100.0


def _proxy_closes() -> dict[date, float]:
    return {d: 80.0 + 0.2 * i for i, d in enumerate(SESSIONS)}


def _probe() -> Account4Probe:
    return Account4Probe(
        probed_at="2026-07-24T20:09:00Z", account_id=4, broker="alpaca", broker_mode="paper",
        account_label="acct4", strategy_id=STRATEGY_ID, binding_user_id=4, resolved_account_id=4,
        candidate_account_ids=(4,), raw_strategy_status="idle", hold_present=True,
        hold_schema_version=1, hold_status="ACTIVE",
        hold_reason_code="AWAITING_PRODUCTION_SIZING_VALIDATION", hold_rev=2, positions_count=0,
        positions_digest="0" * 64, open_order_count=0, strategy_non_running=True,
        account4_operational_hold_active=True, account4_is_safely_paused_and_held=True,
        comparison_digest="c" * 64)


@pytest.fixture
def artifacts():
    dgs3mo = DATA / "data/DGS3MO.csv"
    ledger = DATA / "TrialLedger_v1.0.json"
    if not (dgs3mo.exists() and ledger.exists()):
        pytest.skip("committed artifacts required")
    return dgs3mo, ledger


@pytest.fixture
def runtime(artifacts):
    dgs3mo, trial_ledger = artifacts
    import app.validation.forward_window as fw

    def context_builder(session: date) -> ForwardRunContext:
        return ForwardRunContext(
            session_date=session, is_nyse_trading_session=True,
            code_commit=fw.VALIDATION_MEASUREMENT_COMMIT,
            benchmark_commits=dict(fw.BENCHMARK_COMMITS), dgs3mo_path=dgs3mo,
            dgs3mo_cutoff=fw.DGS3MO_OBSERVATION_CUTOFF, trial_ledger_path=trial_ledger,
            effective_dsr_trial_count=45, config=dict(fw.FROZEN_CONFIG), ledger_account_id=901,
            ledger_is_shadow_or_separate_paper=True, references_account4_capital=False,
            references_retired_baseline=False)

    return SessionRuntime(
        store=object(), accessor=_Accessor(), store_identity=STORE_IDENTITY,
        universe_fn=lambda session, n: NAMES[:n], proxy_closes=_proxy_closes(),
        session_dates=SESSIONS, strict_price_fn=_price, account4_probe=_probe,
        context_builder=context_builder, readiness=_StubReadiness(), market_symbol=MARKET)


class _StubFinality:
    ready = True
    verdict = DataReadiness.READY
    detail = "stub ready"

    def to_open_provenance(self) -> dict:
        return {"verdict": "READY", "detail": "stub ready"}


class _StubReadiness:
    """The R5a/R5b gate stands in here; R5e wires the real one over the governed store."""

    def assess(self, session_date):
        return _StubFinality()

    def verify_unchanged(self, session_date, evidence):
        return None


def _run(runtime, session, tmp_path, **kw):
    return run_production_session(
        runtime, session, store_dir=tmp_path / "store", ledger_path=tmp_path / "store" / "ledger.json",
        book_path=tmp_path / "store" / "instrument_book.json", strategy_id=STRATEGY_ID,
        shadow_ledger_identity="shadow-901", instrument_durable_state_id="durable-901",
        starting_capital=100_000.0, turnover_cost_bps=10.0, backstop_days=10, weight_drift_pct=0.04,
        deployment_blob=DEPLOYMENT, run_timestamp=kw.pop("ts", "2026-07-24T20:10:00Z"),
        deployed_tree_identity="c1efd8e", regime_source_identity="proxy@test")


# ---- a full recorded session -------------------------------------------------------------------------

def test_a_first_session_runs_end_to_end(runtime, tmp_path):
    result = _run(runtime, SESSION_1, tmp_path)
    assert result.status is SessionRunStatus.RECORDED
    assert result.session_count == 1 and result.sequence == 1

    obs = json.loads((tmp_path / "store" / "observations" / "000001" / "open.json").read_bytes())
    # the decision's provider evidence is in the committed record
    evidence = obs["decision_evidence"]
    assert evidence["input_evidence_digest"]
    # the session's own cross-section is scored (the strategy also reads the prior day for exit
    # confirmation, so >1 scores call is expected and recorded)
    assert any(c["session_date"] == SESSION_1.isoformat() for c in evidence["scores_calls"])
    # exactly one regime call: the market proxy over the MA window
    regime = [c for c in evidence["bars_calls"] if c["symbol"] == MARKET and c["requested_n"] >= 200]
    assert len(regime) == 1
    # still no performance in the open record
    assert "strategy_return" not in json.dumps(obs)

    assert (tmp_path / "store" / "instrument_book.json").exists()    # book persisted after the commit


def test_the_instrument_book_persists_and_reconciles(runtime, tmp_path):
    """Session 1 records and persists the instrument book; a later run restores it and reconciles it
    against the advanced record. (The full second-session evaluation exercises momentum-daily's own
    seed-reconciliation lifecycle, which is covered by that strategy's suite; here the assembly's job is
    to carry and reconcile the book, proven directly.)"""
    _run(runtime, SESSION_1, tmp_path)
    book_path = tmp_path / "store" / "instrument_book.json"
    book_after_1 = json.loads(book_path.read_bytes())
    assert book_after_1["sessions_recorded"] == 1 and book_after_1["last_session_date"] ==         SESSION_1.isoformat()

    from app.validation.instrument_state_store import load_instrument_book, reconcile_with_record
    restored = load_instrument_book(book_path)
    assert restored is not None and restored.book_digest == book_after_1["book_digest"]
    # it reconciles against the record that now holds one observation, and would refuse a mismatch
    reconcile_with_record(restored, committed_count=1, last_committed_session=SESSION_1.isoformat(),
                          expected_starting_capital=100_000.0)


def test_rerunning_a_recorded_session_is_a_no_op(runtime, tmp_path):
    _run(runtime, SESSION_1, tmp_path)
    result = _run(runtime, SESSION_1, tmp_path)
    assert result.status is SessionRunStatus.ALREADY_RECORDED
    assert len(committed_observations(tmp_path / "store")) == 1


# ---- the single-snapshot invariant ------------------------------------------------------------------

def test_a_second_snapshot_capture_is_refused():
    calls = {"n": 0}

    def capture(*a, **k):
        calls["n"] += 1
        return object()

    once = SnapshotOnce(capture)
    once("first")
    with pytest.raises(AssemblyError, match="captured more than once"):
        once("second")
    assert calls["n"] == 1                          # the second capture never reached the real function


# ---- the post-commit durability condition -----------------------------------------------------------

def test_a_book_write_failure_after_commit_is_a_distinct_condition(runtime, tmp_path, monkeypatch):
    """The observation commits, then the book write fails: the record has advanced, so this is NOT an
    ordinary retryable failure."""
    from app.validation import session_orchestration as orch

    def failing_writer(lifecycle, adapter):
        def write(sequence, iso):
            raise OSError("disk full")

        return write

    monkeypatch.setattr(orch, "_book_writer", failing_writer)
    result = _run(runtime, SESSION_1, tmp_path)
    assert result.status is SessionRunStatus.RECORDED_BUT_BOOK_UNPERSISTED
    assert result.sequence == 1 and result.session_count == 1
    assert "do NOT retry" in result.detail
    assert "BOOK_WRITE_FAILED_POST_COMMIT" in result.operational_exceptions
    # the observation is genuinely committed; the book is not
    assert len(committed_observations(tmp_path / "store")) == 1
    assert not (tmp_path / "store" / "instrument_book.json").exists()


def test_the_next_run_after_an_unpersisted_book_stops_for_recovery(runtime, tmp_path, monkeypatch):
    from app.validation import session_orchestration as orch

    monkeypatch.setattr(orch, "_book_writer",
                        lambda lifecycle, adapter: (lambda seq, iso: (_ for _ in ()).throw(
                            OSError("disk full"))))
    _run(runtime, SESSION_1, tmp_path)              # commits the observation, loses the book write
    monkeypatch.undo()
    result = _run(runtime, SESSION_2, tmp_path, ts="2026-07-27T20:10:00Z")
    assert result.status is SessionRunStatus.INTEGRITY_STOP
    assert result.exception_code == "INSTRUMENT_BOOK_DIVERGENCE"
    # the record advanced but the book did not, so the next run stops for governed recovery
    assert "never begun" in result.detail or "BOOK_BEHIND_RECORD" in result.detail
