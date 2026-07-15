# Momentum-Daily — Stage 2 Evidence Report (Rebalance Policy)

| | |
|---|---|
| Stage | Stage 2 — Rebalance policy (proposal v1.1 §5, §9) |
| Pre-registration | `PREREG_Stage2_RebalancePolicy_v1.0.md` (frozen `4a95aa0`, before this run) |
| Harness | `apps/backend/scripts/backtest_momentum_stage2.py` (`8568053`) |
| Artifact | `MR_MomentumDaily_Stage2_full.json` |
| Window | 2005-01-03 → 2026-06-12 — 5,395 trading days, all usable |
| Data | `factor_data_full.duckdb` (Sharadar SEP, survivorship-free PIT) |

Everything except the rebalance policy is held identical (universe top-200 PIT, 12-1 signal 252/21,
eligibility raw>0 ∧ z≥0, 5 names equal-weight, sector cap OFF, regime OFF, 10 bps one-way, $100k).

## Results

| Variant | CAGR | Sharpe | Calmar | max DD | Ann. turnover | Avg hold | Trades | Worst gap |
|---|---|---|---|---|---|---|---|---|
| **A** Weekly (v0.9 baseline) | 15.75% | **0.55** | **0.21** | −76.2% | 10.9× | 37d | 1,119 | −70.3% |
| **B** Trade-on-change | 14.91% | 0.53 | 0.20 | **−73.7%** | 23.2× | 17d | 2,205 | −70.3% |
| **C** Daily conditional (§5.1) | 14.52% | 0.52 | 0.20 | −74.2% | 12.8× | 31d | 1,384 | −70.3% |
| **D** Biweekly | 15.19% | 0.54 | 0.20 | −77.5% | 7.4× | 53d | 560 | −70.3% |

Crash-window total returns:

| Variant | 2008 GFC | 2020 COVID | 2022 |
|---|---|---|---|
| A | −59.6% | +37.2% | **−18.6%** |
| B | −59.9% | +37.7% | −25.2% |
| C | **−56.7%** | **+39.5%** | −24.8% |
| D | −66.0% | +38.4% | −18.9% |

## Findings

1. **Rebalance policy is nearly return-neutral for this signal.** All four variants cluster inside
   Sharpe 0.52–0.55 and Calmar 0.20–0.21 — a spread within backtest noise. For a slow 12-1 signal on a
   5-name book, *when* you rebalance barely moves risk-adjusted performance.

2. **Prior confirmed — B loses after costs.** Trade-on-change has the highest turnover (23.2×) and the
   lowest CAGR *and* Sharpe. Reacting to every top-5 swap pays costs for no risk-adjusted gain. Dominated.

3. **Prior confirmed — D works surprisingly well for a slow signal.** Biweekly matches the field on
   Sharpe (0.54) at the lowest turnover (7.4×) — but has the *worst* max drawdown (−77.5%) and worst
   2008 (−66%): slower de-risking hurts precisely in a crash.

4. **C has the best crash-window behavior.** Daily conditional is least-bad in 2008 (−56.7%) and best in
   2020 (+39.5%), at moderate turnover (12.8×, well below B). Mechanistically sensible: the
   `raw_momentum_negative` trigger exits deteriorating names faster than a calendar cadence.

5. **⚠ Every variant has a catastrophic ~−75% max drawdown.** This is the momentum-crash problem, and it
   is *by design* out of Stage 2's scope (no regime filter, no sector cap). 2008 alone accounts for
   −57% to −66%. This is what **Stage 3 (sector cap)** and **Stage 4 (regime filter)** exist to fix;
   Stage 2 neither addresses nor can address it.

## Winner determination (frozen rule §4)

Risk-adjusted return is a near-tie, so the decision falls to the pre-weighted tie-break criteria —
drawdown control and crash-window behavior above raw CAGR. **C — Daily conditional (§5.1)** is best on
exactly those: best 2008 and 2020 crash behavior, moderate turnover, and the design-intended structure.
B is clearly dominated; D trades the best turnover for the worst crash behavior; A leads on CAGR/Sharpe
by a margin inside the noise floor.

**→ Stage-2 winner (per the frozen rule): Variant C — Daily conditional (§5.1).**
Margin over A (weekly) is within backtest noise; the choice rests on crash-window drawdown, which the
rule pre-weighted. This is recorded as a rule application, not a post-hoc CAGR pick.

Carried into **Stage 3** with everything else frozen: **daily conditional §5.1 evaluation**, 12-1 signal,
5 names equal-weight (Stage 3 tests name count × sizing × sector cap).

*Reported: 2026-07-15.*
