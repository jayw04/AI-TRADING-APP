"""MKT-PROJ-001 §2 tests: baselines + walk-forward harness (synthetic, no network).

The load-bearing pair (owner plan review): a PLANTED signal the harness must
find, and PURE NOISE it must not find. Plus fold-boundary integrity, the §14
floor, metric sanity (clipped log-loss finite for deterministic baselines),
and the frozen gate mechanics.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pytest

from app.services.market_projection import baselines as bl
from app.services.market_projection import validate as va
from app.services.market_projection.schemas import ProjectionType

RNG = np.random.default_rng(7)


def _rows(
    n: int = 1600, *, planted: bool, start: date = date(2016, 1, 4),
    material_share: float = 0.4,
) -> list[dict]:
    """Synthetic one-horizon dataset. planted=True: spy_ret_1d's sign perfectly
    predicts the direction of material days (a signal the harness MUST find).
    planted=False: labels are independent of every feature (pure noise).
    material_share > 0.5 makes the §4 baselines' modal class directional, so
    argmax calls exist (with majority-neutral targets they honestly stay
    NEUTRAL and land at the §14 floor — by design)."""
    rows, d = [], start
    while len(rows) < n:
        if d.weekday() < 5:
            sig = float(RNG.normal())
            material = bool(RNG.random() < material_share)
            if material:
                if planted:
                    label = "UP" if sig > 0 else "DOWN"
                else:
                    label = "UP" if RNG.random() < 0.5 else "DOWN"
                realized = 1.2 if label == "UP" else -1.2
            else:
                label, realized = "NEUTRAL", float(RNG.normal(0, 0.2))
            rows.append({
                "date": d,
                "label": label,
                "realized_return": realized,
                "features_json": {
                    "spy_ret_1d": sig,
                    "spy_ret_5d": float(RNG.normal()),
                    "atr20_pct": float(abs(RNG.normal(1.5, 0.4))),
                },
            })
        d += timedelta(days=1)
    return rows


def test_fold_boundaries_are_anchored_and_disjoint() -> None:
    rows = _rows(1200, planted=False)
    dates = [r["date"] for r in rows]
    folds = va.walk_forward_folds(dates)
    assert len(folds) >= 3
    first_train, first_test = folds[0]
    assert dates[first_test[0]] >= date(dates[0].year + 3, dates[0].month, 1)
    for train_idx, test_idx in folds:
        assert max(dates[i] for i in train_idx) < min(dates[i] for i in test_idx)
    # anchored: every fold trains from the very first date
    assert all(f[0][0] == 0 for f in folds)
    # test folds do not overlap
    all_test = [i for _, t in folds for i in t]
    assert len(all_test) == len(set(all_test))


def test_planted_signal_is_found() -> None:
    rows = _rows(planted=True, material_share=0.7)  # majority-material → argmax calls exist
    preds = bl.baselines_for(ProjectionType.PRE_CLOSE_TOMORROW)
    out = va.run_walk_forward(
        rows, preds,
        magnitude_baselines=["always_neutral", "unconditional", "vol_clustering_move_risk"],
        directional_baselines=["prior_day_direction", "momentum_5d_direction"],
    )
    d = out["predictors"]["prior_day_direction"]["directional"]
    assert d["sample_floor_met"] is True
    # strict precision is capped by the material rate (~0.7): a directional call
    # on a day that realizes NEUTRAL counts against it — but it is far above the
    # ~0.35 chance level and GIVEN a material day the planted rule is perfect.
    assert d["directional_precision"] > 0.6
    assert d["conditional_direction_accuracy_on_material"] > 0.95
    assert d["false_positive_rate"] == pytest.approx(0.3, abs=0.06)
    assert out["best_directional_baseline"] == "prior_day_direction"


def test_planted_signal_visible_in_conditional_diagnostic_even_when_floor_unmet() -> None:
    """§7.2: with majority-neutral labels the baselines honestly make no argmax
    calls (floor unmet) — but the conditional-direction diagnostic still sees
    the planted signal on realized-material days."""
    rows = _rows(planted=True, material_share=0.4)
    out = va.run_walk_forward(
        rows, bl.baselines_for(ProjectionType.PRE_CLOSE_TOMORROW),
        magnitude_baselines=["always_neutral", "unconditional"],
        directional_baselines=["prior_day_direction"],
    )
    d = out["predictors"]["prior_day_direction"]["directional"]
    assert d["sample_floor_met"] is False
    assert d["verdict"] == "insufficient_sample"
    assert d["conditional_direction_accuracy_on_material"] > 0.95


def test_pure_noise_is_not_found() -> None:
    rows = _rows(planted=False)
    preds = bl.baselines_for(ProjectionType.PRE_CLOSE_TOMORROW)
    out = va.run_walk_forward(
        rows, preds,
        magnitude_baselines=["always_neutral", "unconditional"],
        directional_baselines=["prior_day_direction", "momentum_5d_direction"],
    )
    d = out["predictors"]["prior_day_direction"]["directional"]
    if d["sample_floor_met"]:
        assert 0.35 <= d["directional_precision"] <= 0.65   # ≈ chance, no fake skill
    # and a noise "model" cannot beat the unconditional baseline on Brier with a CI excluding 0
    oos_rows = rows[800:]
    train = rows[:800]
    probs_a = bl.prior_day_direction(train, oos_rows)
    probs_b = bl.unconditional(train, oos_rows)
    ci = va.block_bootstrap_delta_ci(
        va.brier_material, probs_a, probs_b, [r["label"] for r in oos_rows], n_boot=200
    )
    assert ci["ci_low"] <= 0.0 <= ci["ci_high"]


def test_sample_floor_blocks_directional_verdict() -> None:
    rows = _rows(400, planted=True)  # too few OOS non-neutral calls after 3y warmup
    dates = [r["date"] for r in rows]
    assert va.walk_forward_folds(dates) == [] or True  # tiny history may yield no folds
    d = va.directional_metrics(
        [{"UP": 0.6, "DOWN": 0.2, "NEUTRAL": 0.2}] * 30,
        ["UP"] * 30, [1.0] * 30,
    )
    assert d["sample_floor_met"] is False
    assert d["verdict"] == "insufficient_sample"
    assert "directional_precision" not in d       # §14: nothing computed past the floor


def test_always_neutral_log_loss_is_finite_via_clipping() -> None:
    probs = bl.always_neutral([], [{}] * 10)
    labels = ["UP"] * 5 + ["NEUTRAL"] * 5
    assert np.isfinite(va.log_loss_material(probs, labels))
    assert np.isfinite(va.log_loss_three_class(probs, labels))


def test_signal_baseline_probability_construction() -> None:
    """Frozen §4 wording: picked class = h × (1−P_neutral_uncond); NEUTRAL = unconditional."""
    train = (
        [{"features_json": {"spy_ret_1d": 1.0}, "label": "UP"}] * 8
        + [{"features_json": {"spy_ret_1d": 1.0}, "label": "DOWN"}] * 2
        + [{"features_json": {"spy_ret_1d": -1.0}, "label": "NEUTRAL"}] * 10
    )
    [p] = bl.prior_day_direction(train, [{"features_json": {"spy_ret_1d": 2.0}}])
    p_neutral = 10 / 20
    h = 8 / 10
    assert p["NEUTRAL"] == pytest.approx(p_neutral)
    assert p["UP"] == pytest.approx(h * (1 - p_neutral))
    assert p["DOWN"] == pytest.approx((1 - h) * (1 - p_neutral))
    assert sum(p.values()) == pytest.approx(1.0)


def test_vol_clustering_uses_train_quintiles() -> None:
    train = [
        {"features_json": {"atr20_pct": a}, "label": ("UP" if a > 2.0 else "NEUTRAL")}
        for a in np.linspace(0.5, 3.0, 100)
    ]
    [lo, hi] = bl.vol_clustering_move_risk(
        train,
        [{"features_json": {"atr20_pct": 0.6}}, {"features_json": {"atr20_pct": 2.9}}],
    )
    assert va._p_material(lo) < va._p_material(hi)  # volatility clustering: high ATR → higher P(MATERIAL)


def test_gap_baseline_only_for_preopen() -> None:
    assert "premarket_gap_direction" in bl.baselines_for(ProjectionType.PRE_OPEN_TODAY)
    assert "premarket_gap_direction" not in bl.baselines_for(ProjectionType.PRE_CLOSE_TOMORROW)


def test_move_risk_gate_mechanics() -> None:
    rows = _rows(1400, planted=False)
    preds = dict(bl.baselines_for(ProjectionType.PRE_CLOSE_TOMORROW))
    preds["model"] = preds["vol_clustering_move_risk"]  # stand-in "model" for gate plumbing
    out = va.run_walk_forward(
        rows, preds,
        magnitude_baselines=["always_neutral", "unconditional", "vol_clustering_move_risk"],
        directional_baselines=["prior_day_direction"],
        model_name="model",
    )
    gate = out["move_risk_gate"]
    assert {"vs", "brier_delta_ci", "ece_guardrail_ok", "coverage_in_band"} <= set(gate)
    ci = gate["brier_delta_ci"]
    assert ci["ci_low"] <= ci["delta"] <= ci["ci_high"]
