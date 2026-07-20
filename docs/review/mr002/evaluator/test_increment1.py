"""MR-002 validation/OOS evaluator — Increment 1 v1.1 qualification tests (synthetic ONLY).

Independent-fixture qualification: expected values are hand-derived or computed via numpy/scipy
primitives — NOT by calling the implementation under test. NO real dataset is opened.
Run: apps/backend/.venv/Scripts/python.exe -m pytest test_increment1.py -v
"""

from __future__ import annotations

import copy
import json
import math
import os
import shutil
import tempfile

import numpy as np
import pytest
from scipy.stats import norm

import mr002_valoos_gates as G
import mr002_valoos_metrics as M
import mr002_valoos_report as R
from mr002_valoos_identity import (
    LEDGER,
    PREREG,
    RESOLUTION,
    RefusedIdentity,
    _validate_semantics,
    load_governing_identity,
)
from mr002_valoos_registry import REQUIRED_GATES, cross_validate_registry

GOV_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
EULER = 0.5772156649015329

# Passing (value, sample) for every required gate.
PASS_GATES = {
    "net_sharpe": (1.5, "sealed_OOS"),
    "bootstrap_mean_lower_bound": (0.0001, "sealed_OOS"),
    "net_calmar": (2.0, "sealed_OOS"),
    "combined_max_drawdown": (0.10, "validation+OOS_combined"),
    "positive_validation_folds": (4, "validation"),
    "parameter_stability_A": (0.5, "validation"),
    "parameter_stability_C": (0.5, "validation"),
    "deflated_sharpe": (0.99, "sealed_OOS"),
    "net_annualized_return": (0.08, "sealed_OOS"),
    "cost_stress": (0.02, "sealed_OOS"),
    "breadth_completed_trades": (600, "sealed_OOS"),
    "breadth_distinct_entry_dates": (150, "sealed_OOS"),
    "breadth_long_trades": (300, "sealed_OOS"),
    "breadth_short_trades": (300, "sealed_OOS"),
    "trade_concentration_top10": (0.15, "sealed_OOS"),
    "trade_concentration_single_stock": (0.05, "sealed_OOS"),
    "annual_positive_years": (4, "validation+OOS_combined"),
    "annual_largest_positive_year_fraction": (0.30, "validation+OOS_combined"),
    "trend_regimes_positive_count": (3, "validation+OOS_combined"),
    "trend_regime_loss_concentration": (0.40, "validation+OOS_combined"),
    "volatility_regime_floor": (-0.20, "validation+OOS_combined"),
    "capacity": (0.01, "sealed_OOS"),
}
REQ_DIAGS = ["pbo", "positive_pnl_regime_concentration", "annual_herfindahl", "severe_cost_stress"]


def _full_battery(overrides=None, drop=None, dup=None, diag_error=None, diag_drop=None):
    overrides = overrides or {}
    b = G.GateBattery()
    for gid, (val, sample) in PASS_GATES.items():
        if drop and gid in drop:
            continue
        v = overrides.get(gid, val)
        b.add_gate(gid, v, sample=sample)
    if dup:
        val, sample = PASS_GATES[dup]
        b.add_gate(dup, val, sample=sample)
    for d in REQ_DIAGS:
        if diag_drop and d == diag_drop:
            continue
        b.add_diagnostic(d, 0.1, error=(diag_error == d))
    return b


# ── governing-identity chain ──────────────────────────────────────────────────────────────────────
def test_01_load_returns_N5_from_ledger_no_constant():
    loaded = load_governing_identity(GOV_DIR)
    assert loaded["dsr_trials_N"] == 5
    assert loaded["validation_authorization"] is False
    import mr002_valoos_identity as ident
    assert not hasattr(ident, "TRIALS_N")


def _real_dicts():
    def rd(name):
        return copy.deepcopy(json.load(open(os.path.join(GOV_DIR, name), encoding="utf-8")))
    return rd(PREREG), rd(LEDGER), rd(RESOLUTION)


def test_02_semantic_bool_where_int_rejected():
    prereg, ledger, res = _real_dicts()
    ledger["trials_N"] = True                            # bool masquerading as int
    with pytest.raises(RefusedIdentity, match="NON_INT"):
        _validate_semantics(prereg, ledger, res)


def test_03_semantic_resolution_ledger_crossbinding():
    prereg, ledger, res = _real_dicts()
    res["countersigned_trial_ledger"]["sha256"] = "0" * 64
    with pytest.raises(RefusedIdentity, match="RESOLUTION_LEDGER_HASH_UNBOUND"):
        _validate_semantics(prereg, ledger, res)


