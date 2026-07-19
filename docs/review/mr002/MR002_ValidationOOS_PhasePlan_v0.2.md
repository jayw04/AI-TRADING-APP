# MR-002 Validation / OOS Phase Plan v0.2 (PREPARED, NOT EXECUTED)

**Status:** preregistration revision. No validation or OOS *data* was read. Everything here is
transcribed from FROZEN DESIGN METADATA (cited per item) or flagged as an explicit owner
decision. It authorizes nothing. Companion machine-readable pin file:
`MR002_ValidationOOS_Prereg_Companion_v0.2.json`.

## Governing frozen sources (cited, not re-derived)

- **Window boundaries + session counts:** `TradingWorkbench_MR002_PreRegistration_v1.1_REFREEZE_CANDIDATE.md`
  (sha256 `311e997b92858a7ede9f486ee7da11969703fc0304b2e6eb5c778ed8304f9dd5`) §"Windows", and
  `MR002_SealedManifest_v1.0.json` (sha256 `96f7b3f96c61abb2d146ca25a58698471ae61454af13882ea15c9be9000112cd`).
- **Gate table + verdict labels:** `TradingWorkbench_MR002_PreRegistration_v0.1.md` §gates (carried
  forward v0.2/v0.3/v1.1), and cost/NAV/participation rules in v1.1 §"four-series price policy".
- **Dev-window boundary (authoritative code):** `mr002_stage3_population_runner.py:1043`
  `day_inputs(date(2013,1,2), date(2019,10,2))`.

> ⚠ **Material divergence flag (decision D-NI):** the owner's v0.1→v0.2 correction template asks
> for a validation-vs-OOS **non-inferiority** structure (`S_min`, `Δ_NI`, `H0,O2`). The FROZEN
> MR-002 design does **not** use that: it reads the verdict on the **sealed OOS** against
> **absolute** gates, with validation feeding the positive-folds + stability + A/C-parameter
> gates. Adopting the non-inferiority framework would **amend the frozen preregistration** and is
> therefore presented below as an owner decision, not silently substituted. §§3–4 give BOTH the
> frozen structure (default) and the owner-template overlay (optional, requires ratification).

---

## 1. Literal window boundaries (correction 1) — TRANSCRIBED, not inferred

Total realized window: **2013-01-02 → 2026-07-10, 3,400 trading sessions** (frozen).

| Window | Inclusive dates | Sessions | Status |
|---|---|---|---|
| Development | 2013-01-02 → 2019-10-02 | 1,700 | in use (no performance computed) |
| Validation | 2019-10-03 → 2023-02-16 | 850 | **SEALED AND UNREAD** |
| Sealed OOS | 2023-02-17 → 2026-07-10 | 850 (config B only) | **SEALED AND UNREAD**, one future opening |

**Date semantics (deterministic single-window membership):** the boundary dates are **trading
sessions** on the registered NYSE calendar. A row's window membership is by its **decision session
`t`** (the session whose end-of-day information forms the signal; §"windows ending at t−1"). The
next-open **execution** occurs at session `t+1`; **return realization** accrues from the `t+1`
open forward. Because membership is keyed to `t` (not to `t+1`/realization), each decision session
belongs to exactly one window; no session is shared. Signal-formation observation dates are all
`≤ t−1`.

**Purge (development→validation) and embargo (validation→OOS)** are defined in §2. The frozen
split is contiguous by session index (1,700 / 850 / 850); the purge/embargo are applied as
**session-membership exclusions at the seams**, not by moving the boundaries.

## 2. Purge / embargo — defined mathematically (correction 2)

Registered horizons (frozen, cited from v0.1/v0.2 §normalization + v1.1 §execution):
- Max feature lookback / residual-estimation lookback: **60 complete 5-session observations**
  ⇒ ≈ **64 sessions** of formation history (60 overlapping 5-day windows ending at `t−1`).
- Signal-formation lag: signal uses windows **ending at `t−1`** (0 same-day leakage).
- Trade/execution lag: **next open** = `t+1` (1 session).
- Max holding horizon: **5-session hold** (registered).
- **Required purge length (dev→validation):** `max_lookback (64) + hold (5) = 69 sessions`,
  applied by EXCLUDING the first **69** validation sessions from any gate whose statistic could
  otherwise depend on development-formed information. Proposed literal purge span: the 69 sessions
  from 2019-10-03 forward (exact dates pinned in the companion JSON once the session list is
  confirmed from the pinned calendar — a calendar/metadata read, no returns).
