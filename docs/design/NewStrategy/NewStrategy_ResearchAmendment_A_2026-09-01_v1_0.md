# NewStrategy research amendment A — executable history, C2 conformance, C3 OP-6 binding, C1 crisis rule

| Field | Value |
|---|---|
| Version | **v1.0 — OWNER RULINGS OF 2026-09-01 (§7 rulings 1–3) INCORPORATED — READY FOR CUSTODY** |
| Amends | `NewStrategy_FrozenResearchSpecs_2026-09-01_v1_2_FINAL.md` — sha256 `47a2e26201b6c68ab8105ee08f0169fe64cdd3bca67f63d864b4efa85af34998` (25,279 B), custodied #721, merge `26cf4627e1a7745d65d0f4ad02389bbe873341d9` |
| Scope | **Narrow.** Executable-history boundary · dataset defects · C2 actual-vs-nominal window, repair, alignment defect and comparator availability · C3 OP-6 implementation binding, universe-provider seams and frozen execution package · C1 unreachable crisis criterion and its ruling · updated execution-input identities · program-level consequence |
| Does NOT change | economic hypotheses · OP-1…OP-7 values · ranking rules · `seed=17` · `n_resamples=2000` · `block=21` · crisis dates · signals · cost assumptions · PASS/REVISE/REJECT thresholds. C1's OP-2 is **not weakened** (owner ruling 3): C1 is NOT EVALUABLE instead. |
| Authority basis | Owner rulings of 2026-09-01: window/execution ruling (20:18Z), conformance ruling (20:30Z), amendment §7 rulings 1–3 (evening) |
| Companion evidence | S3 `workbench-backups-219024422756` prefix `research/newstrategy/2026-09-01/evidence/` — every object pinned by VersionId + SHA-256 in §2.3, §3.5 and §3.6 |
| Companion PR | C3 implementation: **PR #723** (`feat/c3-op6-universe-provider`) |

⛔ **Execution boundary unchanged.** Nothing here authorizes production code, account assignment, Account-5 binding, scheduler change, deployment, PAPER activation, or orders. A research PASS remains evidence for a later promotion decision only.

**Tranche state after this amendment**

```
C1 = NOT EVALUABLE / INSUFFICIENT GOVERNED CRISIS HISTORY
C2 = NOT EVALUABLE / PRIMARY ALIGNMENT DEFECT + COMPARATOR EVIDENCE UNAVAILABLE
C3 = PROSPECTIVE DECISIVE CANDIDATE / UNEXECUTED
```

**C1/C2 NOT EVALUABLE ≠ REJECTED STRATEGY.** Neither produced evidence sufficient for its frozen acceptance contract; neither hypothesis was refuted.

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

### 3.1 Decisive execution of record (retained as historical numerical output)

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

**ΔSharpe +0.065 · paired 95 % CI [−0.874, +0.976] · walk-forward 3/5** · corr(momentum, value) −0.086 · corr(momentum, quality) +0.006 over 107 monthly cross-sections.

Owner ruling 1 (2026-09-01): these numbers are retained as **HISTORICAL NUMERICAL OUTPUT / REPRODUCIBLE / ALIGNMENT PREMISE VIOLATED / ZERO PRIMARY VERDICT CREDIT**. ⛔ The CI is **not** evidence for REVISE and is not to be cited as such.

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
| `C2-ACCEPTANCE-COVERAGE-001` | **CONFIRMED** — decisive-executable coverage defect; the artifact persisted no return/equity series |
| `C2-RETURN-ALIGNMENT-001` | **CONFIRMED** — primary estimator premise violated; original ΔSharpe / CI **not adjudicable as registered primary evidence** (§3.6) |
| `C2-DIVERSIFICATION-COMPARATOR-001` | **NOT EVALUABLE FROM FROZEN EVIDENCE** (§3.7) |

### 3.4 Prohibitions — permanent for C2

