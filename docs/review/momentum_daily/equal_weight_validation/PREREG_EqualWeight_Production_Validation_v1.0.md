# PREREG — momentum-daily Equal-Weight Production-Sizing Validation — v1.0 (GOVERNING)

**Date:** 2026-07-22 · **Status:** governing preregistration. §5–§7 **RATIFIED** (owner 2026-07-22).
**Supersedes:** `…_v0.1_DRAFT.md` (drafting history only; never a governing record).

Nothing here activates Account 4, clears the operational hold, or starts a cooldown. A
`PASS_ACTIVATION_READINESS` means only that a **separate operational activation decision may begin**
(§9). The retired `84466.41` baseline and prior realized loss are **not reused** anywhere in this
program.

## 0. Binding block (run-time provenance)

Bound at commit / at run-start. Frozen *decisions* are complete below; these are artifact hashes and
timestamps produced as the program is executed — a binding manifest, **not** open decisions.

| binding | value |
|---|---|
| #469 merge SHA (durable-state parity — last instrument prerequisite) | `5c2c05871df202d2a5268a41080c055fe6b86ce7` |
| production strategy commit | `b0058bf335628f8dbde09a93915314f3a1f7743b` |
| deployed image (ec2-paper) | `sha256:098da002…` (deploy 2026-07-22) |
| validation measurement-code commit | «bound at run-start» |
| benchmark implementation SHAs (FROZEN 2026-07-22) | primary `PIT_UNIVERSE_EQUAL_WEIGHT_REGIME_MATCHED` `539cf6e` (#470) · `ACADEMIC_12_1_MOMENTUM_FACTOR` `4675073` (#471) · `CASH_OR_TBILL_RETURN` `b055b1c` (#472) |
| DGS3MO dataset digest (FROZEN) | `87d8ba2fc5981add5ea48bb5d365f79371fd457488a598e0043758c21ff825d1` · cutoff `2026-07-21` (2004-01-02..2026-07-21) |
| complete trial-ledger SHA (FROZEN v1.0) | `b7d9d71591cc449a1768f33a3f3f5e0dcdf8ae518710ecec13422f0a0a98eb6d` — N=45 conservative (doc-reduction floor 30) |
| data store + digests | `factor_data_full.duckdb`; sep `d9472dfe…`, tickers `2f21b154…` (re-verified fail-closed) |
| data cutoff | «bound at run-start» |
| forward validation start (first eligible session) | «bound at run-start, countersigned» |
| transaction-cost assumptions | registered base `TURNOVER_COST_BPS=10.0`; stress ×1/×2/×3 (§7 F) |
| authorized operator + countersignature | «bound at run-start» |

---

## 1. Governing question

Does the **exact production** momentum-daily strategy (equal weight, 20% per-name cap, cash residual
when fewer than five names qualify, graduated regime, production §5.1 triggers, production pending-buy
semantics) **independently** satisfy the performance and risk standards below, measured on a
production-faithful instrument with a **forward** out-of-sample gate?

Not strategy discovery, retuning, or re-selection. Every parameter frozen (§2); none swept. Revisiting
name count or the 20% cap is a **different** program, out of scope.

## 2. Frozen production configuration

Exact `MomentumDaily` `default_params` at `b0058bf`: signal 252/21, `min_score=0`/`min_raw=0`;
selection `entry_rank=5`/`hold_rank=10`/`exit_confirm_closes=2`/`replace_advantage=0.30`; construction
`max_names=5`/**`max_position_pct=0.20`**/`max_sector_pct=None`/**`weighting="equal"`** (fail-closed);
triggers `weight_drift_pct=0.04`/`backstop_max_days=10`; regime graduated `MA=200`/band `0.02`/gross
`0.98/0.60/0.15`/staleness `2/0.50/4`; inception `initial_seed_investable_gross=0.60`; universe fixed;
`min_trade_pct=0.03`/`cash_buffer_pct=0.02`. Sizing = equal weight, hard-capped at 0.20, **cash
residual when <5 names** (`_per_name_notional`). No inverse-vol tilt (infeasible at N=5 under the cap).

## 3. Instrument — production-faithful, never a reimplementation

Drives the **actual live `MomentumDaily` class** through history via the parity-complete context
lineage — sizing seam `_per_name_notional`/`target_weights` (#461), `pending_buy_qty` (#467),
durable state `get/set/clear/compare_and_set_state` (#469), and the real
`_evaluate`/`_regime`/`_eligible`/`_fired_triggers`/`_select_targets`. **No** selection, sizing,
regime, or trigger logic is reimplemented — reimplementation was the root cause of the drift this whole
episode corrected. The §7 A equivalence gate must pass before any performance number is computed.

## 4. Data & provenance

`factor_data_full.duckdb` — read-only, offline, laptop. Content digests re-verified fail-closed
(sep `d9472dfe…`, tickers `2f21b154…`). PIT universe `momentum_daily_stage2_4:top200_PIT_universe_asof_n200`.
Measurement-code commit, digests, artifact SHA-256s recorded before execution; PID/logs outside tracked dirs.

---

## 5. In-sample / out-of-sample design — RATIFIED: forward-only OOS

**The historical 2005–2026 run is NOT out-of-sample and NOT a performance gate.** Stage 2–4 drove
decisions over that whole window, so nothing in it is unseen. The historical run may be used ONLY for:
instrument equivalence; construct validation; regime & calendar diagnostics; expected-turnover /
operational-range estimation; and catastrophic-instability detection. It must never be called OOS or
used to satisfy the primary performance gate. Historical regime-stratified results are supporting
evidence only and **cannot rescue a failed forward gate**.

### 5.1 Governing forward period (frozen)

The validation start is frozen **before** any forward result is observed. The gate closes only after
**all three** minima are met:

```
minimum duration:        252 completed trading sessions
minimum rebalances:      40
minimum completed years: 1
```

**Extending the period after a failure is prohibited** — no extension is defined here, so none is
permitted. (If all three minima are met and a gate has not yet resolved for lack of data on a specific
statistic, that statistic is reported as INDETERMINATE and treated as a FAIL of its gate, not an
extension trigger.)

### 5.2 Start conditions (all required, then the first eligible session)

(1) #469 merged; (2) the exact validation artifact pinned; (3) all equivalence gates (§7 A) pass;
(4) the data cutoff and start timestamp countersigned. The forward period begins at the first eligible
trading session after all four hold.

### 5.3 Ledger — never Account 4's live capital

The exact strategy runs in a **non-ordering shadow ledger** or a **separate governed paper-validation
account**. Account 4 may remain held throughout; **its live capital state must not be the research
ledger**, and the retired `84466.41` baseline is not reused.

### 5.4 No-peeking rule (sealed adjudication)

Operational health may be monitored; **performance adjudication is sealed** during the forward period.

- **Permitted early stops:** implementation / data-integrity failure; seam-equivalence failure; cap or
  construct violation; unrecoverable missing data; a risk loss exceeding the preregistered
  **catastrophic stop** (absolute strategy drawdown reaching the §7 E ceiling of **35%**).
- **NOT permitted:** stopping because returns look poor; extending because returns look promising;
  changing benchmark, costs, thresholds, universe, triggers, or regime logic.

---

## 6. Benchmarks — RATIFIED

### 6.1 Primary — `PIT_UNIVERSE_EQUAL_WEIGHT_REGIME_MATCHED`

A daily/scheduled-rebalanced equal-weight portfolio of the **same PIT eligible universe**, with
**identical** session calendar, investability filters, pricing convention, transaction-cost model,
graduated-regime gross path, and cash treatment. The **only** intended difference is the momentum
selection and rebalance decisions — this controls for market exposure, the regime overlay, and data
availability. **Primary adjudication is against this benchmark.**

### 6.2 Secondary (both, diagnostic)

- `MOMENTUM_FACTOR_MATCHED` — an equal-weight top-N momentum portfolio **frozen from an external /
  independently specified construction, NOT tuned to this strategy's results** (attribution: policy
  value-add over the raw factor).
- `CASH_OR_TBILL_RETURN` — the absolute-return hurdle (§7 B).

---

## 7. Acceptance thresholds — FROZEN. Every mandatory gate must pass; no averaging, no compensating.

### A. Construct & equivalence gate (before any performance measurement)

```
production seam mismatches:       0
cap violations:                   0
unexpected trigger mismatches:    0
duplicate initial seeds:          0
unexplained pending-buy mismatch: 0
unreconciled durable-state drift: 0
```
Any failure ⟹ **`INVALID_RUN`**, not a performance FAIL.

### B. Absolute performance (net of registered base costs)

```
annualized Sharpe:      ≥ 0.40
net cumulative return:  > 0
annualized net return:  > CASH_OR_TBILL_RETURN
```
No high-CAGR requirement (that would invite overfitting to the historical result).

### C. Primary-benchmark performance (all four)

```
net excess cumulative return over primary benchmark:        > 0
annualized excess return:                                   > 0
paired bootstrap 95% lower bound on excess return:          > 0
strategy Sharpe ≥ primary-benchmark Sharpe
```
A positive strategy return that merely trails the broad benchmark is **not** a PASS.

### D. Multiple-testing control

```
Deflated Sharpe Ratio: P(adjusted Sharpe > 0) ≥ 0.95
```
The **trial ledger is frozen before the run** and includes **every** materially related sizing,
name-count, cap, regime, trigger, and benchmark variant previously evaluated in this research lineage.
Missing/uncertain trials are counted **conservatively**; the trial count **may never default to 1**.

### E. Drawdown & tail risk (all apply)

```
strategy max drawdown        ≤ 1.25 × primary-benchmark max drawdown
strategy CVaR/ES @ 95%       ≤ 1.25 × primary-benchmark CVaR @ 95%
absolute strategy max drawdown ceiling: ≤ 35%     (also the §5.4 catastrophic stop)
```
Both the ratio gates and the absolute 35% ceiling apply (the ceiling guards against an unstably-small
benchmark drawdown making the ratio meaningless).

### F. Cost robustness (frozen scenarios: ×1.0, ×2.0, ×3.0 registered costs)

```
×1.0:  ALL primary gates pass
×2.0:  net cumulative return AND annualized excess return remain > 0
×3.0:  reported, no pass requirement
```
No alternate slippage model may be substituted after results are visible.

### G. Stability (over the 252-session forward period)

```
positive monthly excess return: ≥ 7 of 12 completed months
no single month contributes > 50% of total positive excess return
no single security contributes > 35% of total strategy P&L
```
Historical supporting analysis must show no catastrophic failure in any registered regime — descriptive
only; it cannot rescue a failed forward gate.

### H. Operational reliability

```
scheduled evaluations completed:               ≥ 99%
unexplained missed rebalances:                  0
duplicate orders or duplicate seeds:            0
cap breaches:                                   0
unreconciled broker/local position divergence:  0
unresolved reservations at checkpoint:          0
manual performance-affecting interventions:     0
```
A permitted operational intervention **invalidates the affected performance intervals** — this prereg
defines no exclusion, so an affected interval is treated as INVALID for the statistics it touches.

---

## 8. Reported quantities

Per the forward gate window (and, descriptively, per historical sub-period/regime): total & net
return, CAGR, annualized volatility, Sharpe, max drawdown, Calmar, CVaR@95%, annualized turnover,
cumulative cost drag, trades, avg holding days, per-year and per-month excess return, per-security P&L
share, DSR probability + trial count, the ×1/×2/×3 cost sweep, operational-reliability counters, and
benchmark-relative deltas vs all three benchmarks. All reported regardless of verdict.

## 9. Outcomes (frozen)

```
PASS_ACTIVATION_READINESS   — every mandatory gate (§7 A–H) passes. A SEPARATE operational activation
                              decision MAY BEGIN. Does NOT clear the hold, start cooldown, or activate.
FAIL_PERFORMANCE_OR_RISK    — any performance/risk gate (B–G) fails. Blocker stands.
INVALID_RUN                 — the construct/equivalence gate (A) or operational reliability (H) fails;
                              no performance verdict is issued.
```

A `PASS_ACTIVATION_READINESS` is followed by a separate activation adjudication weighing hold clearance,
the 24-hour (or documented-exception) cooldown, the deployment-lifecycle state, and a **fresh
authoritative session baseline established at activation time** (never from the retired `84466.41`).

## 10. Ratification

```
§2–§4 (config / instrument / data):  frozen; owner to confirm at commit
§5 (forward-only OOS design):        RATIFIED 2026-07-22
§6 (benchmarks):                     RATIFIED 2026-07-22
§7 (acceptance thresholds):          RATIFIED 2026-07-22
```

The binding block (§0) is completed at run-start (benchmark impl SHA, trial-ledger SHA, forward start,
countersignature) — those are artifact hashes, not open decisions. Building the benchmark
implementation and assembling+freezing the trial ledger are the next authorized steps; the forward run
does not begin until §0 is fully bound and countersigned.
