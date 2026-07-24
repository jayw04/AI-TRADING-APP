"""Runnable forward session — end to end (R5c-2b2).

Drives the REAL frozen MomentumDaily through the full orchestration against a synthetic store: one
snapshot captured, its digest wired to provider/evaluator/runner, provider evidence bound into the
committed observation, the instrument book persisted after the commit and restored on the next run, and
the single-snapshot and post-commit-durability invariants enforced.
"""

from __future__ import annotations

import json
from dataclasses import replace
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
def runtime(artifacts, tmp_path):
    dgs3mo, trial_ledger = artifacts
    import app.validation.forward_window as fw
    from app.validation.chain_witness import Ed25519AnchorSigner, FileExternalAnchorSink

    def context_builder(session: date) -> ForwardRunContext:
        return ForwardRunContext(
            session_date=session, is_nyse_trading_session=True,
            code_commit=fw.VALIDATION_MEASUREMENT_COMMIT,
            benchmark_commits=dict(fw.BENCHMARK_COMMITS), dgs3mo_path=dgs3mo,
            dgs3mo_cutoff=fw.DGS3MO_OBSERVATION_CUTOFF, trial_ledger_path=trial_ledger,
            effective_dsr_trial_count=45, config=dict(fw.FROZEN_CONFIG), ledger_account_id=901,
            ledger_is_shadow_or_separate_paper=True, references_account4_capital=False,
            references_retired_baseline=False)

    signer = Ed25519AnchorSigner.generate(witness_identity="orchestration-test-witness")
    # the external witness lives OUTSIDE the observation store (store lives at tmp_path/"store")
    sink = FileExternalAnchorSink(tmp_path / "external_witness", identity="ext-test")
    return SessionRuntime(
        store=object(), accessor=_Accessor(), store_identity=STORE_IDENTITY,
        universe_fn=lambda session, n: NAMES[:n], proxy_closes=_proxy_closes(),
        session_dates=SESSIONS, strict_price_fn=_price, account4_probe=_probe,
        context_builder=context_builder, readiness=_StubReadiness(),
        anchor_signer=signer, anchor_verifier=signer.verifier(), external_anchor_sink=sink,
        market_symbol=MARKET)


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


# ---- the governed execution order -------------------------------------------------------------------