⛔ **NO window recut. NO walk-forward re-slicing. NO rerun to improve or rebalance the 3/5 count. NO economic rerun. NO new LOW-001 execution to manufacture a comparator.** The slices were formed from the nominal calendar window (`_window_bounds`, 5 equal calendar spans) while the curve begins later, so window 1 (`2016-01-29..2018-02-28`, ΔSharpe −0.668) holds roughly 56 % of the curve length of windows 2–4 and is counted with equal weight. This is a **disclosed methodology/reporting limitation**, not a defect to repair.

| walk-forward window | momentum Sharpe | multifactor Sharpe | ΔSharpe |
|---|---|---|---|
| 2016-01-29..2018-02-28 | 2.10 | 1.43 | −0.668 |
| 2018-02-28..2020-03-30 | −0.03 | −0.11 | −0.082 |
| 2020-03-30..2022-04-30 | 0.96 | 1.31 | +0.358 |
| 2022-04-30..2024-05-30 | 0.82 | 0.96 | +0.141 |
| 2024-05-30..2026-07-02 | 0.87 | 1.13 | +0.262 |

### 3.5 Artifact-completeness re-execution — AUTHORIZED, EXECUTED, REPRODUCTION GATE PASSED, VALID EVIDENCE

One re-execution was authorized solely to persist the missing series. Method: the bound script `scripts/multifactor_retest.py` (B-2b, `6caa411b…`) was **imported as a module** and its own `_backtest_pair`, `_paired_sharpe_diff_ci` and `_window_bounds` were called with byte-identical inputs (same store, `2016-01-29..2026-07-02`, `n=200`, 5 windows, 2000 resamples, seed 17). Nothing was reimplemented; no window, threshold, parameter or result-dependent branch changed.

**Reproduction gate: 18/18 primary outputs identical at full float precision.** `DETERMINISTIC REPRODUCTION CONFIRMED`. Owner ruling 1: the repair did exactly what it was authorized to do and **remains valid evidence**.

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

### 3.6 `C2-RETURN-ALIGNMENT-001` — CONFIRMED (owner ruling 1) and the authorized date-aligned diagnostic

The bound estimator `_paired_sharpe_diff_ci` (and the promoted B-4 `paired_sharpe_diff_ci`, identical logic) computes `n = min(len(a), len(b))` and slices **positionally**. Its premise is that both inputs are *aligned* daily-return series. For this execution they were not: momentum's first return is dated 2017-07-11, multifactor's 2017-01-10. Positional pairing matched each momentum return against a multifactor return **125 trading days earlier** and discarded multifactor's final 125 observations. A paired-return estimator requires corresponding observations; the registered ΔSharpe / CI therefore carry **zero primary verdict credit**. This is an estimator-input precondition violation in the bound B-2b call path, not a data or window defect; no rerun fixes it.

**Date-aligned diagnostic — authorized as defect characterization, executed from the persisted series only.** Procedure frozen and hashed **before** computation; no strategy re-execution; inner join on exact trading date; no forward/back fill; no positional pairing; no window recut; no parameter change; no return transformation. Step 1 asserts that the dated returns re-derived from each equity curve equal the persisted undated return lists element-by-element (both assertions held).

| leg | value |
|---|---|
| momentum returns | 2017-07-11 → 2026-07-02, **2,257** |
| multifactor returns | 2017-01-10 → 2026-07-02, **2,382** |
| common dates (inner join) | **2017-07-11 → 2026-07-02, 2,257** |
| dates only in momentum | 0 |
| dates only in multifactor | 125 (2017-01-10 → 2017-07-10) |
| Sharpe on common dates | multifactor 0.7573 · momentum 0.6939 |
| **diagnostic date-aligned ΔSharpe** | **+0.063** |
| **diagnostic 95 % CI** (B-4, seed 17, 2000, block 21) | **[−0.334, +0.522]** |
| registered positional statistic, reproduced from the same series | Δ 0.012 · CI [−0.874, +0.976] (matches the artifact exactly) |

