"""Intraday oscillation screener — pure-function tests (offline, synthetic).

Loaded via importlib (scripts/ isn't a package). No network needed.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "screen_intraday_oscillation.py"
_spec = importlib.util.spec_from_file_location("screen_intraday_oscillation", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)
oscillation_metrics = _mod.oscillation_metrics
OscConfig = _mod.OscConfig

_BARS_PER_SESSION = 78
_RNG = np.random.default_rng(7)


def _make(prices_per_session: list[list[float]], vol: float = 1_000_000.0) -> pd.DataFrame:
    """Build a 5-min RTH bar frame from per-session close paths (ET 09:30→)."""
    rows = []
    day0 = pd.Timestamp("2026-01-05 14:30:00", tz="UTC")  # 09:30 ET Monday
    for d, closes in enumerate(prices_per_session):
        base = day0 + pd.Timedelta(days=d)
        for i, c in enumerate(closes):
            t = base + pd.Timedelta(minutes=5 * i)
            rows.append({"t": t, "o": c, "h": c + 0.05, "l": c - 0.05, "c": c, "v": vol})
    return pd.DataFrame(rows)


def _oscillating_session(level: float = 100.0, phi: float = 0.93, sigma: float = 0.15,
                         n: int = _BARS_PER_SESSION):
    # OU / AR(1) mean reversion: dev_t = phi·dev_{t-1} + noise → crosses VWAP
    # often, negative bar-to-bar return autocorr, half-life = ln0.5/ln(phi)·5min
    # = ~48m for phi=0.93. (A *smooth* sine would be positively autocorrelated.)
    dev = 0.0
    out = []
    for _ in range(n):
        dev = phi * dev + _RNG.normal(0.0, sigma)
        out.append(level + dev)
    return out


def _trending_session(start: float = 100.0, step: float = 0.05, n: int = _BARS_PER_SESSION):
    return [start + step * i for i in range(n)]


def test_oscillatory_symbol_passes():
    bars = _make([_oscillating_session() for _ in range(15)])
    m = oscillation_metrics(bars, OscConfig())
    assert m.passed, m.reasons
    assert m.vwap_crossings_per_day >= 6
    assert m.ret_autocorr_lag1 < 0.05  # not momentum (half-life is the MR signal)
    assert 30 <= m.half_life_minutes <= 120


def test_trending_symbol_fails():
    bars = _make([_trending_session() for _ in range(15)])
    m = oscillation_metrics(bars, OscConfig())
    assert not m.passed
    # a steady trend has few VWAP crossings and is not mean-reverting
    assert any("crossings" in r or "half-life" in r or "autocorr" in r for r in m.reasons)


def test_thin_liquidity_fails():
    bars = _make([_oscillating_session() for _ in range(15)], vol=10.0)  # ~tiny $ADV
    m = oscillation_metrics(bars, OscConfig())
    assert not m.passed
    assert any("thin" in r for r in m.reasons)


def test_too_few_sessions_fails():
    bars = _make([_oscillating_session() for _ in range(3)])
    m = oscillation_metrics(bars, OscConfig())
    assert not m.passed
    assert any("sessions" in r for r in m.reasons)


def test_empty_bars_no_crash():
    m = oscillation_metrics(pd.DataFrame(columns=["t", "o", "h", "l", "c", "v"]), OscConfig())
    assert not m.passed