def test_the_full_session_order_is_governed(runtime, tmp_path, monkeypatch):
    """The one property Blocker 1 turns on: the instrument snapshot is taken at the pre-evaluation
    boundary — after readiness, the held-name price reads and the pre-session ledger snapshot, and
    immediately before the authoritative Account-4 probe and the evaluation — never earlier. The whole
    governed order is asserted end to end."""
    from app.validation import forward_session_runner as frunner
    from app.validation import session_orchestration as orch
    from app.validation.shadow_ledger import ShadowLedger

    order: list[str] = []

    class _RecReadiness:
        def assess(self, s):
            order.append("readiness")
            return _StubFinality()

        def verify_unchanged(self, s, e):
            order.append("store_unchanged")
            return None

    real_probe = runtime.account4_probe

    def rec_probe():
        order.append("account4_probe")
        return real_probe()

    recorded_runtime = replace(runtime, readiness=_RecReadiness(), account4_probe=rec_probe)

    real_unmarkable = frunner.ForwardSessionRunner._unmarkable

    def rec_unmarkable(self, names, sd):
        order.append("held_reads")
        return real_unmarkable(self, names, sd)

    real_save = ShadowLedger.save

    def rec_save(self, path, **kw):
        order.append("ledger_snapshot" if str(path).endswith(frunner.PRE_SESSION_SNAPSHOT)
                     else "ledger_persist")
        return real_save(self, path, **kw)

    real_capture = orch.capture_instrument_snapshot

    def rec_capture(*a, **k):
        order.append("instrument_snapshot")
        return real_capture(*a, **k)

    real_eval = frunner.ForwardEvaluator.evaluate_session

    def rec_eval(self, sd, pf):
        order.append("evaluate")
        return real_eval(self, sd, pf)

    real_assert = frunner.assert_account4_unchanged

    def rec_assert(a, b):
        order.append("account4_post")
        return real_assert(a, b)

    real_open = frunner.open_first_window_session

    def rec_open(*a, **k):
        order.append("commit")
        return real_open(*a, **k)

    real_writer = orch._book_writer

    def rec_writer(lifecycle, adapter):
        inner = real_writer(lifecycle, adapter)

        def w(seq, iso):
            order.append("book_write")
            return inner(seq, iso)

        return w

    monkeypatch.setattr(frunner.ForwardSessionRunner, "_unmarkable", rec_unmarkable)
    monkeypatch.setattr(ShadowLedger, "save", rec_save)
    monkeypatch.setattr(orch, "capture_instrument_snapshot", rec_capture)
    monkeypatch.setattr(frunner.ForwardEvaluator, "evaluate_session", rec_eval)
    monkeypatch.setattr(frunner, "assert_account4_unchanged", rec_assert)
    monkeypatch.setattr(frunner, "open_first_window_session", rec_open)
    monkeypatch.setattr(orch, "_book_writer", rec_writer)

    result = _run(recorded_runtime, SESSION_1, tmp_path)
    assert result.status is SessionRunStatus.RECORDED

    def first(label: str) -> int:
        assert label in order, f"{label} never happened: {order}"
        return order.index(label)

    # the governed chain, in order
    assert (first("readiness") < first("held_reads") < first("ledger_snapshot")
            < first("instrument_snapshot") < first("account4_probe") < first("evaluate")
            < first("store_unchanged") < first("account4_post") < first("commit")
            < first("book_write"))
    # the instrument book is written only after the ledger persists, which is only after the commit
    assert order.index("commit") < order.index("ledger_persist") < first("book_write")
    # an authoritative post-probe read falls between the reads finishing and the commit
    post_reads = [i for i, lbl in enumerate(order) if lbl == "account4_probe" and i > first("evaluate")]
    assert any(first("store_unchanged") < i < first("commit") for i in post_reads)


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


# ---- the independent chain-tip anchor (R5d) ---------------------------------------------------------

def test_the_committed_tip_is_anchored(runtime, tmp_path):
    import hashlib

    from app.validation.chain_anchor import read_anchors, verify_anchor_consistency

    result = _run(runtime, SESSION_1, tmp_path)
    assert result.status is SessionRunStatus.RECORDED
    anchors = read_anchors(tmp_path / "store")
    assert len(anchors) == 1
    commit_sha = hashlib.sha256(
        (tmp_path / "store" / "observations" / "000001" / "commit.json").read_bytes()).hexdigest()
    assert anchors[0].commit_sha256 == commit_sha    # the anchor witnesses the committed tip
    assert anchors[0].witness_signature              # signed across the trust boundary
    # signatures + the external witness all check (the runner's own pre-commit gate)
    verify_anchor_consistency(tmp_path / "store", verifier=runtime.anchor_verifier,
                              external_sink=runtime.external_anchor_sink)


def test_an_anchor_write_failure_after_commit_is_a_distinct_condition(runtime, tmp_path, monkeypatch):
    """The observation commits, then the independent anchor write fails: the record advanced, so this is
    NOT an ordinary retryable failure — and the observation is committed but unwitnessed."""
    from app.validation import forward_session_runner as frunner
    from app.validation.chain_anchor import AnchorError, read_anchors

    def boom(*a, **k):
        raise AnchorError("injected anchor failure", code="ANCHOR_WRITE_FAILED")

    monkeypatch.setattr(frunner, "append_anchor", boom)
    result = _run(runtime, SESSION_1, tmp_path)
    assert result.status is SessionRunStatus.RECORDED_BUT_ANCHOR_UNWRITTEN
    assert result.sequence == 1 and result.session_count == 1
    assert "do NOT retry" in result.detail
    assert "ANCHOR_WRITE_FAILED_POST_COMMIT" in result.operational_exceptions
    assert len(committed_observations(tmp_path / "store")) == 1   # observation committed
    assert read_anchors(tmp_path / "store") == []                 # but the tip is unwitnessed


