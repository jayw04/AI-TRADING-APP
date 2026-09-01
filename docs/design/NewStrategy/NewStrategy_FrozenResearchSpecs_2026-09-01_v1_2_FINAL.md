# Frozen research specifications — C1 / C2 / C3

| Field | Value |
|---|---|
| Version | **v1.2 — FINAL / OWNER ACCEPTED** (supersedes v1.1 final-review draft and v1.0, neither of which was frozen) |
| Status | **FROZEN — OWNER ACCEPTED.** Mechanical freeze closure complete: §0.6 bindings filled, §0.7 OP-1…OP-7 bound, companion corrected, dataset re-verified. ⛔ **Decisive runs remain gated on MERGED custody** (see the Freeze record) — a local commit or open PR is *not* sufficient custody. |
| Authority | Research capital approved 2026-09-01 for C1 + C2 + C3. TREND-003 **HOLD**. |
| Grants | ⛔ Research only. **No** production code, account assignment, Account-5 binding, scheduler change, deployment, PAPER activation, or orders. |
| Companion documents | `NewStrategy_CandidateInventory_2026-09-01` (selection rationale) · `New_Strategy_Business_Logic_Investment_Expert_Review` (economic narrative). Where they differ from this spec, **this spec controls the research**. |

---

# Freeze record

| field | value |
|---|---|
| **Status** | **FROZEN** |
| Owner acceptance | **2026-09-01** (v1.2 accepted; OP-1…OP-7 accepted at proposed defaults) |
| Mechanical freeze closure | **2026-09-01** — §0.6 B-1…B-5 bound · §0.7 OP-1…OP-7 recorded · companion items 4 + 5 applied · dataset re-verified |
| Binding commit for B-1…B-5 | `c674753fc85f029b980cccc480f4108683ebc0e7` |
| **Decisive dataset** | `factor_data.deepen.duckdb` · **678,440,960 B** · `bafc6007f20f6edb8c9fcc7c60b5f77a6d5bb5021a060f8d0bfa7191b768c97a` — re-verified 2026-09-01, digest unchanged |
| Companion (governed) | `docs/design/NewStrategy/NewStrategy_CandidateInventory_2026-09-01_v1_0.md` · sha256 `19d9b6e381b70a1b018a0dcc73c77115d6ccfb03acc3524665bbd3512a29ab20` |

🚨 **NO DECISIVE RESULT HAD BEEN OBSERVED BEFORE THIS FREEZE.** No C1, C2 or C3 decisive run has been
executed. No candidate output of any kind has been generated, inspected, or partially computed. Every
threshold, universe, parameter and acceptance rule above was written with **zero** knowledge of any
outcome.

## Execution-input freeze rule *(owner ruling 2026-09-01 — tightens checklist item 7)*

The research-code commit **may** be stamped at execution qualification (the executable commit may be a
descendant of this custody commit). ⛔ **But the random seed(s) and the decisive parameter artifact
must NOT be first chosen after a run starts.**

Before each candidate begins execution, in this order, and **before any result is read**:

1. materialize the candidate's **complete** parameter/config artifact;
2. freeze all decisive values;
3. freeze the random seed(s);
4. compute the parameter-artifact **SHA-256**;
5. bind the exact research-code commit;
6. verify that commit contains or descends from the accepted research implementation;
7. record all of the above.

⛔ **No post-result seed substitution. No alternate parameter file after observing output.**

## Custody gate

⛔ **Decisive execution may begin only after this package is MERGED to the governed branch** — not on
a local commit, not on an open PR. Otherwise a decisive run could execute against a document that
exists only locally.

⛔ **The decisive result must not influence anything below.** Post-result changes are limited to the
sensitivity analyses each spec names.

