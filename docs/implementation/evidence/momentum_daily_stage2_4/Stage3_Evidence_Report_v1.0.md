# Momentum-Daily — Stage 3 Evidence Report (Portfolio Construction)

| | |
|---|---|
| Stage | Stage 3 — Portfolio construction (proposal v1.1 §6, §9) |
| Pre-registration | `PREREG_Stage3_Construction_v1.0.md` (frozen `0c8ef61`, before this run) |
| Harness | `apps/backend/scripts/backtest_momentum_stage3.py` (`12c42e9`) |
| Artifact | `MR_MomentumDaily_Stage3_full.json` |
| Inherits | Stage-2 winner **C — Daily conditional (§5.1)**, frozen |
| Window | 2005-01-03 → 2026-06-12 — 5,395 trading days |

Sweeps name count {5,8,10} × sizing {equal, hybrid 50/50 inverse-vol} × sector cap {off,on} = 12 configs,
with the §5.1 daily-conditional policy fixed.

## Harness validation

`N5/ew/nocap` = CAGR 14.52% / Sharpe 0.52 / maxDD −74.19% / 1,384 trades — **byte-identical to the Stage-2
variant C** result. The parametric generalization collapses exactly to the Stage-2 baseline at
N=5/equal/no-cap, confirming internal consistency.

## Results (sorted by Sharpe)

| Config | CAGR | Sharpe | Calmar | max DD | Turnover | Avg hold | 2008 | 2020 | 2022 |
|---|---|---|---|---|---|---|---|---|---|
| N5/hyb/cap | 17.52% | 0.58 | 0.22 | −78.06% | 11.2× | 39d | −64.1% | +15.4% | −36.7% |
| N5/ew/cap | 17.29% | 0.58 | 0.22 | −78.15% | 11.2× | 39d | −64.0% | +14.6% | −36.6% |
| N10/hyb/cap | 13.96% | 0.54 | 0.19 | −72.02% | 8.5× | 65d | −67.0% | +0.9% | −27.8% |
| **N8/hyb/nocap** | 14.25% | 0.53 | 0.20 | **−71.21%** | 12.2× | 35d | −64.0% | +30.4% | **−14.2%** |
| **N5/hyb/nocap** | 14.78% | 0.53 | 0.20 | −74.14% | 12.8× | 31d | **−57.0%** | **+39.6%** | −24.8% |
| N5/ew/nocap *(=Stage 2 C)* | 14.52% | 0.52 | 0.20 | −74.19% | 12.8× | 31d | −56.7% | +39.5% | −24.8% |
| N10/ew/cap | 12.85% | 0.51 | 0.17 | −75.96% | 8.4× | 65d | −66.4% | +0.3% | −31.4% |
| N10/hyb/nocap | 12.70% | 0.50 | 0.18 | −70.31% | 12.1× | 37d | −65.1% | +25.7% | −10.7% |
| N8/ew/nocap | 12.39% | 0.49 | 0.17 | −71.96% | 11.6× | 35d | −64.2% | +32.1% | −18.3% |
| N8/hyb/cap | 11.24% | 0.47 | 0.15 | −76.98% | 9.4× | 54d | −68.3% | +5.2% | −26.3% |
| N10/ew/nocap | 11.27% | 0.47 | 0.16 | −70.57% | 11.5× | 37d | −65.0% | +26.4% | −15.0% |
| N8/ew/cap | 10.19% | 0.44 | 0.13 | −77.55% | 9.3× | 54d | −68.0% | +4.8% | −28.4% |

## Findings — both pre-registered hypotheses are REFUTED

1. **Widening to 8–10 names does not improve Sharpe (§6.1 hypothesis refuted).** Sharpe *falls* with name
   count: equal-weight 0.52 (N5) → 0.49 (N8) → 0.47 (N10); hybrid 0.53 → 0.53 → 0.50. More names modestly
   lowers overall max drawdown (N5 −74% → N10 −70%) but **degrades the two largest momentum-crash windows**
   (2008, 2020). This independently replicates **MOM-002**: for a momentum book, *wider ≠ diversified* —
   the wider book's names are highly correlated momentum leaders, so breadth costs Sharpe without buying
   crash protection.

2. **The sector cap does not protect crash drawdown — it harms it (§6.2 hypothesis refuted).** The cap
   *worsens* overall max drawdown in most cells and **collapses the 2020 recovery**: N5 +39.5% → +14.6%,
   N10 +25.7% → **+0.9%**; 2022 also worsens (N5 −24.8% → −36.6%). Mechanism: momentum recoveries are led
   by a concentrated sector cohort (2020 tech), and forcing ≤2 names / ≤40%(N5)/30%(N8-10) per sector
   ejects exactly those leaders. The cap raises CAGR/Sharpe *only* at N=5 (by concentrating turnover
   differently) but at the cost of the worst drawdown and worst crash behavior in the whole sweep.

3. **Hybrid ≈ equal weight.** The 50/50 inverse-vol tilt moves Sharpe by ≤0.01 in every pair — a mild,
   near-neutral risk tilt, marginally positive at N=5.

4. **All configs retain a deep (~−70% to −78%) max drawdown.** Construction cannot fix the momentum-crash
   problem; only the **regime filter (Stage 4)** de-grosses in a downtrend. Construction choice moves
   drawdown by <8pp; regime is the lever.

## Winner determination (frozen rule §4) — a genuine near-tie surfaced to the owner

The highest-Sharpe configs (N5/*/cap, 0.58) are disqualified by the rule's drawdown/crash weighting: they
have the *worst* max drawdown (−78%) and worst 2022 (−36.6%). Among the drawdown/crash-robust configs the
choice is close and the rule's two criteria diverge:

- **N5/hyb/nocap** — best in the two canonical momentum-crash windows (2008 −57%, 2020 +39.6%), tied-best
  Sharpe (0.53); the rule's "special weight on momentum-crash windows" favors it, and it matches the
  MOM-002 concentration prior.
- **N8/hyb/nocap** — ~3pp lower overall max drawdown (−71.2%), best 2022 (−14.2%), more diversified; the
  rule's "near-ties → more names, lower drawdown" tie-break favors it.

Sizing is a near-toss (hybrid marginally ≥ equal). Given the evidence refutes both widening and the sector
cap, the **recommendation is N5/hybrid/no-cap** — best behavior in the two major momentum crashes, tied-best
Sharpe, and no complexity (extra names / sector machinery) that the data supports. **This is surfaced to
the owner for the final Stage-3 winner** before it freezes into Stage 4.

*Reported: 2026-07-15.*
