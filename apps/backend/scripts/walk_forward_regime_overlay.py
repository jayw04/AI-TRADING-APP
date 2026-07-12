"""LOCAL-ONLY analysis (ADR-0022 section 7 promotion backtest): rolling walk-forward of
the P10 section-5 REGIME overlay (breadth + VIX percentile) layered on top of the
section-1 vol-target overlay, across distinct market regimes. Answers: does folding
breadth/VIX into the gross target improve drawdown/Sharpe *beyond* vol-targeting alone?

Faithful to the live overlay: effective gross = vol_target_gross * regime_factor, where
regime_factor = min(breadth_ramp, vix_ramp) (worst signal governs; only scales down; a
None signal contributes nothing). Reuses the SHIPPED logic - regime.market_breadth /
regime.vix_percentile and the overlay ramp helpers/thresholds.

No look-ahead: breadth is computed at each weekly rebalance (slow, 200d-MA based) and
forward-filled; VIX percentile is recomputed DAILY as-of the PRIOR trading day's close
(the fast signal - this is the daily-VIX refinement of the first weekly-VIX pass). ^VIX
depth is ~5y (FMP), so windows before ~2022 are breadth-only (vix_percentile -> None).

    PYTHONPATH=apps/backend apps/backend/.venv/Scripts/python.exe \
      apps/backend/scripts/walk_forward_regime_overlay.py
"""
from __future__ import annotations

from datetime import date, datetime, time

from app.factor_data.backtest import run_momentum_backtest
from app.factor_data.regime import market_breadth, vix_percentile
from app.factor_data.store import FactorDataStore
from app.strategies import metrics
from app.strategies.overlay import (
    _BREADTH_FLOOR,
    _BREADTH_FULL,
    _VIX_CALM_PCT,
    _VIX_STRESS_PCT,
    _ramp_down,
    _ramp_up,
)

STORE = r"C:/LLM-RAG-APP/ai-trading-app/apps/backend/data/factor_data_full.duckdb"

WINDOWS = [
    ("GFC + 2009 reversal", date(2007, 7, 1), date(2010, 6, 30)),
    ("2010-2013 (2011 shock)", date(2010, 7, 1), date(2013, 6, 30)),
    ("2013-2016 (incl 2015)", date(2013, 7, 1), date(2016, 6, 30)),
    ("2019-2022 (COVID)", date(2019, 7, 1), date(2022, 6, 30)),
    ("2022-2026 (rate + AI; +VIX)", date(2022, 7, 1), date(2026, 6, 12)),
]

VOL_TARGET = 0.15
SPAN = 20
N = 80
TOPQ = 0.20
INIT = 100_000.0


def _breadth_ramp_by_rebalance(store: FactorDataStore, rebalances: list[date]) -> dict[date, float]:
    """Breadth ramp factor (slow signal) at each weekly rebalance, PIT as-of that date."""
    out: dict[date, float] = {}
    for rb in rebalances:
        b = market_breadth(store, rb, n=N)
        out[rb] = _ramp_up(b, _BREADTH_FLOOR, _BREADTH_FULL) if b is not None else 1.0
    return out


def _apply_regime(store, curve, rebalances, breadth_ramp):
    """Scale a daily (date, equity) curve's returns by regime_factor = min(breadth,
    vix), where breadth is the most recent rebalance's ramp (ffill) and VIX is
    recomputed DAILY as-of the PRIOR trading day's close (no look-ahead)."""
    if not curve:
        return [], False
    reb = sorted(rebalances)
    out, eq, prev_eq, prev_date, vix_seen = [], INIT, INIT, None, False
    for d, e in curve:
        ret = (e / prev_eq - 1.0) if prev_eq > 0 else 0.0
        prev_eq = e
        brf = 1.0
        for r in reb:
            if r < d:
                brf = breadth_ramp.get(r, 1.0)
            else:
                break
        vrf = 1.0
        if prev_date is not None:
            vp = vix_percentile(store, prev_date)  # daily, as-of the prior close
            if vp is not None:
                vrf = _ramp_down(vp, _VIX_CALM_PCT, _VIX_STRESS_PCT)
                vix_seen = True
        eq *= 1.0 + min(brf, vrf) * ret
        out.append((d, eq))
        prev_date = d
    return out, vix_seen


def _summary(curve):
    if not curve:
        return None
    dt = [(datetime.combine(d, time()), e) for d, e in curve]
    return (curve[-1][1] / INIT - 1.0, metrics.sharpe_ratio(dt), metrics.max_drawdown(dt))


def main() -> int:
    s = FactorDataStore(db_path=STORE, read_only=True)
    try:
        hdr = (f"{'window':30s} {'reb':>4s} | {'vol ret':>8s} {'vol Sh':>6s} {'vol DD':>7s} | "
               f"{'+reg ret':>8s} {'+rg Sh':>6s} {'+rg DD':>7s} | {'dDD':>6s} {'vix':>4s}")
        print("DAILY-VIX refinement (breadth weekly, VIX percentile daily)")
        print(hdr)
        print("-" * len(hdr))
        for label, start, end in WINDOWS:
            r = run_momentum_backtest(
                s, start, end, n=N, top_quantile=TOPQ,
                vol_target_annual=VOL_TARGET, vol_ewma_span=SPAN,
            )
            if r.vol_scaled_metrics is None or not r.vol_scaled_curve:
                print(f"{label:30s} {len(r.rebalances):>4d} | (no curve)")
                continue
            breadth_ramp = _breadth_ramp_by_rebalance(s, r.rebalances)
            reg_curve, vix_seen = _apply_regime(s, r.vol_scaled_curve, r.rebalances, breadth_ramp)
            v, rg = r.vol_scaled_metrics, _summary(reg_curve)
            ddelta = rg[2] - v.max_drawdown  # + = DD improved (less negative)
            print(
                f"{label:30s} {len(r.rebalances):>4d} | "
                f"{v.total_return:>+7.1%} {v.sharpe:>6.2f} {v.max_drawdown:>7.1%} | "
                f"{rg[0]:>+7.1%} {rg[1]:>6.2f} {rg[2]:>7.1%} | "
                f"{ddelta:>+5.1%} {'yes' if vix_seen else 'no':>4s}"
            )
        print("\nReading: 'vol' = section-1 vol-target overlay (baseline section-5 must "
              "beat); '+reg' = vol x section-5 regime factor. dDD>0 = regime improved "
              "drawdown. vix=no -> breadth-only window (^VIX depth ~5y).")
    finally:
        s.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