- **Required embargo length (validation→OOS):** `hold (5) + execution (1) = 6 sessions` minimum to
  prevent a position or 5-day label from straddling 2023-02-16/2023-02-17; extended to the full
  `max_lookback + hold = 69` sessions so no OOS signal is formed from validation-period data.
  Applied by excluding the last 6 (label) and treating the first 69 OOS formation sessions as
  using only OOS-window data.

> Decision **D-PURGE**: confirm whether the frozen design intends purge/embargo as *scoring
> exclusions* (this plan's default) or *boundary shifts*. The frozen design fixes 1,700/850/850
> contiguous; this plan keeps those fixed and excludes seam sessions from scoring.

## 3. Exact hypotheses (correction 3)

**Frozen-design structure (default, per the gate table):** the confirmatory verdict is read on the
**sealed OOS**, config B, net of base costs. There is no separate validation Sharpe null in the
frozen design; validation supplies the positive-folds (≥60% ⇒ ≥3/5) and A/C-stability gates.

- **OOS absolute null** `H0,O`: net OOS Sharpe ≤ `S_min`.
- **OOS absolute alternative** `H1,O`: net OOS Sharpe > `S_min`, with `S_min = 0.70` (Approved) or
  `0.40` (Diversifier) — **frozen literal values**, not chosen post-hoc.
- **Validation gate (not a Sharpe null):** ≥ 3 of 5 contiguous non-overlapping folds with positive
  net return on config B (frozen ≥60%).

**Owner-template overlay (optional, decision D-NI):** add `H0,O2`: `Sharpe_OOS − Sharpe_VALIDATION
≤ −Δ_NI`, OOS passes only if BOTH `H0,O` and `H0,O2` are rejected. **`Δ_NI` has no ex-ante value
in the frozen design** — it cannot be set from the design objective without an owner ruling, and
must not be chosen to make OOS easier. If D-NI is adopted, `Δ_NI` is an owner-pinned constant with
written economic justification, frozen before unsealing.

## 4. Decision thresholds (corrections 4/8) — FROZEN literal values

| Symbol | Meaning | Frozen value | Source |
|---|---|---|---|
| `S_min` (Approved) | absolute net OOS Sharpe | **0.70** | gate table |
| `S_min` (Diversifier) | absolute net OOS Sharpe | **0.40** | gate table |
| Calmar | net OOS Calmar | **≥ 0.75** | gate table |
| MaxDD | net max drawdown (full test) | **≤ 15%** | gate table |
| Positive folds | validation folds net-positive | **≥ 3 of 5 (≥60%)** | gate table |
| Bootstrap CI | date-clustered mean-return CI lower bound | **> 0** | gate table |
| Cost stress | profitable at | **2× base costs** | gate table |
| Parameter stability | configs A and C net-profitable | **both** | gate table |
| PBO | probability of backtest overfit | **< 20%** | gate table |
| DSR | deflated-Sharpe significance | **≥ 95%** | gate table |
| Profit concentration | single-year P&L share | **≤ 35%** | gate table |
| Regime concentration | single-regime P&L share | **≤ 60%** | gate table |
| Capacity | net edge under 2% ADV cap | **positive** | gate table |
| Trades | minimum trades / long / short | **≥ 500 / ≥100 / ≥100** | v1.1 §gates |
| Diversifier corr | \|corr\| vs MOM-001 on overlap | **≤ 0.30** | gate table |
| `α` | significance for CIs/DSR | **0.05** (95%) | gate table (DSR ≥95%, one-sided) |
| `Δ_NI` | OOS non-inferiority margin | **UNSET — owner decision D-NI** | not in frozen design |

None of these were read from Stage-3 development, validation, or OOS performance.

## 5. Exact benchmark (correction 4-benchmark)

The registered book is **dollar-neutral, sector-neutral, beta-neutral** (long gross = short gross;
sector-gross ≤ 0.20, sector-net ≤ 0.05, |beta| small; v1.1 §LP-feasibility). Its return is a
**self-financing long/short spread**, so the economically correct benchmark is **cash/zero excess**
— net return IS excess return over the cash rate on the unfinanced neutral book. Literal
definition: benchmark = **risk-free/cash accrual** on any residual cash; construction = the
registered $10M-NAV neutral portfolio; weights/rebalance/return-source/corporate-action/cash-return
follow the registered pricing policy (four-series price policy · next-open execution). No
benchmark transaction costs (the benchmark is the cash leg). **This is fixed here, before any
validation result** (decision D-BENCH: owner ratifies cash-zero as the benchmark, or names a
matched residual-neutral reference).

## 6. Primary return series (correction 5) — bound to the frozen cost artifact

- Return frequency: **daily** (per-session), realized from the **next-open (`t+1`) execution**.
- Simple returns (not log) for P&L aggregation; log only where a gate names it.
- **Net** returns after the FROZEN cost model: **10 bps/side** commission+slippage, **borrow 50
  bps/yr ÷ 360** on short market value, **$10M NAV**, **2% ADV participation cap (clip, never
  delay)**, **1.5%-of-NAV new-entry cap** (v1.1 §costs). Corporate actions + delisting returns per
  the registered four-series price policy; missing-day treatment = registered (no forward-fill,
  per sealed manifest `forward_fill: prohibited`); partial first/last periods excluded by the
  purge/embargo.
- Excess-return definition: return over the cash rate (see §5).
- **Bind the exact cost-model artifact** (decision D-COST): the cost parameters above are
  transcribed from v1.1 prose; the finalized prereg must bind the committed cost-model
  *implementation* file + version + sha256 (to be produced/identified in the evaluator
  qualification, §16). Until then the cost model is pinned by value here and by hash in the
  companion JSON's `PENDING_EVALUATOR_BIND` field.

## 7. Sharpe estimator (correction 6)

- Point estimate: **arithmetic mean** of daily net excess returns ÷ **sample standard deviation**
  (ddof = 1), annualized by **× √252**.
- Serial correlation: reported via the date-clustered bootstrap (§8); the point estimate is not
  Newey-West-adjusted (the CI carries the dependence).
- Zero-volatility: if sample σ = 0 over the window ⇒ `INTEGRITY_STOP:ZERO_VOLATILITY` (not a
  divide-by-zero, not a pass).
- Minimum observations: ≥ the window session count minus purge/embargo (≥ ~781 validation, ~781
  OOS); fewer ⇒ `REFUSED_DATA_COVERAGE`.
- Numerical precision: float64; report to 4 decimals; the point estimate must be reproducible
  bit-for-bit from the same return vector by an independent implementation.
- Exposure-normalized returns: **not** used for the primary Sharpe (returns are on $10M NAV).

## 8. Confidence interval / bootstrap (correction 7) — frozen algorithm

- **Date-clustered (block) bootstrap** of the daily net mean return and the Sharpe.
- Confidence level **95%**, **one-sided** lower bound (gate: lower bound > 0).
- Block type: **non-overlapping calendar blocks**; block length: **21 trading sessions** (≈ 1
  month), a deterministic fixed selector (not data-driven). Incomplete final block: kept as a
  short block (no wraparound).
- Resamples: **2,000**; RNG: **NumPy PCG64**; **seed 42** (matches the platform convention in
  `mkt_proj_001` ModelCard). Percentile construction (not studentized) for the mean-return CI;
  DSR handled by its own registered formula.
- Non-finite samples ⇒ `INTEGRITY_STOP:NONFINITE_RETURN`.
- The **same** method governs validation folds and OOS (no per-window variation).

## 9. OOS comparator (correction 9)

Default (frozen): the OOS verdict is **absolute** (§3–4), so no validation comparator is required
for the primary gate. **If D-NI is adopted:** the comparison uses a **jointly resampled
difference** `Sharpe_OOS − Sharpe_VALIDATION` under the SAME block bootstrap (seed 42, 21-session
blocks, 2,000 resamples), rejecting `H0,O2` when the one-sided upper bound of `−(Sharpe_OOS −
Sharpe_VALIDATION)` is `< Δ_NI` — i.e. a proper non-inferiority test on the resampled difference,
not a comparison of two independent intervals.

## 10. Hard stops (correction 10) — closed set with stable codes

| Code | Trigger | Denominator | Level | Stops | Preserve |
|---|---|---|---|---|---|
| `REFUSED_DATA_COVERAGE` | window session coverage < registered (per sealed-manifest V1 95% / V2 98% gates) | 40,750 registered ticker-days | window | immediate | coverage report |
| `REFUSED_PRICE_INTEGRITY` | stale-price fraction > 0 beyond registered policy | per-session prices | row→window | immediate | offending rows |
| `REFUSED_CORPORATE_ACTION` | unresolved corporate action | affected names | row→window | immediate | CA log |
| `REFUSED_UNIVERSE_RECONSTRUCTION` | PIT universe/PIT-SIC mismatch vs sealed manifest | universe | window | immediate | reconstruction diff |
| `REFUSED_COST_MODEL` | cost-model artifact hash ≠ bound | — | window | immediate | hash evidence |
| `REFUSED_EXPOSURE_LIMIT` | see §11 | portfolio | row→window | immediate | breach evidence |
| `REFUSED_REPLAY_INTEGRITY` | evidence hash/replay failure | — | window | immediate | failing record |
| `REFUSED_CODE_OR_DATA_IDENTITY` | evaluator commit/tree/image/data-manifest ≠ bound | — | pre-run | immediate | identity evidence |
| `INTEGRITY_STOP:*` | zero-vol / non-finite / seal-audit failure | — | window | immediate | full state |

For each: no repair, no rerun, no window shortening/moving. A data gap is **never** a discretionary
reason to move a boundary — it is a `REFUSED_DATA_COVERAGE` on the fixed window.

## 11. Exposure / risk limits (correction 11) — frozen literals

Bound from v1.1 §LP-feasibility: **sector-gross ≤ 0.2000**, **sector-net ≤ 0.0500**, **|beta| ≤**
its registered band (0.0052 demonstrated feasible; the registered limit value is pinned in the
companion JSON from the LP constraint set), **long gross = short gross** (dollar-neutral), **no
single name above its registered start weight**, **gross exposure** per the neutral construction,
**turnover** implied by the 1.5%-of-NAV new-entry cap + 2% ADV participation cap, **borrow/
shortability** via the 50 bps/yr borrow and ADV cap. **Any hard-limit breach in replay ⇒
`REFUSED_EXPOSURE_LIMIT`** (hard refusal, not a diagnostic) — consistent with the frozen
`INVALID_RUN` rule that a post-target/post-execution constraint breach stops the run.

## 12. Secondary family (correction 12) — CLOSED

All non-gate metrics (CAGR, hit rate, Sortino, tail, exposure-adherence diagnostics) are **purely
descriptive** and **cannot change any verdict**. There is **no** inferential secondary family and
therefore no post-hoc multiplicity correction is applied to "whichever analyses were run." If any
secondary inferential test is later desired, it must be enumerated and corrected (Holm) in a
*further* frozen revision before unsealing — not added afterward.

## 13. Economic-materiality gates (correction 13) — frozen

Statistical significance alone cannot pass. The frozen gate table already encodes economic
materiality: **Sharpe ≥ 0.70**, **Calmar ≥ 0.75**, **MaxDD ≤ 15%**, **cost-stress at 2×**,
**capacity-positive under the 2% ADV cap**, **profit/regime concentration caps**. These are the
economic-materiality gates; no economically-trivial-but-significant result can pass.

## 14. Validation-PASS ≠ OOS-authorization (correction 14) — sequential

1. Owner authorizes the **validation** opening → **one** validation execution (config A/B/C folds
   + stability/positive-folds gates) → immutable evidence + publication → owner adjudication →
   **validation chain closed**.
2. **OOS remains physically inaccessible** during validation. Only after an **accepted validation
   PASS** and a **separate new OOS authorization artifact** may the sealed OOS be opened — **B
   only, exactly once**. A validation PASS does **not** auto-open OOS.

## 15. Sealed-data access protocol (correction 15) — auditable

- **Storage/identity:** the sealed windows are governed by `MR002_SealedManifest_v1.0.json`
  (`96f7b3f9…`, 16 artifacts) + the pinned DuckDB snapshot (`data/mr002_research.duckdb`, sha256
  `24e5153c…` as used by Stage-3). The finalized prereg binds the exact object/version identity of
  the validation and OOS data partitions.
- **Access roles:** owner-authorized only; the evaluator runs under a recorded principal.
- **Access logging:** every read of a validation/OOS partition is logged with UTC timestamp,
  principal, object version, and byte ranges; the log is committed.
- **Permitted pre-unseal metadata:** only what is ALREADY frozen (session counts 850/850, boundary
  dates, calendar). **Prohibited before unsealing:** row counts beyond the frozen 850, date
  distributions, summary statistics, previews, or any return/price value.
- **First-access proof:** the access log's first validation-partition read timestamp, cross-signed
  by the evaluator run manifest, establishes first access.
- **OOS-unread-during-validation proof:** the OOS partition object's S3/versioned last-access (or
  an object-lock/access-log absence) demonstrates no OOS read occurred during validation.