def test_04_semantic_resolution_prereg_crossbinding():
    prereg, ledger, res = _real_dicts()
    res["prereg_update"]["to_sha256"] = "0" * 64
    with pytest.raises(RefusedIdentity, match="RESOLUTION_PREREG_HASH_UNBOUND"):
        _validate_semantics(prereg, ledger, res)


def test_05_semantic_N_chain_inconsistent():
    prereg, ledger, res = _real_dicts()
    prereg["dsr"]["trials_N"] = 4
    with pytest.raises(RefusedIdentity, match="N_CHAIN_INCONSISTENT"):
        _validate_semantics(prereg, ledger, res)


def test_06_semantic_validation_auth_not_false():
    prereg, ledger, res = _real_dicts()
    prereg["sequencing"]["validation_authorization"] = 0   # int, not False
    with pytest.raises(RefusedIdentity, match="VALIDATION_AUTH_NOT_FALSE"):
        _validate_semantics(prereg, ledger, res)


def test_07_semantic_ledger_id_set():
    prereg, ledger, res = _real_dicts()
    ledger["included_trials_ids"][4] = "RNG-WRONG"
    with pytest.raises(RefusedIdentity, match="LEDGER_ID_SET"):
        _validate_semantics(prereg, ledger, res)


def test_08_duplicate_json_key_rejected():
    from mr002_valoos_identity import _loads_strict
    with pytest.raises(RefusedIdentity, match="DUPLICATE_JSON_KEY:trials_N"):
        _loads_strict(b'{"trials_N": 5, "x": 1, "trials_N": 9}')


def test_09_symlink_and_missing_refused():
    with tempfile.TemporaryDirectory() as tmp:
        for f in (PREREG, RESOLUTION):
            shutil.copyfile(os.path.join(GOV_DIR, f), os.path.join(tmp, f))
        with pytest.raises(RefusedIdentity, match="MISSING"):
            load_governing_identity(tmp)


def test_10_registry_cross_validates_and_refuses_divergence():
    loaded = load_governing_identity(GOV_DIR)
    cross_validate_registry(loaded["gates_frozen"])          # passes
    bad = copy.deepcopy(loaded["gates_frozen"])
    bad["net_oos_calmar_min"] = 0.80
    with pytest.raises(RefusedIdentity, match="REGISTRY_THRESHOLD_DIVERGES"):
        cross_validate_registry(bad)


# ── gate completeness + verdict split ─────────────────────────────────────────────────────────────
def test_11_full_battery_pass():
    v = _full_battery().evaluate()
    assert v["research_gate_verdict"] == "PASS" and v["run_disposition"] == "PASS"


def test_12_missing_required_gate_stops():
    v = _full_battery(drop={"capacity"}).evaluate()
    assert v["run_disposition"] == "INTEGRITY_STOP"
    assert v["stop_code"] == "INTEGRITY_STOP:MISSING_REQUIRED_GATE:capacity"


def test_13_twelve_of_twentytwo_never_passes():
    keep = list(PASS_GATES)[:12]
    v = _full_battery(drop=set(PASS_GATES) - set(keep)).evaluate()
    assert v["run_disposition"] == "INTEGRITY_STOP"
    assert v["run_disposition"] != "PASS"


def test_14_duplicate_gate_stops():
    v = _full_battery(dup="net_sharpe").evaluate()
    assert v["stop_code"].startswith("INTEGRITY_STOP:DUPLICATE_GATE")


def test_15_unknown_gate_stops():
    b = _full_battery()
    b.add_gate("bogus_gate", 1.0, sample="sealed_OOS")   # unknown → ERROR entry, caught in enforce
    v = b.evaluate()
    assert v["stop_code"].startswith("INTEGRITY_STOP:UNKNOWN_GATE")


def test_16_sample_mismatch_stops():
    b = _full_battery()
    # rebuild with a wrong sample on one gate
    b = G.GateBattery()
    for gid, (val, sample) in PASS_GATES.items():
        s = "validation" if gid == "net_sharpe" else sample   # net_sharpe should be sealed_OOS
        b.add_gate(gid, val, sample=s)
    for d in REQ_DIAGS:
        b.add_diagnostic(d, 0.1)
    v = b.evaluate()
    assert v["stop_code"].startswith("INTEGRITY_STOP:GATE_SAMPLE_MISMATCH:net_sharpe")


