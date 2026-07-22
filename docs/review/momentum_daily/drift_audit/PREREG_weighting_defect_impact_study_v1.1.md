# PREREG — momentum-daily Weighting-Defect Impact Study — v1.1 (RATIFIED)

**Date:** 2026-07-22 · **Status:** ✅ **RATIFIED (owner, 2026-07-22) — authorized to run.**
**Supersedes:** `PREREG_weighting_defect_impact_study_v1.0.md` (PROPOSED; retained, superseded).
**Governs:** the correction-impact analysis required by `weighting_defect_erratum_v1.0.md` §4.
**Blocker at time of ratification:** `WEIGHTING_VALIDATION_DEFECT_IMPACT_NOT_YET_ADJUDICATED` (interim; never written to the live hold). **Post-study durable blocker:** `AWAITING_PRODUCTION_SIZING_VALIDATION`.

Nothing here authorizes activation or clearing the hold.

---

## 0. Protocol correction carried into v1.1 (disclosed, not silently fixed)

**v1.0 §2.1 named the wrong reproduction reference.** It pinned Arm A to Stage-3 `N5/hyb/nocap`. That row
is **regime-free**: Stage 3 swept construction before Stage 4 introduced the regime filter. It corresponds
to Stage-4 **variant D** — CAGR 0.14783241200020414 (Stage 3) vs 0.14783241200020525 (Stage 4), i.e. equal
to **~7e-15 relative**, floating-point identical from two separate runs of the same configuration. (Stated
as "byte-for-byte" in an earlier draft; the two artifacts are numerically identical, not byte-identical.)

Production runs the **graduated** regime = Stage-4 **variant C**. So:

- The governing pairing is **variant C × hybrid vs variant C × equal**, and **only the first has ever been
  computed** (CAGR 16.915%, Sharpe 0.59654, Calmar 0.26186, maxDD −64.594%, turnover 14.882×, 1,539 trades).
- The **+26.1 bps CAGR / +0.0049 Sharpe** residual quoted in v1.0 §0 and erratum §1.4 is a **variant-D**
  quantity. It is a true characterization of the defect residual in the regime-free control, and it is
  **not** the governing-config residual. The erratum table is relabelled accordingly.
- Consequently the endpoint metrics at variant C are **genuinely unseen**, contrary to v1.0's tier split.

**Owner ruling (2026-07-22):** this is disclosed as a protocol correction and **does not promote endpoint
metrics into gates**. Rationale, unchanged by the correction: CAGR, Sharpe, Calmar, maxDD and turnover are
broad endpoint summaries that can hide compensating differences; the Tier-2 gates test practical
equivalence directly through volatility, rolling-return differences, costs, and trade-date-controlled
behavior. The confirmatory gate set is **Tier 2 only, exactly as ratified**.

---

## 1. Questions

- **Variant C (GOVERNING).** Under the actual graduated production regime, is feasible equal weighting
  practically equivalent to the defective hybrid residual under the pre-registered Tier-2 gates?
  **This question governs Account 4.**
- **Variant D (NON-GOVERNING REGIME-FREE REPRODUCTION CONTROL).** Did the Stage-3 N=5 hybrid "advantage"
  consist entirely of infeasible clamp residual? Descriptive only; **not on the activation-critical path**;
  run only if it adds little operational delay.

Out of scope: strategy discovery, retuning, re-selection among Stage-3 arms, re-running or re-reviewing the
§8 census, and any change to `max_position_pct` (fixed at 0.20).

## 2. Design

Stage-4 harness at **N=5, no sector cap**, 2005-01-03 → 2026-06-12 (5,395 sessions), `INITIAL_EQUITY`
100,000, `TURNOVER_COST_BPS` 10.0, `WEIGHT_DRIFT_PCT` 0.04, `BACKSTOP_DAYS` 10, reading
`factor_data_full.duckdb` **read-only, offline, laptop**. No EC2, no live account/book/DB. `select_n`,
`weigh`, `compute_day`, `build_market_proxy`, `gross_series`, `_CachedPriceStore` and `_summary` are
**imported from the validated harness, not reimplemented**; the simulation loop is a disclosed transcription
of `backtest_momentum_stage4.py::simulate` with instrumentation added and the sizing call parameterized.

- **Arm A — DEFECTIVE (reference):** `sizing = hybrid_50_50`.
- **Arm B-pinned — FEASIBLE, PRIMARY:** `sizing = equal_weight`, trade-date schedule **pinned to Arm A's**.
- **Arm B-free — FEASIBLE, DIAGNOSTIC:** `sizing = equal_weight`, rebalance gate free-running.

