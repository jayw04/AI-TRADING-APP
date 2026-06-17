# Risk overlays on the 12m momentum book — findings (R3)

**Question:** the 12-month momentum book is the validated strategy (R1); the next
risk is *survivability*, not signal. Do the gross-exposure overlays cut the scary
drawdowns without giving back the edge?

**Method:** the production 12m book (`run_momentum_backtest`, lookback 252/skip 0),
top-200 liquid, IS 2016–22 / OOS 2023–26, with each overlay applied at the
portfolio-return level (no leverage, exposure capped at 1.0). Driver:
`scripts/backtest_momentum_overlays.py`. Data table: `momentum_overlays_backtest.md`.

| span | overlay | CAGR | Sharpe | maxDD |
|---|---|---|---|---|
| OOS | none | 76.1% | 1.85 | **−32.1%** |
| OOS | **vol-target** | 30.5% | 1.78 | **−13.6%** |
| OOS | drawdown | 59.1% | 1.73 | −23.7% |
| OOS | both | 29.3% | 1.74 | −13.3% |
| IS | none | 22.1% | 0.92 | −33.0% |
| IS | **vol-target** | 15.0% | 0.98 | −18.6% |
| IS | drawdown | 14.9% | 0.82 | −24.2% |
| IS | both | 13.7% | 0.96 | −16.4% |

## Findings

1. **Vol-targeting is the high-value overlay.** It roughly **halves max drawdown**
   (OOS −32%→−13.6%, IS −33%→−18.6%) while keeping **Sharpe flat** (OOS 1.85→1.78,
   IS 0.92→**0.98**, a slight *improvement*). That is the textbook survivability
   trade: much shallower drawdowns at ~no risk-adjusted cost. The headline CAGR
   falls (76%→31% OOS), but the raw CAGR was regime-inflated full-exposure return;
   on a risk-adjusted basis it is preserved, and the drawdown cut is the point.
2. **The drawdown overlay alone is weaker.** Reactive band-based de-risking trims
   maxDD only to ~−24% and slightly *hurts* Sharpe (it cuts exposure after the
   drawdown is underway — selling into the bottom). Proactive vol-targeting, which
   de-risks as volatility rises (typically *before* the worst of a drawdown),
   dominates it here.
3. **"Both" ≈ vol-target alone.** Stacking the drawdown overlay on vol-targeting
   adds essentially nothing (vol-targeting has already de-risked by the time the
   drawdown bands trigger). So the drawdown overlay is not worth enabling on top of
   vol-targeting; keep it as backtest infrastructure / a standalone option.

## Recommendation

- **Enable vol-targeting on the deployed momentum book.** It already exists in
  `momentum_portfolio.py` (`use_vol_scaling`, currently default-off) — this is the
  one overlay the evidence clearly supports turning on. Flip it the same way R1 was
  flipped: a small config change, this backtest as the evidence. (Suggest the
  default `vol_target_annual=0.15` used here; it halved drawdown at flat Sharpe.)
- **Leave the drawdown overlay off** on the live book — it underperforms
  vol-targeting and adds nothing stacked on it. It stays available in the backtest
  harness for the crash study and future regimes.
- The regime filter (SPY > 200DMA), sector caps, and position caps already exist;
  the **continuous breaker monitor** (P10 §6 `evaluate()`) is wired. So after
  flipping vol-targeting on, the overlay suite the reviewer listed is in place.

## Caveats

Same as the other studies: winner-biased top-200 liquid universe + a single
momentum-friendly OOS regime inflate absolute CAGRs — read the **relative** effect
(drawdown roughly halved at flat Sharpe), not the levels. The overlay is applied at
the portfolio-return level here; the live strategy applies the equivalent scale via
`_gross_scale`, so deployed behavior should track this closely but not identically
(execution, sizing granularity).

## Next

This is also the first input to the **momentum-crash study** (worst-20 drawdowns,
rolling 1/3/6-month, recovery time, SPY/QQQ correlation, sector concentration in
crashes, and the overlay effect quantified above) — the pre-live risk evidence
package.