**Change summary through v1.2** *(no decisive result has been seen; all changes are pre-registration hardening)*:
R1 C2 signal frozen by inheritance from MF-001 V1 (was undefined) · R2 C2 STOP clause corrected from
an always-firing trigger to a prohibition · R3 C1 stress set widened to all four in-window crises +
leave-one-crisis-out · R4 C1 insured book pinned and adjective criteria converted to owner-bound
numbers · R5 C3 tradability screen and overlap metric frozen · R6 shared statistical / decisive-run
protocol added (§0.5) · R7 inherited-mechanism identity binding table added (§0.6) · owner
parameters extracted from the expert review into §0.7 · portfolio test fully specified.

---

# 0. Dataset identities — measured 2026-09-01, read-only

| store | bytes | sha256 | `sep` coverage | `sf1_fundamentals` |
|---|---|---|---|---|
| **`factor_data.deepen.duckdb`** | 678,440,960 | `bafc6007f20f6edb8c9fcc7c60b5f77a6d5bb5021a060f8d0bfa7191b768c97a` | 13,746,435 rows · **1997-12-31 → 2026-07-02** · **10,492 tickers** | 1,030,903 rows · **9,040 tickers** |
| `factor_data.research.duckdb` | 77,869,056 | `5f6d623d036bd6c5482e5c41bef4f569bdadd04abbb585e18a9560b461db7813` | 656,113 rows · 1997-12-31 → 2026-06-12 · **1,254 tickers** | 204,871 rows · 1,251 tickers |
| `factor_data.duckdb` (live) | 46,936,064 | `25fe2138a5898d1e9665c9506ec5a5ea722956f9ac66de66b8c2c46db55d40a3` | 1997-12-31 → 2026-08-31 · 1,254 tickers | **0 rows** |

⛔ The **live** store is not a research dataset — it is refreshed daily (its digest changed at
06:07 on 2026-09-01) and carries **no SF1**. All three candidates use the **deepen** store, whose
digest is pinned above and must be re-verified before each decisive run.

## 🚨 Two PIT traps, frozen as rules

**Trap 1 — `calendardate` is NOT the observable date.**
`calendardate` is the **fiscal period end** and runs to **2026-12-31**, into the future.
`datekey` is the **filing/availability** date, spanning **2016-01-29 → 2026-07-02**.
Median `datekey − calendardate` = **24 days**, and **46,635 / 1,030,903 rows (4.5%)** have
`calendardate > datekey`.
⇒ **PIT key is `datekey`.** ⛔ Keying on `calendardate` is a look-ahead leak.

**Trap 2 — `MRQ`/`MRT`/`MRY` are restated.**
Dimensions present: `MRT` 228,649 · `ART` 227,666 · `MRQ` 226,435 · `ARQ` 225,884 · `ARY` · `MRY`.
`MR*` = **Most-Recent-Reported** (restated with hindsight). `AR*` = **As-Reported**.
⇒ **C2 freezes `dimension ∈ {ARQ, ART}`.** ⛔ `MR*` silently embeds restatements that were not
knowable at the time.

⇒ **The true C2 PIT floor is `datekey` 2016-01-29** — not "2016Q1" as a calendar label.

**PIT usage rule (all candidates):** a fundamental row becomes usable at the **first rebalance
strictly after its `datekey`**, never intraperiod and never at `calendardate`.

---

## 0.5 Shared statistical and decisive-run protocol *(added v1.1 — R6)*

Applies to every decisive run and every CI stated in this document.

1. **Estimator.** ΔSharpe confidence intervals are computed with the **same estimator family used by
   the prior registered programs** (the one that produced LOW-001's H1 [−0.029, +0.53] and MF-001's
   [−0.35, +0.48]) so results are comparable across programs: **95% two-sided**, autocorrelation-robust
   (stationary block bootstrap on the daily/period return differential; block length and bootstrap
   count fixed in code before the run). The exact implementation is pinned in §0.6 and its identity is
   recorded in the result artifact.