Data, universe, scores, selection, regime series, gross exposures and cost model are identical across
arms; the sizing call is the only difference. Pinning is to **variant C's 1,539 rebalance dates** for the
governing comparison (and to variant D's 1,378 for the control, if run).

Selection is sizing-independent, so with dates pinned the target-name sequence and holdings path are
identical to Arm A by construction — leaving weights as the sole difference. §4 T13 asserts this rather
than assuming it.

**Reproduction gate (STOP condition).** Arm A must reproduce the committed `MR_MomentumDaily_Stage4_full.json`
variant C to ≤1e-9 relative on CAGR, Sharpe, Calmar and maxDD, and exactly on `trades`. If it does not,
**the study stops and reports the discrepancy** — a harness that cannot reproduce the validated run cannot
adjudicate it.

## 3. Reported quantities

**Tier 1 — descriptive only. Reported, never used to claim threshold success.** CAGR, Sharpe, Calmar,
maximum drawdown, turnover, crash-window returns, and the entire free-running arm. The known variant-D
differences (≈ +26.1 bps CAGR, +0.0049 Sharpe favouring the defective hybrid) are characterized as
**observed defect residuals — not evidence that hybrid sizing was superior**, since at N=5 hybrid sizing
denotes no feasible portfolio.

**Tier 2 — blind, governing.** Volatility, rolling-return differences, costs, trade-date alignment and
position feasibility, on the **trade-date-pinned** arm, per §4.

## 4. Confirmatory gates (RATIFIED — trade-date-pinned arm, variant C)

| # | quantity | threshold |
|---|---|---|
| T1 | annualized volatility, \|Δ\| | ≤ 25 bps |
| T2 | rolling 1-month return difference, median \|Δ\| | ≤ 10 bps |
| T3 | rolling 1-month return difference, p95 \|Δ\| | ≤ 50 bps |
| T4 | rolling 3-month return difference, median \|Δ\| | ≤ 20 bps |
| T5 | rolling 3-month return difference, p95 \|Δ\| | ≤ 75 bps |
| T6 | rolling 12-month return difference, median \|Δ\| | ≤ 35 bps |
| T7 | rolling 12-month return difference, p95 \|Δ\| | ≤ 125 bps |
| T8 | transaction-cost difference, \|Δ annualized\| | ≤ 10 bps |
| T9 | maximum single-rebalance cost difference | ≤ 2 bps of NAV |
| T10 | trade-date alignment | 100% identical **by construction** |
| T11 | position feasibility, equal-weight arm | **zero** cap violations |
| T12 | no calendar segment or regime state shows a persistent one-directional effect large enough to contradict practical equivalence | qualitative, evidenced per-year and per-regime-state |
| T13 | target-name sequence and holdings path identical to Arm A | asserted, not assumed |

Rolling windows are 21 / 63 / 252 trading days. Volatility is annualized from **daily log returns** at
√252. Annualized transaction cost is `TURNOVER_COST_BPS × annualized_turnover`; per-rebalance cost is
`TURNOVER_COST_BPS × turnoverᵢ`, in bps of NAV.

**Verdict rule.**

- **`PRACTICALLY_EQUIVALENT`** — **every** Tier-2 gate passes. **Compensating failures are not permitted**;
  no composite score, no averaging.
- **`MINOR_BUT_MEASURABLE`** — any gate fails, but every failing quantity is within 2× its threshold.
- **`MATERIALLY_DIFFERENT`** — any failing quantity exceeds 2× its threshold.

The 2× boundary between the two failure categories is pre-declared here (the ratification fixed the pass
thresholds, not the failure gradation). Either failure category leaves the hold standing; only
`PRACTICALLY_EQUIVALENT` supports recommending that the blocker be cleared.

**Every threshold outcome is reported individually, including narrow passes and every failure. No failure
may be averaged away.**

## 5. Free-running diagnostic (reported separately, never mixed into the verdict)

Rebalance-date count and overlap with Arm A; return effect attributable to differing trade dates; cost
effect attributable to gate interaction; whether any divergence compounds materially.

## 6. Deliverables

`weighting_defect_impact_study_v1.0.md` (findings + verdict against §4) and
`weighting_defect_impact_v1.0.json` (machine-readable, all arms), plus the driver, committed to this
directory. Provenance recorded **before** execution: measurement-code commit, input content digests
re-verified fail-closed, artifact SHA-256s; PID/log files written **outside** tracked directories.

## 7. Ratification

```
Owner ratification of §4 thresholds:   [X] RATIFIED  (2026-07-22)
Tier 1 endpoint metrics:               DESCRIPTIVE ONLY — not promoted to gates despite §0
Primary treatment:                     trade-date-pinned, variant C
Variant D:                             NON-GOVERNING REGIME-FREE REPRODUCTION CONTROL
```
