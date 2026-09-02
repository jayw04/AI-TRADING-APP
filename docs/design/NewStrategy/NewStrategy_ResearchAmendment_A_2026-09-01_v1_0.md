# NewStrategy research amendment A — executable history, C2 conformance, C3 OP-6 binding, C1 crisis rule

| Field | Value |
|---|---|
| Version | **v1.0 — DRAFT FOR OWNER RULING** (items marked ⏳ need an explicit owner decision before this document is accepted) |
| Amends | `NewStrategy_FrozenResearchSpecs_2026-09-01_v1_2_FINAL.md` — sha256 `47a2e26201b6c68ab8105ee08f0169fe64cdd3bca67f63d864b4efa85af34998` (25,279 B), custodied #721, merge `26cf4627e1a7745d65d0f4ad02389bbe873341d9` |
| Scope | **Narrow.** Executable-history boundary · dataset defects · C2 actual-vs-nominal window and repair · C2 acceptance-leg coverage · C3 OP-6 implementation binding and universe-provider seam · C1 unreachable crisis criterion and adjudication options · updated execution-input identities |
| Does NOT change | economic hypotheses · OP-1…OP-7 values · ranking rules · `seed=17` · `n_resamples=2000` · `block=21` · crisis dates · signals · cost assumptions · PASS/REVISE/REJECT thresholds. The single exception — C1's unreachable OP-2 criterion — is presented as **options**, not decided here (§5.4). |
| Authority basis | Owner rulings of 2026-09-01: window/execution ruling (20:18Z) and conformance ruling (20:30Z) |
| Companion evidence | S3 `workbench-backups-219024422756` prefix `research/newstrategy/2026-09-01/evidence/` — every object pinned by VersionId + SHA-256 in §2.3 and §3.5 |

⛔ **Execution boundary unchanged.** Nothing here authorizes production code, account assignment, Account-5 binding, scheduler change, deployment, PAPER activation, or orders. A research PASS remains evidence for a later promotion decision only.

---

## 1. Executable-history boundary — ACCEPTED

```
NEW-STRATEGY EXECUTABLE-HISTORY BOUNDARY = [ 2017-01-06 .. 2026-06-12 ]
= MECHANICALLY DERIVED = RETURN-BLIND = COMMON TO C1/C2/C3 = ACCEPTED (owner, 2026-09-01)
```

**Derivation rule (fixed before any rerun output, with zero reference to candidate returns):** the earliest weekly rebalance after which the bound dataset *continuously* holds at least `DEFAULT_MIN_NAMES = 20` (`app/factor_data/factors/engine.py`) PIT-eligible names under the `dollar_volume_universe` lifetime-straddle predicate, through the last rebalance that still does. A stricter factor-readiness tier (names listed ≥ 380 calendar days, covering the longest bound lookback, `low_vol` 252) yields the identical floor.

| measure | value |
|---|---|
| weekly rebalances in the frozen 1997-12-31 → 2026-07-02 span | 1,489 |
| conformant rebalances inside the boundary | **493 of 493** (0 sub-threshold) |
| boundary length | ≈ 9.43 years |
| eligible universe at 2016-12-30 → 2017-01-06 | **4 → 5,116** names |
| eligible universe at 2026-06-12 → 2026-06-18 | **5,628 → 0** names |

The boundary applies to all three candidates. SF1 `datekey` coverage is 88–97 % of the eligible universe throughout 2017+, so C2 is not further constrained. Where a candidate's own lookback needs warm-up inside the boundary (C1 momentum 252+21 d, C3 `low_vol` 252 d), the bound mechanism skips unavailable rebalances; it does not pad or backfill.

## 2. Dataset defects — source-data facts, not strategy outcomes

The pinned dataset (`factor_data.deepen.duckdb`, 678,440,960 B, `bafc6007…`) is **authentic and byte-identical to the pin**. Byte identity proves custody, not fitness. Two independent defects:

