"""Runnable forward session — the assembly (R5c-2b2).

Pins the three things the assembly owns that no component owns alone: the single snapshot digest that
ties provider/evaluator/runner together; the STRUCTURAL binding of the exact provider calls the one
evaluation made (by call-count delta, not a mutable last-field); and the book lifecycle whose write
comes after the observation and whose crash window is BOOK_BEHIND_RECORD.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.strategies.drift_audit import SeamRecord
from app.validation.decision_provider import ForwardDecision, InstrumentDecisionState
from app.validation.instrument_state_store import (
    InstrumentBookError,
    load_instrument_book,
    open_fresh_book,
    save_instrument_book,
)
from app.validation.session_assembly import (
    AssemblyError,
    EvidenceBindingDecisionProvider,
    InstrumentBookLifecycle,
    assert_single_snapshot,
)

SESSION = date(2026, 7, 24)
DEPLOYMENT = {"state": "NEVER_DEPLOYED", "_rev": 0, "has_ever_deployed": False,
              "first_deployed_at": None, "active_seed_attempt": None}


class _EvidenceList:
    """A provider stand-in: an append-only evidence list, one entry per call."""

    def __init__(self, calls_per_invocation: int = 1, kind: str = "scores"):
        self.output_evidence: list[dict] = []
        self._n = calls_per_invocation
        self._kind = kind

    def record(self, session_date: date) -> None:
        for _ in range(self._n):
            key = "session_date" if self._kind == "scores" else "as_of"
            self.output_evidence.append({key: session_date.isoformat(), "kind": self._kind})


def _decision(session_date: date, *, snapshot="d" * 64) -> ForwardDecision:
    rec = SeamRecord(date=session_date.isoformat(), scores={}, eligible=("AAA",), ranking=("AAA",),
                     target_names=("AAA",), weights={"AAA": 0.2}, regime_gross=1.0,
                     trade_initiated=True, trigger="changed")
    state = InstrumentDecisionState(held=("AAA",), current_weights={"AAA": 0.2},
                                    last_applied_target_weights={"AAA": 0.2}, prior_applied_gross=1.0,
                                    sessions_since_rebalance=0, weight_drift_threshold=0.02,
                                    backstop_days=10)
    return ForwardDecision(record=rec, instrument_identity="x", durable_state_id="durable",
                           instrument_state=state, snapshot_digest=snapshot)


# ---- structural evidence binding --------------------------------------------------------------------

def _binding(scores, bars, *, expected_scores=1):
    def inner(session_date):
        scores.record(session_date)
        bars.record(session_date)
        return _decision(session_date)

    return EvidenceBindingDecisionProvider(inner=inner, scores_provider=scores, bars_provider=bars,
                                           expected_scores_calls=expected_scores)


def test_it_binds_exactly_this_evaluations_provider_calls():
    scores, bars = _EvidenceList(kind="scores"), _EvidenceList(kind="bars")
    scores.output_evidence.append({"session_date": "2020-01-01", "kind": "scores"})   # an earlier call
    provider = _binding(scores, bars)
    provider(SESSION)
    assert len(provider.bound_evidence.scores) == 1                # only THIS call, not the earlier one
    assert provider.bound_evidence.scores[0]["session_date"] == SESSION.isoformat()
    assert len(provider.bound_evidence.bars) == 1


def test_an_extra_scores_call_during_evaluation_is_refused():
    scores, bars = _EvidenceList(calls_per_invocation=2, kind="scores"), _EvidenceList(kind="bars")
    with pytest.raises(AssemblyError, match="made 2 scores call"):
        _binding(scores, bars)(SESSION)


def test_a_missing_scores_call_is_refused():
    scores, bars = _EvidenceList(calls_per_invocation=0, kind="scores"), _EvidenceList(kind="bars")
    with pytest.raises(AssemblyError, match="made 0 scores call"):
        _binding(scores, bars)(SESSION)


def test_a_missing_bars_call_is_refused():
    scores, bars = _EvidenceList(kind="scores"), _EvidenceList(calls_per_invocation=0, kind="bars")
    with pytest.raises(AssemblyError, match="no regime/bars call"):
        _binding(scores, bars)(SESSION)


def test_a_provider_call_carrying_a_different_session_is_refused():
    scores, bars = _EvidenceList(kind="scores"), _EvidenceList(kind="bars")

    def inner(session_date):
        scores.output_evidence.append({"session_date": "2020-01-01", "kind": "scores"})
        bars.record(session_date)
        return _decision(session_date)

    provider = EvidenceBindingDecisionProvider(inner=inner, scores_provider=scores,
                                               bars_provider=bars)
    with pytest.raises(AssemblyError, match="different session in its evidence"):
        provider(SESSION)


def test_the_bound_evidence_is_open_provenance():
    scores, bars = _EvidenceList(kind="scores"), _EvidenceList(kind="bars")
    provider = _binding(scores, bars)
    provider(SESSION)
    d = provider.bound_evidence.to_open_provenance()
    assert d["scores_calls"][0]["session_date"] == SESSION.isoformat()
    assert d["bars_calls"][0]["kind"] == "bars"


# ---- the single snapshot ties the run together ------------------------------------------------------

def test_a_snapshot_without_a_digest_is_refused():
    class _NoDigest:
        snapshot_digest = ""

    with pytest.raises(AssemblyError, match="no digest"):
        assert_single_snapshot(_NoDigest())


def test_a_snapshot_with_a_digest_passes():
    class _Snap:
        snapshot_digest = "a" * 64

    assert_single_snapshot(_Snap())          # no raise


# ---- the instrument book lifecycle ------------------------------------------------------------------

class _Adapter:
    def __init__(self):
        from decimal import Decimal

        self._state: dict = {}
        self._positions: dict = {}
        self.equity = Decimal(0)


@pytest.fixture
def lifecycle(tmp_path):
    return InstrumentBookLifecycle(book_path=tmp_path / "instrument_book.json",
                                   starting_capital=100_000.0, deployment_blob=DEPLOYMENT)


def test_a_first_session_opens_a_fresh_book(lifecycle):
    adapter = _Adapter()
    book = lifecycle.restore(adapter, committed_count=0, last_committed_session=None)
    assert book.sessions_recorded == 0 and adapter._positions == {}
    assert adapter._state["deployment"]["state"] == "NEVER_DEPLOYED"


def test_the_book_is_persisted_only_after_the_commit(lifecycle):
    from decimal import Decimal

    adapter = _Adapter()
    lifecycle.restore(adapter, committed_count=0, last_committed_session=None)
    adapter._positions = {"AAA": Decimal("19")}
    adapter.equity = Decimal("99900")
    assert not lifecycle.book_path.exists()                       # nothing written before commit
    book = lifecycle.persist_after_commit(adapter, sequence=1, session_date=SESSION.isoformat())
    assert lifecycle.book_path.exists()
    reloaded = load_instrument_book(lifecycle.book_path)
    assert reloaded == book and reloaded.sessions_recorded == 1
    assert reloaded.positions == {"AAA": "19"}


def test_a_continuing_session_restores_the_saved_book(lifecycle):
    from decimal import Decimal

    adapter = _Adapter()
    lifecycle.restore(adapter, committed_count=0, last_committed_session=None)
    adapter._positions = {"AAA": Decimal("19")}
    lifecycle.persist_after_commit(adapter, sequence=1, session_date=SESSION.isoformat())

    fresh_adapter = _Adapter()
    book = lifecycle.restore(fresh_adapter, committed_count=1,
                             last_committed_session=SESSION.isoformat())
    assert book.sessions_recorded == 1
    assert fresh_adapter._positions == {"AAA": Decimal("19")}     # the book survived the restart


def test_a_book_behind_the_record_stops_the_run(lifecycle):
    """The crash window: the observation committed but the book write was lost."""
    from decimal import Decimal

    adapter = _Adapter()
    lifecycle.restore(adapter, committed_count=0, last_committed_session=None)
    adapter._positions = {"AAA": Decimal("19")}
    lifecycle.persist_after_commit(adapter, sequence=1, session_date=SESSION.isoformat())
    # a SECOND observation committed, but its book write never landed → book still at 1, record at 2
    with pytest.raises(InstrumentBookError, match="BOOK_BEHIND_RECORD"):
        lifecycle.restore(_Adapter(), committed_count=2, last_committed_session="2026-07-27")


def test_a_fresh_book_is_refused_once_the_record_has_begun(lifecycle):
    """A record with observations cannot continue from a missing book on a fresh open."""
    with pytest.raises(InstrumentBookError, match="never begun"):
        lifecycle.restore(_Adapter(), committed_count=3, last_committed_session="2026-07-27")


def test_a_tampered_book_on_disk_stops_the_run(lifecycle):
    book = open_fresh_book(starting_capital=100_000.0, deployment_blob=DEPLOYMENT, committed_count=0)
    save_instrument_book(book, lifecycle.book_path)
    lifecycle.book_path.write_text('{"schema_version": 1, "equity": "9", "positions": {}, '
                                   '"sessions_recorded": 0, "last_session_date": null, '
                                   '"state": {}, "book_digest": "0"}', encoding="utf-8")
    with pytest.raises(InstrumentBookError):
        lifecycle.restore(_Adapter(), committed_count=0, last_committed_session=None)