Every diagnostic number above is **POST-DEFECT DIAGNOSTIC / NOT REGISTERED PRIMARY EVIDENCE / NO PASS-REVISE-REJECT CREDIT.** What it tells us about materiality: the point estimate is essentially unchanged (+0.063 vs the curve-level +0.065), the CI still spans zero, and its width halves (0.856 vs 1.850 Sharpe units) once the common-market move is genuinely paired. The mis-pairing inflated the uncertainty; it did not manufacture or hide a signal. The diagnostic does **not** replace the frozen primary statistic and does not adjudicate C2.

| file | bytes | sha256 | S3 VersionId |
|---|---|---|---|
| `C2_diagnostic/c2_alignment_diagnostic.py` (frozen procedure) | 4,963 | `661765907dc609c0dd067802101a2204e4c61842c0ca8562aaeae5ea61693290` | `f4RSQrVbP8HoD8GYt4J0cCrKJg_Oy2PW` |
| `C2_diagnostic/c2_alignment_diagnostic.json` | 1,649 | `2dfc99c793011499e23b8fe58944772c7dc7be42c674560c913ac46de6df8a9e` | `pe_FWVw2kPfeBhSBflW2miLEw56BrBrT` |

### 3.7 Comparator legs — NOT EVALUABLE FROM FROZEN EVIDENCE (owner ruling 2)

The frozen alternative acceptance clause needs corr(C2, Strategy 8) < 0.3 **and** corr(C2, Range Trader) < 0.3 **and** OP-7 portfolio ΔSharpe CI excluding zero, computed from already-frozen comparator series. Read-only search result:

| comparator | frozen historical series | evidence |
|---|---|---|
| **Strategy 8** (LOW-001; live template = `universe_asof(n=200)`, 252 d vol, top quintile 0.20, equal weight, weekly — identical to B-3) | **NOT AVAILABLE FOR THE C2 PERIOD.** The LOW-001 evidence package (S3, sha256 `a426ff54…`, 2,839 B) is **scalar-only**. Live PAPER equity begins 2026-08-12; the C2 curve ends 2026-07-02 → zero overlap. | same coverage-defect class as `C2-ACCEPTANCE-COVERAGE-001` |
| **Range Trader** (intraday opening-range, 5-min bars) | **NOT AVAILABLE FOR THE C2 PERIOD.** No historical daily-return series at any comparable horizon; live PAPER history begins 2026-06-24 → 7 trading days overlap. | structurally not evaluable against a 2017–2026 curve |

Owner ruling 2: ⛔ **no new LOW-001 execution to manufacture a comparator** — it would be a post-result comparator artifact created after C2's outcome was observed. The diversification alternative is **NOT EVALUABLE** — not PASS, not FAIL. ⛔ Factor-vs-factor correlations (−0.086 / +0.006) may not stand in for correlation to the live strategies.

### 3.8 C2 terminal classification for this tranche (owner ruling 2)

Route A (primary statistical evidence) is **NOT ADJUDICABLE** (§3.6). Route B (decisive diversification / portfolio evidence) is **NOT EVALUABLE** (§3.7). Therefore:

```
C2 = NOT EVALUABLE
   = EXECUTION / EVIDENCE-CONTRACT DEFECTS
   = ECONOMIC SIGNAL RETAINED AS NON-DECISIVE EVIDENCE
   ≠ PASS  ≠ REVISE  ≠ REJECT  ≠ REJECTED STRATEGY
```

Retained economic facts (non-decisive): multifactor maxDD materially shallower than momentum (−40.3 % vs −51.9 %); point Sharpe direction positive; CAGR lower; walk-forward 3/5; factor-level correlations low. None independently satisfies the frozen acceptance contract once the primary estimator is disqualified and the diversification route is unavailable.

### 3.9 Future C2 work — successor research, not repair

C2 may become the basis of a **prospective successor program** that freezes, before execution: explicit date-alignment semantics; a persisted return-series contract; actual-curve window reporting; valid walk-forward segmentation; comparator identities and required histories; complete acceptance computation. That is *C2 successor research*, not a repair or rerun of this decisive tranche. ⛔ No successor C2 run is authorized by this amendment.

