"""MKT-PROJ-001 §3 tests: the frozen pipeline, calibrated models, attribution, registry.

Freeze-compliance is the point: train-window-only imputation/standardization,
the five §6a missingness indicators, the temporal calibration tail, logistic
attribution exactness, and hash-verified artifacts.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pytest

from app.services.market_projection import train as tr
from app.services.market_projection import validate as va
from app.services.market_projection.attribution import logistic_drivers
from app.services.market_projection.model_registry import load_artifact, save_artifact
from app.services.market_projection.schemas import PRECLOSE_FEATURES, ProjectionType

RNG = np.random.default_rng(11)


def _row(d: date, label: str, feats: dict) -> dict:
    base = {name: float(RNG.normal()) for name in PRECLOSE_FEATURES}
    base.update(feats)
    return {"date": d, "label": label, "realized_return": 1.0 if label == "UP" else
            (-1.0 if label == "DOWN" else 0.0), "features_json": base}


def _dataset(n: int = 1400, *, signal: bool) -> list[dict]:
    """When signal=True, materiality is a LINEAR COMBINATION of atr20_pct and
    spy_realized_vol_20d — the atr-quintile baseline sees only half of it, so a
    linear model must beat it; spy_ret_1d drives direction."""
    rows, d = [], date(2016, 1, 4)
    while len(rows) < n:
        if d.weekday() < 5:
            atr = float(abs(RNG.normal(1.5, 0.6)))
            rvol = float(abs(RNG.normal(15.0, 5.0)))
            sig = float(RNG.normal())
            if signal:
                combo = 1.2 * (atr - 1.5) / 0.6 + 1.2 * (rvol - 15.0) / 5.0
                material = RNG.random() < 1.0 / (1.0 + np.exp(-combo))
            else:
                material = RNG.random() < 0.4
            if material:
                label = ("UP" if sig > 0 else "DOWN") if signal else \
                        ("UP" if RNG.random() < 0.5 else "DOWN")
            else:
                label = "NEUTRAL"
            rows.append(_row(d, label, {
                "atr20_pct": atr, "spy_realized_vol_20d": rvol, "spy_ret_1d": sig,
            }))
        d += timedelta(days=1)
    return rows


# --- pipeline (§6a) ----------------------------------------------------------------

def test_pipeline_medians_and_scaling_are_train_only() -> None:
    p = tr.FeaturePipeline(("a", "b"))
    train = [{"features_json": {"a": v, "b": 2.0}} for v in (1.0, 2.0, 9.0)]
    p.fit_transform(train)
    medians_after_fit = p.medians.copy()
    # transforming wildly different data must not move the fitted parameters
    p.transform([{"features_json": {"a": 1000.0, "b": -500.0}}])
    assert np.array_equal(p.medians, medians_after_fit)


def test_pipeline_missingness_indicators_only_for_enumerated_fields() -> None:
    manifest = ("spy_gap_pct_qf", "spy_ret_1d")
    p = tr.FeaturePipeline(manifest)
    assert p.columns == ["spy_gap_pct_qf", "spy_ret_1d", "spy_gap_pct_qf_missing"]
    train = [
        {"features_json": {"spy_gap_pct_qf": 1.0, "spy_ret_1d": 0.5}},
        {"features_json": {"spy_gap_pct_qf": None, "spy_ret_1d": -0.5}},
        {"features_json": {"spy_gap_pct_qf": 3.0, "spy_ret_1d": 0.1}},
    ]
    x = p.fit_transform(train)
    assert x.shape == (3, 3)
    # the indicator column marks exactly the None row (pre-standardization it is 0/1;
    # verify via the raw assembly path)
    raw = p._assemble(p._raw(train))
    assert list(raw[:, 2]) == [0.0, 1.0, 0.0]
    # the imputed numeric value is the train-window median of observed values (2.0)
    assert raw[1, 0] == pytest.approx(2.0)


def test_calibration_tail_is_temporal() -> None:
    """The calibration slice is the FINAL contiguous 20% by date — verified by
    checking fit determinism against an explicit manual split."""
    rows = _dataset(400, signal=True)
    models = tr.fit_models(rows, ProjectionType.PRE_CLOSE_TOMORROW)
    # pipeline medians must equal medians of the FIRST 80% only
    split = int(len(rows) * 0.8)
    manual = tr.FeaturePipeline(tr.manifest_for(ProjectionType.PRE_CLOSE_TOMORROW))
    manual.fit_transform(sorted(rows, key=lambda r: r["date"])[:split])
    assert np.allclose(models.pipeline.medians, manual.medians, equal_nan=True)


# --- the model finds signal; probabilities are sane ---------------------------------

def test_logistic_beats_baselines_on_planted_materiality() -> None:
    rows = _dataset(1400, signal=True)
    from app.services.market_projection.baselines import baselines_for

    predictors = dict(baselines_for(ProjectionType.PRE_CLOSE_TOMORROW))
    predictors.update(tr.model_predictors(ProjectionType.PRE_CLOSE_TOMORROW))
    out = va.run_walk_forward(
        rows, predictors,
        magnitude_baselines=["always_neutral", "unconditional", "vol_clustering_move_risk"],
        directional_baselines=["prior_day_direction"],
        model_name="model_logistic",
    )
    gate = out["move_risk_gate"]
    m = out["predictors"]["model_logistic"]
    best = out["predictors"][gate["vs"]]
    assert m["brier_material"] < best["brier_material"]      # planted signal found
    assert gate["brier_delta_ci"]["ci_high"] < 0             # CI excludes zero
    assert "direction_gate" in out                            # gate wiring present either way


def test_model_probabilities_are_normalized() -> None:
    rows = _dataset(500, signal=True)
    models = tr.fit_models(rows[:400], ProjectionType.PRE_CLOSE_TOMORROW)
    for p in models.predict_logistic(rows[400:]):
        assert sum(p.values()) == pytest.approx(1.0, abs=1e-6)
        assert all(0.0 <= v <= 1.0 for v in p.values())
    for p in models.predict_ensemble(rows[400:]):
        assert sum(p.values()) == pytest.approx(1.0, abs=1e-6)


# --- attribution (FR-008) ------------------------------------------------------------

def test_logistic_attribution_is_exact_coef_times_value() -> None:
    rows = _dataset(600, signal=True)
    models = tr.fit_models(rows, ProjectionType.PRE_CLOSE_TOMORROW)
    x = models.pipeline.transform(rows[-1:])[0]
    from app.services.market_projection.attribution import _base_logistic

    base = _base_logistic(models.logistic)
    drivers = logistic_drivers(models.logistic, x, models.pipeline.columns, "UP", top_n=3)
    assert 1 <= len(drivers) <= 3
    for drv in drivers:
        j = models.pipeline.columns.index(drv["feature"])
        expected = base.coef_[list(base.classes_).index("UP")][j] * x[j]
        assert drv["weight"] == pytest.approx(abs(expected), abs=1e-3)
        assert drv["direction"] == ("supports_UP" if expected > 0 else "against_UP")


# --- registry (NFR-002) ---------------------------------------------------------------

def test_artifact_save_and_hash_verified_load(tmp_path) -> None:
    rows = _dataset(400, signal=False)
    models = tr.fit_models(rows, ProjectionType.PRE_CLOSE_TOMORROW)
    reg = save_artifact(
        models, projection_type="PRE_CLOSE_TOMORROW", model_type="calibrated_logistic_primary",
        training_window="2016-01-04..2017-06-30", validation_window="none",
        git_commit="abc1234", artifact_dir=str(tmp_path),
    )
    assert reg["status"] == "candidate"
    loaded = load_artifact(reg["artifact_path"], reg["artifact_hash"])
    a = loaded.predict_logistic(rows[:3])
    b = models.predict_logistic(rows[:3])
    assert a == b
    with pytest.raises(ValueError, match="hash mismatch"):
        load_artifact(reg["artifact_path"], "0" * 64)
