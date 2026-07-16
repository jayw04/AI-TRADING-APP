# Momentum-Daily — Stage 2-4 Validation Synthesis & Promotion Candidate

| | |
|---|---|
| Program | Momentum Portfolio v1.1 — Workstream B (`momentum-daily`, id=11, user 4) |
| Stages | 1 (Workstream A, prior) · 2 rebalance policy · 3 construction · 4 regime — **all complete** |
| Window | 2005-01-03 → 2026-06-12 (5,395 trading days), survivorship-free PIT SEP |
| Branch | `research/momentum-stage2-4` |
| Status | **Validation complete. NOT promoted — gated (see §5).** |

The four stages were run sequentially, each **pre-registered before it ran** and each freezing the prior
stage's winner. Owner confirmed the Stage-2 and Stage-3 winners at their decision points.

## 1. The validated configuration chain

| Stage | Decision | Winner | Basis |
|---|---|---|---|
| 2 — Rebalance policy | 4 variants | **C — Daily conditional (§5.1)** | Policy near return-neutral; C best crash behavior (near-tie, owner-confirmed) |
| 3 — Construction | 12 configs | **N5 / hybrid 50-50 inverse-vol / no sector cap** | Widening & sector cap both **refuted**; N5 best in major crashes (near-tie, owner-confirmed) |
| 4 — Regime filter | 4 variants | **C — Graduated (0.98/0.60/0.15 vs 200d MA)** | **Decisive** — best Sharpe/Calmar/maxDD/CAGR; binary *harms* |

## 2. Promotion-candidate configuration

```
Signal        12-1 momentum (lookback 252d, skip 21d); winsorized cross-sectional z-score
Eligibility   raw_momentum > 0 AND zscore >= 0
Universe      top-200 PIT-liquid US names, monthly refresh (§8)
Rebalance     daily conditional §5.1 — the six triggers; hold-band entry<=5/hold<=10,
              2-close exit confirmation, 0.30-z displacement, 4pp drift, 10d backstop
Construction  5 names, hybrid 50/50 equal+inverse-vol sizing (per-name <= 20%), NO sector cap
Regime        GRADUATED on SPY 200d MA: gross 0.98 above / 0.60 within +/-2% / 0.15 below
```

Full-window backtest of this config (Stage-4 variant C): **CAGR 16.9% · Sharpe 0.60 · Calmar 0.26 ·
max drawdown −64.6%**; 2008 −7.5%, 2020 +19.8%, 2022 −8.8%.

## 3. What the validation established (and refuted)

- **Rebalance cadence barely matters** for a slow 12-1 signal (Stage 2: Sharpe 0.52-0.55 across all four).
- **Wider ≠ diversified** (Stage 3): 8-10 names do *not* beat 5 on Sharpe; independently replicates MOM-002.
- **Sector cap harms, not helps** (Stage 3): it collapses momentum recoveries (2020 +39.5% → +14.6%).
- **The graduated regime filter is the single biggest lever** (Stage 4): −74% → −64.6% max drawdown,
  2008 −57% → −7.5%, while *raising* Sharpe and CAGR. **A binary on/off filter is worse than no filter**
  (whipsaw) — the intuitive choice is the wrong one.

## 4. ⚠ Honest caveats — required inputs to the promotion decision

1. **The winning regime variant is NOT in the deployed template.** `momentum_daily.py::_regime` currently
   implements the **binary** filter (100% above MA / cash below) — i.e. Stage-4 variant **A, the worst
   performer**. Promoting the validated winner **requires a code change**: add a graduated distance-based
   gross mode (0.98/0.60/0.15) to the template, plus a confirmation re-run. This is the top follow-up.
2. **Even the best config keeps a −64.6% max drawdown.** momentum-daily is inherently a **high-drawdown,
   concentrated** book — the concentration that drives its Sharpe (Stage 3) also drives its drawdown, and
   the residual after the regime filter is single-name/concentration risk that diversification can't fix
   without costing Sharpe. This is a book for a risk-tolerant sleeve, not a low-drawdown core.
3. **Regime results are on a market proxy, not SPY** (SPY absent from the SEP store; PREREG-4 §2). The
   *variant ranking* (graduated ≫ binary; graduated > none) transfers; absolute levels are proxy-dependent.
   The live strategy applies the graduated rule to the real SPY 200-day MA.
4. **Graduated thresholds were pre-registered midpoints, not tuned.** A sensitivity sweep (band ±1-3%,
   gross triples) is a recommended follow-up — reported, not adopted (§9). The frozen result stands.

## 5. Remaining gates before live activation (unchanged by this validation)

Validation makes momentum-daily *ready to be considered*; it does **not** activate it. Still required:
- **ADR-0042 canary GREEN** (staged for 07-16 RTH) — gates all live momentum activation.
- **24-hour activation cooldown** (ADR 0005, deterministic strategy).
- **Promotion gates** — evidence review + paper-trading the winning config against the v0.9 baseline (§9).

## 6. Recommended next steps

1. Implement the **graduated regime mode** in `momentum_daily.py` (params for the 3-level gross + band),
   set the strategy's defaults to the §2 promotion-candidate config, add tests, and run a confirmation
   backtest that reproduces variant C.
2. (Optional) Graduated-threshold sensitivity sweep for robustness (report-only).
3. Open the validation dossier (this synthesis + the four stage reports + PREREGs + artifacts) for the
   promotion evidence review.

*Synthesis: 2026-07-15.*