### 2.1 `SEP-PRE2017-INGESTION-DEFECT-001`
1997-12-31 → 2016-12-30 is a **five-name tape** (NVDA, AAPL, MSFT, KO, CBNJ2; ~1,008 rows/yr = 4 × 252). Breadth jumps **1,279×** in one week at 2017-01-06. Decisive proof that this is incompleteness rather than historical scope: **`sf1_fundamentals` holds 4,804 tickers in 2016 while `sep` holds 4**. Two tables in the same store disagree about whether 2016 exists; fundamentals were ingested to 2016 depth, prices were not. The defect is confined to the SEP price ingest.

### 2.2 `TICKERS-LASTPRICEDATE-STALE-001`
`tickers.lastpricedate` maxes at **2026-06-12** while `sep.date` and `sf1.datekey` reach 2026-07-02. The PIT straddle predicate therefore returns **0 names** for the three rebalances after 2026-06-12, failing silently as an empty universe rather than raising. The frozen `end: 2026-07-02` is unreachable as a rebalance date; the bound simulator holds the last conformant weights through 2026-07-02 without rebalancing.

### 2.3 Conformance evidence
`conformance_series.json` — 1,489 rows `[rebalance_date, eligible_names, factor_ready_names]` — 35,716 B, sha256 `a7006f136b885430baa31185cf79e9fec2f00b0b86ba3582b817f6eed78e481e`, S3 key `research/newstrategy/2026-09-01/evidence/conformance_series.json`, VersionId `ZBtcADpoy6stX.JmHJW4egPuuFcp3P5K`.

## 3. C2 — MF-001 V2

### 3.1 Decisive execution of record (retained)

| identity | value |
|---|---|
| experiment | `EXP-20260901-184340-sf1mf`, started 2026-09-01T18:43:38Z, 401.2 s, exit 0 |
| research code | `26cf4627e1a7745d65d0f4ad02389bbe873341d9` (clean detached worktree, 0 dirty paths) |
| parameter artifact | `params/C2_value_quality.json` sha256 `45e943436c5b6a60b3f58d83eb7675f6f279929fdfbfb7f29f95f234b493520a` — **unchanged by this amendment** |
| dataset | `bafc6007…`, opened `read_only=True` |
| seed / resamples / block | 17 / 2000 / 21 (inherited registered values) |
| result artifact | `C2/multifactor_retest.json` 2,747 B sha256 `492b1a54…` (§3.5) |

| book | CAGR | Sharpe | maxDD | Calmar |
|---|---|---|---|---|
| momentum (v1.1 base) | +18.81 % | 0.69 | −51.9 % | 0.36 |
| multifactor (B-2b composite) | +15.33 % | 0.76 | −40.3 % | 0.38 |

**ΔSharpe +0.065 · paired 95 % CI [−0.874, +0.976] · walk-forward 3/5** · corr(momentum, value) −0.086 · corr(momentum, quality) +0.006 over 107 monthly cross-sections. These are the decisive economic numbers of record.

Disclosure, no change: the B-2b composite (`scripts/multifactor_retest.py`, `ALL = ["momentum", *VALUE, *QUALITY]`) is an equal-weight z-score mean of **momentum, four value and four quality** factors. The spec's shorthand "value + quality" denotes this inherited MF-001 composite; the signal is exactly the bound one.

### 3.2 Nominal window ≠ actually evaluated curve

| | start | end | points |
|---|---|---|---|
| nominal window (artifact `window`) | 2016-01-29 | 2026-07-02 | — |
| momentum equity curve | **2017-07-10** | 2026-07-02 | 2,258 |
| multifactor equity curve | **2017-01-09** | 2026-07-02 | 2,383 |
| skipped thin rebalances | momentum 78 · multifactor 52 (all pre-2017 plus the 3 terminal ones) | | |

`_simulate` builds segments only after successful rebalances and `_summary` measures from the first curve point, so **no five-name cross-section entered either book**. The earlier working claim that walk-forward window 1 consumed the defective tape is **withdrawn**.

### 3.3 Classifications (owner, 2026-09-01)

