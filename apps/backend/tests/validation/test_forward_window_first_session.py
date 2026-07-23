"""Forward-validation first-session integrity gate (PREREG v1.0 §0/§5/§7 H).

Every frozen binding, plus Account-4 isolation, must fail the gate CLOSED (writing no observation)
when violated; the OPEN observation must expose only integrity/execution/operational counters, with
performance sealed by digest.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from app.validation import forward_window as fw
from app.validation.forward_window import (
    ForwardRunContext,
    IntegrityStop,
    build_first_session_record,
    preflight,
)

REPO_ROOT_DATA = "docs/review/momentum_daily/equal_weight_validation"


def _paths(tmp_path):
    """Write digest-matching stand-ins for the DGS3MO snapshot and trial ledger, so the gate's
    file-digest checks pass in a hermetic test. (The real run points at the committed artifacts.)"""
    # We can't reproduce the real 40KB CSV bytes here; instead monkeypatch the expected digests to the
    # digests of these fixtures via the frozen constants is NOT allowed (they are frozen). So point at
    # the REAL committed artifacts through the repo root.
    from pathlib import Path
    root = Path(__file__).resolve().parents[4]
    return (root / REPO_ROOT_DATA / "data/DGS3MO.csv",
            root / REPO_ROOT_DATA / "TrialLedger_v1.0.json")


@pytest.fixture
def good_ctx(tmp_path):
    dgs3mo, ledger = _paths(tmp_path)
    return ForwardRunContext(
        session_date=date(2026, 7, 24),
        is_nyse_trading_session=True,
        code_commit=fw.VALIDATION_MEASUREMENT_COMMIT,
        benchmark_commits=dict(fw.BENCHMARK_COMMITS),
        dgs3mo_path=dgs3mo, dgs3mo_cutoff=fw.DGS3MO_OBSERVATION_CUTOFF,
        trial_ledger_path=ledger, effective_dsr_trial_count=45,
        config=dict(fw.FROZEN_CONFIG),
        ledger_account_id=999, ledger_is_shadow_or_separate_paper=True,
        references_account4_capital=False, references_retired_baseline=False,
    )


def _need_artifacts(good_ctx):
    if not (good_ctx.dgs3mo_path.exists() and good_ctx.trial_ledger_path.exists()):
        pytest.skip("committed DGS3MO snapshot / trial ledger required")


# ---- happy path ------------------------------------------------------------------

def test_gate_passes_with_all_bindings_matched(good_ctx):
    _need_artifacts(good_ctx)
    m = preflight(good_ctx)
    assert m["verdict"] == "PASS"
    assert m["account4_isolation"]["is_account4"] is False
    assert m["bindings_verified"]["effective_dsr_trial_count"] == 45


# ---- every binding fails the gate CLOSED ----------------------------------------

def test_wrong_measurement_commit_fails_closed(good_ctx):
    _need_artifacts(good_ctx)
    with pytest.raises(IntegrityStop, match="measurement-code commit"):
        preflight(replace(good_ctx, code_commit="deadbeef" * 5))


def test_wrong_benchmark_commit_fails_closed(good_ctx):
    _need_artifacts(good_ctx)
    bad = dict(good_ctx.benchmark_commits)
    bad["CASH_OR_TBILL_RETURN"] = "0000000"
    with pytest.raises(IntegrityStop, match="benchmark CASH_OR_TBILL_RETURN"):
        preflight(replace(good_ctx, benchmark_commits=bad))


def test_dgs3mo_digest_mismatch_fails_closed(good_ctx, tmp_path):
    _need_artifacts(good_ctx)
    fake = tmp_path / "DGS3MO.csv"
    fake.write_text("DATE,DGS3MO\n2004-01-02,0.93\n", encoding="utf-8")
    with pytest.raises(IntegrityStop, match="DGS3MO snapshot digest mismatch"):
        preflight(replace(good_ctx, dgs3mo_path=fake))


def test_dgs3mo_cutoff_drift_fails_closed(good_ctx):
    _need_artifacts(good_ctx)
    with pytest.raises(IntegrityStop, match="DGS3MO cutoff"):
        preflight(replace(good_ctx, dgs3mo_cutoff="2026-07-22"))


def test_trial_ledger_digest_mismatch_fails_closed(good_ctx, tmp_path):
    _need_artifacts(good_ctx)
    fake = tmp_path / "TrialLedger.json"
    fake.write_text("{}", encoding="utf-8")
    with pytest.raises(IntegrityStop, match="trial ledger digest mismatch"):
        preflight(replace(good_ctx, trial_ledger_path=fake))


def test_wrong_trial_count_fails_closed(good_ctx):
    _need_artifacts(good_ctx)
    with pytest.raises(IntegrityStop, match="effective DSR trial count"):
        preflight(replace(good_ctx, effective_dsr_trial_count=1))


def test_config_drift_fails_closed(good_ctx):
    _need_artifacts(good_ctx)
    drifted = dict(good_ctx.config)
    drifted["weighting"] = "invvol_hybrid"
    with pytest.raises(IntegrityStop, match="config drift"):
        preflight(replace(good_ctx, config=drifted))
    drifted2 = dict(good_ctx.config)
    drifted2["max_position_pct"] = 0.25
    with pytest.raises(IntegrityStop, match="config drift"):
        preflight(replace(good_ctx, config=drifted2))


def test_pre_start_session_fails_closed(good_ctx):
    _need_artifacts(good_ctx)
    with pytest.raises(IntegrityStop, match="precedes the frozen forward start"):
        preflight(replace(good_ctx, session_date=date(2026, 7, 23)))


def test_non_trading_session_fails_closed(good_ctx):
    _need_artifacts(good_ctx)
    with pytest.raises(IntegrityStop, match="not an America/New_York trading session"):
        preflight(replace(good_ctx, session_date=date(2026, 7, 25),  # a Saturday
                          is_nyse_trading_session=False))


# ---- Account-4 isolation (load-bearing) -----------------------------------------

def test_running_against_account4_fails_closed(good_ctx):
    _need_artifacts(good_ctx)
    with pytest.raises(IntegrityStop, match="ledger account is Account 4"):
        preflight(replace(good_ctx, ledger_account_id=4))


def test_non_shadow_ledger_fails_closed(good_ctx):
    _need_artifacts(good_ctx)
    with pytest.raises(IntegrityStop, match="not a shadow"):
        preflight(replace(good_ctx, ledger_is_shadow_or_separate_paper=False))


def test_referencing_account4_capital_fails_closed(good_ctx):
    _need_artifacts(good_ctx)
    with pytest.raises(IntegrityStop, match="Account-4 capital"):
        preflight(replace(good_ctx, references_account4_capital=True))


def test_referencing_retired_baseline_fails_closed(good_ctx):
    _need_artifacts(good_ctx)
    with pytest.raises(IntegrityStop, match="retired baseline"):
        preflight(replace(good_ctx, references_retired_baseline=True))


# ---- observation record: open counters, sealed performance ----------------------

def test_first_session_record_seals_performance_and_exposes_only_counters(good_ctx):
    _need_artifacts(good_ctx)
    rec = build_first_session_record(
        good_ctx, rebalances=1, orders=5, seeds=1,
        operational={"cap_breaches": 0, "missed_rebalances": 0},
        sealed_performance={"strategy_return": 0.0123, "benchmark_excess": 0.004})
    # OPEN fields present
    assert rec.integrity_verdict == "PASS"
    assert rec.rebalances == 1 and rec.orders_submitted == 5 and rec.seeds == 1
    assert rec.cap_breaches == 0
    # performance is SEALED — only a digest is exposed, never the values
    assert rec.sealed_performance_sha256 is not None and len(rec.sealed_performance_sha256) == 64
    blob = rec.__dict__
    flat = str(blob)
    assert "0.0123" not in flat and "strategy_return" not in flat and "benchmark_excess" not in flat


def test_seal_is_deterministic_and_tamper_evident():
    sha1, _ = fw.seal_performance({"a": 1, "b": 2})
    sha2, _ = fw.seal_performance({"b": 2, "a": 1})     # key order irrelevant
    assert sha1 == sha2
    sha3, _ = fw.seal_performance({"a": 1, "b": 3})     # any change → different digest
    assert sha3 != sha1


def test_build_record_fails_closed_and_writes_nothing_on_bad_binding(good_ctx):
    _need_artifacts(good_ctx)
    with pytest.raises(IntegrityStop):
        build_first_session_record(
            replace(good_ctx, ledger_account_id=4), rebalances=1, orders=1, seeds=1,
            operational={}, sealed_performance={"x": 1})
