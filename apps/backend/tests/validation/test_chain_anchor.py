"""Forward-validation chain-tip ANCHOR log + independent witness (R5d).

The observation chain is only tamper-evident against a root or tip recorded where a rewrite cannot reach.
These tests pin the independent anchor: each committed tip is witnessed in a separately hash-chained local
log, SIGNED by a key the store-writer does not hold, and recorded in an external append-only sink — and
cross-verification refuses any state where the three chains disagree (a rewritten observation, a forged or
altered signature, or a truncated local log the external sink still remembers).
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
from app.validation.chain_witness import Ed25519AnchorSigner, FileExternalAnchorSink
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

SIGNER = Ed25519AnchorSigner.generate(witness_identity="r5d-test-witness")
VERIFIER = SIGNER.verifier()
OTHER_SIGNER = Ed25519AnchorSigner.generate(witness_identity="impostor")


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


def _sink(tmp_path):
    # the external witness lives OUTSIDE the observation store (a separate trust boundary in production)
    return FileExternalAnchorSink(tmp_path / "external_witness", identity="ext-test")


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


def _anchor(store, sink, *, signer=SIGNER):
    return append_anchor(store, signer=signer, external_sink=sink, deployed_tree_identity="c1efd8e",
                         anchored_at="2026-07-24T20:11:00Z", durability=NOOP)


def _verify(store, sink, committed=None, *, verifier=VERIFIER):
    return verify_anchor_consistency(store, committed, verifier=verifier, external_sink=sink)


# ---- anchoring a tip --------------------------------------------------------------------------------

def test_the_first_tip_is_anchored(ctx, tmp_path):
    store = tmp_path / "ledger"
    sink = _sink(tmp_path)
    _open(ctx, store)
    rec = _anchor(store, sink)
    obs = committed_observations(store)
    assert rec.sequence == 1
    assert rec.commit_sha256 == obs[0].commit_sha256
    assert rec.previous_commit_sha256 is None and rec.previous_anchor_sha256 is None
    assert rec.witness_signature and rec.witness_public_key_id == VERIFIER.public_key_id
    anchors = read_anchors(store)
    assert len(anchors) == 1 and anchors[0].commit_sha256 == obs[0].commit_sha256
    _verify(store, sink)                                # signatures + external witness all check


def test_a_second_tip_chains_the_anchor_log(ctx, tmp_path):
    store = tmp_path / "ledger"
    sink = _sink(tmp_path)
    _open(ctx, store)
    _anchor(store, sink)
    _record(ctx, store, SESSION_2)
    rec2 = _anchor(store, sink)
    anchors = read_anchors(store)
    assert len(anchors) == 2 and rec2.sequence == 2
    line1 = (store / ANCHOR_LOG_FILENAME).read_text(encoding="utf-8").split("\n")[0]
    assert rec2.previous_anchor_sha256 == _line_digest(line1)
    _verify(store, sink)


def test_appending_an_already_anchored_tip_is_a_noop(ctx, tmp_path):
    store = tmp_path / "ledger"
    sink = _sink(tmp_path)
    _open(ctx, store)
    first = _anchor(store, sink)
    again = _anchor(store, sink)
    assert again == first
    assert len(read_anchors(store)) == 1


def test_the_full_record_is_anchored_in_order(ctx, tmp_path):
    store = tmp_path / "ledger"
    sink = _sink(tmp_path)
    _open(ctx, store)
    _anchor(store, sink)
    for s in (SESSION_2, SESSION_3):
        _record(ctx, store, s)
        _anchor(store, sink)
    anchors = read_anchors(store)
    obs = committed_observations(store)
    assert [a.sequence for a in anchors] == [1, 2, 3]
    assert [a.commit_sha256 for a in anchors] == [o.commit_sha256 for o in obs]
    _verify(store, sink)


# ---- cross-verification refuses divergence (observation ↔ local anchor) ------------------------------

def test_an_unwitnessed_tip_is_refused(ctx, tmp_path):
    store = tmp_path / "ledger"
    sink = _sink(tmp_path)
    _open(ctx, store)
    _anchor(store, sink)
    _record(ctx, store, SESSION_2)                     # committed, but never anchored
    with pytest.raises(AnchorError) as ei:
        _verify(store, sink)
    assert ei.value.code == "ANCHOR_BEHIND_RECORD"


def test_an_extra_anchor_is_refused(ctx, tmp_path):
    store = tmp_path / "ledger"
    sink = _sink(tmp_path)
    _open(ctx, store)
    _anchor(store, sink)
    _record(ctx, store, SESSION_2)
    _anchor(store, sink)
    obs = committed_observations(store)
    with pytest.raises(AnchorError) as ei:
        _verify(store, sink, obs[:1])                  # pretend only 1 observation exists
    assert ei.value.code == "ANCHOR_AHEAD_OF_RECORD"


def test_a_rewritten_observation_is_refused(ctx, tmp_path):
    store = tmp_path / "ledger"
    sink = _sink(tmp_path)
    _open(ctx, store)
    _anchor(store, sink)
    obs = committed_observations(store)
    tampered = [replace(obs[0], commit_sha256="f" * 64)]
    with pytest.raises(AnchorError) as ei:
        _verify(store, sink, tampered)
    assert ei.value.code == "ANCHOR_DIVERGES_FROM_RECORD"


def test_append_refuses_to_extend_a_divergent_chain(ctx, tmp_path):
    store = tmp_path / "ledger"
    sink = _sink(tmp_path)
    _open(ctx, store)
    _anchor(store, sink)
    path = store / ANCHOR_LOG_FILENAME
    obj = _load_line(path, 0)
    obj["commit_sha256"] = "a" * 64
    _write_lines(path, [_reseal(obj)])
    _record(ctx, store, SESSION_2)
    with pytest.raises(AnchorError) as ei:
        _anchor(store, sink)
    assert ei.value.code == "ANCHOR_DIVERGES_FROM_RECORD"


# ---- the independent witness: signatures and the external sink ---------------------------------------

def test_an_altered_tip_fails_the_signature(ctx, tmp_path):
    """Even when the observation AND the local anchor are rewritten consistently (so the observation
    cross-check passes), the tip cannot be re-signed without the private key: the signature no longer
    verifies, even though the line's own anchor_sha256 was recomputed to look valid."""
    store = tmp_path / "ledger"
    sink = _sink(tmp_path)
    _open(ctx, store)
    _anchor(store, sink)
    path = store / ANCHOR_LOG_FILENAME
    obj = _load_line(path, 0)
    obj["commit_sha256"] = "b" * 64                    # rewrite the witnessed tip, keep the old signature
    _write_lines(path, [_reseal(obj)])                 # re-seal the LINE digest (attacker can do this)
    # a matching (also-rewritten) observation view, so only the signature exposes the forgery
    obs = committed_observations(store)
    rewritten_obs = [replace(obs[0], commit_sha256="b" * 64)]
    with pytest.raises(AnchorError) as ei:
        _verify(store, sink, rewritten_obs)
    assert ei.value.code == "ANCHOR_SIGNATURE_INVALID"