def test_17_wrong_threshold_refuses():
    b = _full_battery()
    # inject an entry with a tampered threshold (as if a divergent registry produced it)
    spec = REQUIRED_GATES["net_sharpe"]
    b.entries = [e for e in b.entries if e.gate_id != "net_sharpe"]
    b.entries.append(G.GateResult("net_sharpe", G.GATE, G.PASS, 1.5, 0.60, spec.sample, ""))
    v = b.evaluate()
    assert v["run_disposition"] == "REFUSED"
    assert v["stop_code"].startswith("REFUSED_CODE_OR_DATA_IDENTITY:GATE_THRESHOLD")


def test_18_required_gate_error_stops():
    b = G.GateBattery()
    for gid, (val, sample) in PASS_GATES.items():
        b.add_gate(gid, val, sample=sample, error=(gid == "deflated_sharpe"))
    for d in REQ_DIAGS:
        b.add_diagnostic(d, 0.1)
    v = b.evaluate()
    assert v["stop_code"] == "INTEGRITY_STOP:GATE_COMPUTATION_ERROR:deflated_sharpe"


def test_19_headline_gates_fail_independently():
    for gid in ("net_sharpe", "bootstrap_mean_lower_bound", "deflated_sharpe"):
        val = {"net_sharpe": 0.5, "bootstrap_mean_lower_bound": -1e-6, "deflated_sharpe": 0.90}[gid]
        v = _full_battery(overrides={gid: val}).evaluate()
        assert v["research_gate_verdict"] == "FAIL" and v["run_disposition"] == "FAIL", gid


# ── diagnostic isolation ──────────────────────────────────────────────────────────────────────────
def test_20_unfavorable_diagnostic_never_fails():
    b = G.GateBattery()
    for gid, (val, sample) in PASS_GATES.items():
        b.add_gate(gid, val, sample=sample)
    for d in REQ_DIAGS:
        b.add_diagnostic(d, 0.99)                        # terrible but valid diagnostic values
    v = b.evaluate()
    assert v["research_gate_verdict"] == "PASS" and v["run_disposition"] == "PASS"


def test_21_diagnostic_error_blocks_publication_only():
    v = _full_battery(diag_error="pbo").evaluate()
    assert v["research_gate_verdict"] == "PASS"           # research verdict still computable
    assert v["run_disposition"] == "INTEGRITY_STOP"
    assert v["stop_code"] == "INTEGRITY_STOP:DIAGNOSTIC_COMPUTATION_ERROR:pbo"


def test_22_missing_diagnostic_blocks_publication():
    v = _full_battery(diag_drop="annual_herfindahl").evaluate()
    assert v["run_disposition"] == "INTEGRITY_STOP"
    assert "DIAGNOSTIC_COMPUTATION_ERROR:MISSING:annual_herfindahl" in v["stop_code"]


def test_23_diagnostic_only_change_leaves_disposition():
    a = _full_battery().evaluate()
    b = G.GateBattery()
    for gid, (val, sample) in PASS_GATES.items():
        b.add_gate(gid, val, sample=sample)
    for d in REQ_DIAGS:
        b.add_diagnostic(d, 0.42)                        # different diagnostic values only
    assert a["run_disposition"] == b.evaluate()["run_disposition"] == "PASS"


# ── compounded return / drawdown / calmar (hand-derived) ──────────────────────────────────────────
HAND_R = [0.01, -0.02, 0.03, -0.01, 0.02]
HAND_GEO_ANN = 3.325636719291218
HAND_MAXDD = 0.020000000000000018
HAND_CALMAR = 166.28183596456074


def test_24_compounded_return_and_drawdown_hand_values():
    assert M.geometric_annualized_return(HAND_R) == pytest.approx(HAND_GEO_ANN, rel=1e-12)
    assert M.compounded_max_drawdown(HAND_R) == pytest.approx(HAND_MAXDD, rel=1e-12)
    c = M.calmar(HAND_R)
    assert c["value"] == pytest.approx(HAND_CALMAR, rel=1e-12) and c["gate_pass"] is True


def test_25_arithmetic_mean_is_descriptive_only():
    # arithmetic annualized mean differs from the geometric gate value
    assert M.arithmetic_annualized_mean(HAND_R) != pytest.approx(HAND_GEO_ANN, rel=1e-6)


def test_26_combined_maxdd_continuous_no_reset():
    val = [0.05, 0.05, 0.05]
    oos = [-0.04, -0.04, -0.04]
    combined = M.combined_max_drawdown(val, oos)
    oos_only = M.compounded_max_drawdown(oos)
    # continuous path drops from the validation peak → deeper than OOS-only (which resets to 1.0)
    assert combined > oos_only