2. **Reproducibility.** Every decisive run records: dataset path + re-verified sha256 · research-code
   commit SHA · random seeds · parameter file hash. A result whose inputs cannot be re-identified is
   not evidence.
3. **One decisive run per candidate.** Each candidate gets **one** decisive run against its frozen
   design; the result is recorded in the trial ledger **whatever it is**. A rerun is permitted only
   for a **documented pipeline defect** (code bug, dataset fault) with a written defect record filed
   *before* the rerun; ⛔ result-motivated reruns are prohibited (the GAPPER lesson — no tuning,
   rescue, or same-evidence rerun).
4. **Multiple-comparison disclosure.** Three decisive tests run in this family. They test **three
   economically distinct hypotheses** and each stands or falls alone, so no cross-candidate
   correction is applied to individual verdicts — but the disclosure is recorded here prospectively,
   and the **promotion** decision (Lane 7) must weigh that three shots were taken. Within each
   candidate, only the named primary metrics decide PASS/REVISE/REJECT; every other computed number
   is diagnostic.
5. **Sensitivities are not verdicts.** Allowed sensitivity analyses run alongside the decisive run;
   they inform robustness language but cannot flip a REJECT to PASS.

## 0.6 Inherited-mechanism identity binding *(added v1.1 — R7)*

A spec that reuses a "frozen" definition must pin **what** is frozen. ⛔ No decisive run until every
row carries an artifact reference + SHA-256, owner-accepted. Prose inheritance ("unchanged") without
identity is not a binding.

| # | inherited definition | consumer | artifact reference | sha256 |
|---|---|---|---|---|
| B-1 | CAP-020 200d-trend gross de-risk mechanism | C1 | `apps/backend/scripts/cap020_regime_validation.py` (19,961 B) | `8890c4bebb8c1707d6f455282ece3a70ca2d7b50cdc8bac229dd2ca10ccfd2cb` |
| B-2a | MF-001 V1 value + quality **factor definitions** (`SF1_VALUE_FACTORS`, `SF1_QUALITY_FACTORS`) | C2 | `apps/backend/app/factor_data/factors/sf1.py` (3,331 B) | `2563518759d57c5e98299174330fc3aee38ca24e5f363b075b1ac6cd873bd62e` |
| B-2b | MF-001 V1 **combination + ranking rule** (equal-weight z-score means of VALUE / QUALITY / `multifactor`) as run in the P14 retest | C2 | `apps/backend/scripts/multifactor_retest.py` (13,422 B) | `6caa411b010e47b5587b6d728fce8e36554dc2eeef34d052be8439b2b8e48a60` |
| B-3 | LOW-001 frozen signal definition — `LOW_001 = ProgramSpec(factor="low_vol", factor_params={"lookback_days": 252}, n=200, construction="quantile", top_quantile=0.20, weighting="equal_weight", baseline="equal_weight")` | C3 | `apps/backend/app/research/factor_lab/configs.py` (10,417 B) | `65521ae18014d0c5a588a56ffd72b3e7bbea615b67984e2218ab815f21922212` |
| B-4 | ΔSharpe CI estimator (§0.5.1) — `paired_sharpe_diff_ci`, circular-block paired bootstrap, 95% percentile, explicit `seed` | all | `apps/backend/app/factor_data/evidence.py` (14,448 B) | `aa050f84293368ad55c494bc1fa1a8fb487726ac55963792b19e4c122f1a8bfb` |
| B-5 | MOM-001 registered construction — survivorship-free weekly cross-sectional 12-1 momentum, long-only equal-weight top quintile, weights applied next trading day (owner-locked 2026-06-14, P9 §3) | C1 | `apps/backend/app/factor_data/backtest.py` → `run_momentum_backtest` (29,396 B) | `f02a90fa5c56d14990868bfd2d618d46e1e9141760a477142e838ef3ad4eb42f` |

**Binding commit:** `c674753fc85f029b980cccc480f4108683ebc0e7` (`origin/main`, 2026-09-01). All six
blob digests were computed from that commit, not from a working tree.

