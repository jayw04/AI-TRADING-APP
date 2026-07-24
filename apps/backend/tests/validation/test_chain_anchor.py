"""Forward-validation chain-tip ANCHOR log (R5d).

The observation chain is only tamper-evident against a root or tip recorded where a rewrite cannot reach.
These tests pin the independent anchor log that provides it: each committed tip is witnessed in a
separately hash-chained log, and cross-verification refuses any state where the two chains disagree — a
rewritten observation whose anchor was not also rewritten, an unwitnessed tip, or a forged anchor.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from app.validation import forward_window as fw
from app.validation.chain_anchor import (
    ANCHOR_LOG_FILENAME,
    AnchorError,
    _digest,
    _line_digest,
    append_anchor,
    read_anchors,
    verify_anchor_consistency,
)
from app.validation.first_session import open_first_window_session
from app.validation.observation_store import (
    Account4StateProbe,
    Durability,
    committed_observations,
)
from app.validation.session_recorder import record_forward_session

REPO = Path(__file__).resolve().parents[4]
DATA = REPO / "docs/review/momentum_daily/equal_weight_validation"

SESSION_1 = date(2026, 7, 24)
SESSION_2 = date(2026, 7, 27)
SESSION_3 = date(2026, 7, 28)


class _NoopDurability(Durability):
    def fsync_file(self, path: Path) -> None:
        pass

    def fsync_dir(self, path: Path) -> None:
        pass


NOOP = _NoopDurability()


def _const_probe(**over):
    base = dict(hold_status="ACTIVE", hold_reason_code="AWAITING_PRODUCTION_SIZING_VALIDATION",
                hold_rev=2, strategy_status="idle", positions_sha256="0" * 64)
    base.update(over)
    p = Account4StateProbe(**base)
    return lambda: p


@pytest.fixture
def ctx():
    dgs3mo = DATA / "data/DGS3MO.csv"
    ledger = DATA / "TrialLedger_v1.0.json"
    if not (dgs3mo.exists() and ledger.exists()):
        pytest.skip("committed artifacts required")
    return _make_ctx(dgs3mo, ledger)


def _make_ctx(dgs3mo, ledger):
    return fw.ForwardRunContext(
        session_date=SESSION_1, is_nyse_trading_session=True,
        code_commit=fw.VALIDATION_MEASUREMENT_COMMIT, benchmark_commits=dict(fw.BENCHMARK_COMMITS),
        dgs3mo_path=dgs3mo, dgs3mo_cutoff=fw.DGS3MO_OBSERVATION_CUTOFF,
        trial_ledger_path=ledger, effective_dsr_trial_count=45, config=dict(fw.FROZEN_CONFIG),
        ledger_account_id=901, ledger_is_shadow_or_separate_paper=True,
        references_account4_capital=False, references_retired_baseline=False)


def _open(ctx, store):
    open_first_window_session(
        ctx, preflight_timestamp="2026-07-24T20:10:00Z", deployed_tree_identity="c1efd8e",
        shadow_ledger_identity="paper-validation-901", account4_probe=_const_probe(),
        rebalances=1, orders=5, seeds=1, operational={"cap_breaches": 0},
        sealed_performance={"strategy_return": 0.0137}, store_dir=store, durability=NOOP)


def _record(ctx, store, session):
    record_forward_session(
        replace(ctx, session_date=session), preflight_timestamp=f"{session.isoformat()}T20:10:00Z",
        deployed_tree_identity="c1efd8e", shadow_ledger_identity="paper-validation-901",
        account4_probe=_const_probe(), rebalances=0, orders=0, seeds=0,
        operational={"cap_breaches": 0}, sealed_performance={"strategy_return": -0.0042},
        store_dir=store, durability=NOOP)


def _anchor(store):
    return append_anchor(store, deployed_tree_identity="c1efd8e", anchored_at="2026-07-24T20:11:00Z",
                         durability=NOOP)


# ---- anchoring a tip --------------------------------------------------------------------------------

def test_the_first_tip_is_anchored(ctx, tmp_path):
    store = tmp_path / "ledger"
    _open(ctx, store)
    rec = _anchor(store)
    obs = committed_observations(store)
    assert rec.sequence == 1
    assert rec.commit_sha256 == obs[0].commit_sha256
    assert rec.previous_commit_sha256 is None
    assert rec.previous_anchor_sha256 is None
    anchors = read_anchors(store)
    assert len(anchors) == 1 and anchors[0].commit_sha256 == obs[0].commit_sha256
    verify_anchor_consistency(store)                    # no raise


def test_a_second_tip_chains_the_anchor_log(ctx, tmp_path):
    store = tmp_path / "ledger"
    _open(ctx, store)
    _anchor(store)
    _record(ctx, store, SESSION_2)
    rec2 = _anchor(store)
    anchors = read_anchors(store)
    assert len(anchors) == 2
    assert rec2.sequence == 2
    # the anchor log is its OWN chain: line 2 binds the digest of line 1's exact bytes
    line1 = (store / ANCHOR_LOG_FILENAME).read_text(encoding="utf-8").split("\n")[0]
    assert rec2.previous_anchor_sha256 == _line_digest(line1)
    verify_anchor_consistency(store)


def test_appending_an_already_anchored_tip_is_a_noop(ctx, tmp_path):
    store = tmp_path / "ledger"
    _open(ctx, store)
    first = _anchor(store)
    again = _anchor(store)                              # the tip is already anchored
    assert again == first
    assert len(read_anchors(store)) == 1


def test_the_full_record_is_anchored_in_order(ctx, tmp_path):
    store = tmp_path / "ledger"
    _open(ctx, store)
    _anchor(store)
    for s in (SESSION_2, SESSION_3):
        _record(ctx, store, s)
        _anchor(store)
    anchors = read_anchors(store)
    obs = committed_observations(store)
    assert [a.sequence for a in anchors] == [1, 2, 3]
    assert [a.commit_sha256 for a in anchors] == [o.commit_sha256 for o in obs]
    verify_anchor_consistency(store)


# ---- cross-verification refuses divergence ----------------------------------------------------------

def test_an_unwitnessed_tip_is_refused(ctx, tmp_path):
    store = tmp_path / "ledger"
    _open(ctx, store)
    _anchor(store)
    _record(ctx, store, SESSION_2)                     # committed, but never anchored
    with pytest.raises(AnchorError) as ei:
        verify_anchor_consistency(store)
    assert ei.value.code == "ANCHOR_BEHIND_RECORD"


def test_an_extra_anchor_is_refused(ctx, tmp_path):
    store = tmp_path / "ledger"
    _open(ctx, store)
    _anchor(store)
    _record(ctx, store, SESSION_2)
    _anchor(store)                                     # two committed tips, both anchored
    obs = committed_observations(store)
    with pytest.raises(AnchorError) as ei:
        verify_anchor_consistency(store, obs[:1])      # pretend only 1 observation exists
    assert ei.value.code == "ANCHOR_AHEAD_OF_RECORD"


def test_a_rewritten_observation_is_refused(ctx, tmp_path):
    store = tmp_path / "ledger"
    _open(ctx, store)
    _anchor(store)
    obs = committed_observations(store)
    tampered = [replace(obs[0], commit_sha256="f" * 64)]   # the observation chain rewritten under the anchor
    with pytest.raises(AnchorError) as ei:
        verify_anchor_consistency(store, tampered)
    assert ei.value.code == "ANCHOR_DIVERGES_FROM_RECORD"


def test_append_refuses_to_extend_a_divergent_chain(ctx, tmp_path):
    store = tmp_path / "ledger"
    _open(ctx, store)
    _anchor(store)
    # hand-corrupt anchor line 1's witnessed commit, keeping the line self-valid, then try to extend
    path = store / ANCHOR_LOG_FILENAME
    obj = _load_line(path, 0)
    obj["commit_sha256"] = "a" * 64
    _write_lines(path, [_reseal(obj)])
    _record(ctx, store, SESSION_2)
    with pytest.raises(AnchorError) as ei:
        _anchor(store)
    assert ei.value.code == "ANCHOR_DIVERGES_FROM_RECORD"


# ---- the anchor log's own integrity -----------------------------------------------------------------

def test_a_tampered_anchor_line_is_refused(ctx, tmp_path):
    store = tmp_path / "ledger"
    _open(ctx, store)
    _anchor(store)
    path = store / ANCHOR_LOG_FILENAME
    obj = _load_line(path, 0)
    obj["deployed_tree_identity"] = "attacker"          # change a field WITHOUT re-sealing anchor_sha256
    _write_lines(path, [_dump(obj)])
    with pytest.raises(AnchorError) as ei:
        read_anchors(store)
    assert ei.value.code == "ANCHOR_LOG_INVALID"


def test_a_broken_anchor_chain_link_is_refused(ctx, tmp_path):
    store = tmp_path / "ledger"
    _open(ctx, store)
    _anchor(store)
    _record(ctx, store, SESSION_2)
    _anchor(store)
    path = store / ANCHOR_LOG_FILENAME
    line1, line2 = path.read_text(encoding="utf-8").split("\n")[:2]
    obj1 = _load_str(line1)
    obj1["deployed_tree_identity"] = "rewritten"        # rewrite line 1 (self-valid), so line 2's link breaks
    _write_lines(path, [_reseal(obj1), line2])
    with pytest.raises(AnchorError) as ei:
        read_anchors(store)
    assert ei.value.code == "ANCHOR_LOG_INVALID"


def test_a_non_contiguous_anchor_sequence_is_refused(ctx, tmp_path):
    store = tmp_path / "ledger"
    _open(ctx, store)
    _anchor(store)
    _record(ctx, store, SESSION_2)
    _anchor(store)
    path = store / ANCHOR_LOG_FILENAME
    line2 = path.read_text(encoding="utf-8").split("\n")[1]
    _write_lines(path, [line2])                         # drop line 1 → the log starts at sequence 2
    with pytest.raises(AnchorError) as ei:
        read_anchors(store)
    assert ei.value.code == "ANCHOR_LOG_INVALID"


# ---- tiny JSON helpers for the tamper tests ---------------------------------------------------------

def _load_line(path: Path, i: int) -> dict:
    return _load_str(path.read_text(encoding="utf-8").split("\n")[i])


def _load_str(line: str) -> dict:
    return json.loads(line)


def _dump(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True)


def _reseal(obj: dict) -> str:
    """Rebuild a self-valid anchor line: recompute anchor_sha256 over the body so the LINE verifies (only
    the cross-chain link, not the line itself, is what should break)."""
    body = {k: v for k, v in obj.items() if k != "anchor_sha256"}
    return json.dumps({**body, "anchor_sha256": _digest(body)}, sort_keys=True)


def _write_lines(path: Path, lines: list[str]) -> None:
    path.write_text("".join(ln + "\n" for ln in lines), encoding="utf-8")
