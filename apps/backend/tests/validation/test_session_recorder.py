"""Forward-validation sessions 2..N — chained observations through the SAME atomic commit (R3).

Pins the properties that only exist once there is a record to extend: the sequence is derived from
validated storage (never supplied); recording refuses while the window is not open; each observation
binds the previous `commit.json` digest (an append-only chain — an internally-consistent rewrite of an
earlier observation is still detected); session dates must strictly increase (no double-recorded and no
back-dated session); committed sequences must be contiguous; the frozen-binding gate runs on EVERY
session; and Account-4 isolation, strict durability, the per-sequence mutex and the sealed/open
segregation hold exactly as they do for the window-opening observation.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from app.validation import forward_window as fw
from app.validation.first_session import open_first_window_session
from app.validation.forward_window import ForwardRunContext, IntegrityStop
from app.validation.observation_store import (
    Account4StateProbe,
    Durability,
    ObservationCommitError,
    committed_observations,
    committed_session_count,
)
from app.validation.session_recorder import record_forward_session

REPO = Path(__file__).resolve().parents[4]
DATA = REPO / "docs/review/momentum_daily/equal_weight_validation"

SESSION_1 = date(2026, 7, 24)
SESSION_2 = date(2026, 7, 27)
SESSION_3 = date(2026, 7, 28)


def _probe(**over):
    base = dict(hold_status="ACTIVE", hold_reason_code="AWAITING_PRODUCTION_SIZING_VALIDATION",
                hold_rev=2, strategy_status="idle", positions_sha256="0" * 64)
    base.update(over)
    return Account4StateProbe(**base)


def _const_probe(**over):
    p = _probe(**over)
    return lambda: p


class _ChangingProbe:
    """Authoritative probe whose live read changes between the before-call and the after-call."""

    def __init__(self, first: Account4StateProbe, second: Account4StateProbe):
        self._seq = [first, second]
        self._i = 0

    def __call__(self) -> Account4StateProbe:
        p = self._seq[min(self._i, len(self._seq) - 1)]
        self._i += 1
        return p


class _NoopDurability(Durability):
    def fsync_file(self, path: Path) -> None:
        pass

    def fsync_dir(self, path: Path) -> None:
        pass


class _FailFileFsync(_NoopDurability):
    def fsync_file(self, path: Path) -> None:
        raise ObservationCommitError(f"injected file fsync failure: {path.name}")


@pytest.fixture
def ctx():
    dgs3mo = DATA / "data/DGS3MO.csv"
    ledger = DATA / "TrialLedger_v1.0.json"
    if not (dgs3mo.exists() and ledger.exists()):
        pytest.skip("committed artifacts required")
    return ForwardRunContext(
        session_date=SESSION_1, is_nyse_trading_session=True,
        code_commit=fw.VALIDATION_MEASUREMENT_COMMIT, benchmark_commits=dict(fw.BENCHMARK_COMMITS),
        dgs3mo_path=dgs3mo, dgs3mo_cutoff=fw.DGS3MO_OBSERVATION_CUTOFF,
        trial_ledger_path=ledger, effective_dsr_trial_count=45, config=dict(fw.FROZEN_CONFIG),
        ledger_account_id=901, ledger_is_shadow_or_separate_paper=True,
        references_account4_capital=False, references_retired_baseline=False)


def _open(ctx, store, *, probe=None):
    """Commit the governed window-opening observation (sequence 1)."""
    return open_first_window_session(
        ctx, preflight_timestamp="2026-07-24T20:10:00Z",
        deployed_tree_identity="c1efd8e", shadow_ledger_identity="paper-validation-901",
        account4_probe=probe or _const_probe(),
        rebalances=1, orders=5, seeds=1, operational={"cap_breaches": 0},
        sealed_performance={"strategy_return": 0.0137, "benchmark_excess": 0.0041},
        store_dir=store)


def _record(ctx, store, session: date, *, probe=None, sealed=None, operational=None,
            durability=None, timestamp=None):
    return record_forward_session(
        replace(ctx, session_date=session),
        preflight_timestamp=timestamp or f"{session.isoformat()}T20:10:00Z",
        deployed_tree_identity="c1efd8e", shadow_ledger_identity="paper-validation-901",
        account4_probe=probe or _const_probe(),
        rebalances=0, orders=0, seeds=0,
        operational=operational if operational is not None else {"cap_breaches": 0},
        sealed_performance=sealed or {"strategy_return": -0.0042},
        store_dir=store, durability=durability)


def _obs(store, seq: int) -> Path:
    return store / "observations" / f"{seq:06d}"


def _commit(store, seq: int) -> dict:
    return json.loads((_obs(store, seq) / "commit.json").read_bytes())


def _commit_digest(store, seq: int) -> str:
    return hashlib.sha256((_obs(store, seq) / "commit.json").read_bytes()).hexdigest()


# ---- happy path: the record extends, chained, with a storage-derived sequence ---------------------

def test_second_session_records_and_advances_the_count(ctx, tmp_path):
    store = tmp_path / "ledger"
    _open(ctx, store)
    obs, prov, count = _record(ctx, store, SESSION_2)
    assert count == 2 and committed_session_count(store) == 2
    assert prov.observation_sequence == 2                       # derived, not supplied
    assert obs.session_date == SESSION_2.isoformat()
    assert prov.previous_session_date == SESSION_1.isoformat()
    assert prov.account4_unchanged is True
    assert prov.account4_state_digest_before == prov.account4_state_digest_after
    for name in ("open.json", "sealed.bin", "provenance.json", "manifest.json", "commit.json"):
        assert (_obs(store, 2) / name).exists()                 # same committed layout as sequence 1


def test_chain_link_binds_the_previous_commit(ctx, tmp_path):
    store = tmp_path / "ledger"
    _open(ctx, store)
    first_digest = _commit_digest(store, 1)
    _, prov, _ = _record(ctx, store, SESSION_2)
    assert _commit(store, 1)["previous_commit_sha256"] is None  # the chain starts at the first observation
    assert _commit(store, 2)["previous_commit_sha256"] == first_digest
    assert prov.previous_commit_sha256 == first_digest


def test_many_sessions_chain_in_order(ctx, tmp_path):
    store = tmp_path / "ledger"
    _open(ctx, store)
    for i, session in enumerate([SESSION_2, SESSION_3, date(2026, 7, 29)], start=2):
        _, _, count = _record(ctx, store, session)
        assert count == i
    records = committed_observations(store)
    assert [r.sequence for r in records] == [1, 2, 3, 4]
    assert [r.session_date for r in records] == sorted(r.session_date for r in records)
    for prev, cur in zip(records[:-1], records[1:], strict=True):
        assert cur.previous_commit_sha256 == prev.commit_sha256


# ---- the recorder never opens the window --------------------------------------------------------

def test_recording_refuses_while_the_window_is_not_open(ctx, tmp_path):
    store = tmp_path / "ledger"
    with pytest.raises(ObservationCommitError, match="window is not open"):
        _record(ctx, store, SESSION_2)
    assert committed_session_count(store) == 0
    assert not (store / "observations").exists() or not any((store / "observations").iterdir())


# ---- a session may not be recorded twice, nor back-dated ------------------------------------------

def test_same_session_cannot_be_recorded_twice(ctx, tmp_path):
    store = tmp_path / "ledger"
    _open(ctx, store)
    _record(ctx, store, SESSION_2)
    with pytest.raises(ObservationCommitError, match="does not strictly follow"):
        _record(ctx, store, SESSION_2)
    assert committed_session_count(store) == 2                  # unchanged
    assert not _obs(store, 3).exists()


def test_backdated_session_fails_closed(ctx, tmp_path):
    store = tmp_path / "ledger"
    _open(ctx, store)
    _record(ctx, store, SESSION_3)
    with pytest.raises(ObservationCommitError, match="does not strictly follow"):
        _record(ctx, store, SESSION_2)                          # earlier than the last committed session
    assert committed_session_count(store) == 2


# ---- tampering with the committed record is detected ---------------------------------------------

def test_internally_consistent_rewrite_of_an_earlier_observation_breaks_the_chain(ctx, tmp_path):
    """Rewriting observation 1's commit marker so it stays valid ON ITS OWN still breaks the chain:
    observation 2 binds the ORIGINAL commit.json bytes."""
    store = tmp_path / "ledger"
    _open(ctx, store)
    _record(ctx, store, SESSION_2)
    commit1 = _commit(store, 1)
    commit1["session_date"] = "2026-07-20"                      # still earlier than session 2; digests intact
    (_obs(store, 1) / "commit.json").write_bytes(
        (json.dumps(commit1, sort_keys=True, indent=2) + "\n").encode("utf-8"))
    with pytest.raises(IntegrityStop, match="chain is broken"):
        committed_observations(store)
    with pytest.raises(IntegrityStop):                          # and no further session can be recorded
        _record(ctx, store, SESSION_3)


def test_tampered_earlier_observation_stops_further_recording(ctx, tmp_path):
    store = tmp_path / "ledger"
    _open(ctx, store)
    _record(ctx, store, SESSION_2)
    (_obs(store, 1) / "sealed.bin").write_bytes(b'{"strategy_return": 9.99}')
    with pytest.raises(IntegrityStop):
        committed_session_count(store)
    with pytest.raises(IntegrityStop):
        _record(ctx, store, SESSION_3)
    assert not _obs(store, 3).exists()


def test_gap_in_committed_sequences_fails_closed(ctx, tmp_path):
    store = tmp_path / "ledger"
    _open(ctx, store)
    _record(ctx, store, SESSION_2)
    (_obs(store, 2)).rename(_obs(store, 4))                     # 000001 + 000004 — a gap
    with pytest.raises(IntegrityStop, match="not contiguous"):
        committed_session_count(store)
    with pytest.raises(IntegrityStop, match="not contiguous"):
        _record(ctx, store, SESSION_3)


# ---- the frozen-binding gate runs on EVERY session ------------------------------------------------

def test_config_drift_mid_window_fails_closed(ctx, tmp_path):
    store = tmp_path / "ledger"
    _open(ctx, store)
    drifted = dict(fw.FROZEN_CONFIG, max_names=7)
    with pytest.raises(IntegrityStop, match="config drift"):
        _record(replace(ctx, config=drifted), store, SESSION_2)
    assert committed_session_count(store) == 1
    assert not _obs(store, 2).exists()


def test_account4_ledger_mid_window_fails_closed(ctx, tmp_path):
    store = tmp_path / "ledger"
    _open(ctx, store)
    with pytest.raises(IntegrityStop, match="Account 4"):
        _record(replace(ctx, ledger_account_id=4), store, SESSION_2)
    assert committed_session_count(store) == 1


def test_non_trading_session_fails_closed(ctx, tmp_path):
    store = tmp_path / "ledger"
    _open(ctx, store)
    with pytest.raises(IntegrityStop, match="trading session"):
        _record(replace(ctx, is_nyse_trading_session=False), store, SESSION_2)
    assert committed_session_count(store) == 1


# ---- Account 4 must be unchanged across the commit ------------------------------------------------

def test_account4_state_change_across_commit_fails_closed(ctx, tmp_path):
    store = tmp_path / "ledger"
    _open(ctx, store)
    probe = _ChangingProbe(_probe(hold_rev=2), _probe(hold_rev=3))
    with pytest.raises(ObservationCommitError, match="Account 4 state changed"):
        _record(ctx, store, SESSION_2, probe=probe)
    assert committed_session_count(store) == 1
    assert not _obs(store, 2).exists()


def test_retry_is_possible_after_a_pre_publish_failure(ctx, tmp_path):
    store = tmp_path / "ledger"
    _open(ctx, store)
    with pytest.raises(ObservationCommitError, match="Account 4 state changed"):
        _record(ctx, store, SESSION_2, probe=_ChangingProbe(_probe(hold_rev=2), _probe(hold_rev=3)))
    assert not (store / ".commit-locks" / "000002.lock").exists()      # mutex released on failure
    _, prov, count = _record(ctx, store, SESSION_2)
    assert count == 2 and prov.observation_sequence == 2


# ---- durability + mutex, per sequence --------------------------------------------------------------

def test_file_fsync_failure_stops_publication(ctx, tmp_path):
    store = tmp_path / "ledger"
    _open(ctx, store)
    with pytest.raises(ObservationCommitError, match="file fsync failure"):
        _record(ctx, store, SESSION_2, durability=_FailFileFsync())
    assert committed_session_count(store) == 1
    assert not _obs(store, 2).exists()


def test_lock_contention_on_this_sequence_fails_closed(ctx, tmp_path):
    store = tmp_path / "ledger"
    _open(ctx, store)
    lock = store / ".commit-locks" / "000002.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.close(fd)                                                # another owner holds sequence 2
    with pytest.raises(ObservationCommitError, match="publish lock"):
        _record(ctx, store, SESSION_2)
    assert not _obs(store, 2).exists()
    assert committed_session_count(store) == 1


def test_lock_is_released_after_a_successful_record(ctx, tmp_path):
    store = tmp_path / "ledger"
    _open(ctx, store)
    _record(ctx, store, SESSION_2)
    assert not (store / ".commit-locks" / "000002.lock").exists()
    assert _obs(store, 2).exists()


# ---- sealed / open segregation holds for every session ---------------------------------------------

def test_open_record_carries_no_performance(ctx, tmp_path):
    store = tmp_path / "ledger"
    _open(ctx, store)
    _record(ctx, store, SESSION_2, sealed={"strategy_return": -0.0042, "sharpe": 1.31})
    txt = (_obs(store, 2) / "open.json").read_text(encoding="utf-8")
    assert "strategy_return" not in txt and "sharpe" not in txt
    assert "-0.0042" not in txt and "1.31" not in txt


def test_sealed_value_leaking_into_the_open_record_fails_closed(ctx, tmp_path):
    store = tmp_path / "ledger"
    _open(ctx, store)
    with pytest.raises(ObservationCommitError, match="sealed value"):
        _record(ctx, store, SESSION_2,
                operational={"operational_exceptions": ["session return was -0.0042"]},
                sealed={"strategy_return": -0.0042})
    assert committed_session_count(store) == 1
