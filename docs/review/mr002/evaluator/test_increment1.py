"""MR-002 validation/OOS evaluator — Increment 1 qualification tests (synthetic ONLY).

Twelve synthetic fixtures proving loader / metric primitives / gate engine / report kernel behave as
the v1.0.3 governing package requires. NO real dataset is opened; every array is fabricated in-test.
Run with: apps/backend/.venv/Scripts/python.exe -m pytest test_increment1.py -v
"""

from __future__ import annotations

import os
import shutil
import tempfile

import numpy as np
import pytest

import mr002_valoos_gates as G
import mr002_valoos_metrics as M
from mr002_valoos_identity import RefusedIdentity, load_governing_identity
from mr002_valoos_report import build_report, report_hash

GOV_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
GOV_FILES = ["MR002_ValidationOOS_Preregistration_v1.0.3.json",
             "MR002_DSR_TrialLedger_v1.0.json", "MR002_DSR_Resolution_v1.0.json"]

SEED = 42
CODE_ID = {"module": "increment1", "note": "synthetic"}
DEP_ID = {"numpy": np.__version__}
FIX_ID = {"fixture": "synthetic-v1"}


def _rng(mu, sigma, n, seed=7):
    return np.random.default_rng(seed).normal(mu, sigma, n)


def _copy_gov(tmp, mutate=None):
    """Copy the 3 governing files into tmp; optionally mutate one JSON before writing."""
    import json
    for f in GOV_FILES:
        src = os.path.join(GOV_DIR, f)
        if mutate and f in mutate:
            d = json.load(open(src, encoding="utf-8"))
            mutate[f](d)
            open(os.path.join(tmp, f), "w", encoding="utf-8").write(json.dumps(d))
        else:
            shutil.copyfile(src, os.path.join(tmp, f))


def _pass_battery(loaded):
    """Build a fully-passing synthetic gate battery (all GATE entries PASS)."""
    b = G.GateBattery()
    daily = _rng(0.0012, 0.004, 900)                 # strong positive drift: clears Sharpe, LB, DSR
    sharpe = M.annualized_sharpe(daily)
    lb = M.block_bootstrap_mean_lower_bound(daily)
    b.gate("sharpe", sharpe >= 0.70, sharpe, 0.70)
    b.gate("bootstrap_mean_lb", lb > 0.0, lb, 0.0)
    b.gate("dsr", M.deflated_sharpe(daily, trials_n=loaded["dsr_trials_N"],
            trial_sharpe_std=0.01)["gate_pass"], None, 0.95)
    b.diagnostic("pbo", 0.1)
    b.diagnostic("regime_concentration", 0.3)
    return b, daily, sharpe, lb


# ── Fixture 1: full PASS ──────────────────────────────────────────────────────────────────────────
def test_01_full_pass():
    loaded = load_governing_identity(GOV_DIR)
    b, *_ = _pass_battery(loaded)
    assert b.disposition() == G.DISP_PASS


# ── Fixture 2: Sharpe < 0.70 -> FAIL ───────────────────────────────────────────────────────────────
def test_02_low_sharpe_fails():
    daily = _rng(0.00005, 0.01, 800)                 # near-zero drift -> Sharpe < 0.70
    b = G.GateBattery()
    s = M.annualized_sharpe(daily)
    assert s < 0.70
    b.gate("sharpe", s >= 0.70, s, 0.70)
    b.gate("bootstrap_mean_lb", True, 0.01, 0.0)     # other gate passes
    assert b.disposition() == G.DISP_FAIL


# ── Fixture 3: mean-return lower bound <= 0 fails INDEPENDENTLY ─────────────────────────────────────
def test_03_bootstrap_lb_fails_independently():
    daily = _rng(0.0, 0.01, 800)                     # zero mean -> LB <= 0
    b = G.GateBattery()
    b.gate("sharpe", True, 2.0, 0.70)                # sharpe gate forced PASS
    lb = M.block_bootstrap_mean_lower_bound(daily)
    b.gate("bootstrap_mean_lb", lb > 0.0, lb, 0.0)
    assert lb <= 0.0
    assert b.disposition() == G.DISP_FAIL


# ── Fixture 4: DSR < 95% -> FAIL ───────────────────────────────────────────────────────────────────
def test_04_dsr_below_threshold_fails():
    loaded = load_governing_identity(GOV_DIR)
    daily = _rng(0.00008, 0.02, 300)                 # weak signal, high trial dispersion -> low DSR
    dsr = M.deflated_sharpe(daily, trials_n=loaded["dsr_trials_N"], trial_sharpe_std=0.5)
    b = G.GateBattery()
    b.gate("sharpe", True, 2.0, 0.70)
    b.gate("dsr", dsr["gate_pass"], dsr["dsr"], 0.95)
    assert dsr["dsr"] < 0.95
    assert b.disposition() == G.DISP_FAIL


# ── Fixture 5: PBO diagnostic failure does NOT cause window FAIL ────────────────────────────────────
def test_05_pbo_diagnostic_never_gates():
    b = G.GateBattery()
    b.gate("sharpe", True, 2.0, 0.70)                # all GATE entries PASS
    b.gate("dsr", True, 0.99, 0.95)
    b.diagnostic("pbo", 0.95)                        # terrible PBO, but only a diagnostic
    assert b.disposition() == G.DISP_PASS


# ── Fixture 6: positive-P&L regime concentration diagnostic has no verdict effect ───────────────────
def test_06_regime_concentration_diagnostic_no_effect():
    regime_pnl = {"trend_up": 900.0, "trend_flat": 50.0, "trend_down": 50.0}
    d = M.positive_pnl_regime_concentration_diagnostic(regime_pnl)
    assert d["classification"] == "DIAGNOSTIC"
    b = G.GateBattery()
    b.gate("sharpe", True, 2.0, 0.70)
    b.diagnostic("regime_concentration", d["top_regime_positive_fraction"])
    assert b.disposition() == G.DISP_PASS


