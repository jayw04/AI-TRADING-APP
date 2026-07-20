"""MKT-PROJ-001 §4 serving tests: capped claim, drift ladder, grading, tick-and-check."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from app.services.market_projection import outcomes as oc
from app.services.market_projection import train as tr
from app.services.market_projection.infer import confidence_for, next_cutoff_for, run_projection
from app.services.market_projection.schemas import (
    PHRASE_ELEVATED,
    PHRASE_NOT_ELEVATED,
    PRECLOSE_FEATURES,
    ProjectionType,
)

RNG = np.random.default_rng(3)
FORBIDDEN = ("UP", "DOWN", "buy", "sell", "direction_up", "supports_")


def _rows(n: int = 300) -> list[dict]:
    rows, d = [], date(2019, 1, 2)
    while len(rows) < n:
        if d.weekday() < 5:
            feats = {name: float(RNG.normal()) for name in PRECLOSE_FEATURES}
            label = ["UP", "DOWN", "NEUTRAL"][int(RNG.integers(0, 3))]
            rows.append({"date": d, "label": label, "realized_return": 0.0,
                         "features_json": feats})
        d += timedelta(days=1)
    return rows


def test_confidence_mapping_frozen_18() -> None:
    assert confidence_for({"UP": 0.62, "DOWN": 0.10, "NEUTRAL": 0.28}) == "HIGH"
    assert confidence_for({"UP": 0.52, "DOWN": 0.20, "NEUTRAL": 0.28}) == "MEDIUM"
    assert confidence_for({"UP": 0.40, "DOWN": 0.35, "NEUTRAL": 0.25}) == "LOW"


def test_run_projection_capped_claim_and_no_directional_vocabulary() -> None:
    rows = _rows()
    models = tr.fit_models(rows, ProjectionType.PRE_CLOSE_TOMORROW)
    features = dict(rows[-1]["features_json"])
    cutoff = datetime(2026, 7, 10, 19, 45, tzinfo=UTC)
    fields = run_projection(models, features, {"feed": "iex", "threshold_pct": 0.75},
                            day=date(2026, 7, 10), cutoff_et=cutoff, model_version="mv-test")
    assert fields["run_status"] == "SUCCESS"
    assert fields["display_phrase"] in (PHRASE_ELEVATED, PHRASE_NOT_ELEVATED)
    assert fields["elevated"] == (fields["prob_material"] >= 0.5)
    # the served drivers payload carries NO directional vocabulary (owner Q1/G3)
    blob = json.dumps(fields["drivers_json"])
    assert "raises_move_risk" in blob or "lowers_move_risk" in blob
    for word in FORBIDDEN:
        assert word not in blob


def test_run_projection_manifest_mismatch_refuses() -> None:
    rows = _rows()
    models = tr.fit_models(rows, ProjectionType.PRE_CLOSE_TOMORROW)
    bad = dict(rows[-1]["features_json"])
    bad.pop(next(iter(bad)))
    with pytest.raises(ValueError, match="manifest"):
        run_projection(models, bad, {}, day=date(2026, 7, 10),
                       cutoff_et=datetime.now(UTC), model_version="mv")


# --- drift ladder (owner-amended rule) ----------------------------------------------

@pytest.fixture
def drift_env(tmp_path, monkeypatch):
    monkeypatch.setattr(oc, "DRIFT_DIR", str(tmp_path))
    monkeypatch.setattr(oc, "DRIFT_STATE", str(tmp_path / "drift_state.json"))
    monkeypatch.setattr(oc, "DRIFT_LEDGER", str(tmp_path / "drift_ledger.jsonl"))
    return tmp_path


def test_drift_warning_at_half_sigma(drift_env) -> None:
    state = oc.apply_drift_ladder(date(2026, 7, 13), {"spy_dist_ma50": 0.6, "fade_recovery": 0.1})
    assert state["status"] == "warning"
    assert "spy_dist_ma50" in state["features"]


def test_drift_hard_downgrade_at_one_sigma(drift_env) -> None:
    state = oc.apply_drift_ladder(date(2026, 7, 13), {"spy_dist_ma50": 1.2})
    assert state["status"] == "downgraded"
    assert "operator-only" in state["restore"]


def test_drift_downgrade_three_consecutive_days(drift_env) -> None:
    for i, day in enumerate((date(2026, 7, 13), date(2026, 7, 14), date(2026, 7, 15))):
        state = oc.apply_drift_ladder(day, {"fade_recovery": 0.6,
                                            "spy_intraday_vol": 0.1 * i})
    assert state["status"] == "downgraded"
    assert any("3 consecutive" in r for r in state["reasons"])


def test_drift_downgrade_breadth(drift_env) -> None:
    drift = {name: 0.6 for name in list(PRECLOSE_FEATURES)[:6]}
    drift.update({name: 0.1 for name in list(PRECLOSE_FEATURES)[6:19]})
    state = oc.apply_drift_ladder(date(2026, 7, 13), drift)
    assert state["status"] == "downgraded"
    assert any("%" in r for r in state["reasons"])


def test_drift_downgrade_is_sticky_operator_only(drift_env) -> None:
    oc.apply_drift_ladder(date(2026, 7, 13), {"spy_dist_ma50": 1.5})
    state = oc.apply_drift_ladder(date(2026, 7, 14), {})  # a clean day does NOT restore
    assert state["status"] == "downgraded"


# --- grading (guardrail 4) -----------------------------------------------------------

def _spy_daily() -> pd.DataFrame:
    days = [date(2026, 7, 8), date(2026, 7, 9), date(2026, 7, 10)]
    return pd.DataFrame({"open": 100.0, "high": 101.0, "low": 99.0,
                         "close": [100.0, 101.0, 100.2], "volume": 1e6}, index=days)


def test_grade_run_fields_matured_and_correctness() -> None:
    run = SimpleNamespace(target_date=date(2026, 7, 8), material_threshold_pct=0.75,
                          elevated=True, prob_up=0.4, prob_down=0.2, prob_neutral=0.4)
    fields = oc.grade_run_fields(run, _spy_daily())
    assert fields["realized_return"] == pytest.approx(1.0)   # 100 → 101
    assert fields["realized_label"] == "UP"
    assert fields["correct_magnitude"] is True               # elevated & material
    assert fields["prob_assigned_to_realized_class"] == pytest.approx(0.4)


def test_grade_run_fields_not_matured_returns_none() -> None:
    run = SimpleNamespace(target_date=date(2026, 7, 10), material_threshold_pct=0.75,
                          elevated=False, prob_up=0.2, prob_down=0.2, prob_neutral=0.6)
    assert oc.grade_run_fields(run, _spy_daily()) is None


# --- calendar tick-and-check -----------------------------------------------------------

def test_next_cutoff_full_day_and_weekend() -> None:
    cutoff = next_cutoff_for(date(2026, 7, 10))            # a regular Friday
    assert cutoff is not None and cutoff.strftime("%H:%M") == "15:45"
    assert next_cutoff_for(date(2026, 7, 11)) is None      # Saturday
