"""The instrument's own durable book (R5c-2b2).

A once-a-day runner must carry the instrument's deployment lifecycle, positions and equity between
invocations, or every session looks like day one. These tests pin that the book is exact (decimal, not
float), self-verifying, separate from the shadow ledger, and held to the same crash-safety discipline:
committed storage is the source of truth, and a divergence is diagnosed rather than repaired.
"""

from __future__ import annotations

import json
from dataclasses import replace
from decimal import Decimal

import pytest

from app.validation.instrument_state_store import (
    InstrumentBookError,
    InstrumentBookPaths,
    apply_to_adapter,
    assert_genuinely_fresh,
    capture_from_adapter,
    load_instrument_book,
    open_fresh_book,
    reconcile_with_record,
    save_instrument_book,
)

DEPLOYMENT = {"state": "NEVER_DEPLOYED", "_rev": 0, "has_ever_deployed": False,
              "first_deployed_at": None, "active_seed_attempt": None}
SESSION = "2026-07-24"


class _Adapter:
    """The surface the book restores onto and captures from."""

    def __init__(self):
        self._state: dict = {}
        self._positions: dict = {}
        self.equity = Decimal(0)


@pytest.fixture
def book():
    return open_fresh_book(starting_capital=100_000.0, deployment_blob=DEPLOYMENT,
                           committed_count=0)


# ---- opening, saving and reloading -------------------------------------------------------------------

def test_a_fresh_book_starts_at_the_governed_capital(book):
    assert Decimal(book.equity) == Decimal(100_000)     # exact, however it was written
    assert book.positions == {} and book.sessions_recorded == 0
    assert book.state["deployment"]["state"] == "NEVER_DEPLOYED"
    assert len(book.book_digest) == 64


def test_a_fresh_book_is_refused_once_the_record_has_begun():
    with pytest.raises(InstrumentBookError, match="never begun"):
        open_fresh_book(starting_capital=100_000.0, deployment_blob=DEPLOYMENT, committed_count=1)


def test_a_saved_book_round_trips_exactly(book, tmp_path):
    path = tmp_path / "instrument_book.json"
    advanced = replace(book, positions={"MSFT": "19", "F": "450.5"}, equity="99876.54321",
                       sessions_recorded=1, last_session_date=SESSION).with_digest()
    save_instrument_book(advanced, path)
    reloaded = load_instrument_book(path)
    assert reloaded == advanced
    assert reloaded.equity == "99876.54321"                  # exact, not a float round-trip
    assert reloaded.positions["F"] == "450.5"