def test_27_calmar_positive_infinity_status_object():
    c = M.calmar([0.01, 0.02, 0.03])                     # monotone up → MaxDD 0, return > 0
    assert c["value"] is None and c["comparison_value"] == "POSITIVE_INFINITY"
    assert c["gate_pass"] is True


def test_28_calmar_zero_dd_nonpositive_return_stops():
    with pytest.raises(M.IntegrityStop, match="ZERO_DRAWDOWN_NONPOSITIVE_RETURN"):
        M.calmar([0.0, 0.0, 0.0])


def test_29_nonpositive_wealth_stops():
    with pytest.raises(M.IntegrityStop, match="NONPOSITIVE_WEALTH"):
        M.compounded_wealth([0.01, -1.0, 0.02])


# ── bootstrap ─────────────────────────────────────────────────────────────────────────────────────
def test_30_block_index_sequence_frozen():
    idx = M._block_indices(5, 2, np.random.default_rng(7))
    assert idx.tolist() == [4, 3, 4, 3, 4]


def test_31_bootstrap_param_validation():
    with pytest.raises(M.IntegrityStop, match="N<2"):
        M.block_bootstrap_mean_lower_bound([0.01])
    with pytest.raises(M.IntegrityStop, match="BLOCK"):
        M.block_bootstrap_mean_lower_bound(np.zeros(30) + 0.001, block=99)
    with pytest.raises(M.IntegrityStop, match="RESAMPLES"):
        M.block_bootstrap_mean_lower_bound(np.linspace(-0.01, 0.01, 30), resamples=10)
    with pytest.raises(M.IntegrityStop, match="CONFIDENCE"):
        M.block_bootstrap_mean_lower_bound(np.linspace(-0.01, 0.01, 30), confidence=1.5)


# ── DSR (independently derived expected values) ───────────────────────────────────────────────────
DSR_SERIES = np.random.default_rng(123).normal(0.001, 0.01, 40)
DSR_N1_EXPECTED = 0.9485960168552995
DSR_N5_EXPECTED = 0.8296873320858645
SR0_N5_STD01_EXPECTED = 0.11925940010147894


def _independent_dsr(x, trials_n, trial_std, benchmark=0.0):
    mean = x.mean()
    sd1 = x.std(ddof=1)
    sd0 = x.std(ddof=0)
    sr = mean / sd1
    z = (x - mean) / sd0
    skew = (z ** 3).mean()
    kurt = (z ** 4).mean()
    if trials_n == 1:
        sr0 = benchmark
    else:
        z1 = norm.ppf(1 - 1 / trials_n)
        z2 = norm.ppf(1 - 1 / (trials_n * math.e))
        sr0 = benchmark + trial_std * ((1 - EULER) * z1 + EULER * z2)
    denom = math.sqrt(1 - skew * sr + (kurt - 1) / 4 * sr ** 2)
    return float(norm.cdf((sr - sr0) * math.sqrt(x.size - 1) / denom))


def test_32_dsr_N1_matches_independent():
    got = M.deflated_sharpe(DSR_SERIES, trials_n=1, trial_sharpe_std=0.1)["dsr"]
    assert got == pytest.approx(_independent_dsr(DSR_SERIES, 1, 0.1), rel=1e-12)
    assert got == pytest.approx(DSR_N1_EXPECTED, rel=1e-12)


def test_33_dsr_N5_matches_independent():
    got = M.deflated_sharpe(DSR_SERIES, trials_n=5, trial_sharpe_std=0.1)["dsr"]
    assert got == pytest.approx(_independent_dsr(DSR_SERIES, 5, 0.1), rel=1e-12)
    assert got == pytest.approx(DSR_N5_EXPECTED, rel=1e-12)


def test_34_expected_max_sharpe_exact():
    assert M.expected_max_sharpe(5, 0.1) == pytest.approx(SR0_N5_STD01_EXPECTED, rel=1e-12)


def test_35_dsr_zero_dispersion_reduces_to_benchmark():
    assert M.expected_max_sharpe(5, 0.0) == 0.0
    d = M.deflated_sharpe(DSR_SERIES, trials_n=5, trial_sharpe_std=0.0)
    assert d["expected_max_sharpe"] == 0.0


def test_36_dsr_too_short_sample_stops():
    with pytest.raises(M.IntegrityStop, match="DSR_SAMPLE_TOO_SHORT"):
        M.deflated_sharpe(np.linspace(-0.01, 0.01, 10), trials_n=5, trial_sharpe_std=0.1)