**BINDING CLOSURE — B-1…B-5 COMPLETE 2026-09-01. No candidate is stopped for a binding gap.**

⭐⭐ **B-4 provenance, verified rather than assumed.** §0.5.1 requires the *same estimator family*
that produced LOW-001's `[−0.029, +0.53]` and MF-001's `[−0.35, +0.48]`. Checked: LOW-001 ran through
`factor_lab/runner.py`, which calls `ev.paired_sharpe_diff_ci(...)`; `runner.py`'s own header
describes it as *"the **promoted** `paired_sharpe_diff_ci`"*, and `multifactor_retest.py` carries the
precursor local implementation (circular block, `block=21`, paired indices, seeded) from which it was
promoted. ⇒ One estimator family, genuinely shared. ⛔ Had these been two divergent implementations
it would have been a binding gap, not a naming detail.

⚠ **B-2 is bound as a PAIR.** The factor *definitions* (B-2a) and the *combination/ranking rule*
(B-2b) live in different artifacts; binding only the first would leave the decisive part of the
signal unpinned.

## 0.7 Owner parameters — bind before any decisive run *(added v1.1 — R4; extracted from the expert review's questions)*

These are economic judgments, not statistics; the expert review poses them to the owner. Each needs
a bound value **before** the affected decisive run so the test remains prospective. Proposed
defaults are stated; the owner may change them **only before** the run.

| # | parameter | consumer | proposed default |
|---|---|---|---|
| OP-1 | Max acceptable calm/bull-regime CAGR drag (insurance carry) | C1 | **≤ 1.5 pp/yr** averaged over non-stress regimes |
| OP-2 | Min stress-regime MaxDD reduction for PASS | C1 | **≥ 8 pp** in at least 3 of the 4 named crises, none worsened |
| OP-3 | Min worst-month / CVaR-5% improvement | C1 | worst month improved **≥ 2 pp**; CVaR-5% improved, sign consistent across crises |
| OP-4 | De-risk depth evaluated | C1 | the CAP-020 mechanism's own frozen depth (B-1); depth is **not** swept as a decisive dimension, only as a named sensitivity |
| OP-5 | Corr threshold defining "decisive diversification" | C2 | **< 0.3** (as v1.0) vs both Strategy 8 and Range Trader |
| OP-6 | C3 tradability screen (part of the frozen universe) | C3 | common stock / primary listing only · close ≥ **$5** · 63-day median dollar ADV ≥ **$2M**, all measured PIT at each rebalance |
| OP-7 | Portfolio combination scheme for the incremental test | all | **equal-capital** sleeves at each rebalance (simple, declared; risk-parity is a named sensitivity, not the decisive scheme) |

**OWNER RULING 2026-09-01:** OP-1 through OP-7 are **ACCEPTED AND FROZEN at the proposed defaults above**. They may not be changed after any decisive result is observed.

---

# C1 — FI-003 / CAP-022 crash-insurance overlay

**Hypothesis.** The 200-day-trend gross de-risk overlay is worthwhile **as insurance** — it buys
stress-regime tail protection at an acceptable calm-market carry — even though it was already
rejected as a Calmar/Sharpe/return improver.

| element | frozen value |
|---|---|
| dataset | `factor_data.deepen.duckdb` @ `bafc6007…` |
| window | 1997-12-31 → 2026-07-02 (full store) |
| **insured book** *(v1.1 — R4)* | primary: the **MOM-001-style ranked book built by its registered construction (B-5), unchanged**; secondary/diagnostic: the equal-weight universe book. ⛔ The insured book may not be chosen or adjusted after results. |
| **stress regimes** *(v1.1 — R3)* | **all four in-window major drawdowns, named in advance:** **2000–2002 dot-com**, **2008–2009 GFC**, **2020 COVID**, **2022 drawdown** (peak/trough dates fixed in the parameter file before the run) |
| mechanism | the **existing** CAP-020 200d-trend gross de-risk, **unchanged** (B-1) — applying it to the pre-2016 portion of the window is in-scope *data*, not a mechanism change |
| primitives | `apps/backend/scripts/cap020_regime_validation.py` @ B-1 |
| benchmark | the same insured book **without** the overlay |
| costs | realistic; escalation sweep required |