| id | classification |
|---|---|
| `C2-HISTORY-WINDOW-CONFORMANCE-001` | **CLOSED** — defective source history existed; defective rebalances skipped by the bound mechanism; actual evaluated curve conformant |
| `C2-WINDOW-METADATA-001` | **CONFIRMED** — reported window ≠ actual curve window; reporting / conformance-observability defect |
| `C2-DATASET-HEALTH-GATE-001` | **CONFIRMED** — `dataset_health_ok = True` was a false pass; surfaced neither §2.1 nor §2.2 |
| `C2-ACCEPTANCE-COVERAGE-001` | **CONFIRMED** — decisive-executable coverage defect; the artifact persisted no return/equity series, so corr vs Strategy 8, corr vs Range Trader and the OP-7 portfolio effect were uncomputable from it |

### 3.4 Prohibitions — permanent for C2

⛔ **NO window recut. NO walk-forward re-slicing. NO rerun to improve or rebalance the 3/5 count.** The slices were formed from the nominal calendar window (`_window_bounds`, 5 equal calendar spans) while the curve begins later, so window 1 (`2016-01-29..2018-02-28`, ΔSharpe −0.668) holds roughly 56 % of the curve length of windows 2–4 and is counted with equal weight. This is a **disclosed methodology/reporting limitation** of the retained result, not a defect to repair. Because that slice is also the worst-performing one, changing the segmentation after observation would be post-result methodological change.

| walk-forward window | momentum Sharpe | multifactor Sharpe | ΔSharpe |
|---|---|---|---|
| 2016-01-29..2018-02-28 | 2.10 | 1.43 | −0.668 |
| 2018-02-28..2020-03-30 | −0.03 | −0.11 | −0.082 |
| 2020-03-30..2022-04-30 | 0.96 | 1.31 | +0.358 |
| 2022-04-30..2024-05-30 | 0.82 | 0.96 | +0.141 |
| 2024-05-30..2026-07-02 | 0.87 | 1.13 | +0.262 |

### 3.5 Artifact-completeness re-execution — AUTHORIZED, EXECUTED, REPRODUCTION GATE PASSED

One re-execution was authorized solely to persist the missing series. Method: the bound script `scripts/multifactor_retest.py` (B-2b, `6caa411b…`) was **imported as a module** and its own `_backtest_pair`, `_paired_sharpe_diff_ci` and `_window_bounds` were called with byte-identical inputs (same store, `2016-01-29..2026-07-02`, `n=200`, 5 windows, 2000 resamples, seed 17). Nothing was reimplemented; no window, threshold, parameter or result-dependent branch changed.

**Reproduction gate: 18/18 primary outputs identical at full float precision** — ΔSharpe, CI low/high/delta, walk-forward 3/5, all eight book metrics, all five window ΔSharpe values. `DETERMINISTIC REPRODUCTION CONFIRMED` — the series are admissible. The prior numerical result remains the decisive economic result.