def test_a_run_over_an_unwitnessed_tip_stops(runtime, tmp_path):
    """A committed tip whose independent anchor is missing (a crash between the commit and the anchor
    append) is a governed stop on the next run — the anchor is never regenerated from the observation."""
    from app.validation.chain_anchor import ANCHOR_LOG_FILENAME

    _run(runtime, SESSION_1, tmp_path)             # records, anchors, and persists the book
    (tmp_path / "store" / ANCHOR_LOG_FILENAME).write_text("", encoding="utf-8")   # lose the anchor only
    result = _run(runtime, SESSION_2, tmp_path, ts="2026-07-27T20:10:00Z")
    assert result.status is SessionRunStatus.INTEGRITY_STOP
    assert result.exception_code == "ANCHOR_BEHIND_RECORD"        # the tip is unwitnessed — governed stop


def test_a_tampered_anchor_stops_even_a_rerun(runtime, tmp_path):
    """Rewriting the observation chain without rewriting the independent anchor is detected — even by a
    no-op re-run of an already-recorded session."""
    from app.validation.chain_anchor import ANCHOR_LOG_FILENAME

    _run(runtime, SESSION_1, tmp_path)              # records + anchors
    path = tmp_path / "store" / ANCHOR_LOG_FILENAME
    obj = json.loads(path.read_text(encoding="utf-8").split("\n")[0])
    obj["commit_sha256"] = "0" * 64                # the anchor now witnesses a different tip
    path.write_text(json.dumps(obj, sort_keys=True) + "\n", encoding="utf-8")
    result = _run(runtime, SESSION_1, tmp_path)    # a no-op re-run must still stop
    assert result.status is SessionRunStatus.INTEGRITY_STOP
    assert result.exception_code in ("ANCHOR_LOG_INVALID", "ANCHOR_SIGNATURE_INVALID",
                                     "ANCHOR_DIVERGES_FROM_RECORD")


def test_both_post_commit_writes_can_fail_independently(runtime, tmp_path, monkeypatch):
    """Blocker 2: the anchor and the book are INDEPENDENT post-commit attempts — a failure of one does
    not suppress the other, and both failing yields a distinct, precise status that preserves each
    divergence model for adjudication."""
    from app.validation import forward_session_runner as frunner
    from app.validation import session_orchestration as orch
    from app.validation.chain_anchor import AnchorError

    monkeypatch.setattr(frunner, "append_anchor",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AnchorError("x", code="ANCHOR_WRITE_FAILED")))
    monkeypatch.setattr(orch, "_book_writer",
                        lambda lifecycle, adapter: (lambda seq, iso: (_ for _ in ()).throw(
                            OSError("disk full"))))
    result = _run(runtime, SESSION_1, tmp_path)
    assert result.status is SessionRunStatus.RECORDED_BUT_ANCHOR_AND_BOOK_UNPERSISTED
    assert "ANCHOR_WRITE_FAILED_POST_COMMIT" in result.operational_exceptions
    assert "BOOK_WRITE_FAILED_POST_COMMIT" in result.operational_exceptions
    assert len(committed_observations(tmp_path / "store")) == 1   # the observation still committed


def test_a_missing_independent_witness_fails_closed(runtime, tmp_path):
    """Without a configured witness (signer/verifier/external sink) the record cannot be tamper-evidently
    anchored, so the runner refuses to commit rather than leave an unwitnessed record."""
    no_witness = replace(runtime, anchor_signer=None)
    result = _run(no_witness, SESSION_1, tmp_path)
    assert result.status is SessionRunStatus.INTEGRITY_STOP
    assert result.exception_code == "INDEPENDENT_WITNESS_UNAVAILABLE"
    assert len(committed_observations(tmp_path / "store")) == 0   # nothing committed