## 4. C3 — LOW-002: OP-6 implementation binding, universe-provider seams and frozen execution package

### 4.1 Implementation (owner design rulings 2026-09-01 §8–§10 applied)

| item | value |
|---|---|
| branch / head | `feat/c3-op6-universe-provider` @ **`561ff932`** — 2 commits rebased onto `origin/main` `75ebb066`; all six §0.6 bindings re-verified byte-identical there; PR **#723** |
| OP-6 module | `apps/backend/app/research/factor_lab/op6_universe.py` — 4,004 B — sha256 `7c1db96462e529aea27a5a7dea344c37712fe7419fe1ee15fd45bff45754dd71` |
| seam 1 (simulator) | `apps/backend/app/factor_data/backtest.py` — 29,944 B — sha256 `bfc8ccb705b80ae98d1ac7bdfb474c8fdc6619bf30eabd5417f7d03153b4ba3e` — `run_momentum_backtest(..., universe_fn=None)` (+9 / −1 lines) |
| seam 2 (signal cross-section) | `apps/backend/app/factor_data/factors/low_vol.py` — 4,043 B — sha256 `958ad06ba4ce4d5282a1322b960e8e4ace8b699c444fc5c620e53c7d0956b4b2` — `low_vol_scores(..., universe_fn=None)`; omitted → historical `universe_asof(n)`; supplied → the provider's list is the cross-section and `n` is not consulted; vol primitive, `min_names` guard and ordering untouched |
| tests | `apps/backend/tests/factor_data/test_op6_universe.py` — 10,252 B — sha256 `6b30d57e10f8c9f5f0509b8e945f01b08da26750ddc66b1081fa88c148f77cc5` — **18 tests** |
| pre-seam B-5 | `backtest.py` `f02a90fa…` (29,396 B) remains the bound MOM-001 construction; `universe_fn=None` reproduces it exactly (curve equality asserted) |

Seam 2 was required because `low_vol_scores` hard-codes `universe_asof(store, as_of, n)`; the alternatives (filtering a top-*n* result, or replacing the imported symbol) are both hidden universe substitution, which the owner ruled against. It is the same explicit-provider design applied to the second consumer.

**OP-6 predicate, PIT at each rebalance:** lifetime straddle `firstpricedate <= as_of <= lastpricedate` (mirrors `dollar_volume_universe`, survivorship-free) · `tickers.category IN ('Domestic Common Stock', 'Domestic Common Stock Primary Class')` · `exchange <> 'OTC'` · last traded **`closeunadj` on/before `as_of` ≥ $5** · **median(`close × volume`) over the trailing 63 calendar days ≥ $2,000,000**.

**Price-field asymmetry, declared and intentional (owner §10):** the $5 floor uses `closeunadj` — the actually-traded nominal price; ADV keeps the **existing governed** `close × volume` convention inherited verbatim from `dollar_volume_universe` (inspected and confirmed).

**Invariant (owner §8):** **one** provider object (`op6_universe_asof`) is passed as `universe_fn` to **both** `low_vol_scores` (book cross-section) and `run_momentum_backtest` (equal-weight benchmark): `C3 STRATEGY UNIVERSE == C3 BENCHMARK UNIVERSE == OP-6 SCREENED UNIVERSE`. ⛔ No runtime replacement of imported symbols anywhere. The end-to-end test asserts every held name came from the provider's universe on its rebalance date and that both consumers called the same provider on every used rebalance.

### 4.2 Validation (local, 2026-09-01, at `561ff932` content)