**Primary metrics.** Per-crisis **MaxDD reduction** · **CVaR-5%** and **worst-month** improvement ·
calm/bull **CAGR drag** (cost-of-carry) · regime-timing **false-positive / false-negative** rates ·
**leave-one-crisis-out** stability.

**PASS** — all of *(thresholds per OP-1…OP-4, bound before the run)*: stress-regime DD reduction
meets OP-2 · worst-month/CVaR improvement meets OP-3 · calm-regime carry within OP-1 · net benefit
sign preserved across the trend-window neighbourhood sweep **and** when each named crisis is
excluded one at a time *(this operationalizes "no curve-fit timing" — v1.1)*.

**REJECT** — carry exceeds OP-1 for the achieved protection, **or** the benefit disappears when any
single crisis is excluded, **or** the benefit's sign flips inside the trend-window neighbourhood.

⛔ **Do NOT reject merely because standalone Sharpe or CAGR declines. Insurance is allowed to cost
carry.** ⛔ Calmar and Sharpe are **not** the acceptance criteria — judging it that way is the error
already made once.

**Allowed sensitivities:** trend-window neighbourhood, cost escalation, stress-window boundary
perturbation (±1 month), overlay aggressiveness (OP-4 sensitivity only). **Prohibited:** re-tuning
the trend window to improve the headline; adding regime features; changing the insured book;
changing acceptance metrics or OP values after seeing results.

---

# C2 — MF-001 V2 value + quality

**Hypothesis.** A value+quality book is an **independent** return source worth its own sleeve —
either standalone credible, or decisively portfolio-improving.

| element | frozen value |
|---|---|
| dataset | `factor_data.deepen.duckdb` @ `bafc6007…`, `sf1_fundamentals` |
| **PIT key** | **`datekey`** ⛔ never `calendardate`; usable at the first rebalance strictly after `datekey` (§0 usage rule) |
| **dimension** | **`ARQ` / `ART` only** ⛔ never `MRQ`/`MRT`/`MRY` |
| **PIT floor** | **`datekey` ≥ 2016-01-29** — hard boundary |
| window | 2016-01-29 → 2026-07-02 (**~10.4 years — a limitation to REPORT, not hide**) |
| **signal** *(v1.1 — R1)* | **MF-001 V1's registered value and quality definitions, combination rule and ranking, unchanged (B-2).** V2 varies **only** dataset depth, universe, window and validation structure. ⛔ No new ratios, no reweighting, no metric substitution — a metric change is a different candidate and needs its own pre-registration. |
| universe | SF1-covered names within the deepen store (9,040 SF1 tickers), frozen before results |
| book construction | V1's registered book size, weighting and rebalance cadence, unchanged (B-2) |
| structure | train / validation / OOS split **inside** the available window + walk-forward |
| benchmark | equal-weight **and** momentum |
| costs | realistic, with escalation sweep |

**Primary metrics.** ΔSharpe vs equal-weight and vs momentum, **with CI (§0.5)** · correlation to
**Strategy 8 (low-vol)** and **Range Trader** · incremental portfolio effect under OP-7 ·
walk-forward stability · factor and sector concentration · turnover and cost sensitivity.

**PASS** — ΔSharpe CI **excludes zero**, **or** decisive diversification (drawdown reduction with
corr < OP-5 **and** portfolio ΔSharpe CI under OP-7 excluding zero).

**REVISE** — directionally positive but under-powered on the ~10.4-year window.
**REJECT** — reproduces the +0.04 result with a CI spanning zero **and** no portfolio benefit.