# ── Fixture 7: missing governing identity -> refusal ───────────────────────────────────────────────
def test_07_missing_governing_identity_refuses():
    with tempfile.TemporaryDirectory() as tmp:
        # copy only two of three files
        for f in GOV_FILES[:2]:
            shutil.copyfile(os.path.join(GOV_DIR, f), os.path.join(tmp, f))
        with pytest.raises(RefusedIdentity, match="MISSING_OR_SYMLINK"):
            load_governing_identity(tmp)


# ── Fixture 8: ledger hash mismatch -> refusal ─────────────────────────────────────────────────────
def test_08_ledger_hash_mismatch_refuses():
    with tempfile.TemporaryDirectory() as tmp:
        _copy_gov(tmp, mutate={"MR002_DSR_TrialLedger_v1.0.json":
                               lambda d: d.__setitem__("_tamper", "x")})
        with pytest.raises(RefusedIdentity, match="HASH_MISMATCH"):
            load_governing_identity(tmp)


# ── Fixture 9: ledger N=4 or N=3 -> refusal (before hash-agnostic checks) ───────────────────────────
def test_09_ledger_wrong_N_refuses():
    # Mutating trials_N also changes the hash, so refusal fires at HASH_MISMATCH — proving a tampered
    # N can never be loaded. Assert refusal occurs for both N=4 and N=3.
    for wrong in (4, 3):
        with tempfile.TemporaryDirectory() as tmp:
            _copy_gov(tmp, mutate={"MR002_DSR_TrialLedger_v1.0.json":
                                   lambda d, w=wrong: d.__setitem__("trials_N", w)})
            with pytest.raises(RefusedIdentity):
                load_governing_identity(tmp)


# ── Fixture 10: hard data-integrity -> INTEGRITY_STOP ──────────────────────────────────────────────
def test_10_zero_volatility_integrity_stop():
    flat = np.full(500, 0.001)
    with pytest.raises(M.IntegrityStop, match="ZERO_VOLATILITY"):
        M.annualized_sharpe(flat)
    # engine surfaces it as an INTEGRITY_STOP disposition
    b = G.GateBattery()
    b.gate("sharpe", False, None, 0.70)
    assert b.disposition(integrity_stop=True) == G.DISP_INTEGRITY_STOP


# ── Fixture 11: identical fixture + seed -> byte-identical reports ──────────────────────────────────
def test_11_determinism_byte_identical():
    loaded = load_governing_identity(GOV_DIR)
    def make():
        b, daily, sharpe, lb = _pass_battery(loaded)
        return build_report(window="synthetic", disposition=b.disposition(),
                            governing_identity=loaded, code_identity=CODE_ID,
                            dependency_identity=DEP_ID, fixture_identity=FIX_ID,
                            metric_values={"sharpe": sharpe, "bootstrap_lb": lb},
                            gate_results=b.to_list(), diagnostics=[], hard_stop_evidence=None,
                            seed=SEED)
    r1, r2 = make(), make()
    assert r1["output_hash"] == r2["output_hash"]
    assert report_hash(r1) == r1["output_hash"]
    assert r1["validation_data_read"] is False and r1["synthetic_fixture_only"] is True


# ── Fixture 12: changing only a diagnostic leaves disposition unchanged ─────────────────────────────
def test_12_diagnostic_change_no_disposition_change():
    b1 = G.GateBattery()
    b1.gate("sharpe", True, 2.0, 0.70)
    b1.diagnostic("pbo", 0.10)
    b2 = G.GateBattery()
    b2.gate("sharpe", True, 2.0, 0.70)
    b2.diagnostic("pbo", 0.99)                       # only the diagnostic value changed
    assert b1.disposition() == b2.disposition() == G.DISP_PASS


# ── Extra loader positive: N sourced from ledger equals 5, no fallback constant ─────────────────────
def test_13_loaded_N_is_five_from_ledger():
    loaded = load_governing_identity(GOV_DIR)
    assert loaded["dsr_trials_N"] == 5
    assert loaded["validation_authorization"] is False
    # prove there is no independent TRIALS_N constant in the loader module
    import mr002_valoos_identity as ident
    assert not hasattr(ident, "TRIALS_N")


# ── Extra metric closed-form checks (breadth / concentration / annual / regime) ─────────────────────
def test_14_supporting_metric_gates():
    trades = ([{"entry_date": f"d{i%120}", "side": "long"} for i in range(300)]
              + [{"entry_date": f"d{i%120}", "side": "short"} for i in range(300)])
    assert M.breadth(trades)["gate_pass"] is True
    pnl = np.concatenate([np.full(200, 5.0), np.full(10, 1.0)])
    ids = [f"s{i}" for i in range(210)]
    assert M.trade_concentration(pnl, ids)["gate_pass"] is True
    annual = {2020: 100.0, 2021: 120.0, 2022: 110.0, 2023: 90.0}
    assert M.annual_profile(annual)["gate_pass"] is True
    # 3 positive trend regimes (no single regime dominating losses) + both vol regimes Sharpe > -0.5
    trend = {"up": 500.0, "flat": 300.0, "down": 50.0}
    vol = {"low": 0.5, "high": 0.2}
    mins = {"up": 200, "flat": 200, "down": 200, "low": 200, "high": 200}
    assert M.regime_gates(trend, vol, min_sessions=mins)["gate_pass"] is True