def test_a_foreign_signing_key_is_refused(ctx, tmp_path):
    """A tip signed by a key that is not the trusted witness key is refused."""
    store = tmp_path / "ledger"
    sink = _sink(tmp_path)
    _open(ctx, store)
    _anchor(store, sink, signer=OTHER_SIGNER)          # signed by the wrong key + recorded externally
    with pytest.raises(AnchorError) as ei:
        _verify(store, sink)                            # verifier trusts SIGNER, not OTHER_SIGNER
    assert ei.value.code == "ANCHOR_SIGNATURE_INVALID"


def test_a_truncated_local_log_is_caught_by_the_external_witness(ctx, tmp_path):
    """The core R5d property: an attacker truncates BOTH the observations and the local anchor log to
    hide the latest sessions — but the external append-only witness still holds them, so verification
    fails closed."""
    store = tmp_path / "ledger"
    sink = _sink(tmp_path)
    _open(ctx, store)
    _anchor(store, sink)
    _record(ctx, store, SESSION_2)
    _anchor(store, sink)
    obs = committed_observations(store)                # the true record: 2 tips, both externally witnessed
    # attacker presents only the first observation + first anchor (a consistent, validly-signed prefix)
    path = store / ANCHOR_LOG_FILENAME
    line1 = path.read_text(encoding="utf-8").split("\n")[0]
    _write_lines(path, [line1])
    with pytest.raises(AnchorError) as ei:
        _verify(store, sink, obs[:1])                  # the truncated view the attacker wants accepted
    assert ei.value.code == "EXTERNAL_WITNESS_AHEAD"


def test_a_locally_witnessed_tip_missing_from_the_sink_is_refused(ctx, tmp_path):
    """A local anchor the external sink never recorded is not independently witnessed."""
    store = tmp_path / "ledger"
    sink = _sink(tmp_path)
    _open(ctx, store)
    _anchor(store, sink)
    # remove the external record, leaving the local anchor unwitnessed
    for p in (tmp_path / "external_witness").iterdir():
        p.unlink()
    with pytest.raises(AnchorError) as ei:
        _verify(store, sink)
    assert ei.value.code == "EXTERNAL_WITNESS_BEHIND"


# ---- the anchor log's own integrity -----------------------------------------------------------------

def test_a_tampered_anchor_line_is_refused(ctx, tmp_path):
    store = tmp_path / "ledger"
    sink = _sink(tmp_path)
    _open(ctx, store)
    _anchor(store, sink)
    path = store / ANCHOR_LOG_FILENAME
    obj = _load_line(path, 0)
    obj["deployed_tree_identity"] = "attacker"          # change a field WITHOUT re-sealing anchor_sha256
    _write_lines(path, [_dump(obj)])
    with pytest.raises(AnchorError) as ei:
        read_anchors(store)
    assert ei.value.code == "ANCHOR_LOG_INVALID"


def test_a_broken_anchor_chain_link_is_refused(ctx, tmp_path):
    store = tmp_path / "ledger"
    sink = _sink(tmp_path)
    _open(ctx, store)
    _anchor(store, sink)
    _record(ctx, store, SESSION_2)
    _anchor(store, sink)
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
    sink = _sink(tmp_path)
    _open(ctx, store)
    _anchor(store, sink)
    _record(ctx, store, SESSION_2)
    _anchor(store, sink)
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
    """Rebuild a self-valid anchor line: recompute anchor_sha256 over the CORE body so the LINE verifies
    (the signature is over the tip, not recomputed — only what a keyless attacker could redo)."""
    core = {k: v for k, v in obj.items()
            if k not in ("anchor_sha256", "witness_signature", "witness_public_key_id",
                         "witness_identity")}
    rest = {k: obj[k] for k in ("witness_signature", "witness_public_key_id", "witness_identity")
            if k in obj}
    return json.dumps({**core, "anchor_sha256": _digest(core), **rest}, sort_keys=True)


def _write_lines(path: Path, lines: list[str]) -> None:
    path.write_text("".join(ln + "\n" for ln in lines), encoding="utf-8")