**History boundary** *(v1.1 — R2, replaces the v1.0 STOP clause, which as written fired
unconditionally)*: the pre-2016 era is **not PIT-satisfiable in SF1 and is permanently out of scope
for this candidate.** ⛔ **Do not extend the window backward; do not reconstruct or backfill
pre-2016 fundamentals from later-known data.** The shorter history is a **limitation to report**,
not a defect to hide and not a STOP trigger. STOP applies only if the *in-window* data proves
PIT-unsafe (e.g., a discovered `datekey` integrity defect), which would be a dataset defect record
under §0.5.3.

---

# C3 — LOW-002 broader-universe low volatility

**Hypothesis.** LOW-001's near-miss standalone edge — **H1 +0.24, CI [−0.029, +0.53]** — becomes
decisive on a materially wider universe.

| element | frozen value |
|---|---|
| dataset | `factor_data.deepen.duckdb` @ `bafc6007…` |
| **universe** *(v1.1 — R5)* | the deepen store's tickers **passing the OP-6 tradability screen**, evaluated PIT at each rebalance — a materially wider universe than LOW-001's 1,254, frozen **before** any result. The unscreened 10,492-ticker tape is a named sensitivity, ⛔ not the decisive universe: an "edge" that lives only in untradeable microcaps is a data artifact, and screening after results would be tuning. |
| signal | **LOW-001's frozen definition, unchanged (B-3)** — ⛔ no re-tuning of lookback, quantile, or weighting |
| window | 1997-12-31 → 2026-07-02 |
| rebalance | LOW-001 cadence, unchanged |
| benchmark | equal-weight over the same screened universe |
| costs | sweep **through 50 bps** (LOW-001 was cost-robust to 50 bps; the wider book must be too); ADV-scaled cost model as a named sensitivity |

**Primary metrics.** Standalone ΔSharpe vs equal-weight **with CI (§0.5)** · maxDD · Calmar · cost
sweep to 50 bps · rolling / walk-forward stability · **correlation to Strategy 8** · **holdings
overlap with Strategy 8** (metric frozen below).

**Overlap metric** *(v1.1 — R5; classification hardened v1.2)*: weight overlap = Σᵢ min(wᵢ^LOW-002, wᵢ^Strategy-8), computed at
each common rebalance date over the run, reported as the mean; correlation = Pearson on daily book
returns over the common period. **Either** exceeding 0.85 trips the falsifier. For evidentiary precision:
- correlation > 0.85 = **RETURN-REDUNDANCY**;
- mean holdings-weight-overlap > 0.85 = **HOLDINGS-REDUNDANCY**;
- either condition = **SAME-FACTOR REDUNDANCY / NO INDEPENDENT-DIVERSIFICATION CLAIM / NO TUNING AROUND RESULT**.

**PASS** — the standalone result becomes **materially stronger** (H1 CI **excludes zero**) **while
preserving** the defensive drawdown advantage.

**REVISE** — CI still spans zero but the DD advantage strengthens on the wider universe.
**REJECT** — CI spans zero and the DD advantage does not improve.

## 🚨 Pre-registered falsifier — frozen

```
IF correlation with Strategy 8 EXCEEDS 0.85
THEN record RETURN-REDUNDANCY

IF mean holdings-weight-overlap with Strategy 8 EXCEEDS 0.85
THEN record HOLDINGS-REDUNDANCY

IF EITHER condition is true
THEN record MOM-002-style SAME-FACTOR REDUNDANCY
     and NO INDEPENDENT-DIVERSIFICATION CLAIM
     and do NOT tune around it
```

⭐ C3 is funded as a **standalone-alpha** test, **not** as a diversifier. The falsifier can refute it
on redundancy grounds even if the standalone number improves. A redundancy finding with a passing
standalone result is a legitimate recorded outcome — its disposition (whether a stronger same-factor
book should ever *replace* rather than join Strategy 8) is a Lane-7 owner question, ⛔ not something
this research may argue for.