`ruff check` clean · `mypy` clean on all three modules · **18/18** OP-6 + seam tests (including the falsifying field-semantics test, the frame-identity default test for `low_vol_scores`, and the shared-provider end-to-end test) · `tests/factor_data` + `tests/universe` green (count recorded in PR #723) · research-plane isolation invariant OK (517 modules). `backtest.py` left `ruff format`-unclean deliberately (already so at `origin/main`; CI runs no `ruff format`).

### 4.3 Frozen execution package — PREPARED, NOT EXECUTED

| item | value |
|---|---|
| driver | `research-out/2026-09-01/C3_package/c3_decisive_driver.py` — sha256 **`c9d0d71c97d961a2a143430b7f853d7cc5368188077413ac2d514676358e282d`** |
| composes only | B-3 `low_vol_scores` (lookback 252, quantile 0.20, equal weight, weekly) · B-5+seam `run_momentum_backtest` · OP-6 `op6_universe_asof` · B-4 `paired_sharpe_diff_ci` (seed 17, 2000, block 21) |
| nominal window | 2017-01-06 → 2026-06-12 (§1); actual curve window, skipped rebalances and per-window actual spans are **persisted** (the C2 metadata lesson) |
| primary cost | 10 bps — inherited `ProgramSpec.turnover_cost_bps` default; sweep 0 / 10 / 25 / 50 bps is diagnostic |
| walk-forward | 5 windows (`factor_lab.runner._windows` arithmetic) |
| book/benchmark alignment | asserted date-identical before the H1 estimator is called (the C2 alignment lesson) |
| verdict legs (frozen spec C3) | PASS = H1 CI excludes zero **and** book maxDD shallower than OP-6 equal-weight · REVISE = CI spans zero **and** DD advantage vs eqw exceeds the LOW-001 record (0.3024) · REJECT = CI spans zero and it does not. A CI-excludes-zero / DD-not-preserved cell is not a frozen outcome and is reported for owner adjudication |
| falsifier comparator (**declared execution input**) | **Strategy-8 reference book = the B-3 LOW_001 definition on the bound store** (`universe_asof(n=200)`, top-quintile low-vol, equal weight, 10 bps), computed **in the same execution, before any C3 number is read**. Correlation = Pearson on date-aligned (inner-join) daily returns; overlap = mean over common rebalance dates of Σᵢ min(wᵢ). Both thresholds 0.85, frozen. |
| pre-flight refuses unless | dataset bytes + sha256 == pin · parameter artifact sha256 == value passed on the command line · `git HEAD` == bound commit **and** worktree clean · `PYTHONUTF8=1` |
| persisted outputs | `environment.json` (host, OS, CPUs, Python, commit, dataset/param/driver SHA, seed/resamples/block) · `c3_result.json` · `c3_series.json` (equity curves, dated returns, per-rebalance holdings and weights for book, benchmark and reference) · optional `c3_sensitivities.json` |
| sensitivities | `--with-sensitivities` only: screen $4 / $1M, $6 / $3M, unscreened full tape — **NAMED SENSITIVITY / NOT A VERDICT**; never alter the verdict legs |

**On the comparator declaration.** The frozen spec names "Strategy 8" for the falsifier without fixing which series. The live Strategy 8 has no historical series (§3.7) and trades the 1,254-ticker live-store universe. The only prospective, tuning-free comparator is the frozen B-3 definition on the bound store, declared here **before** execution. It is a frozen-definition proxy, not the live book; this is recorded as a limitation of the falsifier, not a licence to re-choose it after results. The package proceeds under this declaration unless the owner objects before execution.

### 4.4 Execution authority

```
C3 = PROSPECTIVE DECISIVE CANDIDATE = UNEXECUTED = NO RESULT OF ANY KIND GENERATED
   = OP-6 IMPLEMENTED + TESTED + BOUND = BOTH SEAMS IMPLEMENTED = EXECUTION PACKAGE PREPARED
```

Owner ruling (2026-09-01): C3 decisive execution is **AUTHORIZED without another economic-design ruling** once **all** of: PR #723 qualified and merged · this amendment (PR #724) qualified and merged · OP-6 implementation identity bound (§4.1) · parameter-artifact identity final (§6) · exact execution code bound (the merge commit, stamped at execution qualification) · dataset identity re-verified · worktree/environment clean · no new material conformance finding. One decisive run; the result is recorded whatever it is.

## 5. C1 — FI-003 / CAP-022 crash insurance

### 5.1 `C1-EXECUTION-DEFECT-001` — CONFIRMED, real, no longer controlling

Launched 2026-09-01T18:42:29Z at `26cf4627`, frozen window 1997-12-31..2026-07-02, universe 150. All four books computed (`built 2257 days; IS 1354 / OOS 903`); the process died printing the headline line: `UnicodeEncodeError: 'charmap' codec can't encode character 'Δ'` (stdout redirected under cp1252). **No report artifact was written; no overlay result was observed** — only the benchmark row reached the log. Repair would be `PYTHONUTF8=1`. ⛔ Owner ruling 3: **do not rerun C1 with `PYTHONUTF8=1` merely to obtain an economic result that cannot satisfy its governing acceptance rule.**

### 5.2 `C1-HISTORY-WINDOW-CONFORMANCE-001` — IDENTIFIED, PRE-RESULT

`built 2257 days` ≈ 9.0 y independently confirms that the frozen 28.5-year window collapsed to the §1 boundary (1,021 of ~1,485 momentum rebalances skipped as thin). C1 has **not spent its decisive economic run**.

### 5.3 `C1-CRISIS-ACCEPTANCE-CONFORMANCE-001` — TERMINAL FOR THIS TRANCHE (owner ruling 3)

All four frozen crisis windows are **retained verbatim** in the parameter artifact and are not dropped from the record:

| crisis (frozen peak → trough) | inside boundary | overlap | classification |
|---|---|---|---|
| dotcom 2000-03-24 → 2002-10-09 | no | 0 days | **FROZEN CRISIS = UNAVAILABLE UNDER CONFORMANT PRICE HISTORY** |
| GFC 2007-10-09 → 2009-03-09 | no | 0 days | **FROZEN CRISIS = UNAVAILABLE UNDER CONFORMANT PRICE HISTORY** |
| COVID 2020-02-19 → 2020-03-23 | yes | 33 days | **FROZEN CRISIS = EVALUABLE** |
| 2022 2022-01-03 → 2022-10-12 | yes | 282 days | **FROZEN CRISIS = EVALUABLE** |

Two independent routes make OP-2 (≥ 8 pp MaxDD reduction in **≥ 3 of 4** crises, none worsened) unreachable: only two crises lie inside any conformant history, **and** the bound B-1 artifact defines `ENVIRONMENTS = {covid_2020, bear_2022, bull_2023_24}` — no dotcom or GFC environment even on a complete corpus.

```
C1-CRISIS-ACCEPTANCE-CONFORMANCE-001 = TERMINAL FOR THIS TRANCHE
                                     = REQUIRED 3-OF-4 EVIDENCE UNAVAILABLE
                                     = NOT EVALUABLE
```

### 5.4 Ruling — Option B chosen; OP-2 NOT weakened

Owner ruling 3 (2026-09-01): **Option B.** ⛔ OP-2 is **not** relaxed from "improvement in at least 3 of 4 frozen crises, none worsened" to "improvement in both observable crises" — that would materially alter the evidentiary burden after discovering that dotcom and GFC cannot be evaluated. The original thesis sought repeatability across multiple materially different crash regimes; two observable crises are not equivalent evidence to three-of-four. Option A (recorded in the earlier draft) is **not adopted**.

```
C1 = NOT EVALUABLE UNDER CURRENT GOVERNED CORPUS
   = NO DECISIVE ECONOMIC RESULT OBSERVED = NO EXECUTION AUTHORITY
   ≠ REJECTED STRATEGY
```

**Future path.** C1's economic hypothesis remains researchable through a **prospective successor** using either a genuinely deeper conformant price corpus covering dotcom and GFC, or a newly designed crisis-validation framework frozen prospectively as a distinct program. ⛔ A two-crisis successor is **not** equivalent to this C1 program and may not be labelled as such.

## 6. Execution-input identities after this amendment

| artifact | sha256 before | sha256 after | change |
|---|---|---|---|
| `params/C1_crash_insurance.json` | `5b08b7d7e7a646308a58a3f4d736703acc76c20b518bf1d6d7238990b4bd5ad8` | **`a9747a462466181c21a6c4a9f618d59971f63fbc95a9d90d23cde5b5af77b6f9`** | + executable boundary · + `PYTHONUTF8=1` environment note · + crisis evaluability (frozen-crisis labels) · + acceptance status = Option B ruling · + tranche disposition · + execution record. **All acceptance values and crisis dates retained verbatim** |
| `params/C2_value_quality.json` | `45e943436c5b6a60b3f58d83eb7675f6f279929fdfbfb7f29f95f234b493520a` | **unchanged** (verified `cmp`) | ⛔ must stay byte-identical: input of the retained execution |
| `params/C3_broader_lowvol.json` | `c1a8b15830068093d0d3a79d39e376d57bada9248fcfbe0f06c623ab5932eac5` | **`b1e99698b2432585ab27dea333036bb03446cc4a52fadd4535ef0662765f1a05`** | + executable boundary · + OP-6 implementation binding (module / tests SHA, branch head) · + both seams · + price-field semantics · + execution package (driver SHA, comparator declaration, verdict legs, pre-flight) · + gating text. **Signal, acceptance, falsifier thresholds and cost sweep unchanged** |
| frozen spec v1.2 FINAL | `47a2e262…` | unchanged | this amendment sits beside it; the spec is not edited |
| bound B-1…B-5 | as §0.6 | unchanged at `75ebb066` (re-verified) | B-5 gains a descendant (§4.1); the pre-seam blob remains the binding |
| C3 execution code | — | `feat/c3-op6-universe-provider` @ `561ff932` (branch head); **merge commit stamped at execution qualification** | |
| C3 driver | — | `c9d0d71c97d961a2a143430b7f853d7cc5368188077413ac2d514676358e282d` | |

## 7. Owner rulings — recorded

| # | item | ruling (2026-09-01) |
|---|---|---|
| 1 | §3.6 `C2-RETURN-ALIGNMENT-001` | CONFIRMED; registered ΔSharpe / CI = zero primary verdict credit; one date-aligned **diagnostic** authorized from persisted series only — executed, §3.6 |
| 2 | §3.7 `C2-DIVERSIFICATION-COMPARATOR-001` | NOT EVALUABLE FROM FROZEN EVIDENCE; no LOW-001 comparator execution; C2 = **NOT EVALUABLE** for this tranche (§3.8) |
| 3 | §5.4 C1 crisis rule | **Option B** — NOT EVALUABLE; OP-2 not weakened |
| 4 | §1–§2 | accepted (recorded for custody) |
| 5 | §4 C3 binding | #723 continues through normal qualification; C3 execution authorized only after the §4.4 conditions close |
| 6 | this amendment | fold rulings in (done); qualify; merge; record final sha256 + merge commit in the trial ledger |

**Still open for the owner (non-blocking for custody):** confirmation, or objection, to the §4.3 comparator declaration before C3 executes.

## 8. Program-level consequence (owner ruling)

The original plan of ranking three completed candidates #1 / #2 / #3 is **withdrawn** — the evidence no longer supports it, and incomplete evidence is not ranked merely to produce a podium.

| | tranche disposition |
|---|---|
| C1 | NOT EVALUABLE |
| C2 | NOT EVALUABLE |
| C3 | DECISIVE RESEARCH PENDING |

After C3 executes: **PASS** → C3 is the sole implementation-capital candidate from this tranche (promotion still requires a separate owner ruling); **REVISE** → return the prescribed revision disposition; C1/C2 are **not** promoted by default; **REJECT** → this tranche produces no PAPER-promotion candidate.

## 9. What this amendment did not do

No candidate was executed or re-executed after the 2026-09-01 20:30Z ruling except the authorized C2 artifact-completeness repair (§3.5) and the authorized post-defect diagnostic (§3.6), which used persisted series only. No LOW-001 series was generated. No window was recut. No walk-forward segmentation changed. C1 was not rerun. C3 was not run. No threshold, seed, bootstrap count, block length, crisis date, signal or cost assumption changed. Nothing touched the PAPER host. The primary working tree was not used for any run.
