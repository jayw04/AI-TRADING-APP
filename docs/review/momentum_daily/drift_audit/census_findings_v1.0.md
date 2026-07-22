# §8 Live‑Class Drift Audit — Completed Census Package v1.0 (for final adjudication)

**Run:** commit `29b9c2c` · full 5,395 sessions (2005‑01‑03 → 2026‑06‑12) · countersigned data binding re‑verified fail‑closed · detached ~57 min.

> **⚠ AMENDED 2026‑07‑22 by `weighting_defect_erratum_v1.0.md`.** All measurements below stand unaltered.
> The *classification* of the weights seam (§5 weights row, §6 bullet 2, §7 `SIZING EQUIVALENCE: FAIL —
> MATERIAL`) is superseded: the divergence is now adjudicated as a **`VALIDATION_IMPLEMENTATION_DEFECT`**
> in the Stage‑3 harness — at N=5 the 20% cap equals 1/N, so the clamp‑and‑renormalize loop cannot
> converge and emitted cap‑violating weights on 100% of five‑name sessions. Production equal weighting is
> the feasible implementation of the registered constraints, not a drift from a validated alternative.
> The activation blocker is renamed **`WEIGHTING_VALIDATION_DEFECT_IMPACT_NOT_YET_ADJUDICATED`**; the hold
> stands. Read the erratum alongside §6 and §7.

## 1. Provenance integrity

| item | value |
|---|---|
| measurement_code_commit | `29b9c2c9e1b9b0871417f1a4e13a3baa55922d7c` (compare_day + §8 bands + driver/replica/settlement **byte‑identical to countersigned 87b2d8c**) |
| whole‑file digest | `022ffd01…` ✓ re‑verified |
| sep content digest | `d9472dfe…` ✓ re‑verified (30.7M rows) |
| tickers content digest | `2f21b154…` ✓ re‑verified |
| universe_id | `momentum_daily_stage2_4:top200_PIT_universe_asof_n200` |
| **working_tree_clean** | **FALSE — `PROVENANCE_ACCEPTED_WITH_OPERATIONAL_CLEANLINESS_EXCEPTION`** (owner adjudication 2026‑07‑22) |

**Provenance status — `PROVENANCE_ACCEPTED_WITH_OPERATIONAL_CLEANLINESS_EXCEPTION` (accepted with disclosure; no clean rerun required).** The manifest recorded working_tree_clean=FALSE **only because the census process wrote its own PID and execution log into a tracked output location before the pre‑run cleanliness snapshot. The dirty‑tree flag does NOT indicate modified measurement code.** Basis for acceptance: the measurement code was committed *before* execution and pinned to `29b9c2c`; the comparison core, driver, replica extractor, and settlement logic were verified **byte‑identical** to the countersigned implementation; all input digests were **revalidated fail‑closed** before the run; and the output package is complete and SHA‑bound. **A clean rerun was NOT required** because the measurement code and input bindings were independently fixed and verified.

Exact dirty paths (present at the manifest snapshot) + hashes:
- `docs/review/momentum_daily/drift_audit/census_execution.log` — 1350 B — `c0e7fee2c9895b4b3bb6b55c975e2289dfcc6688563f38ee2a80db5123353a71`
- `docs/review/momentum_daily/drift_audit/.census_pid` — 4 B — `167918ace289465acd4dd6ab6587fe10bfe54bc475ad8074b049ac358f98f9e2`

*Future‑run correction: write PID files and execution logs OUTSIDE tracked directories (or ignore them before the pre‑run cleanliness snapshot).*

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

## 6. Equivalence conclusion

- **Selection + inception: EQUIVALENT** — production picks the same names, same order, same day‑1 inception. This closes the original cold‑start and target‑selection equivalence questions. **Production is selection‑ and inception‑equivalent, NOT strategy‑equivalent overall.**
- **Sizing: MATERIAL and PERFORMANCE‑EVIDENCE‑BREAKING** — production equal‑weight vs validated `hybrid_50_50` inverse‑vol (5,150/5,196 governing sessions, median ~33 bps/name). Position sizing determines name‑level allocation, portfolio volatility, concentration, turnover, drawdown, return attribution, and exposure under partial‑gross regimes. **The equal‑weight production strategy does NOT inherit the performance evidence established for the hybrid‑weight validated strategy.** The validation proved production selects the same securities; it did NOT validate the portfolio actually proposed for activation.
- **Rebalance trigger: behaviorally different, holdings‑neutral, not independently activation‑blocking** — production rebalances more (3,192 weight‑drift maintenance days) but to the SAME names (1,485/1,485 identical when both trade); comparable turnover (248.6 vs 252.9). A rebalance‑frequency distinction, not a selection difference. **Once weighting is aligned, re‑check the trigger seam in a focused acceptance test to confirm it remains holdings‑neutral.**
- **Regime‑gross residual (86 Phase‑2 sessions): documented, conditionally non‑material.** The residual regime‑gross divergence **did not alter selected names in this census, but may alter exposure and performance near regime boundaries** (max band jump 0.45; warmed‑vs‑window proxy). Remains a limitation; no separate resolution required before choosing the sizing path.
- **Phase 1 (199 warm‑up sessions): `EXPECTED_METHODOLOGY_DIVERGENCE`** — kept visible in the full‑period census, **excluded from the Phase‑2 governing equivalence verdict.**

## 7. Final adjudication (owner, 2026‑07‑22)

```
PROVENANCE:                       ACCEPTED WITH DISCLOSURE
                                  (PROVENANCE_ACCEPTED_WITH_OPERATIONAL_CLEANLINESS_EXCEPTION)
COLD-START REPAIR:                VALIDATED
SELECTION EQUIVALENCE:            PASS
INCEPTION EQUIVALENCE:            PASS
SIZING EQUIVALENCE:               FAIL — MATERIAL
PERFORMANCE-EVIDENCE INHERITANCE: NOT ESTABLISHED
ACCOUNT 4 ACTIVATION:             NOT AUTHORIZED
```

**Activation blocker (no longer cold‑start — that defect is repaired and the inception path is validated):**
`PRODUCTION_SIZING_NOT_COVERED_BY_VALIDATED_PERFORMANCE_EVIDENCE`.

**Account 4 remains: strategy 11 PAUSED · operational_hold ACTIVE · cooldown NOT STARTED.**

### Two permissible resolution paths

**Path 1 — align production to the validated weighting (fastest supported route).**
Set production weighting = Stage 4 `hybrid_50_50`. Then a **focused implementation‑equivalence + operational‑acceptance package** proving: production uses the exact validated weighting function + parameters; target weights match the replica within the registered numeric tolerance; weight mismatches fall to zero (or an explicitly justified numeric‑only level); trigger differences remain holdings‑neutral; lifecycle + one‑shot seed behavior unchanged; **no new full historical strategy search / parameter selection.** This is a NEW implementation + acceptance package — it does **not** rerun or re‑review this census document.

**Path 2 — validate equal weighting as a new strategy variant.**
A new validation program for the equal‑weight variant (performance, risk, turnover, out‑of‑sample). The hybrid strategy's results cannot be attributed to it merely because the selected names match.

**Recommended next action:** change production weighting to the validated `hybrid_50_50` implementation and prepare the focused activation‑acceptance package (Path 1).