| file | bytes | sha256 | S3 VersionId (prefix `research/newstrategy/2026-09-01/evidence/`) |
|---|---|---|---|
| `C2/multifactor_retest.json` (original) | 2,747 | `492b1a543ea4d301f3e149e0f8d16c5f145483d37b2c72096f4994ef175095b5` | `MIe_sutoQwPcWco6rDIEIV0u9rRDQM4Z` |
| `C2/multifactor_retest.md` | 1,722 | `2ed7c0e493b10b234f2618dff6e2ce23849463f19917f5c82bc9027ef3a093ac` | `GnkXoMvPduDTgqWpKpfZvItmfsjwkpJr` |
| `C2/run.log` | 1,302 | `135771a65875552276db5f824c7b99c5573548a015dfcdae804928cfe22ffba3` | `8ZfVioX5Sk56TcQemsG7B5Bv5FQObU8j` |
| `C2_repair/c2_repair_driver.py` | 4,079 | `a6dd8f951fc731ac586683ad933d8ba578dba5b9900246b993de8bcf0939638e` | `Zl82floKFqJY6xblGmVvXf2xHfFzPSwA` |
| `C2_repair/c2_reproduced_primary.json` | 1,475 | `15ea6c0546bcfa23987a43c1db13efae13683e3b42c411863e6b13656043fc0e` | `.H13dnxu9633vWtirBl5WZU9xSOMmwQT` |
| `C2_repair/c2_curve_metadata.json` | 250 | `67b37551de580a7848e30d061192e876ad48094bab20b715af62daad9cf43d70` | `KMSdLLd5TqxZ75kpvHgwnB_6AdgWki6O` |
| **`C2_repair/c2_series.json`** (equity curves + daily returns, both books + baseline) | 350,429 | `99570acf84c83d4119cd2b9ce64976468f7d7e46cef5dfb25d5b0ee457de3f03` | `2_cAdnDOz22CN_zjpAvRjXIbvLfPiecT` |
| `C2_repair/repair.log` | 2,696 | `bd38ff0fffb42722ce5c1fdb182f73ec790831cde4e07538fb471bac755f4c3f` | `Y25pyLzS0KLD9mXpUTeKgSefe_CeIN.f` |
| `C1/run.log` (C1 execution defect record, §5.1) | 2,432 | `395e44f59914ea61682d0e8bf7e0c3a30edef4c27a97bb2dbc804715f76cb3bd` | `8gj5aJ76FLnf34Kl0MqwdU.pfWvI0Xsl` |

Bucket: versioning Enabled, SSE-S3 AES256, all four public-access blocks true; every object written once under a unique key, none overwritten.

### 3.6 ⏳ `C2-PAIRED-ALIGNMENT-001` — NEW, exposed by the persisted series, OPEN

The bound estimator `_paired_sharpe_diff_ci` (and the promoted B-4 `paired_sharpe_diff_ci`, identical logic) computes `n = min(len(a), len(b))` and slices **positionally**: `a[:n]`, `b[:n]`. Its docstring premise is that both inputs are *aligned* daily-return series so that a shared block index preserves the common market move.

For this execution the inputs were **not date-aligned**: momentum's first return is dated 2017-07-11, multifactor's 2017-01-10. Positional pairing therefore matched each momentum return against a multifactor return **125 trading days earlier**, and **discarded multifactor's final 125 observations**. The point estimate `ΔSharpe +0.065` (from `_curve_stats` on the full, unequal curves: 9.0 y vs 9.5 y) and the CI (from the mis-paired slices) rest on that premise failure. Destroying the pairing removes the common-market cancellation the paired block bootstrap exists for — a credible **mechanism**, not a measured cause, for a CI 1.85 Sharpe units wide.

Classification proposed: `C2-PAIRED-ALIGNMENT-001 = CONFIRMED / ESTIMATOR-INPUT PRECONDITION VIOLATED / NOT A DATA OR WINDOW DEFECT / NO RERUN FIXES IT`. The defect is in the bound B-2b script's call path (it feeds unaligned series to a positional estimator); B-4's implementation is faithful to its documented precondition.

**No date-aligned comparison has been computed.** Doing so produces a competing primary statistic, which the freeze forbids without authority. ⏳ **Owner ruling required — choose one:**

- **(i)** authorize a **date-aligned diagnostic** — intersect the two return series on common dates (2017-07-11..2026-07-02, both books), recompute ΔSharpe and the paired CI with the same B-4 estimator, seed, resamples and block — recorded as **diagnostic, not a verdict** — and adjudicate C2 only after seeing whether the primary leg is materially affected;
- **(ii)** retain the mis-paired statistic as the decisive result of record and record the alignment defect as a disclosed limitation;
- **(iii)** classify the C2 primary leg NON-ADJUDICABLE on estimator-precondition grounds (zero verdict credit), with any corrected first decisive run requiring a repaired executable and a new pre-registration entry.

Developer note, methodology only: option (i) is the only path that lets the owner rule on materiality with evidence; options (ii) and (iii) both decide without it. Nothing about the direction of the diagnostic is known.

### 3.7 ⏳ Comparator legs — no already-frozen comparator series exists