def test_37_dsr_denom_nonpositive_stops(monkeypatch):
    monkeypatch.setattr(M, "_sample_moments", lambda r: (5.0, 1.0, 1.0))  # denom²=1-5+0<0
    with pytest.raises(M.IntegrityStop, match="DSR_DENOM_NONPOSITIVE"):
        M.deflated_sharpe(DSR_SERIES, trials_n=5, trial_sharpe_std=0.1)


def test_38_dsr_invalid_trials_n():
    with pytest.raises(M.IntegrityStop, match="INVALID_TRIALS_N"):
        M.deflated_sharpe(DSR_SERIES, trials_n=True, trial_sharpe_std=0.1)   # bool rejected
    with pytest.raises(M.IntegrityStop, match="INVALID_TRIALS_N"):
        M.deflated_sharpe(DSR_SERIES, trials_n=0, trial_sharpe_std=0.1)


def test_39_dsr_labels_dispersion_synthetic():
    d = M.deflated_sharpe(DSR_SERIES, trials_n=5, trial_sharpe_std=0.1)
    assert d["trial_sharpe_std_provenance"] == "SYNTHETIC"


# ── canonical exact-float report ──────────────────────────────────────────────────────────────────
def test_40_signed_zero_preserved_and_distinct():
    assert R.encode_float(-0.0)["exact_hex"] == "-0x0.0p+0"
    assert R.encode_float(0.0)["exact_hex"] == "0x0.0p+0"
    assert R.encode_float(-0.0)["exact_hex"] != R.encode_float(0.0)["exact_hex"]


def test_41_canonical_rejects_nonfinite_numpy_set_nonstrkey():
    with pytest.raises(R.CanonicalizationError, match="NONFINITE_FLOAT"):
        R.canonical_bytes({"x": float("nan")})
    with pytest.raises(R.CanonicalizationError, match="NONFINITE_FLOAT"):
        R.canonical_bytes({"x": float("inf")})
    with pytest.raises(R.CanonicalizationError, match="NUMPY_SCALAR"):
        R.canonical_bytes({"x": np.float64(1.0)})
    with pytest.raises(R.CanonicalizationError, match="SET_NOT_ALLOWED"):
        R.canonical_bytes({"x": {1, 2}})
    with pytest.raises(R.CanonicalizationError, match="NON_STRING_KEY"):
        R.canonical_bytes({1: "x"})


def _canonical_report():
    loaded = load_governing_identity(GOV_DIR)
    b = _full_battery()
    verdict = b.evaluate()
    return R.build_report(window="synthetic", verdict=verdict, governing_identity=loaded,
                          code_identity={"module": "increment1-v1.1"},
                          dependency_identity={"numpy": np.__version__},
                          fixture_identity={"fixture": "full-battery", "seed": 42},
                          metric_values={"net_sharpe": 1.5, "neg_zero_probe": -0.0},
                          gate_results=b.to_list(), diagnostics=b.diagnostics_list(),
                          hard_stop_evidence=None, seed=42)


def test_42_report_determinism_and_self_hash():
    r1, r2 = _canonical_report(), _canonical_report()
    assert r1["output_hash"] == r2["output_hash"]
    assert R.report_hash(r1) == r1["output_hash"]
    assert r1["research_gate_verdict"] == "PASS" and r1["run_disposition"] == "PASS"
    assert r1["validation_data_read"] is False and r1["synthetic_fixture_only"] is True
    # the -0.0 probe survives canonicalization as an exact hex, not a normalized 0.0
    assert r1["metric_values"]["neg_zero_probe"]["exact_hex"] == "-0x0.0p+0"


# ── supporting metric closed-form ─────────────────────────────────────────────────────────────────
def test_43_supporting_metric_gates():
    trades = ([{"entry_date": f"d{i % 120}", "side": "long"} for i in range(300)]
              + [{"entry_date": f"d{i % 120}", "side": "short"} for i in range(300)])
    assert M.breadth(trades)["gate_pass"] is True
    pnl = np.concatenate([np.full(200, 5.0), np.full(10, 1.0)])
    assert M.trade_concentration(pnl, [f"s{i}" for i in range(210)])["gate_pass"] is True
    assert M.annual_profile({2020: 100.0, 2021: 120.0, 2022: 110.0, 2023: 90.0})["gate_pass"] is True
    trend = {"up": 500.0, "flat": 300.0, "down": 50.0}
    mins = {k: 200 for k in ("up", "flat", "down", "low", "high")}
    assert M.regime_gates(trend, {"low": 0.5, "high": 0.2}, min_sessions=mins)["gate_pass"] is True
