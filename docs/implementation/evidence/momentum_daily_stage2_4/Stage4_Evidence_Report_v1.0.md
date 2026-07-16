# Momentum-Daily — Stage 4 Evidence Report (Regime Filter)

| | |
|---|---|
| Stage | Stage 4 — Regime filter (proposal v1.1 §7, §9) |
| Pre-registration | `PREREG_Stage4_Regime_v1.0.md` (frozen `0706103`, before this run) |
| Harness | `apps/backend/scripts/backtest_momentum_stage4.py` (`<this commit>`) |
| Artifact | `MR_MomentumDaily_Stage4_full.json` |
| Inherits | Stage-3 winner **N5 / hybrid / no-cap** on §5.1 daily conditional |
| Window | 2005-01-03 → 2026-06-12 · regime gauge = broad market proxy (SPY substitution, PREREG §2) |

## Harness validation

Variant **D (none-control)** = CAGR 14.78% / Sharpe 0.53 / maxDD −74.14% — **byte-identical to the Stage-3
winner** N5/hyb/nocap. The gross-scaling machinery is a no-op at gross ≡ 1.0, confirming consistency.

## Results

| Variant | CAGR | Sharpe | Calmar | max DD | Turnover | Days <full gross | Trades | 2008 | 2020 | 2022 |
|---|---|---|---|---|---|---|---|---|---|---|
| A Binary | 10.64% | 0.45 | 0.13 | −83.10% | 17.5× | 21% | 2,265 | +11.4% | +10.2% | −28.6% |
| B Buffered (±1%/2d) | 13.93% | 0.52 | 0.18 | −76.71% | 12.3× | 20% | 2,207 | +16.5% | −1.5% | −17.8% |
| **C Graduated (0.98/0.60/0.15)** | **16.91%** | **0.60** | **0.26** | **−64.59%** | 14.9× | 96% | 1,539 | **−7.5%** | +19.8% | **−8.8%** |
| D None (control) | 14.78% | 0.53 | 0.20 | −74.14% | 12.8× | 0% | 1,378 | −57.0% | +39.6% | −24.8% |

(The "days <full gross" column for C is 96% because C's maximum gross is 0.98 — nearly every day is
technically below 1.0. It does **not** mean C is out of the market 96% of the time; C holds ~98% gross in
uptrends, 60% in the buffer zone, 15% in downtrends.)

## Findings

1. **C — Graduated is the decisive winner.** Best Sharpe (0.60), best Calmar (0.26), best max drawdown
   (−64.6%, +10pp vs the no-filter control), *and* best CAGR (16.9%). It improves 2008 from −57% → **−7.5%**
   and 2022 from −25% → −9%. Higher CAGR *and* lower drawdown is not a contradiction: avoiding the −57%
   2008 wipeout preserves capital that compounds.

2. **The raw binary filter (A) is the worst option — worse than no filter.** Max drawdown −83% (vs −74%
   with no filter), lowest Sharpe (0.45), highest turnover (17.5×). Binary on/off **whipsaws**: it
   de-risks at bottoms and misses V-recoveries. Its 2008 (+11%) confirms it *can* dodge a sustained bear,
   but the whipsaw cost elsewhere more than erases that benefit. **The "obvious" regime filter actively
   harms** — a genuine, decision-relevant finding.

3. **Graduation, not just a buffer, is what works.** The buffered binary (B) beats raw binary (A) by
   cutting whipsaw, but does **not** beat the no-filter control on Sharpe (0.52 vs 0.53) and is slightly
   worse on max drawdown. Staying *partially* invested across the trend (graduation) is materially better
   than any hard on/off, buffered or not.

4. **C's one weakness is the 2020 V-recovery** (+19.8% vs the control's +39.6%): it de-grossed into the
   COVID crash and caught less of the sharp rebound. C trades V-recovery upside for sustained-bear
   protection — a net win over the full window (2008 dominates), but a real, disclosed tradeoff.

5. **Even the best config retains a −64.6% max drawdown.** The regime filter cuts the sustained-bear
   drawdown but the residual is driven by **single-name concentration** (worst single-name daily gap
   ≈ −70% → ~−14% book hit; Stage 3 showed adding names to diversify *costs* Sharpe). momentum-daily,
   even fully optimized, is an inherently **high-drawdown, concentrated** book: the concentration that
   drives its Sharpe also drives its drawdown. This is a required input to the promotion decision.

## Winner (frozen rule §5)

**C — Graduated regime filter (gross 0.98 above / 0.60 in ±2% buffer / 0.15 below the 200-day MA).**
Dominant on the pre-weighted criteria (Sharpe, Calmar, max drawdown, sustained-crash windows). Not a
near-tie — C beats every alternative including the no-filter control on almost every metric.

**Transferability:** the ranking (graduated ≫ binary; graduated > none) is the transferable conclusion;
the live strategy applies the graduated variant to the **SPY** 200-day MA (not the research proxy).
A sensitivity check on the graduated thresholds (band ±1–3%, gross triples) is a recommended follow-up —
reported, not adopted (§9); the frozen ±2% / 0.98-0.60-0.15 result stands as the pre-registered outcome.

*Reported: 2026-07-15.*