The frozen alternative acceptance clause needs corr(C2, Strategy 8) < 0.3 **and** corr(C2, Range Trader) < 0.3 **and** OP-7 portfolio ΔSharpe CI excluding zero. The owner's preferred path was to compute these mechanically from the C2 series and *already-frozen* comparator series. Read-only search result:

| comparator | frozen historical series available? | evidence |
|---|---|---|
| **Strategy 8** (LOW-001; live template `low_volatility.py` = `universe_asof(n=200)`, 252 d vol, top quintile 0.20, equal weight, weekly — identical to B-3) | **NO.** The LOW-001 evidence package `docs/implementation/evidence/low_001_low_volatility/low_volatility.json` (S3, sha256 `a426ff54…`, 2,839 B) is scalars only — no equity curve, no returns. Live PAPER equity begins 2026-08-12; the C2 curve ends 2026-07-02 → **zero overlap**. | same coverage-defect class as `C2-ACCEPTANCE-COVERAGE-001` |
| **Range Trader** (intraday opening-range, 5-min bars) | **NO.** No historical daily-return series exists at any horizon comparable to C2; its §5c backtests are intraday IS/OOS windows. Live PAPER history begins 2026-06-24 → **7 trading days** overlap with the C2 curve. | structurally not evaluable against a 2017–2026 curve |

Classification proposed: `C2-COMPARATOR-SERIES-001 = NO ALREADY-FROZEN COMPARATOR SERIES FOR EITHER LEG`. ⏳ **Owner ruling required — choose one:**

- **(a)** adjudicate C2 on the primary leg alone; classify the alternative (diversification) clause **NOT EVALUABLE** for this program and record the limitation. Under the retained numbers this yields the indicated **REVISE** (directionally positive, under-powered, CI spans zero; REJECT is not established because "no portfolio benefit" was never evaluable);
- **(b)** authorize a **LOW-001 artifact-completeness re-execution** — the B-3 definition at its own experiment identity (`EXP-20260622-013311-low001`, git `dded451`, research store `5f6d623d…`, window 2000-01-01..2026-06-12) with the same reproduction-gate discipline as §3.5 (H1 delta 0.241, CI [−0.029, 0.53], four book Sharpes must reproduce), to obtain a Strategy-8 comparator series; then compute corr and a **reduced** OP-7 test (Strategy 8 + C2 vs Strategy 8) explicitly labelled partial because the Range Trader leg cannot exist. Requires transferring the pinned research store (77,869,056 B) the same way the deepen store was;
- **(c)** hold C2's final verdict until a Range Trader comparator exists (not foreseeable on any historical basis).

Developer note: (b) is mechanically clean but adds a second re-execution program; (a) is the only option that closes C2 now. Neither is chosen here. ⛔ Under no option may factor-vs-factor correlations (−0.086 / +0.006) stand in for correlation to the live strategies.

### 3.8 C2 current status

```
C2 = PRIMARY DECISIVE RESULT RETAINED = DATA-CONFORMANT = WINDOW METADATA DEFECT RECORDED
   = WALK-FORWARD METHODOLOGY DISCLOSED = ARTIFACT-COMPLETENESS REPAIR EXECUTED (18/18)
   = PAIRED-ALIGNMENT DEFECT OPEN (§3.6) = COMPARATOR LEGS NOT COMPUTABLE FROM FROZEN SERIES (§3.7)
   = FINAL VERDICT HELD
```

REVISE remains the indicated primary-leg disposition. ⛔ Not final until §3.6 and §3.7 are ruled.

## 4. C3 — LOW-002: OP-6 implementation binding and universe-provider seam

### 4.1 Implementation (owner design rulings 2026-09-01 §8–§10 applied)

