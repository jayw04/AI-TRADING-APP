"""Forward-validation first observation — atomic open + full provenance (PREREG v1.0 §0/§5).

Pins the owner directive of 2026-07-23: the complete first observation records the full provenance;
the window-open transition is atomic (count 0→1 only when the observation and BOTH digests are
durably recorded); the open record leaks no sealed content; and Account 4 must be unchanged across
the write. A preflight PASS without a completed atomic write does NOT increment the count.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from app.validation import forward_window as fw
from app.validation.first_session import (
    Account4StateProbe,
    WindowOpenError,
    assert_open_record_has_no_sealed_content,
    open_first_window_session,
)
from app.validation.forward_window import ForwardRunContext, IntegrityStop

REPO = Path(__file__).resolve().parents[4]
DATA = REPO / "docs/review/momentum_daily/equal_weight_validation"


def _probe(**over):
    base = dict(hold_status="ACTIVE", hold_reason_code="AWAITING_PRODUCTION_SIZING_VALIDATION",
                hold_rev=2, strategy_status="idle", positions_sha256="0" * 64)
    base.update(over)
    return Account4StateProbe(**base)


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


def _open(ctx, tmp_path, *, before=None, after=None, count=0, sealed=None):
    return open_first_window_session(
        ctx, preflight_timestamp="2026-07-24T20:10:00Z",
        deployed_tree_identity="c1efd8e", shadow_ledger_identity="paper-validation-901",
        account4_before=before or _probe(), account4_after=after or _probe(),
        rebalances=1, orders=5, seeds=1, operational={"cap_breaches": 0},
        sealed_performance=sealed or {"strategy_return": 0.0137, "benchmark_excess": 0.0041},
        store_dir=tmp_path / "ledger", current_session_count=count)


# ---- happy path: atomic open, count 0 → 1, full provenance -----------------------

def test_first_observation_opens_the_window_atomically(ctx, tmp_path):
    obs, prov, new_count = _open(ctx, tmp_path)
    assert new_count == 1                                        # the operational transition
    assert prov.observation_sequence == 1
    assert prov.deployed_tree_identity == "c1efd8e"
    assert prov.shadow_ledger_identity == "paper-validation-901"
    assert prov.preflight_execution_timestamp == "2026-07-24T20:10:00Z"
    assert len(prov.open_record_sha256) == 64 and len(prov.sealed_payload_sha256) == 64
    assert prov.account4_unchanged is True
    assert prov.account4_state_digest_before == prov.account4_state_digest_after
    # both artifacts durably written
    d = tmp_path / "ledger"
    assert (d / "observation_0001_open.json").exists()
    assert (d / "observation_0001_sealed.bin").exists()
    assert (d / "observation_0001_provenance.json").exists()
    # the OPEN record carries no sealed values
    txt = (d / "observation_0001_open.json").read_text(encoding="utf-8")
    assert "0.0137" not in txt and "strategy_return" not in txt and "benchmark_excess" not in txt


# ---- atomicity: count does not advance without a completed durable write ----------

def test_gate_failure_does_not_open_the_window(ctx, tmp_path):
    # A gate failure (here: ledger points at Account 4) must fail closed and leave nothing on disk.
    # preflight raises IntegrityStop (the parent); the write-only WindowOpenError never fires here.
    with pytest.raises(IntegrityStop):
        open_first_window_session(
            replace(ctx, ledger_account_id=4), preflight_timestamp="t",
            deployed_tree_identity="c1efd8e", shadow_ledger_identity="x",
            account4_before=_probe(), account4_after=_probe(),
            rebalances=1, orders=1, seeds=1, operational={}, sealed_performance={"x": 1},
            store_dir=tmp_path / "l", current_session_count=0)
    assert not (tmp_path / "l" / "observation_0001_open.json").exists()   # nothing written


def test_second_call_is_rejected_first_session_only(ctx, tmp_path):
    with pytest.raises(WindowOpenError, match="expected 0"):
        _open(ctx, tmp_path, count=1)


# ---- Account 4 must be unchanged across the write --------------------------------

def test_account4_state_change_across_write_fails_closed(ctx, tmp_path):
    with pytest.raises(WindowOpenError, match="Account 4 state changed"):
        _open(ctx, tmp_path, before=_probe(hold_rev=2), after=_probe(hold_rev=3))
    assert not (tmp_path / "ledger" / "observation_0001_open.json").exists()


def test_account4_hold_reason_change_across_write_fails_closed(ctx, tmp_path):
    with pytest.raises(WindowOpenError):
        _open(ctx, tmp_path, before=_probe(hold_status="ACTIVE"),
              after=_probe(hold_status="CLEARED"))


# ---- no sealed content in the open record ---------------------------------------

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


# ---- pre-start still fails at the gate inside the opener --------------------------

def test_pre_start_session_fails_closed_in_the_opener(ctx, tmp_path):
    with pytest.raises(IntegrityStop):   # the gate fails before any write; WindowOpenError is write-only
        _open(replace(ctx, session_date=date(2026, 7, 23)), tmp_path)
    assert not (tmp_path / "ledger" / "observation_0001_open.json").exists()
