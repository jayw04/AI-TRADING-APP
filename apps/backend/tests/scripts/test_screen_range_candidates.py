"""§5b screen — screen_symbol pure-function tests (offline, synthetic bars).

Loaded via importlib (scripts/ isn't a package). No cache / network needed.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd

_SCRIPT = (
    Path(__file__).resolve().parents[2] / "scripts" / "screen_range_candidates.py"
)
_spec = importlib.util.spec_from_file_location("screen_range_candidates", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
# Register before exec so the module's dataclasses can resolve their own module
# (dataclasses looks up cls.__module__ in sys.modules under `from __future__
# import annotations`).
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)
screen_symbol = _mod.screen_symbol
ScreenConfig = _mod.ScreenConfig


def _df(closes: list[float], vol: float = 1_000_000.0, spread: float = 0.1) -> pd.DataFrame:
    n = len(closes)
    t = pd.date_range("2026-01-01", periods=n, freq="D", tz="UTC")
    c = pd.Series(closes, dtype=float)
    return pd.DataFrame(
        {"t": t, "o": c, "h": c + spread, "l": c - spread, "c": c, "v": [vol] * n}
    )


def test_range_bound_symbol_passes():
    # 6 cycles of a 10-bar triangle 100..110..100 → repeatedly touches both edges,
    # no directional trend, wide band, liquid.
    cycle = [100, 102, 104, 106, 108, 110, 108, 106, 104, 102]
    df = _df(cycle * 6)  # 60 bars
    r = screen_symbol(df, ScreenConfig())
    assert r.passed, r.reasons
    assert r.adx is not None and r.adx < 20
    assert r.touches_support >= 2 and r.touches_resistance >= 2
    # suggested levels satisfy the template invariant stop < entry < exit
    assert r.stop < r.entry < r.exit
    assert r.reward_risk is not None and r.reward_risk > 0


def test_trending_symbol_fails_on_adx():
    df = _df([100 + i for i in range(60)])  # steady uptrend
    r = screen_symbol(df, ScreenConfig())
    assert not r.passed
    assert any("trending" in reason for reason in r.reasons)


def test_thin_liquidity_fails():
    cycle = [100, 102, 104, 106, 108, 110, 108, 106, 104, 102]
    df = _df(cycle * 6, vol=100.0)  # ~$10k ADV → far below the $20M floor
    r = screen_symbol(df, ScreenConfig())
    assert not r.passed
    assert any("thin" in reason for reason in r.reasons)


def test_insufficient_history_fails():
    r = screen_symbol(_df([100, 101, 102, 101, 100]), ScreenConfig())
    assert not r.passed
    assert any("insufficient history" in reason for reason in r.reasons)


def test_narrow_band_fails():
    # tight oscillation ~1% wide → below the 4% tradeable-width floor
    cycle = [100.0, 100.3, 100.6, 100.9, 100.6, 100.3]
    df = _df(cycle * 12)  # 72 bars
    r = screen_symbol(df, ScreenConfig())
    assert not r.passed
    assert any("narrow" in reason for reason in r.reasons)