| item | value |
|---|---|
| branch / commit | `feat/c3-op6-universe-provider` @ `ec8c33540cf3608883f0a7e1f070e6c30cd2fad5` (based on `origin/main` `980ceb74`; all six §0.6 bindings re-verified byte-identical there) |
| OP-6 module | `apps/backend/app/research/factor_lab/op6_universe.py` — 4,004 B — sha256 `7c1db96462e529aea27a5a7dea344c37712fe7419fe1ee15fd45bff45754dd71` |
| seam | `apps/backend/app/factor_data/backtest.py` — 29,944 B — sha256 `bfc8ccb705b80ae98d1ac7bdfb474c8fdc6619bf30eabd5417f7d03153b4ba3e` (`run_momentum_backtest(..., universe_fn=None)`; 9 added lines, 1 changed) |
| tests | `apps/backend/tests/factor_data/test_op6_universe.py` — 7,591 B — sha256 `4645f6b510d06dc63010ca14ef8ef98d3247da09027ee76c123677ee177d4da8` — 15 tests |
| pre-seam B-5 | `backtest.py` `f02a90fa…` (29,396 B) remains the bound MOM-001 construction; `universe_fn=None` reproduces it exactly (asserted by curve equality, not inspection) |

**OP-6 predicate, PIT at each rebalance:** lifetime straddle `firstpricedate <= as_of <= lastpricedate` (mirrors `dollar_volume_universe`, survivorship-free) · `tickers.category IN ('Domestic Common Stock', 'Domestic Common Stock Primary Class')` · `exchange <> 'OTC'` · last traded **`closeunadj` on/before `as_of` ≥ $5** · **median(`close × volume`) over the trailing 63 calendar days ≥ $2,000,000**.

**Price-field asymmetry, declared and intentional (owner §10):** the $5 floor uses `closeunadj` — the actually-traded nominal price, which is the investability question; ADV keeps the **existing governed** `close × volume` convention inherited verbatim from `dollar_volume_universe` (inspected and confirmed), preserving ADV comparability rather than redesigning it.

**Invariant (owner §8):** the same `op6_universe_asof` provider is passed as `universe_fn` (equal-weight benchmark) and consumed by the `low_vol` `score_fn` (book): `C3 STRATEGY UNIVERSE == C3 BENCHMARK UNIVERSE == OP-6 SCREENED UNIVERSE`. ⛔ No runtime replacement of imported `universe_asof` symbols anywhere.

### 4.2 Validation (local, 2026-09-01)

`ruff check` clean · `mypy` clean on both modules · **15/15** OP-6 tests pass, including the falsifying field-semantics test (`SPLITLOW` adjusted 50 / traded 2 excluded; `SPLITHIGH` adjusted 2 / traded 50 included — both invert if the screen is switched to `close`) · **359** tests pass across `tests/factor_data/` + `tests/universe` (no regression) · research-plane isolation invariant OK (517 modules). `backtest.py` is left `ruff format`-unclean deliberately: it already was at `origin/main` and CI runs no `ruff format`; reformatting would rewrite unrelated code in a bound artifact.

### 4.3 Custody and execution authority

Custody PR: **see §6**. Merge commit and final research-code SHA are stamped at execution qualification per the spec's execution-input freeze rule. The C3 parameter artifact is updated (§6) to carry the OP-6 binding, the seam, the price-field semantics and the executable boundary; signal, acceptance, falsifier and cost sweep are byte-for-byte the frozen values.

```
C3 = NOT EXECUTED = NO RESULT OF ANY KIND GENERATED = COMMON HISTORY BOUNDARY ACCEPTED
   = OP-6 IMPLEMENTED + TESTED + BOUND = EXPLICIT SEAM IMPLEMENTED
   = NO EXECUTION AUTHORITY until the implementation is MERGED and this amendment is ACCEPTED
```

C3's executable window is the §1 boundary; with `low_vol` `lookback_days=252` the first computable rebalance falls ≈ 252 trading days after 2017-01-06, and the unscreened 10,492-ticker tape remains a named sensitivity only.

## 5. C1 — FI-003 / CAP-022 crash insurance

### 5.1 `C1-EXECUTION-DEFECT-001` — CONFIRMED, repairable

