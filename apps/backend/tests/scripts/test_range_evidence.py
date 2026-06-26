"""Range Trader rejection evidence — pure helpers (offline, no network/backtest)."""

from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "range_evidence.py"
_spec = importlib.util.spec_from_file_location("range_evidence", _SCRIPT)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)
edge = _mod._edge
bootstrap = _mod._bootstrap_mean_ci
split = _mod._split


def test_edge_metrics():
    e = edge([100.0, -50.0, 100.0, -50.0])  # PF = 200/100 = 2.0, mean 25, win 50%
    assert e["trades"] == 4
    assert e["profit_factor"] == 2.0
    assert e["mean_pnl"] == 25.0
    assert e["win_rate"] == 0.5
    assert e["total_pnl"] == 100.0


def test_edge_no_losses_is_infinite_pf_none():
    e = edge([10.0, 20.0])
    assert e["profit_factor"] is None  # inf -> None (no losses)


def test_bootstrap_all_positive_excludes_zero():
    ci = bootstrap([50.0] * 40, n_resamples=300, seed=17)
    assert ci["excludes_zero"] is True
    assert ci["ci_low"] == ci["ci_high"] == 50.0  # constant -> degenerate CI


def test_bootstrap_mixed_spans_zero_and_is_deterministic():
    pnls = [100.0, -90.0, 80.0, -85.0, 50.0, -45.0] * 8  # ~breakeven, high variance
    a = bootstrap(pnls, n_resamples=500, seed=17)
    b = bootstrap(pnls, n_resamples=500, seed=17)
    assert a == b  # seeded -> reproducible
    assert a["ci_low"] <= a["mean"] <= a["ci_high"]


def test_bootstrap_too_few_trades_returns_none_ci():
    ci = bootstrap([1.0, -1.0, 2.0], n_resamples=100, seed=1)
    assert ci["ci_low"] is None and ci["excludes_zero"] is False


def test_split_contiguous_windows():
    ws = split(date(2026, 1, 2), date(2026, 6, 12), 4)
    assert len(ws) == 4
    assert ws[0][0] == date(2026, 1, 2) and ws[-1][1] == date(2026, 6, 12)
    for a, b in zip(ws, ws[1:], strict=False):
        assert a[1] == b[0]
