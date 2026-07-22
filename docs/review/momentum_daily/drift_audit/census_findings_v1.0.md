# §8 Live‑Class Drift Audit — Completed Census Package v1.0 (for final adjudication)

**Run:** commit `29b9c2c` · full 5,395 sessions (2005‑01‑03 → 2026‑06‑12) · countersigned data binding re‑verified fail‑closed · detached ~57 min.

## 1. Provenance integrity

| item | value |
|---|---|
| measurement_code_commit | `29b9c2c9e1b9b0871417f1a4e13a3baa55922d7c` (compare_day + §8 bands + driver/replica/settlement **byte‑identical to countersigned 87b2d8c**) |
| whole‑file digest | `022ffd01…` ✓ re‑verified |
| sep content digest | `d9472dfe…` ✓ re‑verified (30.7M rows) |
| tickers content digest | `2f21b154…` ✓ re‑verified |
| universe_id | `momentum_daily_stage2_4:top200_PIT_universe_asof_n200` |
| **working_tree_clean** | **FALSE — see caveat below** |

**⚠ working_tree_clean = FALSE caveat.** The manifest snapshot recorded a dirty tree **only because the run's own `census_execution.log` + `.census_pid` were written into the tracked `docs/…/drift_audit/` directory before the manifest was computed.** It is **not uncommitted code** — the measurement code was committed and clean at `29b9c2c` (verified), and the data digests re‑verified. This is a provenance‑reporting flaw in the run harnessing, not a code‑integrity issue. **Adjudication needed:** accept with this disclosure, or require a clean re‑run (log/pid to a non‑tracked path → working_tree_clean=TRUE; ~57 min).

**Artifact SHA‑256 (all produced + hashed):**
| artifact | bytes | sha256 |
|---|---|---|
| census_report.json | 20,462 | `fe0386adc40b11744a22612871f6442c851b48405f0f26ffaac054be3eba3fa9` |
| live_seams.json | 39,972,511 | `9f682ecb7832bef77b2d1e08dbd73f95e28ca31f408794f5ba9860734d9c23a0` |
| replica_seams.json | 18,852,723 | `70b99e1e494338d7b75c132a4f19fadfea7f67b6c4b4bfb6ac926e7ada18e60e` |
| census_execution.log | 1,350 | `c0e7fee2c9895b4b3bb6b55c975e2289dfcc6688563f38ee2a80db5123353a71` |
| provenance_manifest_bound.json | 13,889 | `c701f38b4cd9888fae5fe648c7215d510beb9bf7ea85d7709b9798fd832f5e8f` |
| content_digest_artifact.json | 2,042 | `7a4da95f6b66bd57bcb7e25f5cab1cf4a4063d869ebf6435e998c92d2f35c151` |
| warm‑up proxy content | — | `6b63656defe70a551ecdda8747b13dd23128e95cd7e8383d93d40024ae79ae0e` |

## 2. Structural (inception) — ALL PASS

first_eligible_date identical ✓ · first_trade_date identical ✓ · initial_target_names identical ✓ · initial_ranking identical ✓ · **cold_start_seed_count == 1** ✓. The live class seeds at day‑1 inception exactly as validated.

## 3. Selection seam — EXACTLY EQUIVALENT (the core equivalence result)

**Across all 5,395 sessions and all 5,196 Phase‑2 sessions: eligible = 0, ranking = 0, target_names = 0 mismatches.** The production selection logic (`_eligible`/`_select_targets`) is identical to the validated `compute_day`/`select_n` on the same universe. On every Phase‑2 day where **both** sides trade, the target set is identical (1,485/1,485).

## 4. Phase split (Option D)

- **Phase 1 — regime warm‑up:** 2005‑01‑03 → 2005‑10‑14 (**199 sessions**). All 199 diverge — `EXPECTED_METHODOLOGY_DIVERGENCE` (replica fail‑open gross 1.0 vs production‑like live real‑MA regime). Counted, isolated, **excluded** from Phase‑2 governing stats.
- **Phase 2 — governing:** `common_regime_available_from = 2005‑10‑17` → 2026‑06‑12 (**5,196 sessions**).

## 5. Phase‑2 governing divergences (the adjudication items)

| seam | Phase‑2 mismatches | nature |
|---|---|---|
| eligible / ranking / target | **0 / 0 / 0** | selection EQUIVALENT |
| **trigger (trade decision)** | 3,207 | live rebalances more often — see below |
| **weights** | 5,150 | production equal‑weight vs validated `hybrid_50_50` |
| regime_gross | 86 (max diff 0.45) | Option‑D residual: warmed vs window proxy at graduated‑band boundaries |

**Trigger gate (direction):** live‑only trades = **3,192**, replica‑only = 15, both = 1,485, neither = 504. The live class trades far more often — almost entirely **`weight_drift` maintenance rebalances** (production trims drifted weights on the *same* target set), which the replica's `changed`‑only gate skips. **When both trade, the held portfolio is identical.** So the trigger divergence is a **maintenance‑frequency** difference, **not a difference in what is held**. Turnover is comparable (live 248.6 vs replica 252.9, diff 4.2) — the live maintenance trims are individually small.

**Weights:** median max‑per‑name diff **33 bps** (p95 155 bps) — far above the §8 1 bp band. This is the genuine, by‑construction gap: **production uses equal‑weight sizing; the validation (Stage 3 winner `N5_hybrid_nocap`, Stage 4) used `hybrid_50_50` inverse‑vol.** Same names, materially different weights.

## 6. Equivalence conclusion (for your adjudication)

- **Selection + inception: EQUIVALENT** — production picks the same names, same order, same day‑1 inception as the validated strategy.
- **Sizing: MATERIALLY DIFFERENT** — production equal‑weight vs validated hybrid inverse‑vol (~33 bps/name median). The validation's *performance* evidence was generated under hybrid sizing, not the production equal‑weight; **this is the primary equivalence gap.**
- **Rebalance trigger: holdings‑neutral difference** — production rebalances more (weight‑drift maintenance) but to the same names; comparable turnover.
- **Regime warm‑up (Phase 1) + 86 Phase‑2 regime residuals:** methodology artifacts of the disclosed SPY‑proxy substitution, not production behavior.

**A successful run proves the audit executed against the countersigned inputs — not strategy equivalence.** The audit shows production is **selection‑equivalent but sizing‑divergent** vs the validated strategy. Whether the equal‑weight production config inherits the hybrid‑validated evidence is the material question for adjudication; the trigger‑frequency and regime‑warm‑up items appear immaterial to holdings.