Launched 2026-09-01T18:42:29Z at `26cf4627`, frozen window 1997-12-31..2026-07-02, universe 150. All four books computed (`built 2257 days; IS 1354 / OOS 903`); the process died printing the headline line: `UnicodeEncodeError: 'charmap' codec can't encode character 'Δ'` (stdout redirected under cp1252). **No report artifact was written; no overlay result was observed** — only the benchmark row (eqw, overlay OFF, OOS) reached the log. Repair: environment `PYTHONUTF8=1` — changes no logic, data, parameterization, estimator or acceptance rule. ⛔ Not yet applied to a run: C1 must not launch until §5.4 is ruled.

### 5.2 `C1-HISTORY-WINDOW-CONFORMANCE-001` — IDENTIFIED, PRE-RESULT

`built 2257 days` ≈ 9.0 y independently confirms that the frozen 28.5-year window collapsed to the §1 boundary (1,021 of ~1,485 momentum rebalances skipped as thin). C1 has **not spent its decisive economic run** and may receive the amended executable window prospectively.

### 5.3 `C1-CRISIS-ACCEPTANCE-CONFORMANCE-001` — CONFIRMED, FROZEN ACCEPTANCE RULE UNREACHABLE, BLOCKING

All four frozen crisis windows are **retained verbatim** in the parameter artifact. Their evaluability under the conformant price history:

| crisis (frozen peak → trough) | inside boundary | overlap | classification |
|---|---|---|---|
| dotcom 2000-03-24 → 2002-10-09 | no | 0 days | **UNAVAILABLE UNDER CONFORMANT PRICE HISTORY** |
| GFC 2007-10-09 → 2009-03-09 | no | 0 days | **UNAVAILABLE UNDER CONFORMANT PRICE HISTORY** |
| COVID 2020-02-19 → 2020-03-23 | yes | 33 days | **EVALUABLE** |
| 2022 2022-01-03 → 2022-10-12 | yes | 282 days | **EVALUABLE** |

Two independent routes make OP-2 (≥ 8 pp MaxDD reduction in **≥ 3 of 4** crises, none worsened) unreachable: only two crises lie inside any conformant history, **and** the bound B-1 artifact defines `ENVIRONMENTS = {covid_2020, bear_2022, bull_2023_24}` with `BEAR_ENVIRONMENTS = (covid_2020, bear_2022)` — it has no dotcom or GFC environment and could not evaluate them on a complete corpus either. A window amendment alone does not repair this. B-1's own `data_sufficiency` gate additionally requires ≥ 4.0 usable years (met: 9.4), ≥ 4 OOS regime flips (unknown until run) and at least one bear environment present (met).

### 5.4 ⏳ Adjudication options — owner must choose BEFORE any C1 run

Both options preserve the original economic thesis (insurance, not Sharpe); neither may be chosen with reference to C1's unobserved overlay output, and none has been observed.

**Option A — evaluate on the two observable crises; classify the lost evidence HISTORY-LIMITED.**
OP-2 becomes: MaxDD reduction ≥ 8 pp in **both** COVID-2020 and 2022, **neither worsened**. OP-1, OP-3, OP-4 and the leave-one-crisis-out stability test apply unchanged over the two evaluable crises (leave-one-out then has two folds). Dotcom and GFC are recorded as `UNAVAILABLE UNDER CONFORMANT PRICE HISTORY`; the verdict carries the qualifier **HISTORY-LIMITED (2 of 4 pre-registered crises observable)** and cannot claim cross-cycle robustness. The frozen windows stay in the record so a future deeper corpus can extend the same test without re-registration.
*Preserves:* the hypothesis, the mechanism (B-1 unchanged), all thresholds' magnitudes, the falsifiability of the insurance claim. *Costs:* a weaker stability test (two folds) and an explicitly limited external-validity claim.

**Option B — declare C1 NOT EVALUABLE under the present corpus.**
The frozen 3-of-4 requirement cannot be satisfied; C1 is recorded `NOT EVALUABLE / HISTORY-INSUFFICIENT`, spends no decisive run, and is re-queued behind acquisition of a price corpus with genuine pre-2017 breadth. No number is produced.
*Preserves:* the exact frozen acceptance rule. *Costs:* forgoes the one insurance test the platform has never run, on the two most recent crises it can observe.

