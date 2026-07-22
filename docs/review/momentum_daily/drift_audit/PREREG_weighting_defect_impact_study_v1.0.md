# PREREG — momentum-daily Weighting-Defect Impact Study — v1.0

**Date:** 2026-07-22 · **Status:** ⏸ **PROPOSED — NOT RATIFIED, STUDY NOT RUN.**
**Governs:** the focused correction-impact analysis required by `weighting_defect_erratum_v1.0.md` §4.
**Blocker addressed:** `WEIGHTING_VALIDATION_DEFECT_IMPACT_NOT_YET_ADJUDICATED`.

Nothing in this document authorizes activation. The study quantifies the historical effect of removing a
defective sizing residual; the activation decision is separate and remains the owner's.

---

## 0. ⚠ Pre-registration integrity disclosure — READ FIRST

**This is not a blind pre-registration, and it would be dishonest to present it as one.** The full-period
endpoint metrics for both arms already exist in a committed artifact (`MR_MomentumDaily_Stage3_full.json`,
configs `N5/hyb/nocap` and `N5/ew/nocap`) and are quoted in the erratum §1.4. Anyone setting thresholds
here — including the author of this document — already knows that the full-period ΔSharpe is +0.0049 and
ΔCAGR is +26.1 bps.

Accordingly:

- **Pre-specified-but-known (Tier 1):** CAGR, Sharpe, Calmar, maxDD, turnover, trades, crash windows.
  Thresholds below are set with these values already visible. They serve to make the *decision rule*
  explicit and reviewable, **not** to establish blind-test integrity, and must not be described as such
  in any downstream document.
- **Genuinely unobserved (Tier 2):** annualized volatility, worst rolling 1-/3-/12-month return
  differences, the turnover-cost decomposition, and every result from the trade-date-pinned arm (§2.2).
  No equity curves exist for either arm — only endpoint summaries — so all path-dependent statistics are
  unseen. **Thresholds on Tier 2 are pre-registered in the strict sense.**

The honest claim this study can support is: *the endpoint effect was already known and is small; the study
establishes whether the path-dependent and risk-shape effects are likewise immaterial.*

---

## 1. Question

Does replacing the defective truncated-clamp weights with the cap-feasible equal weights change any
conclusion that the Stage-2→4 validation reached?

Explicitly **out of scope**: strategy discovery, parameter retuning, re-selection among Stage-3 arms,
re-running or re-reviewing the §8 census, and any change to `max_position_pct` (fixed at 0.20).

## 2. Design

Both arms use the Stage-4 harness (`backtest_momentum_stage4.py`, variant C — graduated regime, the
governing configuration) at **N=5, no sector cap**, over **2005-01-03 → 2026-06-12** (5,395 sessions),
`INITIAL_EQUITY` 100,000, `TURNOVER_COST_BPS` 10.0, `WEIGHT_DRIFT_PCT` 0.04, `BACKSTOP_DAYS` 10, reading
`factor_data_full.duckdb` **read-only, offline, on the laptop**. No EC2 involvement; no live account, book,
or database is touched.

- **Arm A — DEFECTIVE (reference):** `SIZING = "hybrid_50_50"` — reproduces the validated run exactly.
- **Arm B — FEASIBLE:** `SIZING = "equal_weight"` — the unique cap-feasible fully-invested N=5 portfolio.

Data, universe, scores, selection logic, regime series, gross exposures, cost model and RNG-free code
paths are **byte-identical** between arms; the sizing call is the only difference.

### 2.1 Arm A must reproduce the committed artifact before anything else

Gate: Arm A's endpoint metrics must equal `MR_MomentumDaily_Stage3_full.json → N5/hyb/nocap` to ≤1e-9
relative on CAGR, Sharpe, Calmar, maxDD and exactly on `trades`. **If reproduction fails, the study STOPS**
and the discrepancy is reported — a harness that cannot reproduce the validated run cannot adjudicate it.

### 2.2 Two trade-schedule treatments

The rebalance gate reads `target_w`, so changing the weights perturbs *when* the book trades (1,378 vs
1,384 trades). Two treatments separate the two effects:

- **B-pinned (PRIMARY).** The trade-date schedule is pinned to Arm A's and replayed with equal weights.
  This satisfies the owner's requirement to hold selections, gross, trade dates and costs identical, and
  isolates the pure weighting effect.
- **B-free (SECONDARY, diagnostic).** The gate free-runs, as production actually does. Reported alongside
  so the gate-interaction effect is visible and not silently absorbed into the weighting effect.