## 16. Executable evaluator bound before access (correction 16)

**No committed MR-002 P&L/validation evaluator exists** (`apps/backend/scripts/` has no
mr002 backtest/validation script; `app/factor_data/backtest.py` is the momentum harness, not the
MR-002 residual-reversion evaluator). Therefore the finalized prereg **REQUIRES a prior evaluator
qualification phase** (analogous to Stage-3): build + freeze an MR-002 validation/OOS evaluator and
qualify it on **synthetic and development-free fixtures** — **producing no development, validation,
or OOS performance**. The prereg binds, before any unsealing:

- code commit + tree; container digest; dependency lock (with the pandas-ta transplant provenance
  carried forward); data-manifest identity; benchmark implementation; cost-model implementation
  (D-COST hash); metric (Sharpe/Calmar/DD/DSR/PBO) implementation; bootstrap implementation
  (seed 42, 21-block, 2,000); report schema; expected output paths.
- The evaluator is tested on synthetic fixtures with known closed-form Sharpe/CI so correctness is
  provable without touching real returns.

## 17. Terminal dispositions (correction 17) — closed set

- **PASS** — valid evidence clearing the frozen economic/statistical gates for the window.
- **FAIL** — valid evidence that did NOT clear a gate (ends the confirmatory program; no re-param).
- **REFUSED** — the test could not be validly conducted (a §10 hard stop); never a moved window or
  repaired rerun.
