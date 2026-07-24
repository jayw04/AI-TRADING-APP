"""Forward-validation first observation — atomic directory-commit + full provenance (PREREG v1.0 §0/§5).

Pins the owner ruling of 2026-07-23 (second CHANGES REQUESTED): the observation commits as ONE atomic,
no-overwrite directory publish rooted by an immutable commit.json marker; the session count is derived
from FULLY VALIDATED committed storage (corrupt dirs fail closed); Account 4 is re-probed authoritatively
AFTER staging and must equal the before-probe; every staged file (provenance included) is digest-verified
against the manifest and the commit root; fsync failures fail closed (strict durability); the publish
refuses to overwrite from the publish operation itself; and the publish lock is a mutex released on success.
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
from app.validation.first_session import (
    Account4StateProbe,
    Durability,
    WindowOpenError,
    assert_open_record_has_no_sealed_content,
    committed_session_count,
    open_first_window_session,
    publish_no_overwrite,
    validate_committed_observation,
)
from app.validation.forward_window import ForwardRunContext, IntegrityStop

REPO = Path(__file__).resolve().parents[4]
DATA = REPO / "docs/review/momentum_daily/equal_weight_validation"


def _probe(**over):
    base = dict(hold_status="ACTIVE", hold_reason_code="AWAITING_PRODUCTION_SIZING_VALIDATION",
                hold_rev=2, strategy_status="idle", positions_sha256="0" * 64)
    base.update(over)
    return Account4StateProbe(**base)


def _const_probe(**over):
    """An authoritative probe callable that always reads the same (unchanged) Account-4 state."""
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
        raise WindowOpenError(f"injected file fsync failure: {path.name}")


class _FailDirFsync(_NoopDurability):
    def __init__(self, match: str):
        self.match = match

    def fsync_dir(self, path: Path) -> None:
        if self.match in str(path):
            raise WindowOpenError(f"injected dir fsync failure: {path}")


@pytest.fixture
def ctx():
    dgs3mo = DATA / "data/DGS3MO.csv"
    ledger = DATA / "TrialLedger_v1.0.json"
    if not (dgs3mo.exists() and ledger.exists()):
        pytest.skip("committed artifacts required")
    return ForwardRunContext(
        session_date=date(2026, 7, 24), is_nyse_trading_session=True,
        code_commit=fw.VALIDATION_MEASUREMENT_COMMIT, benchmark_commits=dict(fw.BENCHMARK_COMMITS),
        dgs3mo_path=dgs3mo, dgs3mo_cutoff=fw.DGS3MO_OBSERVATION_CUTOFF,
        trial_ledger_path=ledger, effective_dsr_trial_count=45, config=dict(fw.FROZEN_CONFIG),
        ledger_account_id=901, ledger_is_shadow_or_separate_paper=True,
        references_account4_capital=False, references_retired_baseline=False)


def _open(ctx, store_dir, *, probe=None, sealed=None, durability=None):
    return open_first_window_session(
        ctx, preflight_timestamp="2026-07-24T20:10:00Z",
        deployed_tree_identity="c1efd8e", shadow_ledger_identity="paper-validation-901",
        account4_probe=probe or _const_probe(),
        rebalances=1, orders=5, seeds=1, operational={"cap_breaches": 0},
        sealed_performance=sealed or {"strategy_return": 0.0137, "benchmark_excess": 0.0041},
        store_dir=store_dir, durability=durability)


def _obs(store_dir):
    return store_dir / "observations" / "000001"


def _lock(store_dir):
    return store_dir / ".commit-locks" / "000001.lock"


# ---- happy path: one atomic directory commit, count 0 → 1, full provenance -----------------------

def test_first_observation_opens_the_window_atomically(ctx, tmp_path):
    store = tmp_path / "ledger"
    obs, prov, new_count = _open(ctx, store)
    assert new_count == 1                                        # storage-derived operational transition
    assert committed_session_count(store) == 1
    assert prov.observation_sequence == 1
    assert prov.deployed_tree_identity == "c1efd8e"
    assert prov.shadow_ledger_identity == "paper-validation-901"
    assert prov.preflight_execution_timestamp == "2026-07-24T20:10:00Z"
    assert len(prov.open_record_sha256) == 64 and len(prov.sealed_payload_sha256) == 64
    assert prov.account4_unchanged is True
    assert prov.account4_state_digest_before == prov.account4_state_digest_after
    d = _obs(store)
    for name in ("open.json", "sealed.bin", "provenance.json", "manifest.json", "commit.json"):
        assert (d / name).exists()
    # the OPEN record carries no sealed values
    txt = (d / "open.json").read_text(encoding="utf-8")
    assert "0.0137" not in txt and "strategy_return" not in txt and "benchmark_excess" not in txt


# ---- root/commit marker binds the manifest; committed files digest-verify --------------------------

def test_commit_root_marker_is_nonempty_and_binds_the_manifest(ctx, tmp_path):
    store = tmp_path / "ledger"
    _open(ctx, store)
    d = _obs(store)
    commit = json.loads((d / "commit.json").read_bytes())
    assert commit["sequence"] == 1 and commit["session_date"] == "2026-07-24"
    assert len(commit["manifest_sha256"]) == 64                 # nonempty root digest
    assert hashlib.sha256((d / "manifest.json").read_bytes()).hexdigest() == commit["manifest_sha256"]
    manifest = json.loads((d / "manifest.json").read_bytes())
    assert set(manifest) == {"open.json", "sealed.bin", "provenance.json"}
    for name, want in manifest.items():
        assert hashlib.sha256((d / name).read_bytes()).hexdigest() == want
    validate_committed_observation(d)                           # fully valid


# ---- atomicity: the count does not advance without a completed durable commit ---------------------

def test_gate_failure_does_not_open_the_window(ctx, tmp_path):
    store = tmp_path / "ledger"
    with pytest.raises(IntegrityStop):                          # preflight fails closed (ledger == acct 4)
        open_first_window_session(
            replace(ctx, ledger_account_id=4), preflight_timestamp="t",
            deployed_tree_identity="c1efd8e", shadow_ledger_identity="x",
            account4_probe=_const_probe(),
            rebalances=1, orders=1, seeds=1, operational={}, sealed_performance={"x": 1},
            store_dir=store)
    assert committed_session_count(store) == 0
    assert not _obs(store).exists()


def test_second_call_is_rejected_first_session_only(ctx, tmp_path):
    store = tmp_path / "ledger"
    _open(ctx, store)                                            # publishes a fully valid sequence 1
    with pytest.raises(WindowOpenError, match="not the first session"):
        _open(ctx, store)                                       # validated count is now 1
    assert committed_session_count(store) == 1                  # unchanged, not overwritten


# ---- validating storage scan: corrupt / tampered committed dirs fail closed ----------------------

def test_corrupt_numeric_observation_dir_fails_closed(ctx, tmp_path):
    store = tmp_path / "ledger"
    _obs(store).mkdir(parents=True)                             # numeric dir, but not a valid observation
    (_obs(store) / "garbage.txt").write_text("not an observation", encoding="utf-8")
    with pytest.raises(IntegrityStop):
        committed_session_count(store)
    with pytest.raises(IntegrityStop):                          # the opener refuses to advance over it
        _open(ctx, store)


def test_modified_provenance_invalidates_committed_storage(ctx, tmp_path):
    store = tmp_path / "ledger"
    _open(ctx, store)
    (_obs(store) / "provenance.json").write_bytes(b'{"observation_sequence": 1, "tampered": true}\n')
    with pytest.raises(IntegrityStop):
        committed_session_count(store)


def test_missing_provenance_invalidates_committed_storage(ctx, tmp_path):
    store = tmp_path / "ledger"
    _open(ctx, store)
    (_obs(store) / "provenance.json").unlink()
    with pytest.raises(IntegrityStop):
        committed_session_count(store)


def test_tampered_commit_root_invalidates_committed_storage(ctx, tmp_path):
    store = tmp_path / "ledger"
    _open(ctx, store)
    (_obs(store) / "commit.json").write_bytes(
        b'{"sequence": 1, "session_date": "2026-07-24", "manifest_sha256": "' + b"0" * 64 + b'"}\n')
    with pytest.raises(IntegrityStop):
        committed_session_count(store)


# ---- Account 4 must be unchanged across the commit (authoritative after-probe) --------------------

def test_account4_state_change_across_commit_fails_closed(ctx, tmp_path):
    store = tmp_path / "ledger"
    probe = _ChangingProbe(_probe(hold_rev=2), _probe(hold_rev=3))   # live state moves during the commit
    with pytest.raises(WindowOpenError, match="Account 4 state changed"):
        _open(ctx, store, probe=probe)
    assert committed_session_count(store) == 0
    assert not _obs(store).exists()


def test_retry_is_possible_after_a_pre_publish_failure(ctx, tmp_path):
    store = tmp_path / "ledger"
    with pytest.raises(WindowOpenError, match="Account 4 state changed"):
        _open(ctx, store, probe=_ChangingProbe(_probe(hold_rev=2), _probe(hold_rev=3)))
    assert not _lock(store).exists()                            # mutex released on failure -> retry works
    obs, prov, new_count = _open(ctx, store)
    assert new_count == 1 and prov.observation_sequence == 1


# ---- strict durability: fsync failures fail closed -----------------------------------------------

def test_file_fsync_failure_stops_publication(ctx, tmp_path):
    store = tmp_path / "ledger"
    with pytest.raises(WindowOpenError, match="file fsync failure"):
        _open(ctx, store, durability=_FailFileFsync())
    assert committed_session_count(store) == 0
    assert not _obs(store).exists()


def test_staging_dir_fsync_failure_stops_publication(ctx, tmp_path):
    store = tmp_path / "ledger"
    with pytest.raises(WindowOpenError, match="dir fsync failure"):
        _open(ctx, store, durability=_FailDirFsync(".staging"))
    assert committed_session_count(store) == 0
    assert not _obs(store).exists()


def test_parent_dir_fsync_failure_does_not_report_success(ctx, tmp_path):
    store = tmp_path / "ledger"
    with pytest.raises(WindowOpenError, match="dir fsync failure"):
        _open(ctx, store, durability=_FailDirFsync("observations"))   # fails only the parent fsync
    assert not _lock(store).exists()                            # mutex still released on this failure path


# ---- no-overwrite publish primitive --------------------------------------------------------------

def test_publish_refuses_to_overwrite_an_existing_target(tmp_path):
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "x").write_text("new", encoding="utf-8")
    final = tmp_path / "final"
    final.mkdir()
    (final / "y").write_text("existing", encoding="utf-8")
    with pytest.raises(WindowOpenError, match="no-overwrite"):
        publish_no_overwrite(staging, final)
    assert (final / "y").read_text(encoding="utf-8") == "existing"   # target untouched
    assert staging.exists()                                          # source not consumed


# ---- exclusive first-observation ownership + lock lifecycle (mutex) ------------------------------

def test_lock_contention_fails_closed(ctx, tmp_path):
    store = tmp_path / "ledger"
    (store / ".commit-locks").mkdir(parents=True)
    fd = os.open(_lock(store), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.close(fd)                                                # another owner already holds the lock
    with pytest.raises(WindowOpenError, match="publish lock"):
        _open(ctx, store)
    assert not _obs(store).exists()


def test_lock_is_released_after_successful_publish(ctx, tmp_path):
    store = tmp_path / "ledger"
    _open(ctx, store)
    assert not _lock(store).exists()                            # mutex released after a successful publish
    assert _obs(store).exists()                                 # committed tree is the durable record


# ---- abandoned-stage recovery --------------------------------------------------------------------

def test_stale_staging_dir_is_recovered(ctx, tmp_path):
    store = tmp_path / "ledger"
    stale = store / ".staging"
    stale.mkdir(parents=True)
    (stale / "junk.tmp").write_text("crashed prior attempt", encoding="utf-8")
    obs, prov, new_count = _open(ctx, store)                    # recovery removes stale staging, still opens
    assert new_count == 1


# ---- no sealed content in the open record --------------------------------------------------------

def test_open_record_leaking_a_sealed_field_name_fails_closed():
    with pytest.raises(WindowOpenError, match="sealed field name"):
        assert_open_record_has_no_sealed_content(
            {"session_date": "2026-07-24", "sharpe": "x"}, {"sharpe": 0.5})


def test_open_record_leaking_a_sealed_value_fails_closed():
    with pytest.raises(WindowOpenError, match="sealed value"):
        assert_open_record_has_no_sealed_content(
            {"note": "return was 0.0137"}, {"strategy_return": 0.0137})


def test_clean_open_record_passes():
    assert_open_record_has_no_sealed_content(
        {"session_date": "2026-07-24", "rebalances": 1, "cap_breaches": 0},
        {"strategy_return": 0.0137})


# ---- pre-start still fails at the gate inside the opener ------------------------------------------

def test_pre_start_session_fails_closed_in_the_opener(ctx, tmp_path):
    store = tmp_path / "ledger"
    with pytest.raises(IntegrityStop):   # the gate fails before any commit; WindowOpenError is commit-only
        _open(replace(ctx, session_date=date(2026, 7, 23)), store)
    assert not _obs(store).exists()
