"""Cross-asset TSMOM sleeve (PORT-001 Sleeve B, §1) — trend / risk-parity / vol-target."""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.research.factor_lab.cross_asset import cross_asset_tsmom


def _series(n: int, drift: float, vol: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    rets = drift + vol * rng.standard_normal(n)
    return 100.0 * np.cumprod(1.0 + rets)


def _panel(specs: dict[str, tuple[float, float, int]], n: int = 320) -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=n, freq="B")
    return pd.DataFrame({k: _series(n, d, v, s) for k, (d, v, s) in specs.items()}, index=idx)


def test_insufficient_data():
    out = cross_asset_tsmom(_panel({"SPY": (0.0008, 0.004, 1)}, n=50))
    assert out.status == "insufficient_data" and out.gross == 0.0


def test_only_uptrend_assets_selected_and_risk_parity_weighted():
    # UP_LOW + UP_HIGH trend up (positive 12-1); DOWN trends down → flat.
    panel = _panel({
        "UP_LOW": (0.0015, 0.004, 1),   # strong drift, LOW vol
        "UP_HIGH": (0.0050, 0.020, 2),  # strong drift (must clear vol·√252), HIGH vol
        "DOWN": (-0.0020, 0.010, 3),    # negative drift → out of trend
    })
    out = cross_asset_tsmom(panel)
    assert out.status == "ok"
    assert set(out.in_trend) == {"UP_LOW", "UP_HIGH"}     # DOWN excluded
    assert out.weights["DOWN"] == 0.0
    # Risk-parity: the lower-vol asset gets the larger weight.
    assert out.weights["UP_LOW"] > out.weights["UP_HIGH"] > 0.0
    assert out.gross <= 1.0 + 1e-9                        # de-risk only, never levers up


def test_all_cash_when_nothing_trends():
    panel = _panel({
        "A": (-0.0010, 0.010, 1),
        "B": (-0.0012, 0.012, 2),
    })
    out = cross_asset_tsmom(panel)
    assert out.in_trend == [] and out.gross == 0.0 and out.cash == 1.0


def test_vol_target_derisks_high_vol_book():
    # Both assets trend up but are very volatile → annualized vol > 10% → scaled down.
    # Drift must clear vol·√252 so the 12-1 momentum stays positive at high vol.
    panel = _panel({
        "A": (0.0070, 0.030, 1),
        "B": (0.0070, 0.032, 2),
    })
    out = cross_asset_tsmom(panel, vol_target=0.10)
    assert out.port_vol_annual is not None and out.port_vol_annual > 0.10
    assert out.vol_scale < 1.0 and out.gross < 1.0       # vol-target bit


def test_vol_target_no_leverage_on_calm_book():
    # Calm uptrend → annualized vol < 10% → vol_scale capped at 1.0 (no lever-up).
    panel = _panel({
        "A": (0.0008, 0.0020, 1),
        "B": (0.0008, 0.0022, 2),
    })
    out = cross_asset_tsmom(panel, vol_target=0.10)
    assert out.port_vol_annual is not None and out.port_vol_annual < 0.10
    assert out.vol_scale == 1.0 and abs(out.gross - 1.0) < 1e-9


def test_deterministic():
    panel = _panel({"UP_LOW": (0.0015, 0.004, 1), "UP_HIGH": (0.0050, 0.020, 2)})
    a = cross_asset_tsmom(panel)
    b = cross_asset_tsmom(panel)
    assert a.weights == b.weights and a.gross == b.gross