# ---- witness-implementation failures are normalized into governed results (R5d re-review) ------------

class _RaisingSigner:
    """A signer whose client raises a raw SDK-style exception (as a KMS/HSM client might)."""

    def attest(self, tip):
        raise RuntimeError("KMS AccessDenied")

    def identity(self):
        return "raising-signer"


class _RaisingPublishSink:
    """An external sink that reads fine (so pre-commit passes) but whose publish raises a raw client
    exception (as an S3/Object-Lock client might)."""

    def __init__(self, inner):
        self._inner = inner

    def publish(self, tip, receipt):
        raise RuntimeError("S3 PutObject timeout")

    def read_all(self):
        return self._inner.read_all()

    def identity(self):
        return "raising-publish-sink"


class _RaisingReadSink:
    def publish(self, tip, receipt):
        pass

    def read_all(self):
        raise RuntimeError("S3 ListObjects transport error")

    def identity(self):
        return "raising-read-sink"


def test_a_raw_external_read_failure_becomes_a_governed_stop(runtime, tmp_path):
    """A raw exception from the external sink during pre-run verification is normalized into an integrity
    stop, never allowed to escape run_session()."""
    broken = replace(runtime, external_anchor_sink=_RaisingReadSink())
    result = _run(broken, SESSION_1, tmp_path)
    assert result.status is SessionRunStatus.INTEGRITY_STOP
    assert result.exception_code == "INDEPENDENT_WITNESS_UNAVAILABLE"
    assert len(committed_observations(tmp_path / "store")) == 0


def test_a_raw_signer_failure_does_not_suppress_the_book_write(runtime, tmp_path):
    """The observation has advanced; a raw signer-client exception must not stop the book from persisting.
    The anchor is unwritten, the book is written."""
    broken = replace(runtime, anchor_signer=_RaisingSigner())
    result = _run(broken, SESSION_1, tmp_path)
    assert result.status is SessionRunStatus.RECORDED_BUT_ANCHOR_UNWRITTEN
    assert "ANCHOR_WRITE_FAILED_POST_COMMIT" in result.operational_exceptions
    assert len(committed_observations(tmp_path / "store")) == 1
    assert (tmp_path / "store" / "instrument_book.json").exists()      # the book DID persist


def test_a_raw_sink_publish_failure_does_not_suppress_the_book_write(runtime, tmp_path):
    broken = replace(runtime, external_anchor_sink=_RaisingPublishSink(runtime.external_anchor_sink))
    result = _run(broken, SESSION_1, tmp_path)
    assert result.status is SessionRunStatus.RECORDED_BUT_ANCHOR_UNWRITTEN
    assert len(committed_observations(tmp_path / "store")) == 1
    assert (tmp_path / "store" / "instrument_book.json").exists()      # the book DID persist


def test_a_raw_signer_failure_with_a_failing_book_is_the_combined_status(runtime, tmp_path, monkeypatch):
    from app.validation import session_orchestration as orch

    monkeypatch.setattr(orch, "_book_writer",
                        lambda lifecycle, adapter: (lambda seq, iso: (_ for _ in ()).throw(
                            OSError("disk full"))))
    broken = replace(runtime, anchor_signer=_RaisingSigner())
    result = _run(broken, SESSION_1, tmp_path)
    assert result.status is SessionRunStatus.RECORDED_BUT_ANCHOR_AND_BOOK_UNPERSISTED
    assert "ANCHOR_WRITE_FAILED_POST_COMMIT" in result.operational_exceptions
    assert "BOOK_WRITE_FAILED_POST_COMMIT" in result.operational_exceptions
    assert len(committed_observations(tmp_path / "store")) == 1        # the observation still committed