Divergence between B-pinned and B-free is itself a reported quantity; a large divergence would mean the
weighting residual was materially driving trade timing.

## 3. Metrics

Per arm: total return, CAGR, annualized volatility (daily log returns), Sharpe, maximum drawdown, Calmar,
annualized turnover, cumulative cost drag (bps), trades, average holding days, and the three registered
crash windows (2008 GFC, 2020 COVID, 2022). Path statistics: worst rolling 1-, 3-, and 12-month return,
and the **difference** in each between arms. Reported as A, B-pinned, B-free and the differences B−A.

## 4. Materiality thresholds (PROPOSED — require ratification before the run)

Immaterial if **all** hold, on the primary comparison **B-pinned − A**:

| # | quantity | threshold | tier |
|---|---|---|---|
| T1 | \|ΔSharpe\| | ≤ 0.05 | 1 (known) |
| T2 | \|ΔCAGR\| | ≤ 100 bps | 1 (known) |
| T3 | \|Δmax drawdown\| | ≤ 200 bps | 1 (known) |
| T4 | \|ΔCalmar\| | ≤ 0.02 | 1 (known) |
| T5 | \|Δannualized turnover\| | ≤ 0.50× | 1 (known) |
| T6 | \|Δannualized volatility\| | ≤ 100 bps | **2 (unseen)** |
| T7 | \|Δ worst rolling 12-month return\| | ≤ 200 bps | **2 (unseen)** |
| T8 | \|Δ worst rolling 3-month return\| | ≤ 150 bps | **2 (unseen)** |
| T9 | \|Δ worst rolling 1-month return\| | ≤ 100 bps | **2 (unseen)** |
| T10 | crash-window differences | no sign change in any of the three windows, and each \|Δ\| ≤ 200 bps | 1 (known) |
| T11 | Stage-3 winner ordering | the top-two ordering of the 12-config Stage-3 grid is unchanged when Arm A's row is replaced by Arm B's | 1 (known) |
| T12 | B-free vs B-pinned | \|ΔSharpe\| ≤ 0.05 between the two treatments (the gate interaction is not itself material) | **2 (unseen)** |

**Rationale for the Tier-1 magnitudes.** T1 (0.05 Sharpe) is roughly the smallest separation on which the
Stage-3 grid distinguished *adjacent* configurations (e.g. N5/hyb/nocap 0.528 vs N8/hyb/nocap 0.529 were
treated as tied; the cap arms at 0.58 were treated as distinguishable) — so a difference under 0.05 cannot
reorder a conclusion the grid was capable of drawing. T2/T3/T4/T5/T10 are scaled to be comfortably below
the between-config spreads in that same grid (CAGR spread ~7.3pp, maxDD spread ~8.5pp, turnover spread
~4.4×) while remaining tight enough to catch a genuine risk-shape change.

**Decision rule (fixed now):**

- **IMMATERIAL** — all of T1-T12 hold ⟹ the acceptance verdict is preserved under cap-feasible equal
  weighting; the study recommends clearing `WEIGHTING_VALIDATION_DEFECT_IMPACT_NOT_YET_ADJUDICATED`,
  subject to the erratum §2 conditions 4 and 5 (implementation and driver share one equal-weight seam;
  20% limit respected exactly) which are already satisfied on branch
  `fix/momentum-daily-weighting-defect-seams`.
- **MATERIAL** — any threshold breached ⟹ the equal-weight variant **requires separate validation**. The
  hold stands. No partial or discretionary clearance.
- Reporting is unconditional: every metric in §3 is reported whatever the verdict, including thresholds
  that pass narrowly.

## 5. Deliverables

`weighting_defect_impact_study_v1.0.md` (findings + verdict against §4) and
`weighting_defect_impact_v1.0.json` (machine-readable metrics, both arms, both treatments), plus the
driver script, committed to this directory. Provenance: measurement-code commit SHA, input content digests
re-verified fail-closed, and artifact SHA-256s — recorded **before** execution, with PID/log files written
**outside** tracked directories (the operational-cleanliness correction noted in census findings §1).

## 6. Ratification

```
Owner ratification of §4 thresholds:   [ ] RATIFIED   [ ] AMENDED   [ ] REJECTED
Date:
```

Until ratified, the study is **not run**. Setting thresholds after observing Tier-2 results would not be a
pre-registration, and this document would then be a report, not a protocol.