**Allowed sensitivities:** universe-size neighbourhood (screen-threshold perturbation), unscreened
full tape, cost escalation and ADV-scaled costs, rolling windows, start/end perturbation.
**Prohibited:** changing lookback/quantile/weighting; re-cutting the universe after seeing results;
dropping or weakening the overlap test.

---

# Portfolio test — after individual results

For **every** individual survivor, evaluate incremental impact against the currently relevant PAPER
set — **Strategy 8** and **Range Trader** — under the **OP-7 combination scheme**:

total portfolio Sharpe (with CI per §0.5) · maxDD · tail loss (CVaR-5%) · concentration · turnover ·
correlation · capital utilisation.

**"Decisive portfolio improvement" means:** portfolio ΔSharpe CI excludes zero **or** portfolio maxDD
improves with no Sharpe degradation, under OP-7, with the result stable across the walk-forward
segments. *(v1.1 — previously undefined.)*

⛔ **No promotion on standalone Sharpe alone.** A candidate may earn promotion as an
overlay/diversifier even without the highest standalone return — **provided that role was
pre-specified**, which for C1 it is.

---

# Execution boundary

⛔ Research approval authorises **none** of: production strategy code · account assignment ·
Account-5 binding · scheduler changes · deployment · PAPER activation · orders.

⭐ **Account 5's availability is capacity, not a selection criterion.** It must not determine which
candidate wins promotion.

**Separate and non-blocking:** the Strategy-7 retirement-control gap. ⛔ No ad-hoc DB mutation to
manufacture a RETIRED label; Account 5 stays unreclaimed pending a governed control decision. That
blocker does **not** delay C1/C2/C3.

---

# Acceptance checklist for v1.2 — owner accepted, mechanical freeze closure required

1. **Owner acceptance: COMPLETE — 2026-09-01.** v1.2 is the final research specification.
2. Populate §0.6 B-1…B-5 with independently identified artifact references + SHA-256 values. ⛔ Do not guess. If an inherited mechanism cannot be bound, STOP that candidate and report the binding gap.
3. Record §0.7 OP-1…OP-7 exactly at the owner-accepted defaults.
4. Update the companion candidate inventory in two places: `2016Q1` → **`datekey ≥ 2016-01-29`**, and align its C2 history/STOP wording with the R2 correction.
5. Apply the v1.2 C3 redundancy classification: correlation >0.85 = RETURN-REDUNDANCY; holdings overlap >0.85 = HOLDINGS-REDUNDANCY; either = SAME-FACTOR REDUNDANCY.
6. Re-verify the pinned `factor_data.deepen.duckdb` SHA-256 immediately before each decisive run.
7. Record exact research-code commit SHA, random seeds, parameter-file hash, and final frozen-spec SHA-256.
8. Commit/custody the frozen specification **before** any decisive execution and record the freeze timestamp.
9. Then, and only then, classify: **NEW-STRATEGY PRE-REGISTRATION = FROZEN / DECISIVE RESEARCH AUTHORIZED.**
10. Run C1/C2/C3 independently; parallel execution is allowed where compute/data access does not create shared mutation. Each receives exactly one decisive run under §0.5.
11. Return one comparative adjudication package: C1/C2/C3 PASS|REVISE|REJECT; frozen spec/dataset/code identities; primary result + CI; costs; walk-forward/regime stability; falsifiers; portfolio incremental effect; and implementation-capital recommendation. Rank survivors as **#1 PAPER PROMOTION CANDIDATE / #2 NEXT / #3 RESEARCH-ONLY, REVISE, OR REJECT**.
12. ⛔ A research PASS creates **no** production implementation, account binding, scheduler, deployment, PAPER activation, or order authority. Promotion requires a separate owner ruling.