def test_an_absent_book_is_none_but_a_malformed_one_is_not(tmp_path):
    assert load_instrument_book(tmp_path / "never_written.json") is None
    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{not json", encoding="utf-8")
    with pytest.raises(InstrumentBookError, match="unreadable"):
        load_instrument_book(corrupt)


def test_a_book_modified_outside_the_runner_is_refused(book, tmp_path):
    path = tmp_path / "book.json"
    save_instrument_book(book, path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["equity"] = "999999"                              # digest not recomputed
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(InstrumentBookError, match="fails its own digest"):
        load_instrument_book(path)


def test_a_book_of_another_schema_version_is_refused(book, tmp_path):
    path = tmp_path / "old.json"
    save_instrument_book(book, path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["schema_version"] = 99
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(InstrumentBookError, match="schema version"):
        load_instrument_book(path)


def test_a_failed_save_never_destroys_the_existing_book(book, tmp_path, monkeypatch):
    from app.validation.observation_store import Durability

    path = tmp_path / "book.json"
    save_instrument_book(book, path)
    original = path.read_bytes()

    class _FailFsync(Durability):
        def fsync_file(self, p):
            raise InstrumentBookError("injected fsync failure")

        def fsync_dir(self, p):
            pass

    advanced = replace(book, sessions_recorded=1, last_session_date=SESSION).with_digest()
    with pytest.raises(InstrumentBookError, match="injected"):
        save_instrument_book(advanced, path, durability=_FailFsync())
    assert path.read_bytes() == original                      # the authoritative book survives
    assert not (tmp_path / "book.json.tmp").exists()


# ---- the book is restored onto, and captured from, the instrument's context -------------------------

def test_the_book_restores_and_captures_exactly(book):
    adapter = _Adapter()
    advanced = replace(book, positions={"MSFT": "19"}, equity="98765.4321").with_digest()
    apply_to_adapter(advanced, adapter)
    assert adapter.equity == Decimal("98765.4321")
    assert adapter._positions["MSFT"] == Decimal("19")
    assert adapter._state["deployment"]["state"] == "NEVER_DEPLOYED"

    adapter._positions["AAPL"] = Decimal("3.5")
    captured = capture_from_adapter(adapter, sessions_recorded=1, last_session_date=SESSION)
    assert captured.positions == {"MSFT": "19", "AAPL": "3.5"}
    assert captured.sessions_recorded == 1 and captured.last_session_date == SESSION


def test_open_provenance_carries_shape_not_contents(book):
    d = replace(book, positions={"MSFT": "19"}, equity="1234.5").with_digest().to_open_provenance()
    assert d["position_count"] == 1 and d["state_keys"] == ["deployment"]
    assert len(d["book_digest"]) == 64
    assert "positions" not in d and "equity" not in d         # referenced by digest, not published


# ---- reconciliation with committed storage ----------------------------------------------------------

def test_an_agreeing_book_reconciles(book):
    advanced = replace(book, sessions_recorded=2, last_session_date=SESSION).with_digest()
    reconcile_with_record(advanced, committed_count=2, last_committed_session=SESSION)


def test_a_book_ahead_of_the_record_is_diagnosed(book):
    advanced = replace(book, sessions_recorded=3, last_session_date=SESSION).with_digest()
    with pytest.raises(InstrumentBookError, match="BOOK_AHEAD_OF_RECORD"):
        reconcile_with_record(advanced, committed_count=2, last_committed_session=SESSION)


def test_a_book_behind_the_record_is_diagnosed(book):
    advanced = replace(book, sessions_recorded=1, last_session_date="2026-07-23").with_digest()
    with pytest.raises(InstrumentBookError, match="BOOK_BEHIND_RECORD"):
        reconcile_with_record(advanced, committed_count=2, last_committed_session=SESSION)


def test_matching_counts_with_a_different_last_session_are_diagnosed(book):
    advanced = replace(book, sessions_recorded=2, last_session_date="2026-07-23").with_digest()
    with pytest.raises(InstrumentBookError, match="BOOK_SESSION_MISMATCH"):
        reconcile_with_record(advanced, committed_count=2, last_committed_session=SESSION)


def test_a_fresh_book_reconciles_with_an_empty_record(book):
    reconcile_with_record(book, committed_count=0, last_committed_session=None)


# ---- the book is not the ledger ----------------------------------------------------------------------

def test_the_book_and_the_ledger_are_separate_files(tmp_path):
    paths = InstrumentBookPaths(book_path=tmp_path / "instrument_book.json")
    assert paths.book_path.name != "ledger.json"
    assert paths.pre_session_snapshot != paths.book_path
    assert paths.pre_session_snapshot.name.endswith(".pre-session")


def test_the_book_holds_the_instruments_own_equity_not_the_ledgers(book):
    """They diverge by cumulative cost drag by design — which is why a decision is never validated
    against the ledger, and why the two are persisted separately."""
    instrument = replace(book, equity="100000").with_digest()
    ledger_equity = Decimal("99987.65")                        # after registered turnover cost
    assert Decimal(instrument.equity) != ledger_equity


def test_a_book_carrying_a_float_equity_is_still_exact(tmp_path):
    """Quantities and equity are decimal strings: a float round-trip through JSON would quietly change
    what the instrument decides."""
    book = open_fresh_book(starting_capital=Decimal("100000.005"), deployment_blob=DEPLOYMENT,
                           committed_count=0)
    path = tmp_path / "book.json"
    save_instrument_book(book, path)
    assert load_instrument_book(path).equity == "100000.005"


def test_an_untouched_book_keeps_its_digest_across_a_save_and_load(book, tmp_path):
    path = tmp_path / "book.json"
    save_instrument_book(book, path)
    assert load_instrument_book(path).book_digest == book.book_digest


# ---- the empty-record exception requires a GENUINELY fresh book ---------------------------------------

def test_a_zero_session_book_with_positions_is_refused(book):
    """`sessions_recorded == 0` is a claim about history, not about contents."""
    with_positions = replace(book, positions={"MSFT": "19"}).with_digest()
    with pytest.raises(InstrumentBookError, match="holds 1 position"):
        reconcile_with_record(with_positions, committed_count=0, last_committed_session=None)


def test_a_zero_session_book_with_a_last_session_is_refused(book):
    dated = replace(book, last_session_date=SESSION).with_digest()
    with pytest.raises(InstrumentBookError, match="BOOK_SESSION_MISMATCH|records a last session"):
        reconcile_with_record(dated, committed_count=0, last_committed_session=None)


def test_a_zero_session_book_with_unexpected_durable_keys_is_refused(book):
    """The regime memory and the backstop clock are written by a session that already happened."""
    used = replace(book, state={**book.state, "prev_regime": {"gross": 0.98},
                                "last_review_date": SESSION}).with_digest()
    with pytest.raises(InstrumentBookError, match="only a completed session writes"):
        reconcile_with_record(used, committed_count=0, last_committed_session=None)


def test_a_zero_session_book_with_non_starting_equity_is_refused(book):
    drifted = replace(book, equity="98765.43").with_digest()
    with pytest.raises(InstrumentBookError, match="not the governed starting capital"):
        reconcile_with_record(drifted, committed_count=0, last_committed_session=None,
                              expected_starting_capital=100_000)


def test_a_genuinely_fresh_book_passes(book):
    reconcile_with_record(book, committed_count=0, last_committed_session=None,
                          expected_starting_capital=100_000)
    assert_genuinely_fresh(book, expected_starting_capital=100_000)


def test_freshness_is_only_required_of_an_empty_record(book):
    """A book with a history is exactly what a continuing record needs."""
    continuing = replace(book, positions={"MSFT": "19"}, equity="98765.43", sessions_recorded=2,
                         last_session_date=SESSION).with_digest()
    reconcile_with_record(continuing, committed_count=2, last_committed_session=SESSION,
                          expected_starting_capital=100_000)
