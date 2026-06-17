# Momentum-crash study — findings & pre-live risk verdict (R3)

The reviewer's pre-live risk evidence package for the 12-month momentum book. Data
table: `research/momentum_crash_study.md` (script: `scripts/momentum_crash_study.py`),
full sample 2016–2026, top-200 liquid, survivorship-free.

## What the downside looks like

- **Deepest drawdowns are market crashes, amplified.** Worst 4: COVID −33%
  (2020-02→03, recovered 134d), 2025 spring −32% (152d), the **2021–22 bear −27%
  over 597 days underwater**, 2018-Q4 −24% (171d). The book has no defensive
  property — it falls with (and slightly more than) the market.
- **High market beta.** Monthly-return correlation **SPY 0.77, QQQ 0.79**,
  equal-weight universe 0.82. This is a return engine, not a diversifier; sizing it
  in a portfolio must assume it is long-the-market-plus.
- **The slow grind is the real hazard.** The −27% 2021–22 episode took **~20
  months** to recover. A live trader's pain is less the −33% fast COVID dip (back
  in 4 months) than a multi-quarter bleed — the scenario most likely to trigger
  capitulation or a daily-loss halt.
- **Worst rolling losses:** 1-month −12.8%, 3-month −17.0%, 6-month −18.0%.
- **Crashes are tech-concentrated.** At the deepest troughs the book was
  **24–56% Technology** (56% at the 2025-11 trough). Momentum piles into the
  leading sector, so the book is *most* concentrated exactly when that sector
  rolls over — concentration and drawdown coincide.

## Mitigations (what to turn on before live)

| Lever | Evidence | Verdict |
|---|---|---|
| **Vol-targeting** (`use_vol_scaling`, 0.15) | maxDD **−33%→−18.6%** at flat Sharpe (1.30→1.28) | **Enable** — the single biggest survivability win (`momentum_overlays_findings.md`) |
| **Sector caps** (`max_sector_pct`, exists) | troughs hit 38–56% tech | **Enable** (e.g. 25–30%) — directly addresses the concentration-at-crash risk |
| **Regime filter** (SPY > 200DMA, on) | drawdowns track market crashes | already on — keep |
| **Continuous breaker monitor** (P10 §6) | catches overnight drawdown deepening | already wired — keep |
| Drawdown overlay | weaker than vol-target, reactive | leave off live (harness only) |

## Pre-live verdict

The 12-month momentum book is a **validated but high-beta, tech-concentrated**
strategy whose worst historical outcome is a ~−33% drawdown (un-mitigated) and a
~20-month underwater grind. It is **not ready for live as-is on default settings**,
but the mitigations exist and are evidence-backed:

1. **Enable vol-targeting** (halves the drawdown) and **sector caps** (breaks the
   tech concentration) on the deployed book — both already implemented, default
   off; flip with this evidence, as R1 was flipped.
2. Keep the regime filter + breaker monitor on.
3. Size for **beta ≈ 0.8 to the market** and a plausible **−20% drawdown even
   mitigated** — set `max_daily_loss` / position sizing accordingly.

With (1)–(3) in place, paper-trade through at least one drawdown before any live
capital. Absent the mitigations, the book's downside is too sharp and too
concentrated for a live account.

## Caveats

Winner-biased top-200 liquid universe + a single momentum-friendly sample —
absolute depths/recovery are indicative, not guarantees (a worse regime can
produce a deeper, longer crash than anything in-sample). SPY/QQQ/sector data pulled
from FMP (the SEP store has neither). Beta and concentration are the robust,
regime-independent takeaways.
