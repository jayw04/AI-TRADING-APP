"""SEC-001 V2 Pure Sector Baskets research — pure helpers (offline)."""

from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "sector_rotation_v2_research.py"
_spec = importlib.util.spec_from_file_location("sector_rotation_v2_research", _SCRIPT)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)

basket_weights = _mod.basket_weights
v1_weights = _mod.v1_weights
windows = _mod._windows
paired_ci = _mod._paired_sharpe_diff_ci
excludes_zero_pos = _mod._excludes_zero_pos
blend_curve = _mod._blend_curve

# A tiny ranked sector world: 3 sectors strong->weak, with 2/1/3 names.
_RANKED = ["Tech", "Energy", "Health"]
_NAMES = {"Tech": ["AAPL", "MSFT"], "Energy": ["XOM"], "Health": ["JNJ", "PFE", "MRK"]}
_SECMOM = {"Tech": 0.30, "Energy": 0.10, "Health": -0.05}


def test_basket_weights_sector_neutral_and_sum_to_one():
    w = basket_weights(_RANKED, _NAMES, 2)  # top-2 sectors: Tech + Energy
    assert set(w) == {"AAPL", "MSFT", "XOM"}
    # each held sector gets a 1/K = 0.5 sleeve, equal-weight within
    assert w["AAPL"] == w["MSFT"] == 0.25          # 0.5 / 2 names
    assert w["XOM"] == 0.5                          # 0.5 / 1 name
    assert abs(sum(w.values()) - 1.0) < 1e-12       # fully invested


def test_basket_weights_topk_selects_strongest_sectors():
    w1 = basket_weights(_RANKED, _NAMES, 1)         # only the strongest sector
    assert set(w1) == {"AAPL", "MSFT"}
    assert abs(sum(w1.values()) - 1.0) < 1e-12
    w_all = basket_weights(_RANKED, _NAMES, 99)     # K >= sectors -> hold all
    assert set(w_all) == {"AAPL", "MSFT", "XOM", "JNJ", "PFE", "MRK"}
    assert abs(sum(w_all.values()) - 1.0) < 1e-12
    # sector-neutral: each sector sleeve is 1/3 regardless of name count
    assert abs(w_all["XOM"] - 1 / 3) < 1e-12        # 1 name in Energy
    assert abs(w_all["AAPL"] - (1 / 3) / 2) < 1e-12  # 2 names in Tech


def test_basket_weights_empty_when_no_named_sectors():
    assert basket_weights(_RANKED, {"Tech": [], "Energy": []}, 2) == {}
    assert basket_weights([], {}, 3) == {}


def test_v1_weights_top_quintile_equal_weight():
    # 6 names, top-quintile = ceil(0.2*6)=2; scored by sector momentum so the 2 Tech names win
    w = v1_weights(_NAMES, _SECMOM)
    assert set(w) == {"AAPL", "MSFT"}
    assert w["AAPL"] == w["MSFT"] == 0.5
    assert abs(sum(w.values()) - 1.0) < 1e-12


def test_windows_contiguous_and_cover_range():
    ws = windows(date(2000, 1, 1), date(2026, 6, 12), 5)
    assert len(ws) == 5
    assert ws[0][0] == date(2000, 1, 1) and ws[-1][1] == date(2026, 6, 12)
    for a, b in zip(ws, ws[1:], strict=False):
        assert a[1] == b[0]


def test_paired_ci_identical_series_is_zero_and_deterministic():
    r = [0.01, -0.02, 0.015, -0.005, 0.02, -0.01] * 10
    ci = paired_ci(r, list(r), n_resamples=200, seed=17)
    assert ci["delta"] == 0.0 and ci["ci_low"] == 0.0 and ci["ci_high"] == 0.0
    a = [0.01, -0.02, 0.015, -0.005, 0.02, -0.01, 0.008, -0.003] * 8
    b = [x * 0.8 for x in a]
    assert paired_ci(a, b, n_resamples=300, seed=17) == paired_ci(a, b, n_resamples=300, seed=17)


def test_excludes_zero_pos():
    assert excludes_zero_pos({"ci_low": 0.05}) is True
    assert excludes_zero_pos({"ci_low": -0.01}) is False
    assert excludes_zero_pos({"ci_low": float("nan")}) is False


def test_blend_curve_is_5050_of_daily_returns():
    a = [(date(2020, 1, 1), 110.0), (date(2020, 1, 2), 121.0)]   # +10%, +10%
    b = [(date(2020, 1, 1), 100.0), (date(2020, 1, 2), 100.0)]   # 0%, 0% (from initial 100)
    c = blend_curve(a, b, initial=100.0)
    # day-1 blended return = 0.5*0.10 + 0.5*0.00 = 0.05 -> 105
    assert abs(c[0][1] - 105.0) < 1e-9


def test_frozen_constants():
    assert _mod.LOOKBACK_DAYS == 252 and _mod.SKIP_DAYS == 21  # 12-1 frozen, identical to V1
    assert _mod.TOP_QUANTILE_V1 == 0.20
