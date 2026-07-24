"""Assembly helpers (R5c-2b2): the one-shot snapshot, the immutable evidence binding, the governed
provider-call cardinality, and the instrument-book lifecycle.

The end-to-end wiring is in test_session_orchestration; here each helper is pinned in isolation.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

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
    BarsCallSpec,
    BoundProviderEvidence,
    EvidenceBindingDecisionProvider,
    InstrumentBookLifecycle,
    SnapshotOnce,
)

SESSION = date(2026, 7, 24)
PRIOR = date(2026, 7, 23)
PRIOR_ISO = PRIOR.isoformat()
DEPLOYMENT = {"state": "NEVER_DEPLOYED", "_rev": 0, "has_ever_deployed": False,
              "first_deployed_at": None, "active_seed_attempt": None}


# ---- SnapshotOnce -----------------------------------------------------------------------------------

def test_the_snapshot_is_captured_exactly_once():
    calls = {"n": 0}

    def capture(*a, **k):
        calls["n"] += 1
        return {"snapshot": calls["n"]}

    once = SnapshotOnce(capture)
    first = once("arg")
    assert first == {"snapshot": 1}
    assert once.captured is first
    with pytest.raises(AssemblyError, match="captured more than once"):
        once("again")
    assert calls["n"] == 1                          # the real capture never ran a second time


def test_reading_a_snapshot_before_capture_is_refused():
    once = SnapshotOnce(lambda: None)
    with pytest.raises(AssemblyError, match="no instrument snapshot"):
        _ = once.captured


# ---- the bars-call cardinality ----------------------------------------------------------------------

def _bars_call(symbol: str, n: int, as_of: date = SESSION) -> dict:
    return {"symbol": symbol, "requested_n": n, "as_of": as_of.isoformat()}


SPEC = BarsCallSpec(market_symbol="SPY", regime_window_n=201, exit_confirm_window_n=6,
                    name_read_n=1, allowed_security_symbols=frozenset({"AAA", "BBB"}))


def test_the_governed_bars_call_set_is_accepted():
    # one regime call + the exit-confirmation market read + per-name price reads: the real pattern
    calls = [_bars_call("SPY", 201), _bars_call("SPY", 6), _bars_call("AAA", 1), _bars_call("BBB", 1)]
    SPEC.validate(calls, SESSION)                   # no raise


def test_no_regime_call_is_refused():
    with pytest.raises(AssemblyError, match="0 regime call"):
        SPEC.validate([_bars_call("SPY", 6), _bars_call("AAA", 1)], SESSION)


def test_the_regime_call_must_be_exactly_the_governed_window():
    # ma_sessions itself (200), ma_sessions + 2 (202), and a very large value are all NOT the frozen
    # regime request (market_ma_days + 1 = 201) — each is a different construction and refused, even
    # though 500/100000 carry more than enough history for a 200-session MA.
    for bad_n in (200, 202, 500, 100_000):
        with pytest.raises(AssemblyError, match="only governed market reads"):
            SPEC.validate([_bars_call("SPY", bad_n), _bars_call("AAA", 1)], SESSION)


def test_a_future_as_of_bars_call_is_refused():
    with pytest.raises(AssemblyError, match="not 2026-07-24"):
        SPEC.validate([_bars_call("SPY", 201), _bars_call("AAA", 1, date(2026, 7, 25))], SESSION)


def test_an_exact_duplicate_bars_call_is_refused():
    with pytest.raises(AssemblyError, match="duplicate bars call"):
        SPEC.validate([_bars_call("SPY", 201), _bars_call("AAA", 1), _bars_call("AAA", 1)], SESSION)


def test_an_unrelated_security_is_refused():
    # a symbol outside the session's expected universe/holdings — neither a duplicate nor a regime call
    with pytest.raises(AssemblyError, match="not in the session's expected universe"):
        SPEC.validate([_bars_call("SPY", 201), _bars_call("ZZZ", 1)], SESSION)


def test_a_name_read_at_an_ungoverned_n_is_refused():
    with pytest.raises(AssemblyError, match="not the governed price-read n=1"):
        SPEC.validate([_bars_call("SPY", 201), _bars_call("AAA", 5)], SESSION)


def test_an_exit_confirmation_read_is_forbidden_when_the_spec_carries_no_window():
    spec = BarsCallSpec(market_symbol="SPY", regime_window_n=201, exit_confirm_window_n=None,
                        name_read_n=1, allowed_security_symbols=frozenset({"AAA"}))
    with pytest.raises(AssemblyError, match="only governed market reads"):
        spec.validate([_bars_call("SPY", 201), _bars_call("SPY", 6)], SESSION)


def test_no_bars_call_at_all_is_refused():
    with pytest.raises(AssemblyError, match="no regime/bars call"):
        SPEC.validate([], SESSION)


# ---- the immutable evidence binding -----------------------------------------------------------------

class _EvidenceList:
    def __init__(self):
        self.output_evidence: list[dict] = []


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


def _binding(scores, bars, *, on_call, current: int = 2, allowed_prior=(PRIOR_ISO,)):
    return EvidenceBindingDecisionProvider(
        inner=on_call, scores_provider=scores, bars_provider=bars, bars_call_spec=SPEC,
        expected_current_session_scores_calls=current,
        allowed_prior_score_sessions=tuple(allowed_prior))


def _score(session: date, digest: str = "frame-a") -> dict:
    return {"session_date": session.isoformat(), "frame_digest": digest}


def _score_session_twice(scores, bars, session_date):
    """The frozen current-session pattern: two current-session score reads (`_evaluate` + `capture_seam`)
    sharing one frame, and the single regime bars call."""
    scores.output_evidence.append(_score(session_date))
    scores.output_evidence.append(_score(session_date))
    bars.output_evidence.append(_bars_call("SPY", 201))


def test_the_evidence_digest_is_carried_into_the_immutable_decision():
    scores, bars = _EvidenceList(), _EvidenceList()

    def run(session_date):
        _score_session_twice(scores, bars, session_date)
        return _decision(session_date)

    provider = _binding(scores, bars, on_call=run, allowed_prior=())   # no exit-confirmation window here
    decision = provider(SESSION)
    # the digest is INSIDE the returned decision, not just a side field
    assert decision.input_evidence_digest == provider.bound_evidence.digest()
    assert decision.input_evidence_digest != ""


def test_the_prior_session_lookback_is_allowed_but_the_future_is_not():
    scores, bars = _EvidenceList(), _EvidenceList()

    def run(session_date):
        _score_session_twice(scores, bars, session_date)
        scores.output_evidence.append(_score(PRIOR))          # the exit-confirmation lookback
        return _decision(session_date)

    provider = _binding(scores, bars, on_call=run)
    provider(SESSION)                                          # allowed
    assert len(provider.bound_evidence.scores) == 3

    scores2, bars2 = _EvidenceList(), _EvidenceList()

    def run_future(session_date):
        _score_session_twice(scores2, bars2, session_date)
        scores2.output_evidence.append(_score(date(2026, 7, 25)))   # future
        return _decision(session_date)

    with pytest.raises(AssemblyError, match="see the future"):
        _binding(scores2, bars2, on_call=run_future)(SESSION)


def test_exactly_two_current_session_scores_calls_are_required():
    scores, bars = _EvidenceList(), _EvidenceList()

    def run(session_date):
        scores.output_evidence.append(_score(session_date))   # only ONE current-session read
        bars.output_evidence.append(_bars_call("SPY", 201))
        return _decision(session_date)

    with pytest.raises(AssemblyError, match="scored the session .* 1 time"):
        _binding(scores, bars, on_call=run)(SESSION)


def test_a_third_current_session_scores_call_is_refused():
    scores, bars = _EvidenceList(), _EvidenceList()

    def run(session_date):
        _score_session_twice(scores, bars, session_date)
        scores.output_evidence.append(_score(session_date))   # an extra current-session read
        return _decision(session_date)

    with pytest.raises(AssemblyError, match="scored the session .* 3 time"):
        _binding(scores, bars, on_call=run)(SESSION)


def test_too_many_prior_session_scores_calls_are_refused():
    scores, bars = _EvidenceList(), _EvidenceList()

    def run(session_date):
        _score_session_twice(scores, bars, session_date)
        scores.output_evidence.append(_score(PRIOR))
        scores.output_evidence.append(_score(date(2026, 7, 22)))   # a second prior session
        return _decision(session_date)

    # the governed window admits exactly one prior session
    with pytest.raises(AssemblyError, match="do not exactly match the governed exit-confirmation"):
        _binding(scores, bars, on_call=run, allowed_prior=(PRIOR_ISO,))(SESSION)


def test_an_arbitrary_earlier_date_is_refused():
    """A date-unaware count bound would let a 2020 read pass; the exact-window check refuses it."""
    scores, bars = _EvidenceList(), _EvidenceList()

    def run(session_date):
        _score_session_twice(scores, bars, session_date)
        scores.output_evidence.append(_score(date(2020, 1, 2)))    # not the preceding store session
        return _decision(session_date)

    with pytest.raises(AssemblyError, match="do not exactly match the governed exit-confirmation"):
        _binding(scores, bars, on_call=run, allowed_prior=(PRIOR_ISO,))(SESSION)


def test_a_missing_required_prior_read_is_refused():
    """The window requires one prior read; reading none cannot be the frozen path."""
    scores, bars = _EvidenceList(), _EvidenceList()

    def run(session_date):
        _score_session_twice(scores, bars, session_date)           # current only, no prior lookback
        return _decision(session_date)

    with pytest.raises(AssemblyError, match="do not exactly match the governed exit-confirmation"):
        _binding(scores, bars, on_call=run, allowed_prior=(PRIOR_ISO,))(SESSION)


def test_a_partial_prior_window_is_refused():
    """A three-session window read only at its most-recent session is incomplete, so it is refused."""
    scores, bars = _EvidenceList(), _EvidenceList()
    window = ("2026-07-21", "2026-07-22", "2026-07-23")

    def run(session_date):
        _score_session_twice(scores, bars, session_date)
        scores.output_evidence.append(_score(PRIOR))               # only the newest of the window
        return _decision(session_date)

    with pytest.raises(AssemblyError, match="do not exactly match the governed exit-confirmation"):
        _binding(scores, bars, on_call=run, allowed_prior=window)(SESSION)


def test_the_exact_prior_window_is_accepted():
    """Reading every session of the governed window — no more, no fewer — is accepted."""
    scores, bars = _EvidenceList(), _EvidenceList()
    window = ("2026-07-21", "2026-07-22", "2026-07-23")

    def run(session_date):
        _score_session_twice(scores, bars, session_date)
        for iso in window:
            scores.output_evidence.append(_score(date.fromisoformat(iso)))
        return _decision(session_date)

    provider = _binding(scores, bars, on_call=run, allowed_prior=window)
    provider(SESSION)                                              # no raise
    assert len(provider.bound_evidence.scores) == 5               # 2 current + 3 prior


def test_a_repeated_prior_session_is_refused():
    scores, bars = _EvidenceList(), _EvidenceList()

    def run(session_date):
        _score_session_twice(scores, bars, session_date)
        scores.output_evidence.append(_score(PRIOR))
        scores.output_evidence.append(_score(PRIOR))          # the same earlier close, twice
        return _decision(session_date)

    with pytest.raises(AssemblyError, match="scored a prior session more than once"):
        _binding(scores, bars, on_call=run, allowed_prior=("2026-07-22", PRIOR_ISO))(SESSION)


def test_two_distinct_frames_for_the_session_are_refused():
    scores, bars = _EvidenceList(), _EvidenceList()

    def run(session_date):
        scores.output_evidence.append(_score(session_date, "frame-a"))
        scores.output_evidence.append(_score(session_date, "frame-b"))   # different data, same session
        bars.output_evidence.append(_bars_call("SPY", 201))
        return _decision(session_date)

    with pytest.raises(AssemblyError, match="distinct scored frames"):
        _binding(scores, bars, on_call=run)(SESSION)


def test_no_scores_call_is_refused():
    scores, bars = _EvidenceList(), _EvidenceList()

    def run(session_date):
        bars.output_evidence.append(_bars_call("SPY", 201))
        return _decision(session_date)

    with pytest.raises(AssemblyError, match="no scores call"):
        _binding(scores, bars, on_call=run)(SESSION)


def test_only_this_evaluations_calls_are_bound():
    scores, bars = _EvidenceList(), _EvidenceList()
    scores.output_evidence.append(_score(date(2020, 1, 1)))   # an earlier, unrelated call

    def run(session_date):
        _score_session_twice(scores, bars, session_date)
        return _decision(session_date)

    provider = _binding(scores, bars, on_call=run, allowed_prior=())   # no exit-confirmation window here
    provider(SESSION)
    assert len(provider.bound_evidence.scores) == 2           # not the 2020 call
    assert all(s["session_date"] == SESSION.isoformat() for s in provider.bound_evidence.scores)


def test_the_bound_evidence_open_provenance_carries_the_digest():
    bound = BoundProviderEvidence(session_date=SESSION.isoformat(),
                                  scores=(_score(SESSION),), bars=(_bars_call("SPY", 201),))
    d = bound.to_open_provenance()
    assert d["input_evidence_digest"] == bound.digest()
    assert d["scores_calls"] and d["bars_calls"]


# ---- the instrument-book lifecycle ------------------------------------------------------------------

class _Adapter:
    def __init__(self):
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


def test_the_book_persists_after_commit_and_restores(lifecycle):
    adapter = _Adapter()
    lifecycle.restore(adapter, committed_count=0, last_committed_session=None)
    adapter._positions = {"AAA": Decimal("19")}
    adapter.equity = Decimal("99900")
    assert not lifecycle.book_path.exists()
    lifecycle.persist_after_commit(adapter, sequence=1, session_date=SESSION.isoformat())

    fresh = _Adapter()
    book = lifecycle.restore(fresh, committed_count=1, last_committed_session=SESSION.isoformat())
    assert book.sessions_recorded == 1
    assert fresh._positions == {"AAA": Decimal("19")}


def test_a_book_behind_the_record_stops(lifecycle):
    adapter = _Adapter()
    lifecycle.restore(adapter, committed_count=0, last_committed_session=None)
    lifecycle.persist_after_commit(adapter, sequence=1, session_date=SESSION.isoformat())
    with pytest.raises(InstrumentBookError, match="BOOK_BEHIND_RECORD"):
        lifecycle.restore(_Adapter(), committed_count=2, last_committed_session="2026-07-27")


def test_a_missing_book_on_a_nonempty_record_stops(lifecycle):
    with pytest.raises(InstrumentBookError, match="never begun"):
        lifecycle.restore(_Adapter(), committed_count=3, last_committed_session="2026-07-27")


def test_a_tampered_book_stops(lifecycle):
    book = open_fresh_book(starting_capital=100_000.0, deployment_blob=DEPLOYMENT, committed_count=0)
    save_instrument_book(book, lifecycle.book_path)
    lifecycle.book_path.write_text('{"schema_version": 1, "equity": "9", "positions": {}, '
                                   '"sessions_recorded": 0, "last_session_date": null, '
                                   '"state": {}, "book_digest": "0"}', encoding="utf-8")
    with pytest.raises(InstrumentBookError):
        lifecycle.restore(_Adapter(), committed_count=0, last_committed_session=None)
    assert load_instrument_book  # imported for the digest-verify path exercised above