- **INTEGRITY_STOP** — identity/evidence/governance failure (§10 `INTEGRITY_STOP:*`).

## 18. Conclusion language (correction 18)

- **Validation PASS:** evidence of merit in the preregistered **validation** period only (folds +
  stability); it does not establish OOS or production merit.
- **OOS PASS:** evidence that the registered effect cleared the preregistered **absolute** gates
  (and, if D-NI adopted, the non-inferiority gate) in the final untouched OOS period. Even an OOS
  PASS does **not** establish production capacity, scalability, or live-trading robustness.

## Owner decisions required before v1.0 finalization

- **D-NI:** adopt the non-inferiority overlay (and pin `Δ_NI` with economic justification) or keep
  the frozen absolute-OOS structure. *Recommendation: keep the frozen absolute structure; the
  frozen design already gates OOS on Sharpe ≥ 0.70 with a bootstrap-CI lower-bound-> 0 and DSR ≥
  95%, which is stronger than a bare non-inferiority-to-validation test.*
- **D-PURGE:** confirm purge/embargo as seam scoring-exclusions (this plan) vs boundary shifts.
- **D-BENCH:** ratify cash-zero benchmark for the neutral book (recommended) vs a matched
  residual-neutral reference.
- **D-COST:** approve producing/binding the committed cost-model artifact in the evaluator
  qualification.
- **S_min selection:** which verdict tier governs (Approved 0.70 vs Diversifier 0.40) — the frozen
  design runs the full table; confirm the headline gate.

## What is NOT in this package (still sealed / not authorized)

No development-window performance, no validation data, no OOS data, no performance interpretation.
Synthetic-fixture evaluator tests (correction 5 of the assignment) are SPECIFIED here and executed
only in the separately-scoped evaluator-qualification phase — none run yet.