Developer note, methodology only: Option A is a pre-registered *narrowing* of the evidence base with an explicit qualifier, made before any output exists; Option B is the strict reading. Either is defensible; a hybrid that runs Option A and later reinterprets it as B (or vice versa) after seeing results is not. Whichever is chosen must be written into `params/C1_crash_insurance.json` and this amendment **before** `PYTHONUTF8=1` is set and C1 is launched.

```
C1 = NO DECISIVE RESULT OBSERVED = ENCODING DEFECT REPAIRABLE (PYTHONUTF8=1)
   = HISTORY CONFORMANT FROM 2017-01-06 = CRISIS ACCEPTANCE RULE UNREACHABLE (OP-2)
   = NO EXECUTION AUTHORITY until §5.4 is ruled
```

## 6. Execution-input identities after this amendment

| artifact | sha256 before | sha256 after | change |
|---|---|---|---|
| `params/C1_crash_insurance.json` | `5b08b7d7e7a646308a58a3f4d736703acc76c20b518bf1d6d7238990b4bd5ad8` | `e0b1142c548aa6cfaaaca82b77a39bb72bb602e8e4e7b25be3f3b59c0501302a` | + executable boundary · + `PYTHONUTF8=1` · + crisis evaluability · + acceptance status note · + execution record. **Acceptance values unchanged**; OP-2 option to be written in after the §5.4 ruling |
| `params/C2_value_quality.json` | `45e943436c5b6a60b3f58d83eb7675f6f279929fdfbfb7f29f95f234b493520a` | **unchanged** (verified `cmp`) | ⛔ must stay byte-identical: it is the input of the retained decisive execution |
| `params/C3_broader_lowvol.json` | `c1a8b15830068093d0d3a79d39e376d57bada9248fcfbe0f06c623ab5932eac5` | `4dcb669235a9a13dc5ff3e1a553c4bd284448bd233805793bb3a9f8939c933fc` | + executable boundary · + OP-6 implementation binding (module/tests SHA, commit) · + seam · + price-field semantics · + execution status. **Signal, acceptance, falsifier, costs unchanged** |
| frozen spec v1.2 FINAL | `47a2e262…` | unchanged | this amendment sits beside it; the spec is not edited |
| bound B-1…B-5 | as §0.6 | unchanged at `980ceb74` (re-verified) | B-5 gains a descendant (§4.1); the pre-seam blob remains the binding |

Custody PRs: C3 implementation — `feat/c3-op6-universe-provider` → **PR #723**; this amendment + params — **this PR (branch `docs/newstrategy-amendment-a`)**.

## 7. Open owner rulings — checklist

1. ⏳ §3.6 `C2-PAIRED-ALIGNMENT-001`: (i) authorize the date-aligned diagnostic · (ii) retain as-is with disclosure · (iii) non-adjudicable.
2. ⏳ §3.7 `C2-COMPARATOR-SERIES-001`: (a) adjudicate on the primary leg, alternative clause NOT EVALUABLE · (b) authorize the LOW-001 artifact-completeness re-execution + reduced OP-7 test · (c) hold.
3. ⏳ §5.4 C1 crisis rule: Option A (two observable crises, HISTORY-LIMITED) or Option B (NOT EVALUABLE).
4. Accept §1–§2 as recorded (already ruled 2026-09-01; recorded here for custody).
5. Accept §4 C3 binding; merge the implementation PR; then classify `C3 = EXECUTION AUTHORIZED` under the §1 boundary.
6. Accept this amendment for merge; on merge, record its final sha256 and the merge commit in the trial ledger.

## 8. What this amendment did not do

No candidate was executed or re-executed after the 2026-09-01 20:30Z ruling except the authorized C2 artifact-completeness repair (§3.5). No date-aligned C2 statistic was computed. No LOW-001 series was generated. No window was recut. No threshold, seed, bootstrap count, block length, crisis date, signal or cost assumption changed. Nothing touched the PAPER host. The primary working tree was not used for any run.
